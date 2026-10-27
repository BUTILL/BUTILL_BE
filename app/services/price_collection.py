from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.database.kamis import KamisClient
from app.errors import DomainError
from app.schemas.ingredient_prices import CollectionResult, ItemCollection, PriceItem, PriceObservation

KST = timezone(timedelta(hours=9))
MAX_PERIOD_DAYS = 366
MAX_WORKERS = 5
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
    status = "success" if observations or missing else "no_data"
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
