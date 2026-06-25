"""调优会话接口 —— 核心 API"""

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.engine.orchestrator import create_tune_session, get_session_status, run_session
from app.models.tune_models import TuneSession
from app.schemas.tune_schemas import TuneResultResponse, TuneSessionCreate, TuneSessionResponse, TuneStatusResponse

router = APIRouter(prefix="/api/v1/tune", tags=["tune"])


def _run_in_background(session_id: str):
    """后台线程执行调优循环"""
    db = SessionLocal()
    try:
        run_session(db, session_id)
    except Exception as e:
        session = db.query(TuneSession).filter(TuneSession.session_id == session_id).first()
        if session:
            session.status = "failed"
            session.error_message = str(e)
            db.commit()
    finally:
        db.close()


@router.post("/sessions", response_model=TuneSessionResponse)
def start_tune(body: TuneSessionCreate, db: Session = Depends(get_db)):
    """
    启动调优。

    async=true（默认）：立刻返回 session_id，后台跑。
    async=false：同步等待，直到 optimal 或 best_effort。
    """
    try:
        session = create_tune_session(
            db,
            target_id=body.target_id,
            mode=body.mode,
            entry_ref=body.entry_ref,
            success_criteria_override=body.success_criteria_override,
            constraints_override=body.constraints_override,
            input_payload=body.input_payload,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    if body.async_mode:
        thread = threading.Thread(target=_run_in_background, args=(session.session_id,), daemon=True)
        thread.start()
        return TuneSessionResponse(
            session_id=session.session_id,
            status="running",
            target_id=body.target_id,
            entry_ref=session.start_entry_ref,
            message="调优已在后台启动",
            created_at=session.created_at,
        )
    else:
        result = run_session(db, session.session_id)
        return TuneSessionResponse(
            session_id=session.session_id,
            status=result["status"],
            target_id=body.target_id,
            entry_ref=result["best_entry_ref"] or session.start_entry_ref,
            message=f"调优完成: {result['status']}",
            created_at=session.created_at,
        )


@router.get("/sessions/{session_id}", response_model=TuneStatusResponse)
def get_status(session_id: str, include_iters: bool = False, db: Session = Depends(get_db)):
    try:
        data = get_session_status(db, session_id, include_iters=include_iters)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return TuneStatusResponse(**data)


@router.get("/sessions/{session_id}/result", response_model=TuneResultResponse)
def get_result(session_id: str, db: Session = Depends(get_db)):
    session = db.query(TuneSession).filter(TuneSession.session_id == session_id).first()
    if not session:
        raise HTTPException(404, "Session 不存在")

    if session.status in ("pending", "running"):
        raise HTTPException(202, "仍在运行中，请稍后再查")

    recommendations = []
    if session.status == "best_effort":
        recommendations = [
            "未达目标阈值，建议增加样本或放宽 success_criteria",
            f"当前最优版本: {session.best_entry_ref}",
        ]

    best_run = None
    if session.best_entry_ref:
        from app.models.tune_models import TuneRun
        best_run = (
            db.query(TuneRun)
            .filter(TuneRun.session_id == session_id, TuneRun.entry_ref == session.best_entry_ref)
            .order_by(TuneRun.eval_score.desc())
            .first()
        )

    artifact = None
    if best_run:
        artifact = {"run_id": best_run.run_id, "case_id": best_run.case_id, "output": best_run.output_json}

    return TuneResultResponse(
        session_id=session.session_id,
        status=session.status,
        target_id=session.target_id,
        best_entry_ref=session.best_entry_ref,
        score=session.best_score,
        metrics=session.best_metrics_json,
        success_criteria=session.success_criteria_json,
        criteria_met=session.criteria_met,
        total_iters=session.current_iter,
        stop_reason=session.stop_reason,
        artifact=artifact,
        recommendations=recommendations,
        finished_at=session.finished_at,
    )


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(TuneSession).filter(TuneSession.session_id == session_id).first()
    if not session:
        raise HTTPException(404, "Session 不存在")
    session.status = "stopped"
    session.stop_reason = "manual_stop"
    db.commit()
    return {"session_id": session_id, "status": "stopped", "best_entry_ref": session.best_entry_ref}
