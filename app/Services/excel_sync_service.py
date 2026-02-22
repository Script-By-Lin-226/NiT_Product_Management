from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.Model.datamodels import Inventory, InventoryLog, Product
from app.config.configuration import settings


def _resolve_uniform_category(product_name: str, explicit_category: str | None) -> str | None:
    normalized = (explicit_category or "").strip()
    if normalized:
        return normalized

    trimmed_name = (product_name or "").strip()
    if trimmed_name.lower().startswith("uniform - "):
        return trimmed_name
    return None


async def sync_products_to_excel(
    session: AsyncSession,
    file_path: str | None = None,
) -> None:
    query = (
        select(Product.product_name, Inventory.quantity)
        .join(Inventory, Inventory.product_id == Product.id)
        .order_by(Product.product_name.asc())
    )
    result = await session.execute(query)

    rows = [
        {"product_name": product_name, "quantity": int(quantity)}
        for product_name, quantity in result.all()
    ]
    inventory_dataframe = pd.DataFrame(rows, columns=["product_name", "quantity"])

    logs_query = (
        select(
            Product.product_name,
            InventoryLog.change_amount,
            InventoryLog.created_at,
            InventoryLog.given_to,
            InventoryLog.department,
            InventoryLog.actor_name,
            InventoryLog.uniform_category,
        )
        .join(Product, Product.id == InventoryLog.product_id)
        .order_by(InventoryLog.created_at.asc(), InventoryLog.id.asc())
    )
    logs_result = await session.execute(logs_query)

    running_balances: dict[str, int] = defaultdict(int)
    running_uniform_balances: dict[str, int] = defaultdict(int)
    uniform_in_totals: dict[str, int] = defaultdict(int)
    uniform_out_totals: dict[str, int] = defaultdict(int)
    log_rows: list[dict[str, object]] = []
    for (
        product_name,
        change_amount,
        created_at,
        given_to,
        department,
        actor_name,
        uniform_category,
    ) in logs_result.all():
        delta = int(change_amount)
        running_balances[product_name] += delta
        resolved_uniform_category = _resolve_uniform_category(
            product_name=product_name,
            explicit_category=uniform_category,
        )
        if resolved_uniform_category is not None:
            running_uniform_balances[resolved_uniform_category] += delta
            if delta > 0:
                uniform_in_totals[resolved_uniform_category] += delta
            elif delta < 0:
                uniform_out_totals[resolved_uniform_category] += abs(delta)

        log_rows.append(
            {
                "date": created_at.isoformat() if created_at is not None else "",
                "product_name": product_name,
                "movement": "in" if delta > 0 else "out" if delta < 0 else "neutral",
                "quantity": abs(delta),
                "balance": running_balances[product_name],
                "uniform_category": resolved_uniform_category or "",
                "given_to": given_to or "",
                "department": department or "",
                "admin_name": actor_name or "",
            }
        )

    entries_dataframe = pd.DataFrame(
        log_rows,
        columns=[
            "date",
            "product_name",
            "movement",
            "quantity",
            "balance",
            "uniform_category",
            "given_to",
            "department",
            "admin_name",
        ],
    )

    uniform_rows = [
        {
            "uniform_category": category,
            "in_quantity": int(uniform_in_totals.get(category, 0)),
            "out_quantity": int(uniform_out_totals.get(category, 0)),
            "balance": int(balance),
        }
        for category, balance in sorted(running_uniform_balances.items(), key=lambda item: item[0].lower())
    ]
    uniform_dataframe = pd.DataFrame(
        uniform_rows,
        columns=[
            "uniform_category",
            "in_quantity",
            "out_quantity",
            "balance",
        ],
    )

    target_path = Path(file_path or settings.Excel_Path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pd.ExcelWriter(target_path, mode="w") as writer:
            inventory_dataframe.to_excel(writer, index=False, sheet_name="inventory")
            entries_dataframe.to_excel(writer, index=False, sheet_name="stock_entries")
            uniform_dataframe.to_excel(writer, index=False, sheet_name="uniform_categories")
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot write Excel file at {target_path}. Close it in other apps and try again."
        ) from exc
