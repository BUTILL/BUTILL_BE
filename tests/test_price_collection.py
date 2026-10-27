import os
import unittest
from datetime import date, datetime
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.database.kamis import KAMIS_PATH, KamisClient, kamis_settings
from app.errors import DomainError
from app.main import app
from app.schemas.ingredient_prices import CollectionResult, DailyPrice, ItemCollection, PriceItem
from app.services import ingredient_prices
from app.services.ingredient_prices import daily_averages, main_series, price_change, summarize
from app.services.price_collection import KST, collect_prices, parse_day, parse_items, parse_price
from app.services.price_items import PRICE_ITEMS

RICE = PriceItem(key="rice", name="쌀", groups=["common"], category_code="100", item_code="111", kind_code="01", rank_code="04")
CABBAGE = PriceItem(key="napa_cabbage", name="배추", groups=["common"], category_code="200", item_code="211", rank_code="04")
EGG = PriceItem(key="egg", name="계란", groups=["common"], category_code="500", item_code="9903", kind_code="23", rank_code="1")
SECRET = "secret/key+value"
GATEWAY_ERROR = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
                 "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")


def row(day: str, price: str, market: str | None = "0110212", item: str = "111", kind: str = "01", rank: str = "04",
        unit: str = "kg", size: str = "20", per_kg: str = "3165") -> dict:
    return {"exmn_ymd": day, "se_cd": "01", "ctgry_cd": "100", "item_cd": item, "item_nm": "쌀", "vrty_cd": kind,
            "vrty_nm": "20kg", "grd_cd": rank, "grd_nm": "상품", "sgg_cd": "1101", "sgg_nm": "서울", "unit": unit,
            "unit_sz": size, "mrkt_cd": market, "mrkt_nm": "경동" if market else None, "exmn_dd_prc": price,
            "exmn_dd_cnvs_prc": per_kg, "orgnl_reg_dt": "2026-10-19T16:16:39Z"}


def page(rows: list[dict], total: int | None = None) -> dict:
    return {"response": {"header": {"resultCode": "0", "resultMsg": "정상"},
                         "body": {"dataType": "JSON", "items": {"item": rows}, "numOfRows": 1000, "pageNo": 1,
                                  "totalCount": len(rows) if total is None else total}}}


def client(handler) -> KamisClient:
    http = httpx.Client(base_url="https://kamis.test/B552845/perDay", transport=httpx.MockTransport(handler))
    return KamisClient(http, SECRET)


class PriceParsingTest(unittest.TestCase):
    def test_price_values(self) -> None:
        self.assertEqual(parse_price("63300"), 63300)
        self.assertEqual(parse_price("36,600"), 36600)
        self.assertEqual(parse_price("1234.5"), 1235)
        for missing in ("-", "", " ", None, "0", "-100", "abc", "NaN"):
            self.assertIsNone(parse_price(missing), missing)

    def test_day_values(self) -> None:
        self.assertEqual(parse_day("20261019"), date(2026, 10, 19))
        for value in ("2026-10-19", "20261340", None, ""):
            self.assertIsNone(parse_day(value))

    def test_rows(self) -> None:
        rows = [row("20261020", "62900"), row("20261019", "63300"), row("20261019", "63300"), row("20261021", "-"),
                row("bad", "1"), row("20261019", "1", item="999"), "broken", row("20261019", "62900", market="0110403")]
        result = parse_items(RICE, rows)
        self.assertEqual(result.status, "success")
        self.assertEqual([(o.price_date.day, o.market_code, o.price) for o in result.observations],
                         [(19, "0110212", 63300), (19, "0110403", 62900), (20, "0110212", 62900)])
        self.assertEqual((result.missing_count, result.duplicate_count, result.invalid_count), (1, 1, 3))
        self.assertEqual(result.observations[0].unit, "20kg")
        self.assertEqual(result.observations[0].price_per_kg, 3165)

    def test_region_level_rows_without_market(self) -> None:
        result = parse_items(EGG, [row("20261019", "6158", market=None, item="9903", kind="23", rank="1", unit="구", size="30")])
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0].market_code, "-")
        self.assertIsNone(result.observations[0].price_per_kg)

    def test_missing_prices_are_not_zero(self) -> None:
        result = parse_items(RICE, [row("20261019", "-"), row("20261020", "")])
        self.assertEqual((result.status, result.observations, result.missing_count), ("success", [], 2))
        self.assertEqual(parse_items(RICE, []).status, "no_data")


