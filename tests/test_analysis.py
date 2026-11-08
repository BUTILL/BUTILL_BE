import copy
import os
import random
import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.analyses import AnalysisInput, ComparisonInput
from app.services.cashflow import analyze
from app.services.scenarios import compare, scale_money


def sample(**changes: object) -> dict:
    data = {
        "start_month": "2026-11-01", "months": 3, "current_cash": 3_000_000,
        "reserve_cash": 500_000, "unpaid_initial_investment": 0,
        "monthly_sales": 2_000_000, "monthly_ingredient_cost": 500_000,
        "fixed_expenses": [{"name": "임대료·인건비", "amount": 1_000_000}],
        "irregular_expenses": [], "monthly_overrides": [],
    }
    return data | changes


class AnalysisTests(unittest.TestCase):
    def test_normal_cashflow_and_reserve(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample()))
        self.assertEqual([r.cash_balance for r in result.monthly], [3_500_000, 4_000_000, 4_500_000])
        self.assertEqual([r.available_balance for r in result.monthly], [3_000_000, 3_500_000, 4_000_000])
        self.assertEqual(result.cash_runway.status, "no_shortage_in_period")
        self.assertIsNone(result.cash_runway.full_months_before_shortage)
        self.assertFalse(result.persisted)

    def test_zero_is_depleted_not_shortage(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample(months=2, reserve_cash=0, irregular_expenses=[
            {"name": "설비", "amount": 4_000_000, "expected_date": "2026-12-10"},
        ])))
        self.assertEqual(result.monthly[-1].cash_balance, 0)
        self.assertEqual(result.cash_runway.status, "depleted")
        self.assertEqual(result.cash_runway.first_depletion_month, date(2026, 12, 1))
        self.assertIsNone(result.cash_runway.first_shortage_month)

    def test_shortage_month_and_amount(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample(current_cash=1_000_000, monthly_sales=500_000)))
        self.assertEqual(result.cash_runway.first_depletion_month, date(2026, 11, 1))
        self.assertEqual(result.cash_runway.first_shortage_month, date(2026, 12, 1))
        self.assertEqual(result.cash_runway.shortage_amount, 1_000_000)
        self.assertEqual(result.cash_runway.full_months_before_shortage, 1)

    def test_initial_investment_deducted_once(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample(unpaid_initial_investment=1_000_000)))
        self.assertEqual(result.initial_cash, 2_000_000)
        self.assertEqual(result.monthly[-1].cash_balance, 3_500_000)

    def test_initial_shortage(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample(unpaid_initial_investment=4_000_000)))
        self.assertEqual(result.cash_runway.first_shortage_month, date(2026, 11, 1))
        self.assertEqual(result.cash_runway.full_months_before_shortage, 0)
        self.assertEqual(result.cash_runway.shortage_amount, 1_000_000)

    def test_paid_expense_not_deducted(self) -> None:
        data = sample(irregular_expenses=[
            {"name": "지급완료", "amount": 999_999, "expected_date": "2026-01-01", "is_paid": True},
            {"name": "미지급", "amount": 100_000, "expected_date": "2026-12-20"},
        ])
        result = analyze(AnalysisInput.model_validate(data))
        self.assertEqual([r.irregular_cost for r in result.monthly], [0, 100_000, 0])
        self.assertEqual(result.monthly[-1].cash_balance, 4_400_000)

    def test_zero_overrides_and_year_boundary(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample(monthly_overrides=[
            {"month": 2, "sales": 0, "ingredient_cost": 0, "fixed_cost": 0},
        ])))
        self.assertEqual(result.monthly[1].net_cashflow, 0)
        self.assertEqual(result.monthly[2].month, date(2027, 1, 1))

    def test_reject_invalid_and_duplicate_periods(self) -> None:
        cases = [sample(months=0), sample(months=13), sample(start_month="2026-11-02"),
                 sample(current_cash=True), sample(monthly_sales=1.5), sample(monthly_sales="1000"),
                 sample(current_cash=-1), sample(monthly_overrides=[{"month": 1}]),
                 sample(monthly_overrides=[{"month": 1, "sales": 0}, {"month": 1, "sales": 0}]),
                 sample(monthly_overrides=[{"month": 4, "sales": 0}]),
                 sample(irregular_expenses=[{"name": "과거", "amount": 1, "expected_date": "2026-10-31"}]),
                 sample(irregular_expenses=[{"name": "미래", "amount": 1, "expected_date": "2027-02-01"}])]
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    AnalysisInput.model_validate(data)

    def test_deterministic_reconciliation(self) -> None:
        rng = random.Random(41)
        for _ in range(100):
            cash, sales, food, fixed = [rng.randrange(0, 1_000_000) for _ in range(4)]
            result = analyze(AnalysisInput.model_validate(sample(current_cash=cash, reserve_cash=0,
                monthly_sales=sales, monthly_ingredient_cost=food,
                fixed_expenses=[{"name": "고정비", "amount": fixed}])))
            self.assertEqual(result.monthly[-1].cash_balance, cash + 3 * (sales - food - fixed))

    def test_reserve_only_shortage(self) -> None:
        result = analyze(AnalysisInput.model_validate(sample(reserve_cash=4_000_000)))
        self.assertEqual(result.available_runway.status, "shortage")
        self.assertEqual(result.cash_runway.status, "no_shortage_in_period")


