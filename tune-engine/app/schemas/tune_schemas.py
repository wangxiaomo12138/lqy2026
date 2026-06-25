"""API 请求/响应格式（Pydantic）"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TargetCreate(BaseModel):
    target_id: str
    name: str
    description: str | None = None
    type: str
    entry_ref: str
    benchmark_suite_id: str
    evaluator_id: str
    patchable_components: list[str] = Field(default_factory=list)
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool = True
    version: int = 1


class BenchmarkCasesImport(BaseModel):
    suite_id: str
    cases: list[dict[str, Any]]


class TuneSessionCreate(BaseModel):
    target_id: str
    mode: str = "full_auto"
    async_mode: bool = Field(default=True, alias="async")
    entry_ref: str | None = None
    benchmark_suite_id: str | None = None
    success_criteria_override: dict[str, Any] | None = None
    constraints_override: dict[str, Any] | None = None
    input_payload: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class TuneSessionResponse(BaseModel):
    session_id: str
    status: str
    target_id: str
    entry_ref: str
    message: str | None = None
    created_at: datetime | None = None


class TuneStatusResponse(BaseModel):
    session_id: str
    status: str
    target_id: str
    current_iter: int
    max_iters: int
    progress_pct: float
    best: dict[str, Any] | None = None
    success_criteria: dict[str, Any]
    criteria_met: bool
    stop_reason: str | None = None
    iters: list[dict[str, Any]] | None = None
    updated_at: datetime | None = None


class TuneResultResponse(BaseModel):
    session_id: str
    status: str
    target_id: str
    best_entry_ref: str | None
    score: float | None
    metrics: dict[str, Any] | None = None
    success_criteria: dict[str, Any]
    criteria_met: bool
    total_iters: int
    stop_reason: str | None = None
    artifact: dict[str, Any] | None = None
    recommendations: list[str] = Field(default_factory=list)
    finished_at: datetime | None = None
