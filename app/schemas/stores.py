from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.analyses import AnalysisInput, AnalysisResponse, ComparisonResponse, Model, ScenarioInput


class StoreCreate(Model):
    name: str = Field(min_length=1, max_length=100)
    business_type: Literal["restaurant", "cafe"]
    region: str = Field(min_length=1, max_length=100)
    status: Literal["planning", "operating"] = "planning"


class StoreUpdate(Model):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    business_type: Literal["restaurant", "cafe"] | None = None
    region: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["planning", "operating"] | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set or any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError("변경할 필드를 하나 이상 입력하고 null은 사용하지 마세요.")
        return self


class StoreResponse(StoreCreate):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class FinanceSave(Model):
    input: AnalysisInput
    revision: UUID | None = None


class FinanceResponse(Model):
    store_id: UUID
    revision: UUID
    input: AnalysisInput
    created_at: datetime
    updated_at: datetime


class StoredAnalysisResponse(Model):
    id: UUID
    store_id: UUID
    source_revision: UUID
    input: AnalysisInput
    result: AnalysisResponse
    created_at: datetime
    persisted: Literal[True] = True


class StoredScenarioCreate(Model):
    base_analysis_id: UUID
    scenario: ScenarioInput


class StoredScenarioResponse(Model):
    id: UUID
    store_id: UUID
    base_analysis_id: UUID
    scenario: ScenarioInput
    comparison: ComparisonResponse
    created_at: datetime
    persisted: Literal[True] = True
