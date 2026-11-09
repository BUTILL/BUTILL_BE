from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock

from app.database.ingredient_prices import PriceRepository, open_price_reader
from app.errors import DomainError
from app.schemas.ingredient_prices import (
    DailyPrice, IngredientPriceResponse, WeeklyPrice, ItemCollection, ItemRunResult, PriceChange, PriceFilter, PriceItem,
    PriceObservation, PriceSummary, StoredRun,
)
from app.services.price_collection import KST, check_period
from app.services.price_items import PRICE_ITEMS

LOOKBACK_DAYS = 28
WEEK_DAYS = 7
CACHE_SECONDS = 10 * 60
MAX_CACHE_ENTRIES = 64

_cache: dict[PriceFilter, tuple[datetime, IngredientPriceResponse]] = {}
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


def weekly_averages(daily: list[DailyPrice]) -> list[WeeklyPrice]:
    weeks = defaultdict(list)
    for d in daily:
        weeks[d.price_date - timedelta(days=d.price_date.weekday())].append(d.average_price)
    return [WeeklyPrice(week_start=start, average_price=rounded(sum(v), len(v)), days=len(v)) for start, v in sorted(weeks.items())]


def summarize(collected: ItemCollection) -> PriceSummary:
    item = collected.item
    meta = {"key": item.key, "name": item.name, "groups": item.groups, "region_code": item.region_code,
            "error_code": collected.error_code, "missing_count": collected.missing_count,
            "duplicate_count": collected.duplicate_count, "invalid_count": collected.invalid_count}
    series = main_series(collected.observations)
    if not series:
        return PriceSummary(**meta, status="no_data" if collected.status == "success" else collected.status)
    daily = daily_averages(series)
    latest = daily[-1]
    week_ago = latest.price_date - timedelta(days=WEEK_DAYS)
    base = next((d for d in reversed(daily) if d.price_date <= week_ago), None)
    sample = series[-1]
    return PriceSummary(**meta, status=collected.status, stale=collected.status != "success",
                        kind_name=sample.kind_name, rank_name=sample.rank_name, unit=sample.unit, latest=latest,
                        week_change=price_change(base, latest) if base else None, daily=daily,
                        weekly=weekly_averages(daily))


def selected_items(query: PriceFilter) -> list[PriceItem]:
    return [i for i in PRICE_ITEMS
            if (query.group is None or query.group in i.groups)
            and (query.item is None or query.item == i.key)
            and (query.region_code is None or query.region_code == i.region_code)]


def stored_observations(item: PriceItem, rows: list[dict], query: PriceFilter) -> list[PriceObservation]:
    result = [PriceObservation(item_key=item.key, **row) for row in rows]
    return [o for o in result
            if (query.kind_code is None or query.kind_code == o.kind_code)
            and (query.unit is None or query.unit == o.unit)]


def read_response(repo: PriceRepository, query: PriceFilter, today: date) -> IngredientPriceResponse:
    end = query.end_date or today
    start = query.start_date or end - timedelta(days=LOOKBACK_DAYS)
    check_period(start, end)
    raw_run = repo.latest_run()
    if raw_run is None:
        return IngredientPriceResponse(status="no_data", items=[
            PriceSummary(key=i.key, name=i.name, groups=i.groups, region_code=i.region_code, status="no_data")
            for i in selected_items(query)])
    run = StoredRun.model_validate(raw_run)
    items = selected_items(query)
    results = {r.key: r for r in run.item_results}
    ids = repo.ingredient_ids([i.key for i in items]) if items else {}
    by_item = defaultdict(list)
    if ids:
        names = {value: key for key, value in ids.items()}
        for row in repo.prices(list(ids.values()), start, end):
            ingredient_id = row.pop("ingredient_id")
            by_item[names[ingredient_id]].append(row)
    summaries = []
    for item in items:
        result = results.get(item.key) or ItemRunResult(key=item.key, status="no_data")
        summaries.append(summarize(ItemCollection(
            item=item, status=result.status, error_code=result.error_code,
            observations=stored_observations(item, by_item[item.key], query),
            missing_count=result.missing_count, duplicate_count=result.duplicate_count,
            invalid_count=result.invalid_count)))
    return IngredientPriceResponse(collected_at=run.finished_at, last_success_at=repo.last_success_at(),
                                   status=run.status, error_code=run.error_code,
                                   stale=any(s.stale for s in summaries), items=summaries)


def load_response(query: PriceFilter, today: date) -> IngredientPriceResponse:
    with open_price_reader() as repo:
        return read_response(repo, query, today)


def failure_response(query: PriceFilter, code: str) -> IngredientPriceResponse:
    return IngredientPriceResponse(status="failed", error_code=code, items=[
        PriceSummary(key=i.key, name=i.name, groups=i.groups, region_code=i.region_code, status="failed", error_code=code)
        for i in selected_items(query)])


def latest_prices(query: PriceFilter, load: Callable[[PriceFilter, date], IngredientPriceResponse] | None = None) -> IngredientPriceResponse:
    now = datetime.now(KST)
    with _lock:
        cached = _cache.get(query)
    if cached and cached[0] > now:
        return cached[1]
    try:
        response = (load or load_response)(query, now.date())
    except DomainError as exc:
        if exc.code == "INVALID_PERIOD":
            raise
        if cached:
            return cached[1].model_copy(update={"stale": True, "error_code": exc.code})
        return failure_response(query, exc.code)
    if response.status != "failed" or any(i.latest for i in response.items):
        with _lock:
            _cache.pop(query, None)
            while len(_cache) >= MAX_CACHE_ENTRIES:
                _cache.pop(next(iter(_cache)))
            _cache[query] = (now + timedelta(seconds=CACHE_SECONDS), response)
    return response


def clear_cache() -> None:
    with _lock:
        _cache.clear()
