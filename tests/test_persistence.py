import copy
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.main import app

RealClient = httpx.Client
USER_A = str(uuid4())
USER_B = str(uuid4())
NOW = "2026-10-26T00:00:00+00:00"


class FakeSupabase:
    def __init__(self) -> None:
        self.tables = {name: [] for name in ("stores", "startup_plans", "analysis_runs", "scenarios")}

    def handle(self, req: httpx.Request) -> httpx.Response:
        token = req.headers.get("authorization", "").replace("Bearer ", "")
        uid = {"user-a": USER_A, "user-b": USER_B}.get(token)
        if req.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": uid}) if uid else httpx.Response(401, json={"message": "invalid token"})
        if uid is None:
            return httpx.Response(401, json={})
        name = req.url.path.rsplit("/", 1)[-1]
        rows = self.tables[name]

        def owned(row: dict) -> bool:
            if name == "stores":
                return row["user_id"] == uid
            return any(s["id"] == row["store_id"] and s["user_id"] == uid for s in self.tables["stores"])

        def matches(row: dict) -> bool:
            return owned(row) and all(not val.startswith("eq.") or str(row.get(key)) == val[3:]
                                      for key, val in req.url.params.items())

        if req.method == "GET":
            result = [r for r in rows if matches(r)]
            start = int(req.url.params.get("offset", 0))
            limit = int(req.url.params.get("limit", len(result)))
            return httpx.Response(200, json=copy.deepcopy(result[start:start + limit]))
        data = json.loads(req.content)
        if req.method == "POST":
            if not owned(data):
                return httpx.Response(403, json={})
            if name == "startup_plans" and any(r["store_id"] == data["store_id"] for r in rows):
                return httpx.Response(409, json={})
            row = {"id": str(uuid4()), **data, "created_at": NOW}
            if name in ("stores", "startup_plans"):
                row["updated_at"] = NOW
            rows.append(row)
            return httpx.Response(201, json=[copy.deepcopy(row)])
        if req.method == "PATCH":
            found = [r for r in rows if matches(r)]
            for row in found:
                row.update(data)
                row["updated_at"] = NOW
            return httpx.Response(200, json=copy.deepcopy(found))
        return httpx.Response(405, json={})


