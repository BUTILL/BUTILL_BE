from fastapi import APIRouter

from app.schemas.analyses import ComparisonInput, ComparisonResponse
from app.services.scenarios import compare

router = APIRouter()


@router.post("/compare", response_model=ComparisonResponse, summary="기본·변경 시나리오 비교")
def compare_scenarios(data: ComparisonInput) -> ComparisonResponse:
    return compare(data)
