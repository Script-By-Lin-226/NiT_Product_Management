from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.Model.datamodels import Inventory, InventoryLog, Product
from app.config.configuration import settings


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
        )
        .join(Product, Product.id == InventoryLog.product_id)
        .order_by(InventoryLog.created_at.asc(), InventoryLog.id.asc())
    )
    logs_result = await session.execute(logs_query)

    running_balances: dict[str, int] = defaultdict(int)
    log_rows: list[dict[str, object]] = []
    for (
        product_name,
        change_amount,
        created_at,
        given_to,
        department,
        actor_name,
    ) in logs_result.all():
        delta = int(change_amount)
        running_balances[product_name] += delta
        log_rows.append(
            {
                "date": created_at.isoformat() if created_at is not None else "",
                "product_name": product_name,
                "movement": "in" if delta > 0 else "out" if delta < 0 else "neutral",
                "quantity": abs(delta),
                "balance": running_balances[product_name],
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
            "given_to",
            "department",
            "admin_name",
        ],
    )

    target_path = Path(file_path or settings.Excel_Path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(target_path, mode="w") as writer:
        inventory_dataframe.to_excel(writer, index=False, sheet_name="inventory")
        entries_dataframe.to_excel(writer, index=False, sheet_name="stock_entries")
