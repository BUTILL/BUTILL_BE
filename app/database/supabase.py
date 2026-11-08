import os
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from dotenv import load_dotenv
from supabase import Client, create_client
from supabase.client import ClientOptions

_client: Client | None = None
_lock = Lock()


def get_supabase() -> Client:
    global _client

    with _lock:
        if _client is not None:
            return _client

        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError("SUPABASE_URL과 SUPABASE_KEY를 설정해야 합니다.")

        try:
            addr = urlsplit(url)
            if (
                addr.scheme not in ("http", "https")
                or not addr.hostname
                or addr.username
                or addr.password
                or addr.query
                or addr.fragment
                or addr.path not in ("", "/")
            ):
                raise ValueError
        except ValueError:
            raise RuntimeError("SUPABASE_URL은 유효한 HTTP(S) 프로젝트 주소여야 합니다.") from None

        try:
            _client = create_client(
                url,
                key,
                options=ClientOptions(
                    auto_refresh_token=False,
                    persist_session=False,
                    postgrest_client_timeout=10,
                    storage_client_timeout=10,
                ),
            )
        except Exception:
            raise RuntimeError("Supabase Client 초기화에 실패했습니다. 연결 설정을 확인하세요.") from None
        return _client
