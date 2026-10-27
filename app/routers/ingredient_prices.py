from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.schemas.ingredient_prices import IngredientPriceResponse
from app.services.ingredient_prices import latest_prices

router = APIRouter()


@router.get("", response_model=IngredientPriceResponse, summary="원재료 최근 가격·1주 전 대비 변동")
def list_ingredient_prices(
    group: Annotated[Literal["common", "dakgalbi", "pasta"] | None, Query()] = None,
) -> IngredientPriceResponse:
    return latest_prices(group)
