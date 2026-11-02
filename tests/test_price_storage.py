import base64
import contextlib
import io
import json
import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.database.ingredient_prices import PriceRepository, auth_headers, writer_settings
from app.database.kamis import KamisClient
from app.errors import DomainError
from app.jobs import collect_prices as job
from app.main import app
from app.schemas.ingredient_prices import PriceFilter, PriceItem
from app.services import ingredient_prices
from app.services.ingredient_prices import latest_prices, read_response
from app.services.price_collection import KST, run_collection

RICE = PriceItem(key="rice", name="쌀", groups=["common"], category_code="100", item_code="111", kind_code="01", rank_code="04")
ONION = PriceItem(key="onion", name="양파", groups=["common"], category_code="200", item_code="245", kind_code="00", rank_code="04")
TODAY = date(2026, 11, 2)
RICE_ID = "11111111-1111-1111-1111-111111111111"
ONION_ID = "22222222-2222-2222-2222-222222222222"
NOW = "2026-11-02T09:00:00+09:00"
SECRET = "sb_secret_value"


def stored(day: str, price: int, ingredient: str = RICE_ID, kind: str = "01", unit: str = "20kg") -> dict:
    return {"ingredient_id": ingredient, "price_date": day, "kind_code": kind, "kind_name": "20kg", "rank_code": "04",
            "rank_name": "상품", "unit": unit, "market_code": "-", "market_name": None, "price": price, "price_per_kg": None}


def run_row(status: str = "success", results: list[dict] | None = None) -> dict:
    return {"source": "KAMIS", "started_at": NOW, "finished_at": NOW, "status": status, "success_count": 1,
            "failure_count": 0, "saved_count": 2, "error_code": None, "item_results": results or []}