class ScenarioTests(unittest.TestCase):
    def test_comparison_changes_all_months_and_preserves_original(self) -> None:
        raw = {"base": sample(monthly_overrides=[{"month": 2, "sales": 1_000_000}]),
               "scenarios": [{"name": "매출 20% 감소", "sales_change_bps": -2_000}]}
        original = copy.deepcopy(raw)
        data = ComparisonInput.model_validate(raw)
        before = data.model_dump()
        result = compare(data)
        self.assertEqual(raw, original)
        self.assertEqual(data.model_dump(), before)
        self.assertEqual([r.sales for r in result.scenarios[0].analysis.monthly], [1_600_000, 800_000, 1_600_000])
        self.assertEqual(result.scenarios[0].ending_cash_delta, -1_000_000)

    def test_zero_change_equals_base(self) -> None:
        result = compare(ComparisonInput.model_validate({"base": sample(), "scenarios": [{"name": "동일"}]}))
        self.assertEqual(result.base, result.scenarios[0].analysis)
        self.assertEqual(result.scenarios[0].ending_cash_delta, 0)
        self.assertIsNone(result.scenarios[0].cash_shortage_month_delta)

    def test_exact_rounding_and_full_sales_loss(self) -> None:
        self.assertEqual(scale_money(1, 5_000), 2)
        result = compare(ComparisonInput.model_validate({"base": sample(),
            "scenarios": [{"name": "매출 없음", "sales_change_bps": -10_000}]}))
        self.assertTrue(all(r.sales == 0 for r in result.scenarios[0].analysis.monthly))

    def test_extra_expense_and_limits(self) -> None:
        data = {"base": sample(), "scenarios": [{"name": "추가지출", "extra_expenses": [
            {"name": "수리", "amount": 500_000, "expected_date": "2026-11-10"}]}]}
        result = compare(ComparisonInput.model_validate(data))
        self.assertEqual(result.scenarios[0].ending_cash_delta, -500_000)
        for changes in [[], [{"name": "중복"}, {"name": "중복"}],
                        [{"name": "범위", "sales_change_bps": -10_001}],
                        [{"name": "범위", "sales_change_bps": 0.5}]]:
            with self.assertRaises(ValidationError):
                ComparisonInput.model_validate({"base": sample(), "scenarios": changes})


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        env = patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_real_app_analysis_only_and_openapi(self) -> None:
        self.assertIsNone(app.state.supabase)
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/analyses/preview", schema["paths"])
        self.assertIn("/api/v1/scenarios/compare", schema["paths"])

    def test_preview_and_compare(self) -> None:
        response = self.client.post("/api/v1/analyses/preview", json=sample())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["monthly"][-1]["cash_balance"], 4_500_000)
        response = self.client.post("/api/v1/scenarios/compare", json={"base": sample(), "scenarios": [{"name": "기본"}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scenarios"][0]["ending_cash_delta"], 0)

    def test_validation_never_echoes_input(self) -> None:
        marker = "private-test-value"
        response = self.client.post("/api/v1/analyses/preview", json=sample(monthly_sales=marker))
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)
        self.assertEqual(response.json()["code"], "INVALID_INPUT")

    def test_malformed_json_and_unknown_fields(self) -> None:
        self.assertEqual(self.client.post("/api/v1/analyses/preview", content='{', headers={"Content-Type": "application/json"}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/analyses/preview", json=sample(unknown=123)).status_code, 422)


if __name__ == "__main__":
    unittest.main()
