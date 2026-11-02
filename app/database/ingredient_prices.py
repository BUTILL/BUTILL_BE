import base64
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import httpx

from app.database.persistence import connection_settings
from app.errors import DomainError
from app.schemas.ingredient_prices import PriceItem

REST_PATH = "/rest/v1/"
PAGE_SIZE = 1000
MAX_PAGES = 50
WRITE_CHUNK = 500
PRICE_COLUMNS = ("ingredient_id,price_date,kind_code,kind_name,rank_code,rank_name,unit,"
                 "market_code,market_name,price,price_per_kg")
RUN_COLUMNS = ("source,started_at,finished_at,status,success_count,failure_count,saved_count,"
               "error_code,item_results")
PRICE_CONFLICT = "ingredient_id,price_date,kind_code,rank_code,market_code"


def writer_settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url.startswith("https://") or not key:
        raise DomainError("CONFIG_REQUIRED", "가격 수집 작업에 필요한 Supabase 주소와 서버 작업용 키 설정이 없습니다.")
    if key.startswith("sb_secret_"):
        return url, key
    try:
        body = key.split(".")[1]
        if json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))["role"] == "service_role":
            return url, key
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    raise DomainError("CONFIG_REQUIRED", "가격 수집 작업에는 서버 작업용 키를 사용해야 합니다.")


def auth_headers(key: str) -> dict[str, str]:
    return {"apikey": key} if key.startswith("sb_") else {"apikey": key, "Authorization": "Bearer " + key}


class PriceRepository:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def send(self, method: str, table: str, params: dict | None = None, data: list | dict | None = None,
             prefer: str | None = None) -> httpx.Response:
        try:
            res = self.http.request(method, REST_PATH + table, params=params, json=data,
                                    headers={"Prefer": prefer} if prefer else None)
        except httpx.HTTPError:
            raise DomainError("DB_UNAVAILABLE", "가격 데이터 서버에 연결할 수 없습니다.") from None
        if res.status_code >= 400:
            raise DomainError("DB_UNAVAILABLE", "가격 데이터를 처리할 수 없습니다.")
        return res

    def rows(self, res: httpx.Response) -> list[dict]:
        try:
            rows = res.json()
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError
        except ValueError:
            raise DomainError("DB_UNAVAILABLE", "가격 데이터 응답 형식을 확인할 수 없습니다.") from None
        return rows

    def read_all(self, table: str, params: dict) -> list[dict]:
        result = []
        for _ in range(MAX_PAGES):
            page = self.rows(self.send("GET", table, params | {"limit": str(PAGE_SIZE), "offset": str(len(result))}))
            if not page:
                return result
            result.extend(page)
        raise DomainError("DB_UNAVAILABLE", "가격 데이터가 조회 한도를 넘었습니다. 기간을 줄여 주세요.")

    def ingredient_ids(self, keys: list[str]) -> dict[str, str]:
        rows = self.read_all("ingredients", {"select": "id,key", "key": "in.(" + ",".join(keys) + ")", "order": "key.asc"})
        try:
            return {r["key"]: r["id"] for r in rows}
        except KeyError:
            raise DomainError("DB_UNAVAILABLE", "가격 데이터 응답 형식을 확인할 수 없습니다.") from None

    def prices(self, ingredient_ids: list[str], start: date, end: date) -> list[dict]:
        return self.read_all("ingredient_prices", {
            "select": PRICE_COLUMNS, "ingredient_id": "in.(" + ",".join(ingredient_ids) + ")",
            "and": f"(price_date.gte.{start.isoformat()},price_date.lte.{end.isoformat()})",
            "order": "price_date.asc,id.asc",
        })

    def latest_run(self) -> dict | None:
        rows = self.rows(self.send("GET", "price_collection_runs",
                                   {"select": RUN_COLUMNS, "order": "started_at.desc", "limit": "1"}))
        return rows[0] if rows else None

    def last_success_at(self) -> str | None:
        rows = self.rows(self.send("GET", "price_collection_runs", {
            "select": "finished_at", "status": "in.(success,partial)", "order": "started_at.desc", "limit": "1"}))
        return rows[0].get("finished_at") if rows else None

    def save_ingredients(self, items: list[PriceItem]) -> dict[str, str]:
        data = [{"key": i.key, "name": i.name, "groups": i.groups, "category_code": i.category_code,
                 "item_code": i.item_code, "kind_code": i.kind_code, "rank_code": i.rank_code,
                 "product_class": i.product_class, "region_code": i.region_code} for i in items]
        rows = self.rows(self.send("POST", "ingredients", {"on_conflict": "key"}, data,
                                   "resolution=merge-duplicates,return=representation"))
        try:
            return {r["key"]: r["id"] for r in rows}
        except KeyError:
            raise DomainError("DB_UNAVAILABLE", "가격 데이터 응답 형식을 확인할 수 없습니다.") from None

    def save_prices(self, rows: list[dict]) -> int:
        for start in range(0, len(rows), WRITE_CHUNK):
            self.send("POST", "ingredient_prices", {"on_conflict": PRICE_CONFLICT}, rows[start:start + WRITE_CHUNK],
                      "resolution=merge-duplicates,return=minimal")
        return len(rows)

    def save_run(self, run: dict) -> None:
        self.send("POST", "price_collection_runs", None, run, "return=minimal")


@contextmanager
def open_price_client(url: str, key: str) -> Iterator[PriceRepository]:
    with httpx.Client(base_url=url, headers=auth_headers(key), timeout=httpx.Timeout(10, connect=5),
                      follow_redirects=False) as http:
        yield PriceRepository(http)


@contextmanager
def open_price_reader() -> Iterator[PriceRepository]:
    with open_price_client(*connection_settings()) as repo:
        yield repo


@contextmanager
def open_price_writer() -> Iterator[PriceRepository]:
    with open_price_client(*writer_settings()) as repo:
        yield repo