class FakeDb:
    def __init__(self, run: dict | None = None, prices: list[dict] | None = None, down: bool = False) -> None:
        self.run, self.prices, self.down = run, prices or [], down
        self.posts: list[tuple[str, dict, object, str]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(500, text="secret stack")
        table = req.url.path.rsplit("/", 1)[-1]
        if req.method == "POST":
            body = json.loads(req.content)
            self.posts.append((table, dict(req.url.params), body, req.headers.get("prefer", "")))
            if table == "ingredients":
                return httpx.Response(201, json=[{"id": RICE_ID if r["key"] == "rice" else ONION_ID, "key": r["key"]} for r in body])
            return httpx.Response(201)
        if table == "price_collection_runs":
            return httpx.Response(200, json=[self.run] if self.run else [])
        offset = int(req.url.params.get("offset", "0"))
        if table == "ingredients":
            return httpx.Response(200, json=[] if offset else [{"id": RICE_ID, "key": "rice"}, {"id": ONION_ID, "key": "onion"}])
        return httpx.Response(200, json=self.prices[offset:offset + int(req.url.params["limit"])])

    def repo(self) -> PriceRepository:
        return PriceRepository(httpx.Client(base_url="https://db.test", transport=httpx.MockTransport(self)))


def kamis(rows_by_item: dict[str, list[dict] | None]) -> KamisClient:
    def handler(req: httpx.Request) -> httpx.Response:
        rows = rows_by_item.get(req.url.params["cond[item_cd::EQ]"])
        if rows is None:
            return httpx.Response(500)
        return httpx.Response(200, json={"response": {"header": {"resultCode": "0"},
                                                      "body": {"items": {"item": rows}, "totalCount": len(rows)}}})
    return KamisClient(httpx.Client(base_url="https://kamis.test", transport=httpx.MockTransport(handler)), "kamis-key")


def raw(day: str, price: str, item: str = "111") -> dict:
    return {"exmn_ymd": day, "item_cd": item, "vrty_cd": "01", "vrty_nm": "20kg", "grd_cd": "04", "grd_nm": "상품",
            "unit": "kg", "unit_sz": "20", "mrkt_cd": None, "exmn_dd_prc": price, "exmn_dd_cnvs_prc": "3000"}


class RunCollectionTest(unittest.TestCase):
    def test_saves_rows_and_run_without_zero_prices(self) -> None:
        db = FakeDb()
        run = run_collection(kamis({"111": [raw("20261030", "60000"), raw("20261031", "-")], "245": []}), db.repo(), [RICE, ONION], TODAY)
        self.assertEqual((run.status, run.saved_count), ("success", 1))
        tables = [p[0] for p in db.posts]
        self.assertEqual(tables, ["ingredients", "ingredient_prices", "price_collection_runs"])
        table, params, rows, prefer = db.posts[1]
        self.assertEqual(params["on_conflict"], "ingredient_id,price_date,kind_code,rank_code,market_code")
        self.assertIn("merge-duplicates", prefer)
        self.assertEqual([(r["price"], r["ingredient_id"]) for r in rows], [(60000, RICE_ID)])
        results = {r["key"]: r for r in db.posts[2][2]["item_results"]}
        self.assertEqual((results["rice"]["status"], results["rice"]["missing_count"]), ("success", 1))
        self.assertEqual(results["onion"]["status"], "no_data")

    def test_failed_item_keeps_old_rows_and_is_recorded(self) -> None:
        db = FakeDb()
        run = run_collection(kamis({"111": None, "245": [raw("20261030", "1000", "245")]}), db.repo(), [RICE, ONION], TODAY)
        self.assertEqual(run.status, "partial")
        self.assertEqual({p[2][0]["ingredient_id"] for p in db.posts if p[0] == "ingredient_prices"}, {ONION_ID})
        self.assertEqual({r["key"]: r["status"] for r in db.posts[-1][2]["item_results"]}, {"rice": "failed", "onion": "success"})

    def test_upsert_chunks(self) -> None:
        db = FakeDb()
        rows = [{"n": i} for i in range(1201)]
        self.assertEqual(db.repo().save_prices(rows), 1201)
        self.assertEqual([len(p[2]) for p in db.posts], [500, 500, 201])

    def test_write_failure_hides_response(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            FakeDb(down=True).repo().save_prices([{"n": 1}])
        self.assertEqual(ctx.exception.code, "DB_UNAVAILABLE")
        self.assertNotIn("secret stack", ctx.exception.message)


class ReadResponseTest(unittest.TestCase):
    def query(self, **kw) -> PriceFilter:
        return PriceFilter(item="rice", **kw)

    def test_no_run_is_no_data_not_zero(self) -> None:
        res = read_response(FakeDb().repo(), self.query(), TODAY)
        self.assertEqual((res.status, res.collected_at, res.items[0].status, res.items[0].latest), ("no_data", None, "no_data", None))

    def test_failed_collection_shows_last_prices_as_stale(self) -> None:
        run = run_row("failed", [{"key": "rice", "status": "failed", "error_code": "PRICE_SOURCE_UNAVAILABLE"}])
        res = read_response(FakeDb(run, [stored("2026-10-23", 59000), stored("2026-10-30", 60000)]).repo(), self.query(), TODAY)
        item = res.items[0]
        self.assertEqual((res.status, res.stale, item.status, item.stale, item.error_code),
                         ("failed", True, "failed", True, "PRICE_SOURCE_UNAVAILABLE"))
        self.assertEqual((item.latest.price_date, item.latest.average_price), (date(2026, 10, 30), 60000))
        self.assertEqual(item.week_change.change_amount, 1000)

    def test_missing_counts_are_returned(self) -> None:
        run = run_row(results=[{"key": "rice", "status": "no_data", "missing_count": 3, "duplicate_count": 1}])
        item = read_response(FakeDb(run).repo(), self.query(), TODAY).items[0]
        self.assertEqual((item.status, item.missing_count, item.duplicate_count, item.latest), ("no_data", 3, 1, None))

    def test_filters(self) -> None:
        run = run_row(results=[{"key": "rice", "status": "success"}])
        rows = [stored("2026-10-30", 60000), stored("2026-10-30", 9000, kind="02", unit="1kg")]
        res = read_response(FakeDb(run, rows).repo(), self.query(kind_code="02", unit="1kg"), TODAY)
        self.assertEqual(res.items[0].latest.average_price, 9000)
        none = read_response(FakeDb(run, rows).repo(), self.query(unit="5kg"), TODAY).items[0]
        self.assertEqual((none.status, none.latest), ("no_data", None))
        self.assertEqual(read_response(FakeDb(run).repo(), self.query(region_code="2100"), TODAY).items, [])

    def test_reads_every_page(self) -> None:
        run = run_row(results=[{"key": "rice", "status": "success"}])
        rows = [stored((date(2026, 10, 5) + timedelta(days=i % 28)).isoformat(), 100 + i) for i in range(2500)]
        repo = FakeDb(run, rows).repo()
        self.assertEqual(len(repo.prices([RICE_ID], date(2026, 10, 1), TODAY)), 2500)

    def test_period_limit(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            read_response(FakeDb(run_row()).repo(), self.query(start_date=date(2025, 1, 1)), TODAY)
        self.assertEqual(ctx.exception.code, "INVALID_PERIOD")


class CacheTest(unittest.TestCase):
    def setUp(self) -> None:
        ingredient_prices.clear_cache()
        self.addCleanup(ingredient_prices.clear_cache)
        self.query = PriceFilter(item="rice")

    def good(self):
        run = run_row(results=[{"key": "rice", "status": "success"}])
        return lambda q, today: read_response(FakeDb(run, [stored("2026-10-30", 60000)]).repo(), q, TODAY)

    def fail(self, q: PriceFilter, today: date):
        raise DomainError("DB_UNAVAILABLE", "x")

    def expire(self) -> None:
        cached = ingredient_prices._cache[self.query]
        ingredient_prices._cache[self.query] = (datetime.now(KST) - timedelta(seconds=1), cached[1])

    def test_fresh_cache_skips_db(self) -> None:
        latest_prices(self.query, self.good())
        self.assertEqual(latest_prices(self.query, self.fail).items[0].latest.average_price, 60000)

    def test_db_failure_keeps_last_good_response(self) -> None:
        latest_prices(self.query, self.good())
        self.expire()
        res = latest_prices(self.query, self.fail)
        self.assertEqual((res.stale, res.error_code, res.items[0].latest.average_price), (True, "DB_UNAVAILABLE", 60000))

    def test_db_failure_without_cache_is_failed_not_zero(self) -> None:
        res = latest_prices(self.query, self.fail)
        self.assertEqual((res.status, res.items[0].status, res.items[0].latest), ("failed", "failed", None))
        self.assertNotIn(self.query, ingredient_prices._cache)

    def test_cache_is_bounded(self) -> None:
        for day in range(1, 80):
            latest_prices(PriceFilter(item="rice", end_date=date(2026, 1, 1) + timedelta(days=day)), self.good())
        self.assertLessEqual(len(ingredient_prices._cache), ingredient_prices.MAX_CACHE_ENTRIES)


class RouteTest(unittest.TestCase):
    def setUp(self) -> None:
        ingredient_prices.clear_cache()
        self.addCleanup(ingredient_prices.clear_cache)

    def test_public_route_never_calls_kamis_or_writer(self) -> None:
        with patch("app.database.kamis.open_kamis_client", side_effect=AssertionError), \
                patch("app.database.ingredient_prices.writer_settings", side_effect=AssertionError), \
                patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1", "SUPABASE_URL": "", "SUPABASE_KEY": ""}), TestClient(app) as http:
            res = http.get("/api/v1/ingredient-prices?item=rice")
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.json()["status"], res.json()["error_code"]), ("failed", "CONFIG_REQUIRED"))

    def test_no_public_collection_route(self) -> None:
        paths = {path: set(ops) for path, ops in app.openapi()["paths"].items() if "ingredient-prices" in path}
        self.assertEqual(paths, {"/api/v1/ingredient-prices": {"get"}})

    def test_invalid_input(self) -> None:
        with patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"}), TestClient(app) as http:
            self.assertEqual(http.get("/api/v1/ingredient-prices?group=x").status_code, 422)
            self.assertEqual(http.get("/api/v1/ingredient-prices?kind_code=abc").status_code, 422)
            self.assertEqual(http.get("/api/v1/ingredient-prices?start_date=nope").status_code, 422)

    def test_reversed_period_is_422(self) -> None:
        with patch.object(ingredient_prices, "open_price_reader", lambda: contextlib.nullcontext(FakeDb(run_row()).repo())), \
                patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"}), TestClient(app) as http:
            res = http.get("/api/v1/ingredient-prices?start_date=2026-10-30&end_date=2026-10-01")
        self.assertEqual((res.status_code, res.json()["code"]), (422, "INVALID_PERIOD"))


class SettingsTest(unittest.TestCase):
    def legacy(self, role: str) -> str:
        body = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
        return f"h.{body}.s"

    def env(self, key: str, url: str = "https://db.test"):
        return patch.dict(os.environ, {"SUPABASE_URL": url, "SUPABASE_SERVICE_KEY": key})

    def test_accepts_only_server_keys(self) -> None:
        for key in (SECRET, self.legacy("service_role")):
            with self.env(key):
                self.assertEqual(writer_settings(), ("https://db.test", key))
        for key in ("", "sb_publishable_x", self.legacy("anon"), "garbage"):
            with self.env(key), self.assertRaises(DomainError) as ctx:
                writer_settings()
            self.assertEqual(ctx.exception.code, "CONFIG_REQUIRED")
        with self.env(SECRET, "http://db.test"), self.assertRaises(DomainError):
            writer_settings()

    def test_auth_headers(self) -> None:
        self.assertEqual(auth_headers("sb_secret_x"), {"apikey": "sb_secret_x"})
        self.assertEqual(auth_headers("a.b.c")["Authorization"], "Bearer a.b.c")

    def test_web_reader_rejects_server_key(self) -> None:
        with patch.dict(os.environ, {"SUPABASE_URL": "https://db.test", "SUPABASE_KEY": SECRET}), self.assertRaises(DomainError):
            with ingredient_prices.open_price_reader():
                pass


class JobTest(unittest.TestCase):
    def run_job(self, db: FakeDb, source: KamisClient) -> tuple[int, str]:
        out = io.StringIO()
        with patch.object(job, "load_dotenv"), patch.object(job, "PRICE_ITEMS", [RICE]), \
                patch.object(job, "open_kamis_client", lambda: contextlib.nullcontext(source)), \
                patch.object(job, "open_price_writer", lambda: contextlib.nullcontext(db.repo())), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            return job.main(), out.getvalue()

    def test_success(self) -> None:
        code, out = self.run_job(FakeDb(), kamis({"111": [raw("20261030", "60000")]}))
        self.assertEqual(code, 0)
        self.assertIn("저장 1건", out)

    def test_all_failed_exits_nonzero_and_hides_keys(self) -> None:
        code, out = self.run_job(FakeDb(), kamis({"111": None}))
        self.assertEqual(code, 1)
        self.assertIn("rice: failed PRICE_SOURCE_UNAVAILABLE", out)
        self.assertNotIn("kamis-key", out)

    def test_db_down_exits_nonzero(self) -> None:
        code, out = self.run_job(FakeDb(down=True), kamis({"111": [raw("20261030", "60000")]}))
        self.assertEqual(code, 1)
        self.assertIn("DB_UNAVAILABLE", out)
        self.assertNotIn("secret stack", out)

    def test_missing_config(self) -> None:
        out = io.StringIO()
        with patch.object(job, "load_dotenv"), patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": ""}), contextlib.redirect_stderr(out):
            self.assertEqual(job.main(), 1)
        self.assertIn("CONFIG_REQUIRED", out.getvalue())


if __name__ == "__main__":
    unittest.main()
