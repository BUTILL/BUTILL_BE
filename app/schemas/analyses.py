from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000_000)]
MonthIndex = Annotated[int, Field(strict=True, ge=1, le=12)]
Bps = Annotated[int, Field(strict=True, ge=-10_000, le=50_000)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExpenseInput(Model):
    name: str = Field(min_length=1, max_length=60)
    amount: Money


class FixedExpenseInput(ExpenseInput):
    due_day: Annotated[int, Field(strict=True, ge=1, le=31)] | None = None


class IrregularExpenseInput(ExpenseInput):
    expected_date: date
    is_paid: bool = Field(default=False, strict=True)


class MonthlyOverride(Model):
    month: MonthIndex
    sales: Money | None = None
    ingredient_cost: Money | None = None
    fixed_cost: Money | None = None

    @model_validator(mode="after")
    def require_value(self) -> Self:
        if all(v is None for v in (self.sales, self.ingredient_cost, self.fixed_cost)):
            raise ValueError("월별 변경 금액을 하나 이상 입력해야 합니다.")
        return self


class AnalysisInput(Model):
    start_month: date
    months: MonthIndex = 12
    current_cash: Money
    reserve_cash: Money = 0
    unpaid_initial_investment: Money = 0
    monthly_sales: Money
    monthly_ingredient_cost: Money = 0
    ingredient_items: list[ExpenseInput] = Field(default_factory=list, max_length=100)
    fixed_expenses: list[FixedExpenseInput] = Field(default_factory=list, max_length=100)
    irregular_expenses: list[IrregularExpenseInput] = Field(default_factory=list, max_length=100)
    monthly_overrides: list[MonthlyOverride] = Field(default_factory=list, max_length=12)

    @field_validator("start_month")
    @classmethod
    def check_start(cls, value: date) -> date:
        if value.day != 1 or not 2000 <= value.year <= 2100:
            raise ValueError("분석 시작 월은 2000~2100년의 해당 월 첫날로 입력하세요.")
        return value

    @model_validator(mode="after")
    def check_periods(self) -> Self:
        if self.ingredient_items and sum(item.amount for item in self.ingredient_items) != self.monthly_ingredient_cost:
            raise ValueError("원재료별 금액의 합계가 월 식재료비와 일치해야 합니다.")
        seen = set()
        for item in self.monthly_overrides:
            if item.month > self.months or item.month in seen:
                raise ValueError("월별 변경은 분석기간 안에서 월별로 한 번만 입력하세요.")
            seen.add(item.month)
        end = self.start_month.year * 12 + self.start_month.month - 1 + self.months
        for item in self.irregular_expenses:
            idx = item.expected_date.year * 12 + item.expected_date.month - 1
            if not item.is_paid and not self.start_month.year * 12 + self.start_month.month - 1 <= idx < end:
                raise ValueError("미지급 비정기 지출의 예정일은 분석기간 안에 있어야 합니다.")
        return self


class RiskResponse(Model):
    code: str
    month: date
    amount: int
    message: str


class MonthResponse(Model):
    month: date
    sales: int
    ingredient_cost: int
    fixed_cost: int
    irregular_cost: int
    net_cashflow: int
    cash_balance: int
    available_balance: int


class RunwayResponse(Model):
    initial_balance: int
    first_depletion_month: date | None
    first_shortage_month: date | None
    shortage_amount: int
    full_months_before_shortage: int | None
    status: Literal["shortage", "depleted", "no_shortage_in_period"]


class AnalysisResponse(Model):
    calculation_version: str
    start_month: date
    months: int
    initial_cash: int
    initial_available_cash: int
    cash_runway: RunwayResponse
    available_runway: RunwayResponse
    monthly: list[MonthResponse]
    risks: list[RiskResponse]
    warnings: list[str]
    persisted: bool = False


class ScenarioInput(Model):
    name: str = Field(min_length=1, max_length=60)
    sales_change_bps: Bps = 0
    ingredient_change_bps: Bps = 0
    fixed_change_bps: Bps = 0
    extra_expenses: list[IrregularExpenseInput] = Field(default_factory=list, max_length=100)


class ComparisonInput(Model):
    base: AnalysisInput
    scenarios: list[ScenarioInput] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def check_scenarios(self) -> Self:
        names = [item.name for item in self.scenarios]
        if len(names) != len(set(names)):
            raise ValueError("시나리오 이름은 서로 다르게 입력하세요.")
        for item in self.scenarios:
            data = self.base.model_dump()
            data["irregular_expenses"] += [e.model_dump() for e in item.extra_expenses]
            AnalysisInput.model_validate(data)
        return self


class MonthDelta(Model):
    month: date
    cash_balance_delta: int
    available_balance_delta: int
    net_cashflow_delta: int


class ScenarioResponse(Model):
    name: str
    changes: ScenarioInput
    analysis: AnalysisResponse
    monthly_delta: list[MonthDelta]
    ending_cash_delta: int
    cash_shortage_month_delta: int | None


class ComparisonResponse(Model):
    base: AnalysisResponse
    scenarios: list[ScenarioResponse]
    persisted: bool = False
