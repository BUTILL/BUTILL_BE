import html
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from threading import Lock

from app.database.bizinfo import BizinfoClient, open_bizinfo_client
from app.errors import DomainError
from app.schemas.support_programs import SupportCollection, SupportProgram
from app.services.price_collection import KST

BIZINFO_HOME = "https://www.bizinfo.go.kr"
TARGET_KEYWORD = "소상공인"
REGION = "서울"
TITLE_REGION = re.compile(r"^\[([^\]]+)\]")
LOCAL_GOVERNMENT = re.compile(r"(도|광역시|특별시|특별자치시|특별자치도|시청|군청|구청)$")
DATE_PATTERN = re.compile(r"(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})")
CACHE_SECONDS = 3 * 60 * 60
RETRY_CACHE_SECONDS = 10 * 60

_cache: dict[str, tuple[datetime, SupportCollection]] = {}
_lock = Lock()


def clean_text(value: object) -> str | None:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value if value is not None else "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def to_date(found: re.Match) -> date | None:
    try:
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


def parse_period(text: str | None) -> tuple[date | None, date | None]:
    if not text:
        return None, None
    found = list(DATE_PATTERN.finditer(text))
    if len(found) >= 2:
        return to_date(found[0]), to_date(found[-1])
    if len(found) == 1:
        day = to_date(found[0])
        return (None, day) if "~" in text[:found[0].start()] else (day, None)
    return None, None


def split_tags(value: object) -> list[str]:
    return [t for t in (s.strip() for s in str(value or "").split(",")) if t]


def first(row: dict, *keys: str) -> str | None:
    return next((v for v in (clean_text(row.get(k)) for k in keys) if v), None)


def from_bizinfo(row: dict) -> SupportProgram | None:
    program_id = first(row, "pblancId", "seq")
    title = first(row, "pblancNm", "title")
    if not program_id or not title:
        return None
    period = first(row, "reqstBeginEndDe", "reqstDt")
    start, end = parse_period(period)
    url = first(row, "pblancUrl", "link")
    if url and url.startswith("/"):
        url = BIZINFO_HOME + url
    if url and not url.startswith(("https://", "http://")):
        url = None
    return SupportProgram(
        source="BIZINFO", program_id=program_id, title=title, url=url, apply_period_text=period,
        apply_start=start, apply_end=end, always_open=end is None, agency=first(row, "jrsdInsttNm", "author"),
        summary=first(row, "bsnsSumryCn", "description"), target=first(row, "trgetNm"),
        category=first(row, "pldirSportRealmLclasCodeNm", "lcategory"),
        hashtags=split_tags(row.get("hashTags") or row.get("hashtags")),
    )


def open_programs(programs: list[SupportProgram], today: date) -> list[SupportProgram]:
    seen = set()
    result = []
    for item in programs:
        key = re.sub(r"\s+", "", item.title)
        if (item.apply_end is not None and item.apply_end < today) or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda p: (p.apply_end is None, p.apply_end or date.max, p.title))


def is_relevant(item: SupportProgram) -> bool:
    for_small_business = TARGET_KEYWORD in (item.target or "") or TARGET_KEYWORD in item.title \
        or TARGET_KEYWORD in item.hashtags
    agency = item.agency or ""
    prefix = TITLE_REGION.match(item.title)
    other_region = (prefix is not None and prefix.group(1) != REGION) \
        or (LOCAL_GOVERNMENT.search(agency) is not None and not agency.startswith(REGION))
    in_region = REGION in item.hashtags or item.title.startswith(f"[{REGION}]") or agency.startswith(REGION)
    return for_small_business and in_region and not other_region


def collect_support_programs(client: BizinfoClient, today: date | None = None) -> SupportCollection:
    now = datetime.now(KST)
    try:
        rows = client.programs([])
    except DomainError as exc:
        return SupportCollection(collected_at=now, status="failed", error_code=exc.code, programs=[])
    items = [from_bizinfo(r) for r in rows]
    found = [p for p in items if p is not None]
    relevant = [p for p in found if is_relevant(p)]
    return SupportCollection(collected_at=now, status="success", fetched_count=len(found),
                             skipped_count=len(items) - len(found), matched_count=len(relevant),
                             programs=open_programs(relevant, today or now.date()))


def fetch_programs(today: date) -> SupportCollection:
    with open_bizinfo_client() as client:
        return collect_support_programs(client, today=today)


def latest_programs(fetch: Callable[[date], SupportCollection] | None = None) -> SupportCollection:
    now = datetime.now(KST)
    key = now.date().isoformat()
    with _lock:
        cached = _cache.get(key)
        if cached is None or cached[0] <= now:
            result = (fetch or fetch_programs)(now.date())
            ttl = CACHE_SECONDS if result.status == "success" else RETRY_CACHE_SECONDS
            _cache.clear()
            _cache[key] = (now + timedelta(seconds=ttl), result)
            cached = _cache[key]
    return cached[1]


def clear_cache() -> None:
    with _lock:
        _cache.clear()