def finance() -> dict:
    return {"start_month": "2026-11-01", "months": 2, "current_cash": 3_000_000,
            "monthly_sales": 2_000_000, "monthly_ingredient_cost": 500_000,
            "fixed_expenses": [{"name": "고정비", "amount": 1_000_000}]}


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.remote = FakeSupabase()
        env = patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.http = TestClient(app)
        self.http.__enter__()
        self.addCleanup(self.http.__exit__, None, None, None)
        settings = patch("app.dependencies.auth.connection_settings", return_value=("https://example.supabase.co", "sb_publishable_test"))
        settings.start()
        self.addCleanup(settings.stop)
        factory = patch("app.dependencies.auth.httpx.Client", side_effect=lambda **kw: RealClient(
            **kw, transport=httpx.MockTransport(self.remote.handle)))
        factory.start()
        self.addCleanup(factory.stop)
        self.headers = {"Authorization": "Bearer user-a"}

    def create_store(self) -> dict:
        res = self.http.post("/api/v1/stores", headers=self.headers, json={
            "name": "테스트 음식점", "business_type": "restaurant", "region": "서울", "status": "operating"})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def test_full_persistence_flow_and_source_snapshot(self) -> None:
        store = self.create_store()
        root = "/api/v1/stores/" + store["id"]
        first = self.http.put(root + "/finances", headers=self.headers, json={"input": finance()})
        self.assertEqual(first.status_code, 200, first.text)
        saved = first.json()
        self.assertEqual(self.http.get(root + "/finances", headers=self.headers).json(), saved)
        run = self.http.post(root + "/analyses", headers=self.headers)
        self.assertEqual(run.status_code, 201, run.text)
        result = run.json()
        self.assertTrue(result["persisted"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(result["source_revision"], saved["revision"])
        self.assertEqual(result["result"]["monthly"][-1]["cash_balance"], 4_000_000)
        scenario = self.http.post(root + "/scenarios", headers=self.headers, json={
            "base_analysis_id": result["id"], "scenario": {"name": "매출 감소", "sales_change_bps": -2000}})
        self.assertEqual(scenario.status_code, 201, scenario.text)
        s = scenario.json()
        self.assertEqual(s["comparison"]["scenarios"][0]["ending_cash_delta"], -800_000)
        self.assertTrue(s["comparison"]["persisted"])
        self.assertEqual(self.http.get(root + "/scenarios/" + s["id"] + "/comparison", headers=self.headers).json(), s)
        self.assertEqual(self.http.get(root + "/finances", headers=self.headers).json(), saved)

    def test_revision_prevents_lost_update(self) -> None:
        store = self.create_store()
        root = "/api/v1/stores/" + store["id"] + "/finances"
        first = self.http.put(root, headers=self.headers, json={"input": finance()}).json()
        update = self.http.put(root, headers=self.headers, json={"input": finance() | {"current_cash": 5}, "revision": first["revision"]})
        self.assertEqual(update.status_code, 200, update.text)
        self.assertNotEqual(first["revision"], update.json()["revision"])
        self.assertEqual(self.http.put(root, headers=self.headers, json={"input": finance(), "revision": first["revision"]}).status_code, 409)
        self.assertEqual(self.http.put(root, headers=self.headers, json={"input": finance()}).status_code, 409)
        self.assertEqual(self.http.get(root, headers=self.headers).json()["input"]["current_cash"], 5)

    def test_other_user_cannot_access_any_child(self) -> None:
        store = self.create_store()
        root = "/api/v1/stores/" + store["id"]
        self.http.put(root + "/finances", headers=self.headers, json={"input": finance()})
        run = self.http.post(root + "/analyses", headers=self.headers).json()
        other = {"Authorization": "Bearer user-b"}
        self.assertEqual(self.http.get("/api/v1/stores", headers=other).json(), [])
        for url in (root, root + "/finances", root + "/analyses/" + run["id"]):
            self.assertEqual(self.http.get(url, headers=other).status_code, 404)
        self.assertEqual(self.http.put(root + "/finances", headers=other, json={"input": finance()}).status_code, 404)
        self.assertEqual(self.http.post(root + "/analyses", headers=other).status_code, 404)

    def test_cross_store_analysis_rejected(self) -> None:
        a = self.create_store()
        b = self.create_store()
        root = "/api/v1/stores/" + a["id"]
        self.http.put(root + "/finances", headers=self.headers, json={"input": finance()})
        run = self.http.post(root + "/analyses", headers=self.headers).json()
        res = self.http.post("/api/v1/stores/" + b["id"] + "/scenarios", headers=self.headers, json={
            "base_analysis_id": run["id"], "scenario": {"name": "잘못된 연결"}})
        self.assertEqual(res.status_code, 404)

    def test_missing_and_invalid_auth(self) -> None:
        self.assertEqual(self.http.get("/api/v1/stores").status_code, 401)
        bad = self.http.get("/api/v1/stores", headers={"Authorization": "Bearer private-invalid-token"})
        self.assertEqual(bad.status_code, 401)
        self.assertNotIn("private-invalid-token", bad.text)

    def test_schema_rejects_owner_injection_and_null_patch(self) -> None:
        store = self.create_store()
        self.assertEqual(self.http.patch("/api/v1/stores/" + store["id"], headers=self.headers, json={"user_id": USER_B}).status_code, 422)
        self.assertEqual(self.http.patch("/api/v1/stores/" + store["id"], headers=self.headers, json={"name": None}).status_code, 422)
        self.assertEqual(self.http.get("/api/v1/stores/not-a-uuid", headers=self.headers).status_code, 422)

    def test_remote_failure_is_sanitized(self) -> None:
        with patch.object(self.remote, "handle", return_value=httpx.Response(503, text="secret-provider-body")):
            res = self.http.get("/api/v1/stores", headers=self.headers)
        self.assertEqual(res.status_code, 503)
        self.assertNotIn("secret-provider-body", res.text)

    def test_changed_calculation_version_requires_new_baseline(self) -> None:
        store = self.create_store()
        root = "/api/v1/stores/" + store["id"]
        self.http.put(root + "/finances", headers=self.headers, json={"input": finance()})
        run = self.http.post(root + "/analyses", headers=self.headers).json()
        self.remote.tables["analysis_runs"][0]["result"]["calculation_version"] = "old-version"
        res = self.http.post(root + "/scenarios", headers=self.headers, json={
            "base_analysis_id": run["id"], "scenario": {"name": "새 비교"}})
        self.assertEqual(res.status_code, 409)

    def test_bad_provider_data_never_echoes_input(self) -> None:
        self.create_store()
        self.remote.tables["stores"][0]["name"] = ""
        res = self.http.get("/api/v1/stores", headers=self.headers)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["code"], "DB_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
