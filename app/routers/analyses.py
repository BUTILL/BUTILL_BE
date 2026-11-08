from fastapi import APIRouter

from app.schemas.analyses import AnalysisInput, AnalysisResponse
from app.services.cashflow import analyze

router = APIRouter()


@router.post("/preview", response_model=AnalysisResponse, summary="입력값으로 현금흐름·Runway 미리보기")
def preview_analysis(data: AnalysisInput) -> AnalysisResponse:
    return analyze(data)
