from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal


class ProductCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=0)


class ProductUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=1, max_length=255)
    quantity: int | None = Field(default=None, ge=0)


class ProductItem(BaseModel):
    id: int
    product_name: str
    quantity: int


class StockEntryCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    entry_date: datetime | None = None
    movement: Literal["in", "out"]
    quantity: int = Field(ge=1)
    given_to: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
