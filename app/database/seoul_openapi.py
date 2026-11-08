import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import quote

import httpx

from app.errors import DomainError

SEOUL_URL = "http://openapi.seoul.go.kr:8088"
PAGE_SIZE = 1000
MAX_ROWS = 5000
RETRY_COUNT = 1
SUCCESS_CODE = "INFO-000"
NO_DATA_CODE = "INFO-200"
INVALID_KEY_CODE = "INFO-100"


def seoul_settings() -> str:
    key = os.getenv("SEOUL_OPENAPI_KEY", "").strip()
    if not key:
        raise DomainError("CONFIG_REQUIRED", "서울 열린데이터광장 인증키 설정이 없습니다.")
    return key


def result_code(res: httpx.Response, service: str) -> tuple[str, dict]:
    try:
        payload = res.json()
    except ValueError:
        found = re.search(r"<CODE>\s*([A-Z]+-\d+)\s*</CODE>", res.text)
        return (found.group(1) if found else "", {})
    if not isinstance(payload, dict):
        return "", {}
    body = payload.get(service, payload)
    if not isinstance(body, dict):
        return "", {}
    result = body.get("RESULT")
    code = str(result.get("CODE", "")) if isinstance(result, dict) else ""
    return code, body


class SeoulOpenApiClient:
    def __init__(self, http: httpx.Client, key: str) -> None:
        self.http = http
        self.key = key

    def page(self, service: str, start: int, end: int) -> tuple[int, list[dict]]:
        if not re.fullmatch(r"[A-Za-z0-9_]+", service) or not 1 <= start <= end or end - start >= PAGE_SIZE:
            raise DomainError("INVALID_REQUEST", "서울 열린데이터광장 조회 조건을 확인하세요.")
        path = f"/{quote(self.key, safe='')}/json/{service}/{start}/{end}/"
        for attempt in range(RETRY_COUNT + 1):
            try:
                res = self.http.get(path)
            except httpx.TransportError:
                if attempt < RETRY_COUNT:
                    continue
                raise DomainError("EXTERNAL_SOURCE_UNAVAILABLE", "서울 열린데이터광장에 연결할 수 없습니다.") from None
            if res.status_code >= 500 and attempt < RETRY_COUNT:
                continue
            break
        if res.status_code != 200:
            raise DomainError("EXTERNAL_SOURCE_UNAVAILABLE", "서울 열린데이터광장 응답을 확인할 수 없습니다.")
        code, body = result_code(res, service)
        if code == NO_DATA_CODE:
            return 0, []
        if code == INVALID_KEY_CODE:
            raise DomainError("EXTERNAL_SOURCE_REJECTED", "서울 열린데이터광장 인증키를 확인하세요.")
        if code != SUCCESS_CODE:
            raise DomainError("EXTERNAL_SOURCE_UNAVAILABLE", "서울 열린데이터광장 데이터를 받을 수 없습니다.")
        rows = body.get("row", [])
        try:
            total = int(body.get("list_total_count", 0))
        except (TypeError, ValueError):
            total = 0
        if not isinstance(rows, list):
            raise DomainError("EXTERNAL_SOURCE_INVALID", "서울 열린데이터광장 응답 형식을 확인할 수 없습니다.")
        return total, [r for r in rows if isinstance(r, dict)]

    def rows(self, service: str, limit: int = MAX_ROWS) -> list[dict]:
        result = []
        start = 1
        while start <= limit:
            total, rows = self.page(service, start, min(start + PAGE_SIZE - 1, limit))
            result.extend(rows)
            if not rows or start + PAGE_SIZE > min(total, limit):
                break
            start += PAGE_SIZE
        return result


@contextmanager
def open_seoul_client() -> Iterator[SeoulOpenApiClient]:
    key = seoul_settings()
    with httpx.Client(base_url=SEOUL_URL, timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as http:
        yield SeoulOpenApiClient(http, key)
