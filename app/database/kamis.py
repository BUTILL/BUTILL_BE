import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import httpx

from app.errors import DomainError
from app.schemas.ingredient_prices import PriceItem

KAMIS_URL = "https://apis.data.go.kr/B552845/perDay"
KAMIS_PATH = "/price"
PAGE_SIZE = 1000
MAX_PAGES = 10
RETRY_COUNT = 1
REJECTED_CODES = frozenset({"20", "30", "31", "32", "33"})


def kamis_settings() -> str:
    key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key:
        raise DomainError("CONFIG_REQUIRED", "원재료 가격 수집에 필요한 공공데이터포털 인증키 설정이 없습니다.")
    return key


def gateway_error(res: httpx.Response) -> DomainError:
    found = re.search(r"<returnReasonCode>\s*(\d+)\s*</returnReasonCode>", res.text)
    if found and found.group(1) in REJECTED_CODES:
        return DomainError("PRICE_SOURCE_REJECTED", "공공데이터포털 인증키 또는 활용신청 상태를 확인하세요.")
    return DomainError("PRICE_SOURCE_UNAVAILABLE", "원재료 가격 서버 응답을 확인할 수 없습니다.")


class KamisClient:
    def __init__(self, http: httpx.Client, key: str) -> None:
        self.http = http
        self.key = key

    def page(self, item: PriceItem, start: date, end: date, page_no: int) -> tuple[int, list[dict]]:
        params = {
            "serviceKey": self.key, "returnType": "json", "pageNo": str(page_no), "numOfRows": str(PAGE_SIZE),
            "cond[exmn_ymd::GTE]": start.strftime("%Y%m%d"), "cond[exmn_ymd::LTE]": end.strftime("%Y%m%d"),
            "cond[se_cd::EQ]": item.product_class, "cond[sgg_cd::EQ]": item.region_code,
            "cond[ctgry_cd::EQ]": item.category_code, "cond[item_cd::EQ]": item.item_code,
        }
        if item.kind_code:
            params["cond[vrty_cd::EQ]"] = item.kind_code
        if item.rank_code:
            params["cond[grd_cd::EQ]"] = item.rank_code
        for attempt in range(RETRY_COUNT + 1):
            try:
                res = self.http.get(KAMIS_PATH, params=params)
            except httpx.TransportError:
                if attempt < RETRY_COUNT:
                    continue
                raise DomainError("PRICE_SOURCE_UNAVAILABLE", "원재료 가격 서버에 연결할 수 없습니다.") from None
            if res.status_code >= 500 and attempt < RETRY_COUNT:
                continue
            break
        if res.status_code != 200:
            raise DomainError("PRICE_SOURCE_UNAVAILABLE", "원재료 가격 서버 응답을 확인할 수 없습니다.")
        try:
            payload = res.json()
            response = payload["response"]
            code = str(response["header"]["resultCode"])
        except (ValueError, KeyError, TypeError):
            raise gateway_error(res) from None
        if code not in ("0", "00"):
            raise DomainError("PRICE_SOURCE_UNAVAILABLE", "원재료 가격 서버가 요청을 처리하지 못했습니다.")
        body = response.get("body") or {}
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            raise DomainError("PRICE_SOURCE_INVALID", "원재료 가격 응답 형식을 확인할 수 없습니다.")
        try:
            total = int(body.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = 0
        return total, items

    def daily_prices(self, item: PriceItem, start: date, end: date) -> list:
        rows = []
        for page_no in range(1, MAX_PAGES + 1):
            total, items = self.page(item, start, end, page_no)
            rows.extend(items)
            if not items or page_no * PAGE_SIZE >= total:
                break
        return rows


@contextmanager
def open_kamis_client() -> Iterator[KamisClient]:
    key = kamis_settings()
    with httpx.Client(base_url=KAMIS_URL, timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as http:
        yield KamisClient(http, key)
