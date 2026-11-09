from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.database.persistence import SupabaseRepository
from app.dependencies.auth import get_repository
from app.schemas.store_settings import (
    IngredientCostSave, IngredientCostsResponse, NotificationsResponse, Preferences, PreferencesResponse, TaxSettings,
    TaxSettingsResponse,
)
from app.services import store_settings as service

router = APIRouter()
Repo = Annotated[SupabaseRepository, Depends(get_repository)]


@router.get("/{store_id}/tax-settings", response_model=TaxSettingsResponse, summary="세금 설정과 다가오는 세무 일정")
def get_tax_settings(store_id: UUID, repo: Repo) -> TaxSettingsResponse:
    return service.get_tax_settings(repo, store_id)


@router.put("/{store_id}/tax-settings", response_model=TaxSettingsResponse, summary="세금 설정 저장")
def save_tax_settings(store_id: UUID, data: TaxSettings, repo: Repo) -> TaxSettingsResponse:
    return service.save_tax_settings(repo, store_id, data)


@router.get("/{store_id}/preferences", response_model=PreferencesResponse, summary="알림·화면 설정")
def get_preferences(store_id: UUID, repo: Repo) -> PreferencesResponse:
    return service.get_preferences(repo, store_id)


@router.put("/{store_id}/preferences", response_model=PreferencesResponse, summary="알림·화면 설정 저장")
def save_preferences(store_id: UUID, data: Preferences, repo: Repo) -> PreferencesResponse:
    return service.save_preferences(repo, store_id, data)


@router.get("/{store_id}/ingredient-costs", response_model=IngredientCostsResponse,
            summary="매장 원재료 단가·월 지출 영향·런웨이 영향")
def get_ingredient_costs(store_id: UUID, repo: Repo) -> IngredientCostsResponse:
    return service.get_ingredient_costs(repo, store_id)


@router.put("/{store_id}/ingredient-costs", response_model=IngredientCostsResponse, summary="매장 원재료 단가 저장(전체 교체)")
def save_ingredient_costs(store_id: UUID, data: IngredientCostSave, repo: Repo) -> IngredientCostsResponse:
    return service.save_ingredient_costs(repo, store_id, data)


@router.get("/{store_id}/notifications", response_model=NotificationsResponse,
            summary="앱 내 알림 목록 (런웨이·원재료·지출·세금, 발송 없음)")
def get_notifications(store_id: UUID, repo: Repo) -> NotificationsResponse:
    return service.get_notifications(repo, store_id)
