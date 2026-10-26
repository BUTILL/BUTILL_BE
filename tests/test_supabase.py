import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from supabase import Client

import app.database.supabase as db
from app.main import app


class SupabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "sb_publishable_test_key",
        })
        self.env.start()
        self.loader = patch.object(db, "load_dotenv")
        self.loader.start()
        self.state = patch.object(db, "_client", None)
        self.state.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.loader.stop)
        self.addCleanup(self.state.stop)

    def test_single_client_under_concurrent_requests(self) -> None:
        obj = object()
        with patch.object(db, "create_client", return_value=obj) as factory:
            with ThreadPoolExecutor(max_workers=8) as pool:
                clients = list(pool.map(lambda _: db.get_supabase(), range(20)))
            self.assertTrue(all(client is obj for client in clients))
            factory.assert_called_once()
            opts = factory.call_args.kwargs["options"]
            self.assertFalse(opts.persist_session)
            self.assertFalse(opts.auto_refresh_token)

    def test_missing_or_blank_settings(self) -> None:
        for name in ("SUPABASE_URL", "SUPABASE_KEY"):
            for value in ("", "   "):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaisesRegex(RuntimeError, "설정해야"):
                        db.get_supabase()

    def test_invalid_urls(self) -> None:
        for url in ("example.supabase.co", "ftp://example.com", "https://", "https://user:secret@example.com", "https://example.com?key=secret", "https://example.com/rest/v1", "https://["):
            with self.subTest(url=url), patch.dict(os.environ, {"SUPABASE_URL": url}):
                with self.assertRaisesRegex(RuntimeError, "유효한 HTTP"):
                    db.get_supabase()

    def test_failure_does_not_expose_key_and_can_retry(self) -> None:
        secret = os.environ["SUPABASE_KEY"]
        with patch.object(db, "create_client", side_effect=ValueError(secret)):
            with self.assertRaises(RuntimeError) as err:
                db.get_supabase()
            self.assertNotIn(secret, str(err.exception))
            self.assertTrue(err.exception.__suppress_context__)
        obj = object()
        with patch.object(db, "create_client", return_value=obj):
            self.assertIs(db.get_supabase(), obj)

    def test_dotenv_path_and_existing_environment_precedence(self) -> None:
        from dotenv import load_dotenv

        with TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text("SUPABASE_KEY=file_key\n", encoding="utf-8")
            with patch.object(db, "load_dotenv", side_effect=lambda _, **opts: load_dotenv(path, **opts)) as loader:
                with patch.object(db, "create_client", return_value=object()) as factory:
                    db.get_supabase()
                    self.assertEqual(factory.call_args.args[1], "sb_publishable_test_key")
                    self.assertEqual(loader.call_args.args[0], Path(db.__file__).resolve().parents[2] / ".env")
                    self.assertFalse(loader.call_args.kwargs["override"])

    def test_real_sdk_client_and_database_request(self) -> None:
        client = db.get_supabase()
        self.assertIsInstance(client, Client)
        seen = []

        def reply(req: httpx.Request) -> httpx.Response:
            seen.append(req)
            return httpx.Response(200, json=[{"id": "test-store"}])

        with httpx.Client(transport=httpx.MockTransport(reply)) as http:
            with patch.object(client.postgrest, "session", http):
                data = client.table("stores").select("id").limit(1).execute()
        self.assertEqual(data.data, [{"id": "test-store"}])
        self.assertEqual(seen[0].url.path, "/rest/v1/stores")
        self.assertEqual(seen[0].url.params["limit"], "1")

    def test_fastapi_startup_and_existing_routes(self) -> None:
        obj = object()
        with patch.object(db, "create_client", return_value=obj):
            with TestClient(app) as http:
                self.assertIs(app.state.supabase, obj)
                self.assertEqual(http.get("/health").json(), {"status": "ok"})
                self.assertEqual(http.get("/").json(), {"message": "BUTILL API Server"})
                self.assertEqual(http.get("/docs").status_code, 200)

    def test_fastapi_startup_fails_on_missing_settings(self) -> None:
        with patch.dict(os.environ, {"SUPABASE_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "설정해야"):
                with TestClient(app):
                    pass


if __name__ == "__main__":
    unittest.main()
