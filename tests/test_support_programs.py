import os
import unittest
from datetime import date
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.database.bizinfo import BizinfoClient, bizinfo_settings
from app.errors import DomainError
from app.main import app
from app.schemas.support_programs import SupportCollection, SupportProgram
from app.services import support_programs
from app.services.support_programs import collect_support_programs, from_bizinfo, open_programs, parse_period

SECRET = "secret/key+value"
TODAY = date(2026, 10, 27)


def biz_row(pid: str, title: str, period: str = "20261001 ~ 20261130", **extra: str) -> dict:
    return {"pblancId": pid, "pblancNm": title, "jrsdInsttNm": "중소벤처기업부", "reqstBeginEndDe": period,
            "pblancUrl": f"/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId={pid}", "hashTags": "2026,소상공인,서울",
            "bsnsSumryCn": "<p>소상공인&nbsp;경영 &amp; 판로 지원</p>", "trgetNm": "소상공인", **extra}


def biz_client(handler) -> BizinfoClient:
    http = httpx.Client(base_url="https://bizinfo.test/uss/rss/bizinfoApi.do", transport=httpx.MockTransport(handler))
    return BizinfoClient(http, SECRET)


class PeriodTest(unittest.TestCase):
    def test_formats(self) -> None:
        self.assertEqual(parse_period("20220727 ~ 20220930"), (date(2022, 7, 27), date(2022, 9, 30)))
        self.assertEqual(parse_period("2026-10-01 ~ 2026.10.31"), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(parse_period("2026-10-01 ~"), (date(2026, 10, 1), None))
        self.assertEqual(parse_period("~ 2026-10-31"), (None, date(2026, 10, 31)))
        for text in ("상시", "예산 소진 시까지", "", None, "20261340 ~ 20261399"):
            self.assertEqual(parse_period(text), (None, None))


class BizinfoTest(unittest.TestCase):
    def test_request_and_both_wrappers(self) -> None:
        seen = []

        def handler(req: httpx.Request) -> httpx.Response:
            seen.append(dict(req.url.params))
            wrap = [biz_row("P1", "A")] if len(seen) == 1 else {"item": biz_row("P2", "B")}
            return httpx.Response(200, json={"jsonArray": wrap})

        client = biz_client(handler)
        self.assertEqual(client.programs(["소상공인", "서울"], category="01")[0]["pblancId"], "P1")
        self.assertEqual(client.programs([])[0]["pblancId"], "P2")
        self.assertEqual(seen[0], {"crtfcKey": SECRET, "dataType": "json", "searchCnt": "0",
                                   "hashtags": "소상공인,서울", "searchLclasId": "01"})
        self.assertNotIn("hashtags", seen[1])

    def test_errors_hide_key(self) -> None:
        cases = [(httpx.Response(200, json={"reqErr": "존재하지 않는 인증키 입니다."}), "SUPPORT_SOURCE_REJECTED"),
                 (httpx.Response(200, text="<rss/>"), "SUPPORT_SOURCE_INVALID"),
                 (httpx.Response(200, json={"jsonArray": "x"}), "SUPPORT_SOURCE_INVALID"),
                 (httpx.Response(403), "SUPPORT_SOURCE_UNAVAILABLE")]
        for res, code in cases:
            with self.assertRaises(DomainError) as ctx:
                biz_client(lambda req, res=res: res).programs([])
            self.assertEqual(ctx.exception.code, code)
            self.assertNotIn(SECRET, ctx.exception.message)

    def test_retry_then_fail(self) -> None:
        calls = []

        def down(req: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError(str(req.url))

        with self.assertRaises(DomainError) as ctx:
            biz_client(down).programs([])
        self.assertEqual((len(calls), ctx.exception.code), (2, "SUPPORT_SOURCE_UNAVAILABLE"))
        self.assertIsNone(ctx.exception.__cause__)

    def test_convert_row(self) -> None:
        item = from_bizinfo(biz_row("P1", " 소상공인  판로 지원 "))
        self.assertEqual((item.title, item.agency, item.summary), ("소상공인 판로 지원", "중소벤처기업부", "소상공인 경영 & 판로 지원"))
        self.assertEqual((item.apply_start, item.apply_end, item.always_open), (date(2026, 10, 1), date(2026, 11, 30), False))
        self.assertEqual(item.hashtags, ["2026", "소상공인", "서울"])
        self.assertTrue(item.url.startswith("https://www.bizinfo.go.kr/web/"))
        always = from_bizinfo(biz_row("P2", "상시 지원", period="예산 소진 시까지"))
        self.assertEqual((always.apply_end, always.always_open, always.apply_period_text), (None, True, "예산 소진 시까지"))
        self.assertIsNone(from_bizinfo({"pblancNm": "ID 없음"}))
        self.assertIsNone(from_bizinfo(biz_row("P3", "x", pblancUrl="javascript:alert(1)")).url)

    def test_settings(self) -> None:
        with patch.dict(os.environ, {"BIZINFO_API_KEY": ""}):
            with self.assertRaises(DomainError):
                bizinfo_settings()
        with patch.dict(os.environ, {"BIZINFO_API_KEY": " k "}):
            self.assertEqual(bizinfo_settings(), "k")


class CollectTest(unittest.TestCase):
    def program(self, pid: str, title: str, end: date | None) -> SupportProgram:
        return SupportProgram(program_id=pid, title=title, apply_end=end, always_open=end is None)

    def test_open_programs_filters_dedupes_and_sorts(self) -> None:
        programs = [self.program("1", "마감 지남", date(2026, 10, 26)), self.program("2", "상시", None),
                    self.program("3", "오늘 마감", TODAY), self.program("4", "다음 달", date(2026, 11, 30)),
                    self.program("5", "오늘  마감", TODAY)]
        self.assertEqual([p.program_id for p in open_programs(programs, TODAY)], ["3", "4", "2"])

    def test_collect(self) -> None:
        rows = [biz_row("P1", "공고"), biz_row("P2", "지난 공고", period="20260901 ~ 20260930"), {"pblancNm": "x"}]
        result = collect_support_programs(biz_client(lambda req: httpx.Response(200, json={"jsonArray": rows})), today=TODAY)
        self.assertEqual((result.status, result.fetched_count, result.skipped_count, result.matched_count),
                         ("success", 2, 1, 2))
        self.assertEqual([p.program_id for p in result.programs], ["P1"])

    def test_keeps_only_seoul_small_business(self) -> None:
        rows = [biz_row("A", "전국 소상공인 정책자금", hashTags="금융,서울,부산,소상공인"),
                biz_row("B", "[서울] 광진구 경영주치의", hashTags="경영", jrsdInsttNm="서울특별시"),
                biz_row("C", "데이터 품질대상", trgetNm="중소기업", hashTags="경영,서울,부산"),
                biz_row("D", "부산 소상공인 지원", hashTags="부산,소상공인", jrsdInsttNm="부산광역시"),
                biz_row("E", "서울시 홍보관", trgetNm="중소기업", hashTags="내수,서울,소상공인", jrsdInsttNm="서울특별시"),
                biz_row("F", "[광주] 소상공인 SNS 홍보", hashTags="서울,부산,광주,소상공인", jrsdInsttNm="전남광주통합특별시"),
                biz_row("G", "과천시 소상공인 육성자금", hashTags="서울,경기,소상공인", jrsdInsttNm="경기도")]
        result = collect_support_programs(biz_client(lambda req: httpx.Response(200, json={"jsonArray": rows})), today=TODAY)
        self.assertEqual(sorted(p.program_id for p in result.programs), ["A", "B", "E"])
        self.assertEqual((result.fetched_count, result.matched_count), (7, 3))

    def test_failed(self) -> None:
        client = biz_client(lambda req: httpx.Response(200, json={"reqErr": "인증키를 입력해주세요."}))
        result = collect_support_programs(client, today=TODAY)
        self.assertEqual((result.status, result.error_code, result.programs), ("failed", "SUPPORT_SOURCE_REJECTED", []))


class SupportRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        support_programs.clear_cache()
        self.addCleanup(support_programs.clear_cache)

    def test_route_caches_success(self) -> None:
        calls = []

        def fetch(today: date) -> SupportCollection:
            calls.append(today)
            return collect_support_programs(biz_client(lambda req: httpx.Response(200, json={"jsonArray": [biz_row("P1", "공고")]})),
                                            today=TODAY)

        with patch.object(support_programs, "fetch_programs", fetch), \
                patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1"}), TestClient(app) as http:
            first = http.get("/api/v1/support-programs")
            http.get("/api/v1/support-programs")
        self.assertEqual(first.status_code, 200)
        self.assertEqual([p["program_id"] for p in first.json()["programs"]], ["P1"])
        self.assertEqual(len(calls), 1)

    def test_route_without_key(self) -> None:
        with patch.dict(os.environ, {"BUTILL_ANALYSIS_ONLY": "1", "BIZINFO_API_KEY": ""}), TestClient(app) as http:
            res = http.get("/api/v1/support-programs")
        self.assertEqual((res.status_code, res.json()["code"]), (503, "CONFIG_REQUIRED"))


if __name__ == "__main__":
    unittest.main()
