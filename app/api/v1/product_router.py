from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.Model.datamodels import Inventory, InventoryLog, Product
from app.Schemas.product_schemas import ProductCreate, ProductItem, ProductUpdate, StockEntryCreate
from app.Services.admin_service import require_admin
from app.Services.activity_service import get_actor_details, serialize_activity_log
from app.Services.excel_snapshot_service import read_excel_snapshot
from app.Services.excel_sync_service import sync_products_to_excel
from app.Services.loading_excel_data import load_excel_data
from app.config.database_utils import get_async_session

router = APIRouter(prefix="/products", tags=["products"])


def _to_product_item(product: Product, inventory: Inventory) -> ProductItem:
    return ProductItem(
        id=product.id,
        product_name=product.product_name,
        quantity=int(inventory.quantity),
    )


def _to_local_day_key(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.date().isoformat()
    return value.astimezone().date().isoformat()


async def _commit_with_excel_sync(session: AsyncSession) -> None:
    try:
        await sync_products_to_excel(session=session)
        await session.commit()
    except PermissionError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync Excel file: {exc}",
        ) from exc


@router.post("/load-excel")
async def load_excel_route(
    request: Request,
    file: UploadFile | None = File(default=None),
    file_path: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    require_admin(request)
    actor_name, actor_class = get_actor_details(request)
    return await load_excel_data(
        session=session,
        file=file,
        file_path=file_path,
        actor_name=actor_name,
        actor_class=actor_class,
        sync_excel_file=True,
    )


@router.get("/", response_model=list[ProductItem])
async def list_products_route(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    require_admin(request)
    products_query = (
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .order_by(Product.product_name.asc())
    )
    products_result = await session.execute(products_query)
    return [
        _to_product_item(product, inventory)
        for product, inventory in products_result.all()
    ]


@router.post("/", response_model=ProductItem, status_code=status.HTTP_201_CREATED)
async def create_product_route(
    payload: ProductCreate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    require_admin(request)
    actor_name, actor_class = get_actor_details(request)

    product_name = payload.product_name.strip()
    existing_result = await session.execute(
        select(Product).where(Product.product_name == product_name)
    )
    if existing_result.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product name already exists.",
        )

    product = Product(product_name=product_name)
    session.add(product)
    await session.flush()

    inventory = Inventory(product_id=product.id, quantity=payload.quantity)
    session.add(inventory)
    session.add(
        InventoryLog(
            product_id=product.id,
            change_amount=payload.quantity,
            actor_name=actor_name,
            actor_class=actor_class,
        )
    )
    await session.flush()
    await _commit_with_excel_sync(session)

    return _to_product_item(product, inventory)


@router.put("/{product_id}", response_model=ProductItem)
async def update_product_route(
    product_id: int,
    payload: ProductUpdate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    require_admin(request)
    actor_name, actor_class = get_actor_details(request)

    if payload.product_name is None and payload.quantity is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide product_name or quantity to update.",
        )

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    inventory_result = await session.execute(
        select(Inventory).where(Inventory.product_id == product.id)
    )
    inventory = inventory_result.scalars().first()
    if inventory is None:
        inventory = Inventory(product_id=product.id, quantity=0)
        session.add(inventory)
        await session.flush()

    if payload.product_name is not None:
        new_name = payload.product_name.strip()
        existing_result = await session.execute(
            select(Product).where(
                Product.product_name == new_name,
                Product.id != product.id,
            )
        )
        if existing_result.scalars().first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product name already exists.",
            )
        product.product_name = new_name

    if payload.quantity is not None:
        delta = payload.quantity - int(inventory.quantity)
        inventory.quantity = payload.quantity
        if delta != 0:
            session.add(
                InventoryLog(
                    product_id=product.id,
                    change_amount=delta,
                    actor_name=actor_name,
                    actor_class=actor_class,
                )
            )

    session.add(product)
    session.add(inventory)
    await session.flush()
    await _commit_with_excel_sync(session)

    return _to_product_item(product, inventory)


@router.delete("/{product_id}")
async def delete_product_route(
    product_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    require_admin(request)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    await session.delete(product)
    await session.flush()
    await _commit_with_excel_sync(session)
    return {"message": "Product deleted successfully."}


@router.get("/admin/excel-snapshot")
async def get_admin_excel_snapshot_route(request: Request):
    require_admin(request)
    try:
        return await read_excel_snapshot()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/admin/stock-entry")
async def create_admin_stock_entry_route(
    payload: StockEntryCreate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    require_admin(request)
    actor_name, actor_class = get_actor_details(request)
    normalized_product_name = payload.product_name.strip()
    if not normalized_product_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product name is required.",
        )
    is_uniform_product = normalized_product_name.lower().startswith("uniform -")

    product_result = await session.execute(
        select(Product).where(func.lower(Product.product_name) == normalized_product_name.lower())
    )
    product = product_result.scalars().first()
    if product is None:
        if payload.movement == "in" and is_uniform_product:
            product = Product(product_name=normalized_product_name)
            session.add(product)
            await session.flush()
        elif payload.movement == "out" and is_uniform_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Uniform size not found in inventory. "
                    "Add it first using an In entry."
                ),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found in inventory database.",
            )

    inventory_result = await session.execute(
        select(Inventory).where(Inventory.product_id == product.id)
    )
    inventory = inventory_result.scalars().first()
    if inventory is None:
        inventory = Inventory(product_id=product.id, quantity=0)
        session.add(inventory)
        await session.flush()

    change_amount = payload.quantity if payload.movement == "in" else -payload.quantity
    next_quantity = int(inventory.quantity) + int(change_amount)
    if next_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Out quantity exceeds available stock.",
        )
    given_to = (payload.given_to or "").strip() or None
    department = (payload.department or "").strip() or None
    uniform_category = (payload.uniform_category or "").strip() or None
    if payload.movement == "out" and (given_to is None or department is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="For out entries, both given_to and department are required.",
        )

    inventory.quantity = next_quantity
    entry_date = payload.entry_date or datetime.now(timezone.utc)
    if entry_date.tzinfo is None:
        entry_date = entry_date.replace(tzinfo=timezone.utc)

    session.add(inventory)
    session.add(
        InventoryLog(
            product_id=product.id,
            change_amount=change_amount,
            actor_name=actor_name,
            actor_class=actor_class,
            uniform_category=uniform_category,
            given_to=given_to,
            department=department,
            created_at=entry_date,
        )
    )
    await session.flush()
    await _commit_with_excel_sync(session)

    updated_snapshot = await read_excel_snapshot()
    return {
        "message": "Stock entry saved successfully.",
        "entry": {
            "product_name": product.product_name,
            "movement": payload.movement,
            "quantity": payload.quantity,
            "date": entry_date.isoformat(),
            "balance": next_quantity,
            "uniform_category": uniform_category,
            "given_to": given_to,
            "department": department,
        },
        "summary": updated_snapshot.get("summary", {}),
    }


