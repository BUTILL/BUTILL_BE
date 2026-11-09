from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.database.persistence import SupabaseRepository
from app.errors import DomainError
from app.schemas.analyses import AnalysisInput, AnalysisResponse
from app.schemas.ingredient_prices import PriceFilter, PriceSummary
from app.schemas.store_settings import (
    IngredientCostItem, IngredientCostSave, IngredientCostsResponse, Notification, NotificationsResponse,
    Preferences, PreferencesResponse, RunwayImpact, TaxEvent, TaxSettings, TaxSettingsResponse,
)
from app.services.cashflow import analyze
from app.services.ingredient_prices import latest_prices
from app.services.price_collection import KST
from app.services.price_items import PRICE_ITEMS
from app.services.stores import get_finances

SCHEDULE_LIMIT = 8
EXPENSE_NOTICE_DAYS = 7
TAX_NOTICE_DAYS = 14
PRICE_ALERT_BPS = 500
RUNWAY_CRITICAL_MONTHS = 2
RUNWAY_SAFE_MONTHS = 6
DEFAULT_DUE_DAY = 5
CATALOG = {item.key: item for item in PRICE_ITEMS}

VAT_GENERAL = [(1, 25, "vat_2nd_final", "부가가치세 2기 확정신고·납부"), (4, 25, "vat_1st_prepaid", "부가가치세 1기 예정고지 납부"),
               (7, 25, "vat_1st_final", "부가가치세 1기 확정신고·납부"), (10, 25, "vat_2nd_prepaid", "부가가치세 2기 예정고지 납부")]
VAT_CORPORATION = [(1, 25, "vat_2nd_final", "부가가치세 2기 확정신고·납부"), (4, 25, "vat_1st_preliminary", "부가가치세 1기 예정신고·납부"),
                   (7, 25, "vat_1st_final", "부가가치세 1기 확정신고·납부"), (10, 25, "vat_2nd_preliminary", "부가가치세 2기 예정신고·납부")]
VAT_SIMPLE = [(1, 25, "vat_simple", "부가가치세 간이과세자 신고·납부"), (7, 25, "vat_simple_prepaid", "간이과세자 예정부과 납부")]
INCOME_TAX = [(5, 31, "income_tax", "종합소득세 신고·납부"), (11, 30, "income_tax_prepaid", "종합소득세 중간예납")]
CORPORATE_TAX = [(3, 31, "corporate_tax", "법인세 신고·납부 (12월 결산 법인)"), (8, 31, "corporate_tax_interim", "법인세 중간예납")]


def today_kst() -> date:
    return datetime.now(KST).date()


