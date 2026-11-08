from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.database.persistence import SupabaseRepository
from app.dependencies.auth import get_repository
from app.schemas.stores import (
    FinanceResponse, FinanceSave, StoreCreate, StoreResponse, StoreUpdate,
    StoredAnalysisResponse, StoredScenarioCreate, StoredScenarioResponse,
)
from app.services import stores as service

router = APIRouter()
Repo = Annotated[SupabaseRepository, Depends(get_repository)]


@router.post("", response_model=StoreResponse, status_code=201)
def create_store(data: StoreCreate, repo: Repo) -> StoreResponse:
    return service.create_store(repo, data)


@router.get("", response_model=list[StoreResponse])
def list_stores(repo: Repo, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                offset: Annotated[int, Query(ge=0)] = 0) -> list[StoreResponse]:
    return service.list_stores(repo, limit, offset)


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(store_id: UUID, repo: Repo) -> StoreResponse:
    return service.get_store(repo, store_id)


@router.patch("/{store_id}", response_model=StoreResponse)
def update_store(store_id: UUID, data: StoreUpdate, repo: Repo) -> StoreResponse:
    return service.update_store(repo, store_id, data)


@router.put("/{store_id}/finances", response_model=FinanceResponse)
def save_finances(store_id: UUID, data: FinanceSave, repo: Repo) -> FinanceResponse:
    return service.save_finances(repo, store_id, data)


@router.get("/{store_id}/finances", response_model=FinanceResponse)
def get_finances(store_id: UUID, repo: Repo) -> FinanceResponse:
    return service.get_finances(repo, store_id)


@router.post("/{store_id}/analyses", response_model=StoredAnalysisResponse, status_code=201)
def create_analysis(store_id: UUID, repo: Repo) -> StoredAnalysisResponse:
    return service.create_analysis(repo, store_id)


@router.get("/{store_id}/analyses/{analysis_id}", response_model=StoredAnalysisResponse)
def get_analysis(store_id: UUID, analysis_id: UUID, repo: Repo) -> StoredAnalysisResponse:
    return service.get_analysis(repo, store_id, analysis_id)


@router.post("/{store_id}/scenarios", response_model=StoredScenarioResponse, status_code=201)
def create_scenario(store_id: UUID, data: StoredScenarioCreate, repo: Repo) -> StoredScenarioResponse:
    return service.create_scenario(repo, store_id, data)


@router.get("/{store_id}/scenarios/{scenario_id}/comparison", response_model=StoredScenarioResponse)
def get_scenario(store_id: UUID, scenario_id: UUID, repo: Repo) -> StoredScenarioResponse:
    return service.get_scenario(repo, store_id, scenario_id)
