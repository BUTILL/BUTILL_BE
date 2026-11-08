from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.database.ingredient_prices import PriceRepository
from app.database.kamis import KamisClient
from app.errors import DomainError
from app.schemas.ingredient_prices import (
    CollectionResult, ItemCollection, ItemRunResult, PriceItem, PriceObservation, StoredRun,
)

KST = timezone(timedelta(hours=9))
MAX_PERIOD_DAYS = 366
MAX_WORKERS = 5
COLLECT_DAYS = 35
REGION_MARKET = "-"
WEIGHT_UNITS = frozenset({"g", "kg"})


def parse_price(value: object) -> int | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    if text in ("", "-"):
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_day(value: object) -> date | None:
    try:
        return datetime.strptime(str(value).strip(), "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def text(row: dict, key: str) -> str:
    return str(row.get(key) or "").strip()


def parse_items(item: PriceItem, rows: list) -> ItemCollection:
    seen = set()
    observations = []
    missing = duplicate = invalid = 0
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        day = parse_day(row.get("exmn_ymd"))
        kind, rank = text(row, "vrty_cd"), text(row, "grd_cd")
        market = text(row, "mrkt_cd") or REGION_MARKET
        if day is None or not kind or not rank or text(row, "item_cd") != item.item_code:
            invalid += 1
            continue
        key = (day, kind, rank, market)
        if key in seen:
            duplicate += 1
            continue
        seen.add(key)
        price = parse_price(row.get("exmn_dd_prc"))
        if price is None:
            missing += 1
            continue
        unit = text(row, "unit")
        observations.append(PriceObservation(
            item_key=item.key, price_date=day, kind_code=kind, kind_name=text(row, "vrty_nm") or None,
            rank_code=rank, rank_name=text(row, "grd_nm") or None, unit=text(row, "unit_sz") + unit,
            market_code=market, market_name=text(row, "mrkt_nm") or None, price=price,
            price_per_kg=parse_price(row.get("exmn_dd_cnvs_prc")) if unit.lower() in WEIGHT_UNITS else None,
        ))
    observations.sort(key=lambda o: (o.price_date, o.kind_code, o.rank_code, o.market_code))
    status = "success" if observations else "no_data"
    return ItemCollection(item=item, status=status, observations=observations,
                          missing_count=missing, duplicate_count=duplicate, invalid_count=invalid)


def check_period(start: date, end: date) -> None:
    if start > end or (end - start).days >= MAX_PERIOD_DAYS:
        raise DomainError("INVALID_PERIOD", "가격 조회 기간은 시작일부터 1년 이내로 입력하세요.")


def collect_prices(client: KamisClient, items: list[PriceItem], start: date, end: date) -> CollectionResult:
    check_period(start, end)
    started = datetime.now(KST)

    def collect(item: PriceItem) -> ItemCollection:
        try:
            return parse_items(item, client.daily_prices(item, start, end))
        except DomainError as exc:
            return ItemCollection(item=item, status="failed", error_code=exc.code, observations=[])

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(collect, items))
    failures = sum(1 for r in results if r.status == "failed")
    status = "success" if failures == 0 else "failed" if failures == len(results) else "partial"
    return CollectionResult(started_at=started, finished_at=datetime.now(KST), status=status,
                            success_count=len(results) - failures, failure_count=failures, items=results)


def overall_status(results: list[ItemRunResult]) -> str:
    failures = sum(1 for r in results if r.status == "failed")
    return "success" if failures == 0 else "failed" if failures == len(results) else "partial"


def run_result(collected: ItemCollection, status: str | None = None, error_code: str | None = None) -> ItemRunResult:
    return ItemRunResult(key=collected.item.key, status=status or collected.status,
                         error_code=error_code or collected.error_code, missing_count=collected.missing_count,
                         duplicate_count=collected.duplicate_count, invalid_count=collected.invalid_count)


def price_row(ingredient_id: str, o: PriceObservation, collected_at: datetime) -> dict:
    return {"ingredient_id": ingredient_id, "price_date": o.price_date.isoformat(), "kind_code": o.kind_code,
            "kind_name": o.kind_name, "rank_code": o.rank_code, "rank_name": o.rank_name, "unit": o.unit,
            "market_code": o.market_code, "market_name": o.market_name, "price": o.price,
            "price_per_kg": o.price_per_kg, "source": o.source, "collected_at": collected_at.isoformat()}


def run_collection(client: KamisClient, repo: PriceRepository, items: list[PriceItem], today: date) -> StoredRun:
    collected = collect_prices(client, items, today - timedelta(days=COLLECT_DAYS), today)
    ids = repo.save_ingredients(items)
    results = []
    saved = 0
    error_code = None
    for entry in collected.items:
        if error_code:
            results.append(run_result(entry, "failed", error_code))
            continue
        try:
            saved += repo.save_prices([price_row(ids[entry.item.key], o, collected.finished_at) for o in entry.observations])
            results.append(run_result(entry))
        except DomainError as exc:
            error_code = exc.code
            results.append(run_result(entry, "failed", error_code))
    failures = sum(1 for r in results if r.status == "failed")
    run = StoredRun(started_at=collected.started_at, finished_at=datetime.now(KST), status=overall_status(results),
                    success_count=len(results) - failures, failure_count=failures, saved_count=saved,
                    error_code=error_code, item_results=results)
    repo.save_run(run.model_dump(mode="json"))
    return run
