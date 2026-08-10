from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str | None
    site: str
    target_price: float
    current_price: float | None
    created_at: datetime


class PriceHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price: float
    checked_at: datetime
