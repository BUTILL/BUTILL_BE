from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock

from app.database.kamis import open_kamis_client
from app.schemas.ingredient_prices import (
    CollectionResult, DailyPrice, IngredientPriceResponse, ItemCollection, PriceChange, PriceObservation, PriceSummary,
)
from app.services.price_collection import KST, collect_prices
from app.services.price_items import PRICE_ITEMS

LOOKBACK_DAYS = 21
WEEK_DAYS = 7
CACHE_SECONDS = 3 * 60 * 60
RETRY_CACHE_SECONDS = 10 * 60

_cache: dict[str, tuple[datetime, IngredientPriceResponse]] = {}
_lock = Lock()


def rounded(numerator: int, denominator: int) -> int:
    return int((Decimal(numerator) / Decimal(denominator)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def price_change(base: DailyPrice, latest: DailyPrice) -> PriceChange | None:
    if base.average_price <= 0 or base.price_date >= latest.price_date:
        return None
    diff = latest.average_price - base.average_price
    return PriceChange(base_date=base.price_date, base_price=base.average_price, latest_date=latest.price_date,
                       latest_price=latest.average_price, change_amount=diff,
                       change_bps=rounded(diff * 10_000, base.average_price))


def main_series(observations: list[PriceObservation]) -> list[PriceObservation]:
    if not observations:
        return []
    latest = max(o.price_date for o in observations)
    counts = defaultdict(int)
    for o in observations:
        if o.price_date == latest:
            counts[(o.kind_code, o.rank_code, o.unit)] += 1
    kind, rank, unit = max(sorted(counts), key=lambda k: counts[k])
    return [o for o in observations if (o.kind_code, o.rank_code, o.unit) == (kind, rank, unit)]


def daily_averages(series: list[PriceObservation]) -> list[DailyPrice]:
    days = defaultdict(list)
    for o in series:
        days[o.price_date].append(o)
    result = []
    for day in sorted(days):
        rows = days[day]
        per_kg = [o.price_per_kg for o in rows if o.price_per_kg is not None]
        result.append(DailyPrice(price_date=day, average_price=rounded(sum(o.price for o in rows), len(rows)),
                                 average_price_per_kg=rounded(sum(per_kg), len(per_kg)) if per_kg else None,
                                 market_count=len(rows)))
    return result


def summarize(collected: ItemCollection) -> PriceSummary:
    item = collected.item
    series = main_series(collected.observations)
    if not series:
        return PriceSummary(key=item.key, name=item.name, groups=item.groups, status=collected.status)
    daily = daily_averages(series)
    latest = daily[-1]
    week_ago = latest.price_date - timedelta(days=WEEK_DAYS)
    base = next((d for d in reversed(daily) if d.price_date <= week_ago), None)
    sample = series[-1]
    return PriceSummary(key=item.key, name=item.name, groups=item.groups, status="success",
                        kind_name=sample.kind_name, rank_name=sample.rank_name, unit=sample.unit, latest=latest,
                        week_change=price_change(base, latest) if base else None, daily=daily)


def build_response(result: CollectionResult) -> IngredientPriceResponse:
    return IngredientPriceResponse(collected_at=result.finished_at, status=result.status,
                                   items=[summarize(r) for r in result.items])


def fetch_latest(today: date) -> CollectionResult:
    with open_kamis_client() as client:
        return collect_prices(client, PRICE_ITEMS, today - timedelta(days=LOOKBACK_DAYS), today)


def latest_prices(group: str | None = None, fetch: Callable[[date], CollectionResult] | None = None) -> IngredientPriceResponse:
    now = datetime.now(KST)
    key = now.date().isoformat()
    with _lock:
        cached = _cache.get(key)
        if cached is None or cached[0] <= now:
            response = build_response((fetch or fetch_latest)(now.date()))
            ttl = CACHE_SECONDS if response.status == "success" else RETRY_CACHE_SECONDS
            _cache.clear()
            _cache[key] = (now + timedelta(seconds=ttl), response)
            cached = _cache[key]
    response = cached[1]
    if group is None:
        return response
    return response.model_copy(update={"items": [i for i in response.items if group in i.groups]})


def clear_cache() -> None:
    with _lock:
        _cache.clear()
