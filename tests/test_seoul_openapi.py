import os
import unittest
from unittest.mock import patch

import httpx

from app.database.seoul_openapi import SeoulOpenApiClient, seoul_settings
from app.errors import DomainError

SECRET = "secret/key+value"
SERVICE = "VwsmTrdarStorQq"
INVALID_KEY_XML = "<RESULT><CODE>INFO-100</CODE><MESSAGE><![CDATA[인증키가 유효하지 않습니다.]]></MESSAGE></RESULT>"


def page(rows: list[dict], total: int) -> dict:
    return {SERVICE: {"list_total_count": total, "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"}, "row": rows}}


def client(handler) -> SeoulOpenApiClient:
    return SeoulOpenApiClient(httpx.Client(base_url="http://seoul.test:8088", transport=httpx.MockTransport(handler)), SECRET)


class SeoulOpenApiTest(unittest.TestCase):
    def test_path_and_pagination(self) -> None:
        paths = []

        def handler(req: httpx.Request) -> httpx.Response:
            paths.append(req.url.raw_path.decode())
            start = int(req.url.path.rstrip("/").split("/")[-2])
            return httpx.Response(200, json=page([{"TRDAR_CD": str(start)}], total=2500))

        rows = client(handler).rows(SERVICE)
        self.assertEqual([r["TRDAR_CD"] for r in rows], ["1", "1001", "2001"])
        self.assertEqual(paths[0], f"/secret%2Fkey%2Bvalue/json/{SERVICE}/1/1000/")
        self.assertTrue(paths[2].endswith("/2001/3000/"))

    def test_limit_stops_paging(self) -> None:
        calls = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(req.url.path)
            return httpx.Response(200, json=page([{"TRDAR_CD": "1"}], total=9000))

        client(handler).rows(SERVICE, limit=1500)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1].endswith("/1001/1500/"))

    def test_result_codes(self) -> None:
        no_data = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
        self.assertEqual(client(lambda req: httpx.Response(200, json=no_data)).rows(SERVICE), [])
        cases = [(httpx.Response(200, text=INVALID_KEY_XML), "EXTERNAL_SOURCE_REJECTED"),
                 (httpx.Response(200, json={"RESULT": {"CODE": "ERROR-500", "MESSAGE": "서버 오류입니다."}}), "EXTERNAL_SOURCE_UNAVAILABLE"),
                 (httpx.Response(200, text="broken"), "EXTERNAL_SOURCE_UNAVAILABLE"),
                 (httpx.Response(502), "EXTERNAL_SOURCE_UNAVAILABLE"),
                 (httpx.Response(200, json={SERVICE: {"RESULT": {"CODE": "INFO-000"}, "row": "x"}}), "EXTERNAL_SOURCE_INVALID")]
        for res, code in cases:
            with self.assertRaises(DomainError) as ctx:
                client(lambda req, res=res: res).page(SERVICE, 1, 10)
            self.assertEqual(ctx.exception.code, code)
            self.assertNotIn(SECRET, ctx.exception.message)

    def test_retry_hides_key(self) -> None:
        calls = []

        def down(req: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError(str(req.url))

        with self.assertRaises(DomainError) as ctx:
            client(down).page(SERVICE, 1, 10)
        self.assertEqual(len(calls), 2)
        self.assertIsNone(ctx.exception.__cause__)

    def test_rejects_bad_request_before_call(self) -> None:
        never = client(lambda req: self.fail("잘못된 조건은 호출 전에 막아야 합니다."))
        for args in (("../x", 1, 10), (SERVICE, 0, 10), (SERVICE, 1, 1001), (SERVICE, 10, 1)):
            with self.assertRaises(DomainError):
                never.page(*args)

    def test_settings(self) -> None:
        with patch.dict(os.environ, {"SEOUL_OPENAPI_KEY": ""}):
            with self.assertRaises(DomainError):
                seoul_settings()
        with patch.dict(os.environ, {"SEOUL_OPENAPI_KEY": " k "}):
            self.assertEqual(seoul_settings(), "k")


if __name__ == "__main__":
    unittest.main()
