from fastapi import APIRouter

from app.schemas.support_programs import SupportCollection
from app.services.support_programs import latest_programs

router = APIRouter()


@router.get("", response_model=SupportCollection, summary="서울 소상공인 지원사업 공고(마감 전)")
def list_support_programs() -> SupportCollection:
    return latest_programs()
