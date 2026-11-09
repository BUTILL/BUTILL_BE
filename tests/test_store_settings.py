import os
import unittest
from datetime import date, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.errors import DomainError
from app.main import app
from app.schemas.ingredient_prices import DailyPrice, IngredientPriceResponse, PriceChange, PriceSummary
from app.schemas.store_settings import IngredientCostSave, Preferences, TaxSettings
from app.services import ingredient_prices, store_settings as service
from app.services.ingredient_prices import weekly_averages
from app.services.price_collection import KST

STORE = uuid4()
TODAY = date(2026, 11, 9)
FINANCE_INPUT = {"start_month": "2026-11-01", "months": 12, "current_cash": 3_000_000, "reserve_cash": 1_000_000,
                 "monthly_sales": 5_000_000, "monthly_ingredient_cost": 2_000_000,
                 "fixed_expenses": [{"name": "월세", "amount": 6_000_000, "due_day": 10}],
                 "irregular_expenses": [{"name": "에어컨 수리", "amount": 300_000, "expected_date": "2026-11-12", "is_paid": False}]}


class FakeRepo:
    """store_settings 서비스가 쓰는 SupabaseRepository 메서드만 흉내 낸다."""

    def __init__(self, finance: dict | None = None, own: bool = True) -> None:
        self.own = own
        self.tables: dict[str, list[dict]] = {"store_settings": [], "store_ingredient_costs": []}
        self.finance = finance

    def owned_store(self, store_id: UUID) -> dict:
        if not self.own:
            raise DomainError("NOT_FOUND", "매장을 찾을 수 없거나 접근할 수 없습니다.")
        return {"id": str(store_id)}

    def request(self, method: str, table: str, params: dict | None = None, data: dict | None = None) -> list[dict]:
        if table == "startup_plans":
            if self.finance is None:
                return []
            return [{"store_id": str(STORE), "revision": str(uuid4()), "input": self.finance,
                     "created_at": "2026-11-01T00:00:00+00:00", "updated_at": "2026-11-01T00:00:00+00:00"}]
        rows = self.tables[table]
        if method == "GET":
            return [dict(r) for r in sorted(rows, key=lambda r: r.get("price_key", ""))]
        if method == "POST":
            rows.append(dict(data))
            return [dict(data)]
        if method == "PATCH":
            for r in rows:
                r.update(data)
            return [dict(r) for r in rows]
        if method == "DELETE":
            self.tables[table] = []
            return []
        raise AssertionError(method)


def price(key: str, name: str, latest: int, bps: int | None, status: str = "success") -> PriceSummary:
    day = DailyPrice(price_date=date(2026, 11, 6), average_price=latest, market_count=1)
    change = None if bps is None else PriceChange(base_date=date(2026, 10, 30), base_price=10_000, latest_date=day.price_date,
                                                    latest_price=latest, change_amount=latest - 10_000, change_bps=bps)
    return PriceSummary(key=key, name=name, groups=["common"], status=status, unit="1kg", latest=day, week_change=change,
                        daily=[day])


PRICES = IngredientPriceResponse(collected_at=datetime(2026, 11, 8, tzinfo=KST), status="success", items=[
    price("pork_belly", "돼지고기 삼겹살", 11_000, 1_000), price("onion", "양파", 9_500, -500), price("rice", "쌀", 10_000, 0)])


