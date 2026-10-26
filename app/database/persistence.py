import base64
import json
import os
from uuid import UUID

import httpx

from app.errors import DomainError


def connection_settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url.startswith("https://") or not key:
        raise DomainError("CONFIG_REQUIRED", "Supabase HTTPS 주소와 공개용 API 키 설정이 필요합니다.")
    if key.startswith("sb_secret_"):
        raise DomainError("CONFIG_REQUIRED", "사용자 데이터 API에는 publishable 또는 anon 키를 사용해야 합니다.")
    if not key.startswith("sb_publishable_"):
        try:
            body = key.split(".")[1]
            role = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))["role"]
            if role != "anon":
                raise ValueError
        except (ValueError, KeyError, IndexError, TypeError):
            raise DomainError("CONFIG_REQUIRED", "사용자 데이터 API의 공개용 키 설정을 확인하세요.") from None
    return url, key


class SupabaseRepository:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http
        self.user_id: str | None = None

    def authenticate(self) -> str:
        try:
            res = self.http.get("/auth/v1/user")
        except httpx.HTTPError:
            raise DomainError("AUTH_UNAVAILABLE", "인증 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from None
        if res.status_code in (401, 403):
            raise DomainError("UNAUTHORIZED", "로그인이 만료되었거나 유효하지 않습니다.")
        if res.status_code != 200:
            raise DomainError("AUTH_UNAVAILABLE", "인증 서버 응답을 확인할 수 없습니다.")
        try:
            self.user_id = str(UUID(res.json()["id"]))
        except (ValueError, KeyError, TypeError):
            raise DomainError("AUTH_UNAVAILABLE", "사용자 정보를 확인할 수 없습니다.") from None
        return self.user_id

    def request(self, method: str, table: str, params: dict | None = None, data: dict | None = None) -> list[dict]:
        if self.user_id is None:
            raise DomainError("UNAUTHORIZED", "사용자 인증이 필요합니다.")
        try:
            res = self.http.request(method, "/rest/v1/" + table, params=params, json=data,
                                    headers={"Prefer": "return=representation"})
        except httpx.HTTPError:
            raise DomainError("DB_UNAVAILABLE", "데이터 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from None
        if res.status_code == 401:
            raise DomainError("UNAUTHORIZED", "로그인이 만료되었습니다. 다시 로그인하세요.")
        if res.status_code == 403:
            raise DomainError("FORBIDDEN", "해당 작업에 접근할 수 없습니다.")
        if res.status_code == 409:
            raise DomainError("CONFLICT", "이미 저장된 정보와 충돌합니다. 새로 조회한 뒤 다시 시도하세요.")
        if res.status_code >= 400:
            raise DomainError("DB_UNAVAILABLE", "데이터를 처리할 수 없습니다. 설정과 연결 상태를 확인하세요.")
        try:
            rows = res.json()
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError
        except ValueError:
            raise DomainError("DB_UNAVAILABLE", "데이터 응답 형식을 확인할 수 없습니다.") from None
        return rows

    def owned_store(self, store_id: UUID) -> dict:
        rows = self.request("GET", "stores", {"id": f"eq.{store_id}", "user_id": f"eq.{self.user_id}", "select": "*", "limit": "1"})
        if not rows:
            raise DomainError("NOT_FOUND", "매장을 찾을 수 없거나 접근할 수 없습니다.")
        return rows[0]
