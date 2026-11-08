import unittest
from pydantic import ValidationError
from app.schemas.analyses import AnalysisInput
from app.services.cashflow import analyze


class ManagementFieldsTests(unittest.TestCase):
    def test_item_details_roundtrip_without_double_counting(self) -> None:
        data = AnalysisInput(start_month="2026-10-01", current_cash=1000,
                             monthly_sales=500, monthly_ingredient_cost=100,
                             ingredient_items=[{"name": "원두", "amount": 100}],
                             fixed_expenses=[{"name": "월세", "amount": 200, "due_day": 31}])
        restored = AnalysisInput.model_validate_json(data.model_dump_json())
        self.assertEqual(restored.fixed_expenses[0].due_day, 31)
        self.assertEqual(restored.ingredient_items[0].name, "원두")
        self.assertEqual(analyze(restored).monthly[0].net_cashflow, 200)

    def test_invalid_due_day(self) -> None:
        for day in [0, 32, 1.5]:
            with self.subTest(day=day), self.assertRaises(ValidationError):
                AnalysisInput(start_month="2026-10-01", current_cash=1000, monthly_sales=500,
                              fixed_expenses=[{"name": "월세", "amount": 200, "due_day": day}])

    def test_ingredient_total_must_match(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisInput(start_month="2026-10-01", current_cash=1000, monthly_sales=500,
                          monthly_ingredient_cost=50, ingredient_items=[{"name": "원두", "amount": 100}])