class TaxTest(unittest.TestCase):
    def test_general_individual_with_employees(self) -> None:
        events = service.tax_schedule(TaxSettings(), TODAY)
        codes = [e.code for e in events]
        self.assertEqual(codes[0], "withholding")
        self.assertEqual(events[0].due_date, date(2026, 11, 10))
        self.assertIn("income_tax_prepaid", codes)
        self.assertEqual(next(e for e in events if e.code == "vat_2nd_final").due_date, date(2027, 1, 25))
        self.assertTrue(all(e.due_date >= TODAY and e.due_date.weekday() < 5 for e in events))

    def test_variants(self) -> None:
        simple = [e.code for e in service.tax_schedule(TaxSettings(tax_type="simple", employees="no"), TODAY)]
        self.assertTrue(set(simple) <= {"vat_simple", "vat_simple_prepaid", "income_tax", "income_tax_prepaid"})
        corp = [e.code for e in service.tax_schedule(TaxSettings(business_entity="corporation", employees="no"), TODAY)]
        self.assertIn("corporate_tax", corp)
        self.assertNotIn("income_tax", corp)
        split = service.tax_schedule(TaxSettings(installments=3), TODAY)
        self.assertEqual(next(e for e in split if e.code.startswith("vat")).note, "3회 분할 납부 선택")

    def test_weekend_moves_to_monday(self) -> None:
        self.assertEqual(service.business_day(date(2026, 1, 24)), date(2026, 1, 26))
        self.assertEqual(service.business_day(date(2026, 1, 25)), date(2026, 1, 26))
        self.assertEqual(service.business_day(date(2026, 1, 23)), date(2026, 1, 23))

    def test_save_and_read(self) -> None:
        repo = FakeRepo()
        first = service.get_tax_settings(repo, STORE)
        self.assertFalse(first.saved)
        saved = service.save_tax_settings(repo, STORE, TaxSettings(tax_type="simple"))
        self.assertTrue(saved.saved)
        self.assertEqual(saved.settings.tax_type, "simple")
        service.save_tax_settings(repo, STORE, TaxSettings(tax_type="general"))
        self.assertEqual(len(repo.tables["store_settings"]), 1)

    def test_other_users_store(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            service.save_tax_settings(FakeRepo(own=False), STORE, TaxSettings())
        self.assertEqual(ctx.exception.code, "NOT_FOUND")

    def test_invalid_saved_value(self) -> None:
        repo = FakeRepo()
        repo.tables["store_settings"].append({"store_id": str(STORE), "tax": {"tax_type": "x"}, "preferences": {}})
        with self.assertRaises(DomainError) as ctx:
            service.get_tax_settings(repo, STORE)
        self.assertEqual(ctx.exception.code, "SAVED_INPUT_INVALID")


class PreferencesTest(unittest.TestCase):
    def test_defaults_and_columns_kept_separate(self) -> None:
        repo = FakeRepo()
        self.assertEqual(service.get_preferences(repo, STORE).preferences, Preferences())
        service.save_tax_settings(repo, STORE, TaxSettings(tax_type="simple"))
        service.save_preferences(repo, STORE, Preferences(runway_alert=False, font_size="large"))
        row = repo.tables["store_settings"][0]
        self.assertEqual((row["tax"]["tax_type"], row["preferences"]["runway_alert"]), ("simple", False))


class IngredientCostTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(service, "latest_prices", lambda query: PRICES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_impact_and_gap(self) -> None:
        repo = FakeRepo(FINANCE_INPUT)
        res = service.save_ingredient_costs(repo, STORE, IngredientCostSave(items=[
            {"price_key": "pork_belly", "unit_price": 12_100, "monthly_amount": 1_200_000},
            {"price_key": "onion", "monthly_amount": 300_000}, {"price_key": "rice"}]))
        items = {i.price_key: i for i in res.items}
        self.assertEqual(items["pork_belly"].monthly_impact, 120_000)
        self.assertEqual(items["pork_belly"].unit_price_gap_bps, 1_000)
        self.assertEqual(items["onion"].monthly_impact, -15_000)
        self.assertIsNone(items["rice"].monthly_impact)
        self.assertEqual((res.total_monthly_amount, res.total_monthly_impact), (1_500_000, 105_000))
        impact = res.runway_impact
        self.assertEqual(impact.monthly_cost_increase, 105_000)
        self.assertLessEqual(impact.adjusted_available_months, impact.base_available_months)

    def test_replace_all_and_unknown_key(self) -> None:
        repo = FakeRepo()
        service.save_ingredient_costs(repo, STORE, IngredientCostSave(items=[{"price_key": "pork_belly"}, {"price_key": "onion"}]))
        res = service.save_ingredient_costs(repo, STORE, IngredientCostSave(items=[{"price_key": "rice"}]))
        self.assertEqual([i.price_key for i in res.items], ["rice"])
        self.assertIsNone(res.runway_impact)
        with self.assertRaises(DomainError) as ctx:
            service.save_ingredient_costs(repo, STORE, IngredientCostSave(items=[{"price_key": "olive_oil"}]))
        self.assertEqual(ctx.exception.code, "UNKNOWN_INGREDIENT")

    def test_duplicate_and_zero_rejected(self) -> None:
        for items in ([{"price_key": "rice"}, {"price_key": "rice"}], [{"price_key": "rice", "unit_price": 0}]):
            with self.assertRaises(ValueError):
                IngredientCostSave(items=items)

    def test_shift_keeps_original(self) -> None:
        from app.schemas.analyses import AnalysisInput
        data = AnalysisInput.model_validate({**FINANCE_INPUT, "ingredient_items": [{"name": "a", "amount": 2_000_000}],
                                             "monthly_overrides": [{"month": 2, "ingredient_cost": 100}]})
        shifted = service.shift_ingredient_cost(data, -500)
        self.assertEqual((shifted.monthly_ingredient_cost, shifted.monthly_overrides[0].ingredient_cost), (1_999_500, 0))
        self.assertEqual(data.monthly_ingredient_cost, 2_000_000)


class NotificationTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(service, "latest_prices", lambda query: PRICES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_builds_all_kinds(self) -> None:
        repo = FakeRepo(FINANCE_INPUT)
        service.save_tax_settings(repo, STORE, TaxSettings())
        res = service.get_notifications(repo, STORE, today=TODAY)
        types = [n.type for n in res.notifications]
        self.assertEqual(types[0], "runway")
        self.assertEqual(res.notifications[0].severity, "critical")
        self.assertIn("ingredient", types)
        self.assertIn("돼지고기 삼겹살 +10.0%", next(n for n in res.notifications if n.type == "ingredient").message)
        self.assertEqual({n.title for n in res.notifications if n.type == "expense"},
                         {"월세 지급일이 다가와요", "에어컨 수리 지출 예정일이에요"})
        self.assertTrue(any(n.type == "tax" and n.days_left == 1 for n in res.notifications))

    def test_preferences_turn_off_alerts(self) -> None:
        repo = FakeRepo(FINANCE_INPUT)
        service.save_preferences(repo, STORE, Preferences(runway_alert=False, ingredient_alert=False))
        types = {n.type for n in service.get_notifications(repo, STORE, today=TODAY).notifications}
        self.assertEqual(types, {"expense"})

    def test_without_finance_or_settings(self) -> None:
        res = service.get_notifications(FakeRepo(), STORE, today=TODAY)
        self.assertEqual([n.type for n in res.notifications], ["ingredient"])


class WeeklyTest(unittest.TestCase):
    def test_weekly_averages_start_on_monday(self) -> None:
        days = [DailyPrice(price_date=date(2026, 11, d), average_price=p, market_count=1)
                for d, p in ((2, 100), (3, 101), (6, 104), (9, 110))]
        weeks = weekly_averages(days)
        self.assertEqual([(w.week_start, w.average_price, w.days) for w in weeks],
                         [(date(2026, 11, 2), 102, 3), (date(2026, 11, 9), 110, 1)])


class RouteTest(unittest.TestCase):
    def setUp(self) -> None:
        ingredient_prices.clear_cache()
        self.addCleanup(ingredient_prices.clear_cache)

    def test_routes_require_login(self) -> None:
        with patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"}), TestClient(app) as http:
            for path in ("tax-settings", "preferences", "ingredient-costs", "notifications"):
                self.assertEqual(http.get(f"/api/v1/stores/{STORE}/{path}").status_code, 401, path)
        with self.assertRaises(ValueError):
            TaxSettings(tax_type="x")

    def test_routes_registered(self) -> None:
        paths = app.openapi()["paths"]
        for path in ("tax-settings", "preferences", "ingredient-costs"):
            self.assertEqual(set(paths[f"/api/v1/stores/{{store_id}}/{path}"]), {"get", "put"})
        self.assertEqual(set(paths["/api/v1/stores/{store_id}/notifications"]), {"get"})


if __name__ == "__main__":
    unittest.main()
