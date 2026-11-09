from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.analyses import Model, Money

PriceKey = Annotated[str, Field(pattern=r"^[a-z_]+$", max_length=40)]


class TaxSettings(Model):
    business_entity: Literal["individual", "corporation", "unregistered", "unknown"] = "individual"
    tax_type: Literal["general", "simple", "unknown"] = "general"
    filing_method: Literal["self", "accountant", "undecided"] = "accountant"
    reserve_method: Literal["monthly", "lump_sum", "unknown"] = "monthly"
    employees: Literal["yes", "no", "pending"] = "yes"
    installments: Literal[1, 2, 3, 4] = 1


class TaxEvent(Model):
    code: str
    title: str
    due_date: date
    days_left: int
    note: str | None = None


class TaxSettingsResponse(Model):
    store_id: UUID
    settings: TaxSettings
    saved: bool
    schedule: list[TaxEvent]
    basis: str = "세법상 기본 신고·납부 기한 기준 참고 일정입니다. 세액은 계산하지 않으며, 주말이면 다음 평일로 옮겼습니다."


class Preferences(Model):
    runway_alert: bool = True
    ingredient_alert: bool = True
    font_size: Literal["normal", "large"] = "normal"


class PreferencesResponse(Model):
    store_id: UUID
    preferences: Preferences
    saved: bool


class IngredientCostInput(Model):
    price_key: PriceKey
    unit_price: Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)] | None = None
    monthly_amount: Money | None = None


class IngredientCostSave(Model):
    items: list[IngredientCostInput] = Field(default_factory=list, max_length=30)

    @field_validator("items")
    @classmethod
    def unique_keys(cls, items: list[IngredientCostInput]) -> list[IngredientCostInput]:
        keys = [i.price_key for i in items]
        if len(keys) != len(set(keys)):
            raise ValueError("같은 원재료를 두 번 입력할 수 없습니다.")
        return items


class IngredientCostItem(Model):
    price_key: str
    name: str
    unit: str | None = None
    market_price: int | None = None
    market_price_date: date | None = None
    market_status: Literal["success", "no_data", "failed"]
    week_change_bps: int | None = None
    unit_price: int | None = None
    unit_price_gap_bps: int | None = None
    monthly_amount: int | None = None
    monthly_impact: int | None = None


class RunwayImpact(Model):
    base_available_months: int | None
    adjusted_available_months: int | None
    base_first_shortage_month: date | None
    adjusted_first_shortage_month: date | None
    monthly_cost_increase: int


class IngredientCostsResponse(Model):
    store_id: UUID
    items: list[IngredientCostItem]
    total_monthly_amount: int
    total_monthly_impact: int
    runway_impact: RunwayImpact | None
    prices_collected_at: datetime | None = None
    basis: str = "월 지출 영향 = 월 사용금액 × 시세의 1주 전 대비 변동률. 시세는 참고 정보이며 경영정보에 자동 반영하지 않습니다."


class Notification(Model):
    type: Literal["runway", "ingredient", "expense", "tax"]
    severity: Literal["info", "warning", "critical"]
    title: str
    message: str
    due_date: date | None = None
    days_left: int | None = None
    target: Literal["home", "raw_materials", "calendar", "tax"]


class NotificationsResponse(Model):
    store_id: UUID
    generated_at: datetime
    notifications: list[Notification]
