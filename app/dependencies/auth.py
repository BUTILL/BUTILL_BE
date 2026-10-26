from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database.persistence import SupabaseRepository, connection_settings
from app.errors import DomainError

bearer = HTTPBearer(auto_error=False)


def get_repository(
    auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Iterator[SupabaseRepository]:
    if auth is None or not auth.credentials or len(auth.credentials) > 8192:
        raise DomainError("UNAUTHORIZED", "Bearer 토큰으로 로그인해야 합니다.")
    url, key = connection_settings()
    with httpx.Client(base_url=url, headers={"apikey": key, "Authorization": "Bearer " + auth.credentials},
                      timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as client:
        repo = SupabaseRepository(client)
        repo.authenticate()
        yield repo