@router.get("/inventory")
async def get_inventory_route(session: AsyncSession = Depends(get_async_session)):
    inventory_query = (
        select(Product.product_name, Inventory.quantity)
        .join(Inventory, Inventory.product_id == Product.id)
        .order_by(Inventory.quantity.desc(), Product.product_name.asc())
    )
    inventory_result = await session.execute(inventory_query)

    items = [
        {"product_name": product_name, "quantity": quantity}
        for product_name, quantity in inventory_result.all()
    ]

    return {
        "items": items,
        "summary": {
            "products": len(items),
            "total_quantity": sum(item["quantity"] for item in items),
            "zero_stock_products": sum(1 for item in items if item["quantity"] == 0),
        },
    }


@router.get("/dashboard")
async def get_dashboard_route(
    session: AsyncSession = Depends(get_async_session),
):
    inventory_query = (
        select(Product.product_name, Inventory.quantity)
        .join(Inventory, Inventory.product_id == Product.id)
        .order_by(Inventory.quantity.desc(), Product.product_name.asc())
    )
    inventory_result = await session.execute(inventory_query)
    inventory_rows = inventory_result.all()

    inventory_items = [
        {"product_name": product_name, "quantity": quantity}
        for product_name, quantity in inventory_rows
    ]

    daily_logs_query = select(
        InventoryLog.change_amount,
        InventoryLog.created_at,
    )
    daily_logs_result = await session.execute(daily_logs_query)

    daily_map: dict[str, int] = {}
    for change_amount, created_at in daily_logs_result.all():
        day_key = _to_local_day_key(created_at)
        if day_key is None:
            continue
        daily_map[day_key] = daily_map.get(day_key, 0) + int(change_amount)

    logs_query = (
        select(
            InventoryLog.change_amount,
            InventoryLog.created_at,
            Product.product_name,
            InventoryLog.actor_name,
            InventoryLog.actor_class,
            InventoryLog.uniform_category,
            InventoryLog.given_to,
            InventoryLog.department,
        )
        .join(Product, Product.id == InventoryLog.product_id)
        .order_by(InventoryLog.created_at.desc())
        .limit(200)
    )
    logs_result = await session.execute(logs_query)

    recent_logs = []
    for (
        change_amount,
        created_at,
        product_name,
        actor_name,
        actor_class,
        uniform_category,
        given_to,
        department,
    ) in logs_result.all():
        recent_logs.append(
            serialize_activity_log(
                product_name=product_name,
                change_amount=int(change_amount),
                created_at=created_at,
                actor_name=actor_name,
                actor_class=actor_class,
                uniform_category=uniform_category,
                given_to=given_to,
                department=department,
            )
        )

    daily_changes = [
        {"date": date_key, "net_change": daily_map[date_key]}
        for date_key in sorted(daily_map.keys())
    ]

    return {
        "summary": {
            "products": len(inventory_items),
            "total_quantity": sum(item["quantity"] for item in inventory_items),
            "zero_stock_products": sum(1 for item in inventory_items if item["quantity"] == 0),
        },
        "top_products": inventory_items[:8],
        "inventory": inventory_items,
        "daily_net_changes": daily_changes,
        "recent_logs": recent_logs[:50],
    }
