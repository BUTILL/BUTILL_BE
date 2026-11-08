from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.analyses import Model


class SupportProgram(Model):
    source: Literal["BIZINFO"] = "BIZINFO"
    program_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    agency: str | None = None
    summary: str | None = None
    target: str | None = None
    category: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    apply_start: date | None = None
    apply_end: date | None = None
    apply_period_text: str | None = None
    always_open: bool = False
    url: str | None = None


class SupportCollection(Model):
    source: Literal["BIZINFO"] = "BIZINFO"
    collected_at: datetime
    status: Literal["success", "failed"]
    error_code: str | None = None
    fetched_count: int = 0
    skipped_count: int = 0
    matched_count: int = 0
    programs: list[SupportProgram]
