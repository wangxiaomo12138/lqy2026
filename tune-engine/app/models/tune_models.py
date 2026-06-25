"""数据库表模型"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TargetRegistry(Base):
    __tablename__ = "target_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    entry_ref: Mapped[str] = mapped_column(String(128))
    config_json: Mapped[dict] = mapped_column(JSON)
    benchmark_suite_id: Mapped[str] = mapped_column(String(64))
    evaluator_id: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BenchmarkCase(Base):
    __tablename__ = "benchmark_case"
    __table_args__ = (UniqueConstraint("suite_id", "case_id", name="uk_suite_case"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suite_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict] = mapped_column(JSON)
    ground_truth_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TuneSession(Base):
    __tablename__ = "tune_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    mode: Mapped[str] = mapped_column(String(32), default="full_auto")

    start_entry_ref: Mapped[str] = mapped_column(String(128))
    current_entry_ref: Mapped[str] = mapped_column(String(128))
    best_entry_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    success_criteria_json: Mapped[dict] = mapped_column(JSON)
    constraints_json: Mapped[dict] = mapped_column(JSON)

    current_iter: Mapped[int] = mapped_column(Integer, default=0)
    max_iters: Mapped[int] = mapped_column(Integer, default=8)
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criteria_met: Mapped[bool] = mapped_column(Boolean, default=False)

    total_cost_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TuneIter(Base):
    __tablename__ = "tune_iter"
    __table_args__ = (UniqueConstraint("session_id", "iter_no", name="uk_session_iter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    iter_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="running")

    entry_ref: Mapped[str] = mapped_column(String(128))
    candidate_entry_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    eval_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    diagnosis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    patch_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    patch_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    patch_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    shadow_compare_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    cost_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TuneRun(Base):
    __tablename__ = "tune_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    iter_no: Mapped[int] = mapped_column(Integer)
    case_id: Mapped[str] = mapped_column(String(64))
    entry_ref: Mapped[str] = mapped_column(String(128))

    status: Mapped[str] = mapped_column(String(32))
    input_json: Mapped[dict] = mapped_column(JSON)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trace_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    eval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    eval_detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConfigVersion(Base):
    __tablename__ = "config_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    component_type: Mapped[str] = mapped_column(String(32))
    component_id: Mapped[str] = mapped_column(String(64))
    version_no: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict] = mapped_column(JSON)
    parent_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    patch_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
