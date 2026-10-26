from uuid import UUID, uuid4
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.database.persistence import SupabaseRepository
from app.errors import DomainError
from app.schemas.analyses import ComparisonInput
from app.schemas.stores import (
    FinanceResponse, FinanceSave, StoreCreate, StoreResponse, StoreUpdate,
    StoredAnalysisResponse, StoredScenarioCreate, StoredScenarioResponse,
)
from app.services.cashflow import CALCULATION_VERSION, analyze
from app.services.scenarios import compare

Record = TypeVar("Record", bound=BaseModel)


def validate_record(model: type[Record], row: dict) -> Record:
    try:
        return model.model_validate(row)
    except ValidationError:
        raise DomainError("DB_UNAVAILABLE", "저장된 데이터의 형식을 확인할 수 없습니다.") from None


def first_row(rows: list[dict]) -> dict:
    if not rows:
        raise DomainError("DB_UNAVAILABLE", "저장 결과를 확인할 수 없습니다.")
    return rows[0]


def create_store(repo: SupabaseRepository, data: StoreCreate) -> StoreResponse:
    rows = repo.request("POST", "stores", data=data.model_dump() | {"user_id": repo.user_id})
    return validate_record(StoreResponse, first_row(rows))


def list_stores(repo: SupabaseRepository, limit: int, offset: int) -> list[StoreResponse]:
    rows = repo.request("GET", "stores", {"user_id": f"eq.{repo.user_id}", "select": "*",
        "order": "created_at.desc,id.desc", "limit": str(limit), "offset": str(offset)})
    return [validate_record(StoreResponse, r) for r in rows]


def get_store(repo: SupabaseRepository, store_id: UUID) -> StoreResponse:
    return validate_record(StoreResponse, repo.owned_store(store_id))


def update_store(repo: SupabaseRepository, store_id: UUID, data: StoreUpdate) -> StoreResponse:
    repo.owned_store(store_id)
    rows = repo.request("PATCH", "stores", {"id": f"eq.{store_id}", "user_id": f"eq.{repo.user_id}"}, data.model_dump(exclude_unset=True))
    if not rows:
        raise DomainError("NOT_FOUND", "매장을 찾을 수 없습니다.")
    return validate_record(StoreResponse, rows[0])


def get_finances(repo: SupabaseRepository, store_id: UUID) -> FinanceResponse:
    repo.owned_store(store_id)
    rows = repo.request("GET", "startup_plans", {"store_id": f"eq.{store_id}", "select": "*", "limit": "1"})
    if not rows:
        raise DomainError("NOT_FOUND", "경영정보를 먼저 저장하세요.")
    row = rows[0]
    try:
        return FinanceResponse.model_validate({k: row[k] for k in ("store_id", "revision", "input", "created_at", "updated_at")})
    except (ValidationError, KeyError):
        raise DomainError("SAVED_INPUT_INVALID", "저장된 경영정보의 형식을 확인하고 다시 저장하세요.") from None


def save_finances(repo: SupabaseRepository, store_id: UUID, data: FinanceSave) -> FinanceResponse:
    repo.owned_store(store_id)
    payload = {"store_id": str(store_id), "revision": str(uuid4()), "input": data.input.model_dump(mode="json")}
    if data.revision is None:
        rows = repo.request("POST", "startup_plans", data=payload)
    else:
        rows = repo.request("PATCH", "startup_plans", {"store_id": f"eq.{store_id}", "revision": f"eq.{data.revision}"}, payload)
    if not rows:
        raise DomainError("CONFLICT", "다른 곳에서 경영정보가 수정되었습니다. 다시 조회한 뒤 저장하세요.")
    row = rows[0]
    return validate_record(FinanceResponse, {k: row.get(k) for k in ("store_id", "revision", "input", "created_at", "updated_at")})


def create_analysis(repo: SupabaseRepository, store_id: UUID) -> StoredAnalysisResponse:
    finance = get_finances(repo, store_id)
    result = analyze(finance.input)
    result.persisted = True
    result.warnings = [w for w in result.warnings if w != "요청 입력값으로만 계산하며 DB에 저장하지 않습니다."]
    payload = {"store_id": str(store_id), "source_revision": str(finance.revision),
               "input": finance.input.model_dump(mode="json"), "result": result.model_dump(mode="json")}
    rows = repo.request("POST", "analysis_runs", data=payload)
    return validate_record(StoredAnalysisResponse, first_row(rows))


def get_analysis(repo: SupabaseRepository, store_id: UUID, analysis_id: UUID) -> StoredAnalysisResponse:
    repo.owned_store(store_id)
    rows = repo.request("GET", "analysis_runs", {"id": f"eq.{analysis_id}", "store_id": f"eq.{store_id}", "select": "*", "limit": "1"})
    if not rows:
        raise DomainError("NOT_FOUND", "분석 결과를 찾을 수 없습니다.")
    return validate_record(StoredAnalysisResponse, rows[0])


def create_scenario(repo: SupabaseRepository, store_id: UUID, data: StoredScenarioCreate) -> StoredScenarioResponse:
    base = get_analysis(repo, store_id, data.base_analysis_id)
    if base.result.calculation_version != CALCULATION_VERSION:
        raise DomainError("CALCULATION_VERSION_MISMATCH", "계산 기준이 변경되었습니다. 기본 분석을 다시 실행하세요.")
    try:
        request = ComparisonInput(base=base.input, scenarios=[data.scenario])
    except ValidationError:
        raise DomainError("INVALID_SCENARIO", "시나리오의 추가 지출·분석기간을 확인하세요.") from None
    comparison = compare(request)
    comparison.persisted = True
    comparison.base.persisted = True
    for item in [comparison.base, *[s.analysis for s in comparison.scenarios]]:
        item.persisted = True
        item.warnings = [w for w in item.warnings if w != "요청 입력값으로만 계산하며 DB에 저장하지 않습니다."]
    rows = repo.request("POST", "scenarios", data={"store_id": str(store_id), "base_analysis_id": str(base.id),
        "scenario": data.scenario.model_dump(mode="json"), "comparison": comparison.model_dump(mode="json")})
    return validate_record(StoredScenarioResponse, first_row(rows))


def get_scenario(repo: SupabaseRepository, store_id: UUID, scenario_id: UUID) -> StoredScenarioResponse:
    repo.owned_store(store_id)
    rows = repo.request("GET", "scenarios", {"id": f"eq.{scenario_id}", "store_id": f"eq.{store_id}", "select": "*", "limit": "1"})
    if not rows:
        raise DomainError("NOT_FOUND", "시나리오를 찾을 수 없습니다.")
    return validate_record(StoredScenarioResponse, rows[0])
