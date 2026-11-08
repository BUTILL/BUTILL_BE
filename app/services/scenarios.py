from app.schemas.analyses import (
    ComparisonInput, ComparisonResponse, MonthDelta, ScenarioResponse,
)
from app.services.cashflow import analyze


def scale_money(amount: int, bps: int) -> int:
    return (amount * (10_000 + bps) + 5_000) // 10_000


def compare(data: ComparisonInput) -> ComparisonResponse:
    base = analyze(data.base)
    results = []
    for change in data.scenarios:
        adjusted = data.base.model_copy(deep=True)
        adjusted.monthly_sales = scale_money(adjusted.monthly_sales, change.sales_change_bps)
        adjusted.monthly_ingredient_cost = scale_money(adjusted.monthly_ingredient_cost, change.ingredient_change_bps)
        for item in adjusted.fixed_expenses:
            item.amount = scale_money(item.amount, change.fixed_change_bps)
        for item in adjusted.monthly_overrides:
            if item.sales is not None:
                item.sales = scale_money(item.sales, change.sales_change_bps)
            if item.ingredient_cost is not None:
                item.ingredient_cost = scale_money(item.ingredient_cost, change.ingredient_change_bps)
            if item.fixed_cost is not None:
                item.fixed_cost = scale_money(item.fixed_cost, change.fixed_change_bps)
        adjusted.irregular_expenses.extend(e.model_copy(deep=True) for e in change.extra_expenses)
        result = analyze(adjusted)
        base_month = base.cash_runway.first_shortage_month
        new_month = result.cash_runway.first_shortage_month
        delta = None
        if base_month is not None and new_month is not None:
            delta = (new_month.year - base_month.year) * 12 + new_month.month - base_month.month
        results.append(ScenarioResponse(
            name=change.name, changes=change, analysis=result,
            monthly_delta=[MonthDelta(month=b.month, cash_balance_delta=r.cash_balance - b.cash_balance,
                                      available_balance_delta=r.available_balance - b.available_balance,
                                      net_cashflow_delta=r.net_cashflow - b.net_cashflow)
                           for b, r in zip(base.monthly, result.monthly, strict=True)],
            ending_cash_delta=result.monthly[-1].cash_balance - base.monthly[-1].cash_balance,
            cash_shortage_month_delta=delta,
        ))
    return ComparisonResponse(base=base, scenarios=results)
