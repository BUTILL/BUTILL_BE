from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.schemas.ingredient_prices import IngredientPriceResponse, PriceFilter
from app.services.ingredient_prices import latest_prices

router = APIRouter()


@router.get("", response_model=IngredientPriceResponse, summary="원재료 저장 가격·1주 전 대비 변동 (외부 호출 없음)")
def list_ingredient_prices(
    group: Annotated[Literal["common", "dakgalbi", "pasta"] | None, Query()] = None,
    item: Annotated[str | None, Query(pattern=r"^[a-z_]+$", max_length=40)] = None,
    kind_code: Annotated[str | None, Query(pattern=r"^\d{1,7}$")] = None,
    unit: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    region_code: Annotated[str | None, Query(pattern=r"^\d{1,7}$")] = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> IngredientPriceResponse:
    return latest_prices(PriceFilter(group=group, item=item, kind_code=kind_code, unit=unit, region_code=region_code,
                                     start_date=start_date, end_date=end_date))