class KamisClientTest(unittest.TestCase):
    def test_request_parameters(self) -> None:
        seen = []

        def handler(req: httpx.Request) -> httpx.Response:
            seen.append((req.url.path, dict(req.url.params)))
            return httpx.Response(200, json=page([row("20261019", "63300")]))

        client(handler).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7))
        path, params = seen[0]
        self.assertTrue(path.endswith("/perDay" + KAMIS_PATH))
        self.assertEqual(params, {
            "serviceKey": SECRET, "returnType": "json", "pageNo": "1", "numOfRows": "1000",
            "cond[exmn_ymd::GTE]": "20261001", "cond[exmn_ymd::LTE]": "20261007", "cond[se_cd::EQ]": "01",
            "cond[sgg_cd::EQ]": "1101", "cond[ctgry_cd::EQ]": "100", "cond[item_cd::EQ]": "111",
            "cond[vrty_cd::EQ]": "01", "cond[grd_cd::EQ]": "04",
        })
        client(handler).daily_prices(CABBAGE, date(2026, 10, 1), date(2026, 10, 7))
        self.assertNotIn("cond[vrty_cd::EQ]", seen[1][1])

    def test_pagination(self) -> None:
        pages = []

        def handler(req: httpx.Request) -> httpx.Response:
            pages.append(req.url.params["pageNo"])
            return httpx.Response(200, json=page([row("20261019", "1", market=req.url.params["pageNo"])], total=2500))

        rows = client(handler).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual((pages, len(rows)), (["1", "2", "3"], 3))

    def test_item_shapes(self) -> None:
        single = page([])
        single["response"]["body"]["items"] = {"item": row("20261019", "1")}
        empty = page([])
        empty["response"]["body"]["items"] = ""
        self.assertEqual(len(client(lambda req: httpx.Response(200, json=single)).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7))), 1)
        self.assertEqual(client(lambda req: httpx.Response(200, json=empty)).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7)), [])

    def test_errors_hide_key(self) -> None:
        bad_code = page([])
        bad_code["response"]["header"]["resultCode"] = "99"
        cases = [(httpx.Response(200, text=GATEWAY_ERROR), "PRICE_SOURCE_REJECTED"),
                 (httpx.Response(200, text="<xml/>"), "PRICE_SOURCE_UNAVAILABLE"),
                 (httpx.Response(200, json=bad_code), "PRICE_SOURCE_UNAVAILABLE"),
                 (httpx.Response(404), "PRICE_SOURCE_UNAVAILABLE")]
        for res, code in cases:
            with self.assertRaises(DomainError) as ctx:
                client(lambda req, res=res: res).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7))
            self.assertEqual(ctx.exception.code, code)
            self.assertNotIn(SECRET, ctx.exception.message)

    def test_retry_once(self) -> None:
        calls = []

        def down(req: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError(str(req.url))

        with self.assertRaises(DomainError) as ctx:
            client(down).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual((len(calls), ctx.exception.code), (2, "PRICE_SOURCE_UNAVAILABLE"))
        self.assertIsNone(ctx.exception.__cause__)
        responses = [httpx.Response(502), httpx.Response(200, json=page([row("20261019", "1")]))]
        self.assertEqual(len(client(lambda req: responses.pop(0)).daily_prices(RICE, date(2026, 10, 1), date(2026, 10, 7))), 1)

    def test_settings(self) -> None:
        with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": ""}):
            with self.assertRaises(DomainError) as ctx:
                kamis_settings()
            self.assertEqual(ctx.exception.code, "CONFIG_REQUIRED")
        with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": " key "}):
            self.assertEqual(kamis_settings(), "key")


class CollectPricesTest(unittest.TestCase):
    def test_partial_failure_keeps_order_and_other_items(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.url.params["cond[item_cd::EQ]"] == "211":
                return httpx.Response(200, text=GATEWAY_ERROR)
            return httpx.Response(200, json=page([row("20261019", "63300")]))

        result = collect_prices(client(handler), [RICE, CABBAGE, RICE], date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual((result.status, result.success_count, result.failure_count), ("partial", 2, 1))
        self.assertEqual([i.item.key for i in result.items], ["rice", "napa_cabbage", "rice"])
        self.assertEqual(result.items[1].error_code, "PRICE_SOURCE_REJECTED")
        self.assertEqual(result.started_at.utcoffset().total_seconds(), 9 * 3600)

    def test_period_limit(self) -> None:
        never = client(lambda req: self.fail("기간 오류는 호출 전에 막아야 합니다."))
        for start, end in ((date(2026, 10, 8), date(2026, 10, 7)), (date(2025, 10, 1), date(2026, 10, 2))):
            with self.assertRaises(DomainError) as ctx:
                collect_prices(never, [RICE], start, end)
            self.assertEqual(ctx.exception.code, "INVALID_PERIOD")


class SummaryTest(unittest.TestCase):
    def collected(self, rows: list[dict], item: PriceItem = CABBAGE) -> ItemCollection:
        return parse_items(item, rows)

    def test_daily_average_and_week_change(self) -> None:
        rows = [row("20261019", "4000", item="211", kind="02"), row("20261019", "5000", item="211", kind="02", market="2"),
                row("20261023", "4400", item="211", kind="02"), row("20261026", "4300", item="211", kind="02"),
                row("20261026", "4400", item="211", kind="02", market="2")]
        summary = summarize(self.collected(rows))
        self.assertEqual(summary.latest, DailyPrice(price_date=date(2026, 10, 26), average_price=4350,
                                                    average_price_per_kg=3165, market_count=2))
        self.assertEqual((summary.week_change.base_date, summary.week_change.base_price), (date(2026, 10, 19), 4500))
        self.assertEqual((summary.week_change.change_amount, summary.week_change.change_bps), (-150, -333))
        self.assertEqual(len(summary.daily), 3)

    def test_main_series_follows_latest_season_variety(self) -> None:
        rows = [row("20261019", "3000", item="211", kind="01"), row("20261026", "9000", item="211", kind="01"),
                row("20261026", "4000", item="211", kind="02"), row("20261026", "4200", item="211", kind="02", market="2")]
        series = main_series(self.collected(rows).observations)
        self.assertEqual({o.kind_code for o in series}, {"02"})
        summary = summarize(self.collected(rows))
        self.assertEqual(summary.latest.average_price, 4100)
        self.assertIsNone(summary.week_change)

    def test_no_data_and_failed(self) -> None:
        self.assertEqual(summarize(self.collected([])).status, "no_data")
        failed = ItemCollection(item=RICE, status="failed", error_code="X", observations=[])
        self.assertEqual((summarize(failed).status, summarize(failed).latest), ("failed", None))

    def test_price_change_guards(self) -> None:
        day = DailyPrice(price_date=date(2026, 10, 19), average_price=3, market_count=1)
        later = DailyPrice(price_date=date(2026, 10, 26), average_price=2, market_count=1)
        self.assertEqual(price_change(day, later).change_bps, -3333)
        self.assertIsNone(price_change(later, day))
        self.assertEqual(daily_averages([]), [])


class CatalogTest(unittest.TestCase):
    def test_catalog(self) -> None:
        keys = [i.key for i in PRICE_ITEMS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual({g for i in PRICE_ITEMS for g in i.groups}, {"common", "dakgalbi", "pasta"})
        self.assertTrue(all(i.product_class == "01" and i.region_code == "1101" for i in PRICE_ITEMS))


class IngredientPriceRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        ingredient_prices.clear_cache()
        self.addCleanup(ingredient_prices.clear_cache)

    def fake(self, status: str = "success"):
        calls = []

        def fetch(today: date) -> CollectionResult:
            calls.append(today)
            items = [parse_items(RICE, [row("20261026", "62900")]), parse_items(CABBAGE, [])]
            now = datetime.now(KST)
            return CollectionResult(started_at=now, finished_at=now, status=status, success_count=2, failure_count=0, items=items)

        return fetch, calls

    def test_route_caches_and_filters(self) -> None:
        fetch, calls = self.fake()
        with patch.object(ingredient_prices, "fetch_latest", fetch), \
                patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"}), TestClient(app) as http:
            first = http.get("/api/v1/ingredient-prices")
            second = http.get("/api/v1/ingredient-prices?group=dakgalbi")
            bad = http.get("/api/v1/ingredient-prices?group=x")
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual([i["key"] for i in body["items"]], ["rice", "napa_cabbage"])
        self.assertEqual(body["items"][0]["latest"]["average_price"], 62900)
        self.assertEqual(body["items"][1]["status"], "no_data")
        self.assertEqual(second.json()["items"], [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(bad.status_code, 422)

    def test_route_without_key(self) -> None:
        with patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1", "DATA_GO_KR_SERVICE_KEY": ""}), TestClient(app) as http:
            res = http.get("/api/v1/ingredient-prices")
        self.assertEqual((res.status_code, res.json()["code"]), (503, "CONFIG_REQUIRED"))


if __name__ == "__main__":
    unittest.main()
