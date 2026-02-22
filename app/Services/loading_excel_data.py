from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd
from fastapi import UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.Model.datamodels import Inventory, InventoryLog, Product
from app.config.configuration import settings
from app.Services.excel_sync_service import sync_products_to_excel

COLUMN_ALIASES = {
    "product_name": {"product_name", "product", "productname", "name"},
    "quantity": {"quantity", "qty", "stock", "inventory"},
}
SUMMARY_DATE_LABELS = {"in", "out", "stock balance", "total stock balance"}
BASE_LEDGER_COLUMNS = {"date", "name", "class"}


def _resolve_columns(columns: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for source in columns:
        normalized = source.strip().lower()
        for target, aliases in COLUMN_ALIASES.items():
            if normalized in aliases and target not in resolved:
                resolved[target] = source
    return resolved


def _to_int(value: Any) -> int:
    if pd.isna(value):
        raise ValueError("quantity is missing")
    if isinstance(value, bool):
        raise ValueError("quantity must be a number")
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            raise ValueError("quantity is missing")
        numeric = float(cleaned)
    else:
        numeric = float(value)

    if not numeric.is_integer():
        raise ValueError("quantity must be an integer")

    parsed = int(numeric)
    if parsed < 0:
        raise ValueError("quantity cannot be negative")
    return parsed


def _to_optional_int(value: Any) -> int:
    if pd.isna(value):
        return 0
    return _to_int(value)


def _normalize_label(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def _to_optional_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _to_optional_datetime(value: Any) -> datetime | None:
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime()
    return parsed


def _extract_simple_quantities(dataframe: pd.DataFrame) -> tuple[dict[str, int] | None, list[str]]:
    resolved_columns = _resolve_columns(list(dataframe.columns))
    missing = [key for key in ("product_name", "quantity") if key not in resolved_columns]
    if missing:
        return None, []

    normalized_df = dataframe.rename(
        columns={
            resolved_columns["product_name"]: "product_name",
            resolved_columns["quantity"]: "quantity",
        }
    )

    quantities: dict[str, int] = {}
    errors: list[str] = []
    for index, row in normalized_df.iterrows():
        row_number = int(index) + 2
        if pd.isna(row["product_name"]) and pd.isna(row["quantity"]):
            continue

        product_name = str(row["product_name"]).strip()
        if not product_name:
            errors.append(f"Row {row_number}: product_name is empty")
            continue

        try:
            quantity = _to_int(row["quantity"])
        except ValueError as exc:
            errors.append(f"Row {row_number}: {exc}")
            continue

        quantities[product_name] = quantity

    return quantities, errors


def _extract_ledger_quantities(
    dataframe: pd.DataFrame,
) -> tuple[dict[str, int] | None, list[str], list[dict[str, Any]]]:
    normalized_columns = {column.strip().lower(): column for column in dataframe.columns}
    date_column = normalized_columns.get("date")
    name_column = normalized_columns.get("name")
    class_column = normalized_columns.get("class")

    if dataframe.empty or date_column is None:
        return None, [], []

    first_row = dataframe.iloc[0]
    columns = list(dataframe.columns)
    product_pairs: dict[str, tuple[str, str | None]] = {}

    index = 0
    while index < len(columns):
        column = columns[index]
        if column.strip().lower() in BASE_LEDGER_COLUMNS:
            index += 1
            continue

        marker = _normalize_label(first_row[column])
        if marker != "in":
            index += 1
            continue

        out_column: str | None = None
        if index + 1 < len(columns):
            next_column = columns[index + 1]
            next_marker = _normalize_label(first_row[next_column])
            if next_marker == "out":
                out_column = next_column
                index += 1

        product_pairs[column.strip()] = (column, out_column)
        index += 1

    if not product_pairs:
        return None, [], []

    quantities: dict[str, int] = {product: 0 for product in product_pairs}
    errors: list[str] = []
    events: list[dict[str, Any]] = []

    for row_index, row in dataframe.iterrows():
        if int(row_index) == 0:
            continue

        date_label = _normalize_label(row[date_column])
        if date_label in SUMMARY_DATE_LABELS:
            continue

        actor_name = _to_optional_text(row[name_column]) if name_column else None
        actor_class = _to_optional_text(row[class_column]) if class_column else None
        occurred_at = _to_optional_datetime(row[date_column])
        row_has_values = False
        for product_name, (in_column, out_column) in product_pairs.items():
            try:
                incoming = _to_optional_int(row[in_column])
                outgoing = _to_optional_int(row[out_column]) if out_column is not None else 0
            except ValueError as exc:
                errors.append(f"Row {int(row_index) + 2} ({product_name}): {exc}")
                continue

            if incoming == 0 and outgoing == 0:
                continue

            quantities[product_name] += incoming - outgoing
            if incoming > 0:
                events.append(
                    {
                        "product_name": product_name,
                        "change_amount": incoming,
                        "name": actor_name,
                        "class": actor_class,
                        "given_to": actor_name,
                        "department": actor_class,
                        "date": occurred_at,
                    }
                )
            if outgoing > 0:
                events.append(
                    {
                        "product_name": product_name,
                        "change_amount": -outgoing,
                        "name": actor_name,
                        "class": actor_class,
                        "given_to": actor_name,
                        "department": actor_class,
                        "date": occurred_at,
                    }
                )
            row_has_values = True

        if not row_has_values and date_label in {"", "nan"}:
            continue

    return quantities, errors, events


async def _read_excel_dataframe(file: UploadFile | None, file_path: str | None) -> pd.DataFrame:
    if file is not None:
        suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
        contents = await file.read()
        if not contents:
            raise ValueError("Uploaded file is empty")

        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(contents)
            temp_path = Path(temp.name)

        try:
            return pd.read_excel(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    resolved_path = Path(file_path or settings.Excel_Path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"Excel file not found at {resolved_path}")
    return pd.read_excel(resolved_path)


async def load_excel_data(
    session: AsyncSession,
    file: UploadFile | None = None,
    file_path: str | None = None,
    actor_name: str | None = None,
    actor_class: str | None = None,
    sync_excel_file: bool = False,
) -> JSONResponse:
    try:
        dataframe = await _read_excel_dataframe(file=file, file_path=file_path)
    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": f"Unable to read Excel file: {exc}"},
        )

    if dataframe.empty:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Excel file is empty"},
        )

    quantities, errors = _extract_simple_quantities(dataframe)
    ledger_events: list[dict[str, Any]] = []
    source_format = "simple"
    if quantities is None:
        quantities, errors, ledger_events = _extract_ledger_quantities(dataframe)
        source_format = "ledger"

    if quantities is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "message": (
                    "Unsupported Excel format. Expected either columns "
                    "'product_name' and 'quantity' or a ledger sheet with 'Date' and product In/Out columns."
                )
            },
        )

    if not quantities:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "No valid inventory data found in Excel file"},
        )

    created = 0
    updated = 0
    unchanged = 0
    fallback_actor_name = actor_name or "System"
    fallback_actor_class = actor_class or "system"
    product_ids_by_name: dict[str, int] = {}

    try:
        for product_name, quantity in quantities.items():
            product_result = await session.execute(
                select(Product).where(Product.product_name == product_name)
            )
            product = product_result.scalars().first()
            product_was_created = False

            if product is None:
                product = Product(product_name=product_name)
                session.add(product)
                await session.flush()
                product_was_created = True
            product_ids_by_name[product_name] = int(product.id)

            inventory_result = await session.execute(
                select(Inventory).where(Inventory.product_id == product.id)
            )
            inventory = inventory_result.scalars().first()

            if inventory is None:
                inventory = Inventory(product_id=product.id, quantity=quantity)
                session.add(inventory)
                if source_format == "simple":
                    session.add(
                        InventoryLog(
                            product_id=product.id,
                            change_amount=quantity,
                            actor_name=fallback_actor_name,
                            actor_class=fallback_actor_class,
                        )
                    )
                if product_was_created:
                    created += 1
                else:
                    updated += 1
                continue

            delta = quantity - inventory.quantity
            if delta == 0:
                unchanged += 1
                continue

            inventory.quantity = quantity
            session.add(inventory)
            if source_format == "simple":
                session.add(
                    InventoryLog(
                        product_id=product.id,
                        change_amount=delta,
                        actor_name=fallback_actor_name,
                        actor_class=fallback_actor_class,
                    )
                )
            updated += 1

        if source_format == "ledger":
            for event in ledger_events:
                event_product_id = product_ids_by_name.get(event["product_name"])
                if event_product_id is None:
                    continue

                log_payload = {
                    "product_id": event_product_id,
                    "change_amount": int(event["change_amount"]),
                    "actor_name": (event.get("name") or fallback_actor_name),
                    "actor_class": (event.get("class") or fallback_actor_class),
                    "given_to": event.get("given_to"),
                    "department": event.get("department"),
                }
                if event.get("date") is not None:
                    log_payload["created_at"] = event["date"]

                session.add(InventoryLog(**log_payload))

        if sync_excel_file:
            await sync_products_to_excel(session=session)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": f"Failed to load data: {exc}"},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "Excel data loaded successfully",
            "summary": {
                "format": source_format,
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
                "errors": errors,
            },
        },
    )


async def load_excel(
    session: AsyncSession,
    file: UploadFile | None = None,
    file_path: str | None = None,
) -> JSONResponse:
    return await load_excel_data(session=session, file=file, file_path=file_path)

