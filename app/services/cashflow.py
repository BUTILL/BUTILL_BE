from datetime import date

from app.schemas.analyses import (
    AnalysisInput, AnalysisResponse, MonthResponse, RiskResponse, RunwayResponse,
)

CALCULATION_VERSION = "mvp-1.0"


def add_month(start: date, offset: int) -> date:
    idx = start.year * 12 + start.month - 1 + offset
    return date(idx // 12, idx % 12 + 1, 1)


def get_runway(initial: int, balances: list[int], start: date) -> RunwayResponse:
    values = [initial, *balances]
    shortage = next((i for i, value in enumerate(values) if value < 0), None)
    depletion = next((i for i, value in enumerate(values) if value <= 0), None)

    def month_at(idx: int | None) -> date | None:
        return None if idx is None else add_month(start, max(0, idx - 1))

    return RunwayResponse(
        initial_balance=initial,
        first_depletion_month=month_at(depletion),
        first_shortage_month=month_at(shortage),
        shortage_amount=0 if shortage is None else -values[shortage],
        full_months_before_shortage=None if shortage is None else max(0, shortage - 1),
        status="shortage" if shortage is not None else "depleted" if depletion is not None else "no_shortage_in_period",
    )


def analyze(data: AnalysisInput) -> AnalysisResponse:
    cash = data.current_cash - data.unpaid_initial_investment
    initial = cash
    fixed = sum(item.amount for item in data.fixed_expenses)
    overrides = {item.month: item for item in data.monthly_overrides}
    expenses = {}
    paid = False
    for item in data.irregular_expenses:
        if item.is_paid:
            paid = True
            continue
        month = item.expected_date.replace(day=1)
        expenses[month] = expenses.get(month, 0) + item.amount
    rows = []
    risks = []
    warnings = [
        "요청 입력값으로만 계산하며 DB에 저장하지 않습니다.",
        "월말 잔액 기준 분석으로 월중 지급 순서에 따른 부족 시점은 계산하지 않습니다.",
        "보유자금은 분석 시작 월 첫날 기준이며 이미 지급한 비용은 포함하지 마세요.",
        "외부 원재료 가격은 자동 적용하지 않습니다. 반영할 비용은 사용자가 확인해야 합니다.",
    ]
    if paid:
        warnings.append("지급 완료 비정기 지출은 보유자금에 반영된 것으로 보고 다시 차감하지 않았습니다.")
    if initial < 0:
        risks.append(RiskResponse(code="INITIAL_CASH_SHORTAGE", month=data.start_month, amount=-initial,
                                  message="미지급 초기 투자비를 반영하면 시작 시점부터 현금이 부족합니다."))
    if data.reserve_cash > max(initial, 0):
        warnings.append("예비자금이 시작 현금보다 커서 초기 가용자금이 음수입니다.")
    for idx in range(data.months):
        month = add_month(data.start_month, idx)
        override = overrides.get(idx + 1)
        sales = data.monthly_sales if override is None or override.sales is None else override.sales
        food = data.monthly_ingredient_cost if override is None or override.ingredient_cost is None else override.ingredient_cost
        fixed_cost = fixed if override is None or override.fixed_cost is None else override.fixed_cost
        extra = expenses.get(month, 0)
        net = sales - food - fixed_cost - extra
        cash += net
        available = cash - data.reserve_cash
        rows.append(MonthResponse(month=month, sales=sales, ingredient_cost=food, fixed_cost=fixed_cost,
                                  irregular_cost=extra, net_cashflow=net, cash_balance=cash, available_balance=available))
        if sales < food + fixed_cost:
            risks.append(RiskResponse(code="OPERATING_DEFICIT", month=month, amount=food + fixed_cost - sales,
                                      message="월 매출보다 식재료비와 고정비가 많습니다."))
        if extra:
            risks.append(RiskResponse(code="IRREGULAR_OUTFLOW", month=month, amount=extra,
                                      message="해당 월에 비정기 지출이 반영되었습니다."))
        if available < 0 <= cash:
            risks.append(RiskResponse(code="RESERVE_NEEDED", month=month, amount=-available,
                                      message="현금은 남아 있지만 예비자금을 제외한 가용자금은 부족합니다."))
        if cash < 0:
            risks.append(RiskResponse(code="CASH_SHORTAGE", month=month, amount=-cash,
                                      message="예상 현금잔액이 음수입니다. 운영자금 보완이 필요합니다."))
    return AnalysisResponse(
        calculation_version=CALCULATION_VERSION, start_month=data.start_month, months=data.months,
        initial_cash=initial, initial_available_cash=initial - data.reserve_cash,
        cash_runway=get_runway(initial, [r.cash_balance for r in rows], data.start_month),
        available_runway=get_runway(initial - data.reserve_cash, [r.available_balance for r in rows], data.start_month),
        monthly=rows, risks=risks, warnings=warnings,
    )
