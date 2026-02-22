from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pandas as pd

from app.Services.loading_excel_data import _extract_ledger_quantities, _extract_simple_quantities
from app.config.configuration import settings


def _read_excel_snapshot_sync(file_path: str | None = None) -> dict[str, Any]:
    target_path = Path(file_path or settings.Excel_Path)
    if not target_path.exists():
        raise FileNotFoundError(f"Excel file not found at {target_path}")

    with pd.ExcelFile(target_path) as workbook:
        sheet_name = "inventory" if "inventory" in workbook.sheet_names else workbook.sheet_names[0]
        dataframe = pd.read_excel(workbook, sheet_name=sheet_name)
    if dataframe.empty:
        return {
            "file_path": str(target_path),
            "products": [],
            "items": [],
            "summary": {"product_count": 0, "total_stock_balance": 0},
        }

    quantities, _ = _extract_simple_quantities(dataframe)
    if quantities is None:
        quantities, _, _ = _extract_ledger_quantities(dataframe)

    if quantities is None:
        raise ValueError(
            "Unsupported Excel format. Expected either 'product_name/quantity' or ledger layout."
        )

    items = [
        {"product_name": product_name, "quantity": int(quantity)}
        for product_name, quantity in sorted(quantities.items(), key=lambda item: item[0].lower())
    ]

    return {
        "file_path": str(target_path),
        "products": [item["product_name"] for item in items],
        "items": items,
        "summary": {
            "product_count": len(items),
            "total_stock_balance": sum(item["quantity"] for item in items),
        },
    }


async def read_excel_snapshot(file_path: str | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_read_excel_snapshot_sync, file_path)
