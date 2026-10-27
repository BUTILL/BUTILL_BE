from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.analyses import Model

Code = Annotated[str, Field(pattern=r"^\d{1,7}$")]
Group = Literal["common", "dakgalbi", "pasta"]


class PriceItem(Model):
    key: str = Field(pattern=r"^[a-z_]+$")
    name: str = Field(min_length=1, max_length=60)
    groups: list[Group]
    category_code: Code
    item_code: Code
    kind_code: Code | None = None
    rank_code: Code | None = None
    product_class: Literal["01", "02"] = "01"
    region_code: Code = "1101"


class PriceObservation(Model):
    item_key: str
    price_date: date
    kind_code: str
    kind_name: str | None = None
    rank_code: str
    rank_name: str | None = None
    unit: str
    market_code: str
    market_name: str | None = None
    price: int = Field(gt=0)
    price_per_kg: int | None = Field(default=None, gt=0)
    source: Literal["KAMIS"] = "KAMIS"


class ItemCollection(Model):
    item: PriceItem
    status: Literal["success", "no_data", "failed"]
    error_code: str | None = None
    observations: list[PriceObservation]
    missing_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0


class CollectionResult(Model):
    source: Literal["KAMIS"] = "KAMIS"
    started_at: datetime
    finished_at: datetime
    status: Literal["success", "partial", "failed"]
    success_count: int
    failure_count: int
    items: list[ItemCollection]


class DailyPrice(Model):
    price_date: date
    average_price: int
    average_price_per_kg: int | None = None
    market_count: int


class PriceChange(Model):
    base_date: date
    base_price: int
    latest_date: date
    latest_price: int
    change_amount: int
    change_bps: int


class PriceSummary(Model):
    key: str
    name: str
    groups: list[Group]
    status: Literal["success", "no_data", "failed"]
    kind_name: str | None = None
    rank_name: str | None = None
    unit: str | None = None
    latest: DailyPrice | None = None
    week_change: PriceChange | None = None
    daily: list[DailyPrice] = Field(default_factory=list)


class IngredientPriceResponse(Model):
    source: str = "한국농수산식품유통공사(KAMIS) 일별 소매가격"
    basis: str = "서울 조사 시장 평균. 참고 정보이며 매장 식재료비에 자동 반영하지 않습니다."
    collected_at: datetime
    status: Literal["success", "partial", "failed"]
    items: list[PriceSummary]