def rounded(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def business_day(day: date) -> date:
    return day + timedelta(days=(7 - day.weekday()) % 7 if day.weekday() >= 5 else 0)


def next_yearly(month: int, day: int, today: date) -> date:
    for year in (today.year, today.year + 1):
        due = business_day(date(year, month, day))
        if due >= today:
            return due
    raise RuntimeError("unreachable")


def next_monthly(day: int, today: date) -> date:
    for offset in range(3):
        idx = today.year * 12 + today.month - 1 + offset
        due = business_day(date(idx // 12, idx % 12 + 1, min(day, 28)))
        if due >= today:
            return due
    raise RuntimeError("unreachable")


def tax_schedule(settings: TaxSettings, today: date) -> list[TaxEvent]:
    yearly = []
    if settings.business_entity == "corporation":
        yearly += VAT_CORPORATION + CORPORATE_TAX
    else:
        yearly += (VAT_SIMPLE if settings.tax_type == "simple" else VAT_GENERAL) + INCOME_TAX
    vat_note = f"{settings.installments}회 분할 납부 선택" if settings.installments > 1 else None
    if settings.business_entity == "unregistered":
        vat_note = "사업자 등록 후 적용되는 일정입니다."
    events = [TaxEvent(code=code, title=title, due_date=due, days_left=(due - today).days,
                       note=vat_note if code.startswith("vat") else None)
              for month, day, code, title in yearly for due in [next_yearly(month, day, today)]]
    if settings.employees == "yes":
        due = next_monthly(10, today)
        events.append(TaxEvent(code="withholding", title="원천세 신고·납부와 4대보험 납부", due_date=due,
                               days_left=(due - today).days, note="직원 급여를 지급한 다음 달 10일"))
    return sorted(events, key=lambda e: (e.due_date, e.code))[:SCHEDULE_LIMIT]


def settings_row(repo: SupabaseRepository, store_id: UUID) -> dict | None:
    rows = repo.request("GET", "store_settings", {"store_id": f"eq.{store_id}", "select": "*", "limit": "1"})
    return rows[0] if rows else None


def parse_saved(model: type[BaseModel], value: object) -> BaseModel:
    try:
        return model.model_validate(value or {})
    except ValidationError:
        raise DomainError("SAVED_INPUT_INVALID", "저장된 설정의 형식을 확인하고 다시 저장하세요.") from None


def save_column(repo: SupabaseRepository, store_id: UUID, column: str, value: dict) -> None:
    if settings_row(repo, store_id) is None:
        repo.request("POST", "store_settings", data={"store_id": str(store_id), column: value})
    else:
        repo.request("PATCH", "store_settings", {"store_id": f"eq.{store_id}"}, {column: value})


def get_tax_settings(repo: SupabaseRepository, store_id: UUID, today: date | None = None) -> TaxSettingsResponse:
    repo.owned_store(store_id)
    row = settings_row(repo, store_id)
    saved = row is not None and bool(row.get("tax"))
    settings = parse_saved(TaxSettings, row.get("tax") if row else None)
    return TaxSettingsResponse(store_id=store_id, settings=settings, saved=saved,
                               schedule=tax_schedule(settings, today or today_kst()))


def save_tax_settings(repo: SupabaseRepository, store_id: UUID, settings: TaxSettings) -> TaxSettingsResponse:
    repo.owned_store(store_id)
    save_column(repo, store_id, "tax", settings.model_dump(mode="json"))
    return get_tax_settings(repo, store_id)


def get_preferences(repo: SupabaseRepository, store_id: UUID) -> PreferencesResponse:
    repo.owned_store(store_id)
    row = settings_row(repo, store_id)
    return PreferencesResponse(store_id=store_id, preferences=parse_saved(Preferences, row.get("preferences") if row else None),
                               saved=row is not None and bool(row.get("preferences")))


def save_preferences(repo: SupabaseRepository, store_id: UUID, preferences: Preferences) -> PreferencesResponse:
    repo.owned_store(store_id)
    save_column(repo, store_id, "preferences", preferences.model_dump(mode="json"))
    return get_preferences(repo, store_id)


def market_prices(keys: list[str] | None = None) -> tuple[dict[str, PriceSummary], datetime | None]:
    response = latest_prices(PriceFilter())
    items = {i.key: i for i in response.items if keys is None or i.key in keys}
    return items, response.collected_at


def saved_costs(repo: SupabaseRepository, store_id: UUID) -> list[dict]:
    return repo.request("GET", "store_ingredient_costs", {"store_id": f"eq.{store_id}", "select": "*", "order": "price_key.asc"})


def bps(numerator: int, denominator: int) -> int:
    return rounded(Decimal(numerator) * 10_000 / Decimal(denominator))


def cost_item(row: dict, price: PriceSummary | None) -> IngredientCostItem:
    key = row["price_key"]
    latest = price.latest if price else None
    change = price.week_change.change_bps if price and price.week_change else None
    unit_price, amount = row.get("unit_price"), row.get("monthly_amount")
    return IngredientCostItem(
        price_key=key, name=CATALOG[key].name if key in CATALOG else key, unit=price.unit if price else None,
        market_price=latest.average_price if latest else None, market_price_date=latest.price_date if latest else None,
        market_status=price.status if price else "no_data", week_change_bps=change, unit_price=unit_price,
        unit_price_gap_bps=bps(unit_price - latest.average_price, latest.average_price) if unit_price and latest else None,
        monthly_amount=amount,
        monthly_impact=rounded(Decimal(amount) * change / 10_000) if amount is not None and change is not None else None,
    )


def shift_ingredient_cost(data: AnalysisInput, delta: int) -> AnalysisInput:
    adjusted = data.model_copy(deep=True)
    adjusted.monthly_ingredient_cost = max(0, adjusted.monthly_ingredient_cost + delta)
    adjusted.ingredient_items = []
    for item in adjusted.monthly_overrides:
        if item.ingredient_cost is not None:
            item.ingredient_cost = max(0, item.ingredient_cost + delta)
    return adjusted


def runway_impact(repo: SupabaseRepository, store_id: UUID, delta: int) -> RunwayImpact | None:
    try:
        finance = get_finances(repo, store_id)
    except DomainError as exc:
        if exc.code in ("NOT_FOUND", "SAVED_INPUT_INVALID"):
            return None
        raise
    base = analyze(finance.input).available_runway
    adjusted = analyze(shift_ingredient_cost(finance.input, delta)).available_runway
    return RunwayImpact(base_available_months=base.full_months_before_shortage,
                        adjusted_available_months=adjusted.full_months_before_shortage,
                        base_first_shortage_month=base.first_shortage_month,
                        adjusted_first_shortage_month=adjusted.first_shortage_month, monthly_cost_increase=delta)


def get_ingredient_costs(repo: SupabaseRepository, store_id: UUID) -> IngredientCostsResponse:
    repo.owned_store(store_id)
    rows = saved_costs(repo, store_id)
    prices, collected_at = market_prices([r["price_key"] for r in rows])
    items = [cost_item(r, prices.get(r["price_key"])) for r in rows]
    impact = sum(i.monthly_impact or 0 for i in items)
    return IngredientCostsResponse(
        store_id=store_id, items=items, total_monthly_amount=sum(i.monthly_amount or 0 for i in items),
        total_monthly_impact=impact, runway_impact=runway_impact(repo, store_id, impact) if items else None,
        prices_collected_at=collected_at)


def save_ingredient_costs(repo: SupabaseRepository, store_id: UUID, data: IngredientCostSave) -> IngredientCostsResponse:
    unknown = [i.price_key for i in data.items if i.price_key not in CATALOG]
    if unknown:
        raise DomainError("UNKNOWN_INGREDIENT", "시세를 제공하지 않는 원재료입니다: " + ", ".join(unknown))
    repo.owned_store(store_id)
    repo.request("DELETE", "store_ingredient_costs", {"store_id": f"eq.{store_id}"})
    for item in data.items:
        repo.request("POST", "store_ingredient_costs", data={"store_id": str(store_id), **item.model_dump()})
    return get_ingredient_costs(repo, store_id)


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def runway_notifications(result: AnalysisResponse, today: date) -> list[Notification]:
    shortage = result.available_runway.first_shortage_month
    if shortage is None:
        return []
    left = months_between(date(today.year, today.month, 1), shortage)
    if left >= RUNWAY_SAFE_MONTHS:
        return []
    critical = left < RUNWAY_CRITICAL_MONTHS
    when = "이번 달" if left <= 0 else f"{left}개월 뒤({shortage.year}년 {shortage.month}월)"
    return [Notification(type="runway", severity="critical" if critical else "warning",
                         title="가용 자금이 곧 부족해져요" if critical else "가용 자금이 안전선(6개월) 아래예요",
                         message=f"지금 입력된 매출·지출 기준으로 {when} 가용 자금이 부족해질 수 있어요.",
                         due_date=shortage, target="home")]


def price_notifications(prices: dict[str, PriceSummary]) -> list[Notification]:
    rising = [p for p in prices.values() if p.week_change and p.week_change.change_bps >= PRICE_ALERT_BPS]
    if not rising:
        return []
    rising.sort(key=lambda p: -p.week_change.change_bps)
    names = ", ".join(f"{p.name} +{p.week_change.change_bps / 100:.1f}%" for p in rising[:3])
    more = f" 외 {len(rising) - 3}개" if len(rising) > 3 else ""
    return [Notification(type="ingredient", severity="warning", title="주요 원재료 가격이 올랐어요",
                         message=f"1주 전보다 5% 이상 오른 품목: {names}{more}", target="raw_materials")]


def expense_notifications(data: AnalysisInput, today: date) -> list[Notification]:
    result = []
    for item in data.fixed_expenses:
        if not item.amount:
            continue
        due = next_monthly(item.due_day or DEFAULT_DUE_DAY, today) if (item.due_day or DEFAULT_DUE_DAY) <= 28 else None
        if due is None:
            continue
        left = (due - today).days
        if left <= EXPENSE_NOTICE_DAYS:
            result.append(Notification(type="expense", severity="info", title=f"{item.name} 지급일이 다가와요",
                                       message=f"{item.amount:,}원 지급 예정", due_date=due, days_left=left, target="calendar"))
    for item in data.irregular_expenses:
        left = (item.expected_date - today).days
        if not item.is_paid and item.amount and 0 <= left <= EXPENSE_NOTICE_DAYS:
            result.append(Notification(type="expense", severity="info", title=f"{item.name} 지출 예정일이에요",
                                       message=f"{item.amount:,}원 지출 예정", due_date=item.expected_date,
                                       days_left=left, target="calendar"))
    return result


def tax_notifications(events: list[TaxEvent]) -> list[Notification]:
    return [Notification(type="tax", severity="warning" if e.days_left <= 3 else "info", title=f"{e.title} 기한이 다가와요",
                         message="세금 관리에서 납부 일정을 확인해 주세요." + (f" ({e.note})" if e.note else ""),
                         due_date=e.due_date, days_left=e.days_left, target="tax")
            for e in events if e.days_left <= TAX_NOTICE_DAYS]


def get_notifications(repo: SupabaseRepository, store_id: UUID, today: date | None = None) -> NotificationsResponse:
    day = today or today_kst()
    repo.owned_store(store_id)
    row = settings_row(repo, store_id)
    preferences = parse_saved(Preferences, row.get("preferences") if row else None)
    tax = parse_saved(TaxSettings, row.get("tax") if row else None)
    notifications = []
    try:
        finance = get_finances(repo, store_id)
    except DomainError as exc:
        if exc.code not in ("NOT_FOUND", "SAVED_INPUT_INVALID"):
            raise
        finance = None
    if finance and preferences.runway_alert:
        notifications += runway_notifications(analyze(finance.input), day)
    if preferences.ingredient_alert:
        keys = [r["price_key"] for r in saved_costs(repo, store_id)] or [i.key for i in PRICE_ITEMS if "common" in i.groups]
        notifications += price_notifications(market_prices(keys)[0])
    if finance:
        notifications += expense_notifications(finance.input, day)
    if row and row.get("tax"):
        notifications += tax_notifications(tax_schedule(tax, day))
    order = {"critical": 0, "warning": 1, "info": 2}
    notifications.sort(key=lambda n: (order[n.severity], n.days_left if n.days_left is not None else -1))
    return NotificationsResponse(store_id=store_id, generated_at=datetime.now(KST), notifications=notifications)
