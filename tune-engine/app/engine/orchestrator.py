"""调优引擎核心 —— 整个循环在这里"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.clients.agent_platform import get_agent_client
from app.engine.patch_proposer import diagnose, propose_patch
from app.evaluators.contract_evaluator import aggregate_eval_results, criteria_met, evaluate_output
from app.models.tune_models import BenchmarkCase, ConfigVersion, TargetRegistry, TuneIter, TuneRun, TuneSession


def _new_session_id() -> str:
    return f"ts_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:8]}"


def create_tune_session(
    db: Session,
    target_id: str,
    mode: str = "full_auto",
    entry_ref: str | None = None,
    success_criteria_override: dict | None = None,
    constraints_override: dict | None = None,
    input_payload: dict | None = None,
) -> TuneSession:
    """创建调优会话"""
    target = db.query(TargetRegistry).filter(TargetRegistry.target_id == target_id).first()
    if not target:
        raise ValueError(f"Target 不存在: {target_id}")

    config = target.config_json
    start_ref = entry_ref or target.entry_ref
    success_criteria = success_criteria_override or config.get("success_criteria", {})
    constraints = {**config.get("constraints", {}), **(constraints_override or {})}

    session = TuneSession(
        session_id=_new_session_id(),
        target_id=target_id,
        status="pending",
        mode=mode,
        start_entry_ref=start_ref,
        current_entry_ref=start_ref,
        success_criteria_json=success_criteria,
        constraints_json=constraints,
        max_iters=constraints.get("max_tune_iters", 8),
        input_payload_json=input_payload,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def run_benchmark(db: Session, session: TuneSession, entry_ref: str, iter_no: int, target: TargetRegistry) -> list[dict]:
    """对测试集里每个 case 调用 Agent，返回评估结果列表"""
    agent = get_agent_client()
    suite_id = target.benchmark_suite_id
    cases = (
        db.query(BenchmarkCase)
        .filter(BenchmarkCase.suite_id == suite_id, BenchmarkCase.enabled.is_(True))
        .all()
    )

    case_results = []
    for case in cases:
        run_id = _new_run_id()
        try:
            agent_resp = agent.run(entry_ref, case.input_json, case.ground_truth_json)

            output = agent_resp.get("output", {})
            eval_detail = evaluate_output(target.evaluator_id, output, case.ground_truth_json or {})

            tune_run = TuneRun(
                run_id=run_id,
                session_id=session.session_id,
                iter_no=iter_no,
                case_id=case.case_id,
                entry_ref=entry_ref,
                status=agent_resp.get("status", "success"),
                input_json=case.input_json,
                output_json=output,
                trace_json=agent_resp.get("plan_trace"),
                summary_text=agent_resp.get("summary"),
                eval_score=eval_detail["score"],
                eval_passed=eval_detail["passed"],
                eval_detail_json=eval_detail,
                latency_ms=agent_resp.get("latency_ms"),
                cost_tokens=agent_resp.get("cost_tokens"),
            )
            db.add(tune_run)

            case_results.append({
                "case_id": case.case_id,
                "score": eval_detail["score"],
                "passed": eval_detail["passed"],
                "failures": eval_detail.get("failures", []),
                "weight": case.weight,
                "output": output,
            })
        except Exception as e:
            tune_run = TuneRun(
                run_id=run_id,
                session_id=session.session_id,
                iter_no=iter_no,
                case_id=case.case_id,
                entry_ref=entry_ref,
                status="error",
                input_json=case.input_json,
                error_message=str(e),
            )
            db.add(tune_run)
            case_results.append({
                "case_id": case.case_id,
                "score": 0.0,
                "passed": False,
                "failures": [{"reason": str(e)}],
                "weight": case.weight,
            })

    db.commit()
    return case_results


def should_stop(session: TuneSession, scores_history: list[float], iter_no: int) -> str | None:
    """检查是否应该停止（未达标情况下）"""
    constraints = session.constraints_json or {}
    max_iters = constraints.get("max_tune_iters", session.max_iters)

    if iter_no >= max_iters:
        return "max_iters"

    window = constraints.get("stagnation_window", 3)
    min_delta = constraints.get("min_delta", 0.02)

    if len(scores_history) >= window:
        recent = scores_history[-window:]
        if max(recent) - min(recent) < min_delta:
            return "stagnation"

    return None


def run_session(db: Session, session_id: str) -> dict[str, Any]:
    """
    ★★★ 主循环：这是整个系统的心脏 ★★★

    流程：
    1. 跑 benchmark
    2. 评估
    3. 达标 → optimal，返回
    4. 未达标 → 归因 → 打补丁 → 新版本再跑
  5. 到上限 → best_effort，返回当前最优
    """
    session = db.query(TuneSession).filter(TuneSession.session_id == session_id).first()
    if not session:
        raise ValueError(f"Session 不存在: {session_id}")

    target = db.query(TargetRegistry).filter(TargetRegistry.target_id == session.target_id).first()
    if not target:
        raise ValueError(f"Target 不存在: {session.target_id}")

    agent = get_agent_client()
    session.status = "running"
    db.commit()

    config = target.config_json
    patchable = config.get("patchable_components", ["skill"])
    scores_history: list[float] = []

    best_score = -1.0
    best_ref = session.current_entry_ref
    best_artifact: dict | None = None
    best_metrics: dict | None = None

    try:
        for iter_no in range(1, session.max_iters + 1):
            session.current_iter = iter_no
            entry_ref = session.current_entry_ref
            db.commit()

            iter_rec = TuneIter(
                session_id=session.session_id,
                iter_no=iter_no,
                entry_ref=entry_ref,
                status="running",
            )
            db.add(iter_rec)
            db.commit()

            # ---- 1. 跑 benchmark ----
            case_results = run_benchmark(db, session, entry_ref, iter_no, target)
            eval_result = aggregate_eval_results(case_results)
            score = eval_result["aggregate_score"]
            scores_history.append(score)

            iter_rec.score = score
            iter_rec.pass_rate = eval_result["pass_rate"]
            iter_rec.metrics_json = eval_result["metrics"]
            iter_rec.eval_json = eval_result

            # 更新最优
            if score > best_score:
                best_score = score
                best_ref = entry_ref
                best_metrics = eval_result["metrics"]
                # 取第一个 case 的输出作为 artifact 样例
                if case_results:
                    best_artifact = {
                        "case_id": case_results[0].get("case_id"),
                        "output": case_results[0].get("output"),
                    }

            session.best_entry_ref = best_ref
            session.best_score = best_score
            session.best_metrics_json = best_metrics
            db.commit()

            # ---- 2. 达标？----
            if criteria_met(eval_result, session.success_criteria_json):
                iter_rec.status = "completed"
                iter_rec.finished_at = datetime.utcnow()
                session.status = "optimal"
                session.criteria_met = True
                session.stop_reason = "target_met"
                session.finished_at = datetime.utcnow()
                db.commit()
                return build_result(session, best_ref, best_score, best_metrics, best_artifact)

            # ---- 3. 该停了吗？----
            stop = should_stop(session, scores_history, iter_no)
            if stop:
                iter_rec.status = "completed"
                iter_rec.finished_at = datetime.utcnow()
                session.status = "best_effort"
                session.stop_reason = stop
                session.finished_at = datetime.utcnow()
                db.commit()
                return build_result(session, best_ref, best_score, best_metrics, best_artifact, not_met=True)

            # evaluate_only 模式不补丁
            if session.mode == "evaluate_only":
                iter_rec.status = "completed"
                iter_rec.finished_at = datetime.utcnow()
                db.commit()
                continue

            # ---- 4. 归因 + 补丁 ----
            diag = diagnose(eval_result)
            patch = propose_patch(diag, patchable)
            iter_rec.diagnosis_json = diag
            iter_rec.patch_json = patch
            iter_rec.patch_type = patch.get("target_type")

            if session.mode == "dry_run" or patch.get("type") == "none":
                iter_rec.status = "completed"
                iter_rec.finished_at = datetime.utcnow()
                db.commit()
                continue

            # ---- 5. 应用补丁，生成新版本 ----
            candidate_ref = agent.apply_patch(entry_ref, patch)
            iter_rec.candidate_entry_ref = candidate_ref
            iter_rec.patch_applied = True

            # 保存配置版本（已存在则跳过）
            version_no = int(candidate_ref.split("@v")[-1]) if "@v" in candidate_ref else 1
            existing_cv = db.query(ConfigVersion).filter(ConfigVersion.ref == candidate_ref).first()
            if not existing_cv:
                cv = ConfigVersion(
                    ref=candidate_ref,
                    component_type=patch.get("type", "skill"),
                    component_id=patch.get("component_id", "unknown"),
                    version_no=version_no,
                    config_json=patch,
                    parent_ref=entry_ref,
                    patch_json=patch,
                    created_by="tune_engine",
                )
                db.add(cv)

            # MVP：补丁后直接晋升（真实环境应 shadow_compare）
            session.current_entry_ref = candidate_ref
            target.entry_ref = candidate_ref
            iter_rec.promoted = True
            iter_rec.shadow_compare_json = {"improved": True, "note": "MVP 跳过 shadow，直接晋升"}

            iter_rec.status = "completed"
            iter_rec.finished_at = datetime.utcnow()
            db.commit()

        # 跑满轮数
        session.status = "best_effort"
        session.stop_reason = "max_iters"
        session.finished_at = datetime.utcnow()
        db.commit()
        return build_result(session, best_ref, best_score, best_metrics, best_artifact, not_met=True)

    except Exception as e:
        session.status = "failed"
        session.error_message = str(e)
        session.finished_at = datetime.utcnow()
        db.commit()
        raise


def build_result(
    session: TuneSession,
    best_ref: str,
    best_score: float,
    best_metrics: dict | None,
    best_artifact: dict | None,
    not_met: bool = False,
) -> dict[str, Any]:
    recommendations = []
    if not_met:
        recommendations = [
            "增加 benchmark 样本数量",
            "检查 evaluator 标准是否过严",
            "尝试允许修改 workflow 而不仅是 skill",
            f"当前最优版本 {best_ref}，可人工检查后手动晋升",
        ]

    return {
        "session_id": session.session_id,
        "status": session.status,
        "target_id": session.target_id,
        "best_entry_ref": best_ref,
        "score": best_score,
        "metrics": best_metrics,
        "success_criteria": session.success_criteria_json,
        "criteria_met": session.criteria_met,
        "total_iters": session.current_iter,
        "stop_reason": session.stop_reason,
        "artifact": best_artifact,
        "recommendations": recommendations,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
    }


def get_session_status(db: Session, session_id: str, include_iters: bool = False) -> dict:
    session = db.query(TuneSession).filter(TuneSession.session_id == session_id).first()
    if not session:
        raise ValueError(f"Session 不存在: {session_id}")

    progress = (session.current_iter / session.max_iters * 100) if session.max_iters else 0

    result = {
        "session_id": session.session_id,
        "status": session.status,
        "target_id": session.target_id,
        "current_iter": session.current_iter,
        "max_iters": session.max_iters,
        "progress_pct": round(progress, 1),
        "best": {
            "entry_ref": session.best_entry_ref,
            "score": session.best_score,
            "pass_rate": session.best_metrics_json.get("field_f1") if session.best_metrics_json else None,
            "metrics": session.best_metrics_json,
        } if session.best_entry_ref else None,
        "success_criteria": session.success_criteria_json,
        "criteria_met": session.criteria_met,
        "stop_reason": session.stop_reason,
        "updated_at": session.updated_at,
    }

    if include_iters:
        iters = (
            db.query(TuneIter)
            .filter(TuneIter.session_id == session_id)
            .order_by(TuneIter.iter_no)
            .all()
        )
        result["iters"] = [
            {
                "iter_no": it.iter_no,
                "entry_ref": it.entry_ref,
                "score": it.score,
                "pass_rate": it.pass_rate,
                "patch_applied": it.patch_applied,
                "patch_type": it.patch_type,
                "promoted": it.promoted,
            }
            for it in iters
        ]

    return result
