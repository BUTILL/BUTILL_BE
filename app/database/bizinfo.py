import os
from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from app.errors import DomainError

BIZINFO_URL = "https://www.bizinfo.go.kr/uss/rss"
BIZINFO_PATH = "/bizinfoApi.do"
RETRY_COUNT = 1


def bizinfo_settings() -> str:
    key = os.getenv("BIZINFO_API_KEY", "").strip()
    if not key:
        raise DomainError("CONFIG_REQUIRED", "지원사업 정보 수집에 필요한 기업마당 인증키 설정이 없습니다.")
    return key


class BizinfoClient:
    def __init__(self, http: httpx.Client, key: str) -> None:
        self.http = http
        self.key = key

    def programs(self, hashtags: list[str], category: str | None = None, count: int = 0) -> list[dict]:
        params = {"crtfcKey": self.key, "dataType": "json", "searchCnt": str(count)}
        if hashtags:
            params["hashtags"] = ",".join(hashtags)
        if category:
            params["searchLclasId"] = category
        for attempt in range(RETRY_COUNT + 1):
            try:
                res = self.http.get(BIZINFO_PATH, params=params)
            except httpx.TransportError:
                if attempt < RETRY_COUNT:
                    continue
                raise DomainError("SUPPORT_SOURCE_UNAVAILABLE", "지원사업 정보 서버에 연결할 수 없습니다.") from None
            if res.status_code >= 500 and attempt < RETRY_COUNT:
                continue
            break
        if res.status_code != 200:
            raise DomainError("SUPPORT_SOURCE_UNAVAILABLE", "지원사업 정보 서버 응답을 확인할 수 없습니다.")
        try:
            payload = res.json()
            if not isinstance(payload, dict):
                raise ValueError
        except ValueError:
            raise DomainError("SUPPORT_SOURCE_INVALID", "지원사업 정보 응답 형식을 확인할 수 없습니다.") from None
        if payload.get("reqErr"):
            raise DomainError("SUPPORT_SOURCE_REJECTED", "기업마당이 요청을 거부했습니다. 인증키와 조회 조건을 확인하세요.")
        rows = payload.get("jsonArray", [])
        if isinstance(rows, dict):
            rows = rows.get("item", [])
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise DomainError("SUPPORT_SOURCE_INVALID", "지원사업 정보 응답 형식을 확인할 수 없습니다.")
        return [r for r in rows if isinstance(r, dict)]


@contextmanager
def open_bizinfo_client() -> Iterator[BizinfoClient]:
    key = bizinfo_settings()
    with httpx.Client(base_url=BIZINFO_URL, timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as http:
        yield BizinfoClient(http, key)
