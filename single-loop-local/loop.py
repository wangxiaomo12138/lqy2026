"""
单次循环编排：执行 → 检查 → 重试 → 总结

不依赖 Agent 平台，直接调你们的模型服务 + 本地规则评估。
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.evaluators import EVALUATORS, parse_output  # noqa: E402

from model_client import ModelClient


@dataclass
class AttemptRecord:
    attempt: int
    prompt: str
    raw_response: str
    output: dict
    summary: str
    eval_result: dict


@dataclass
class LoopResult:
    status: str
    attempts: int
    query: str
    task_type: str
    best_output: dict
    best_summary: str
    best_eval: dict
    history: list[AttemptRecord] = field(default_factory=list)


EXECUTE_SYSTEM = """你是结构化信息抽取助手。严格按用户要求输出，不要多余解释。
若要求 JSON，只输出一个 JSON 对象，不要 markdown 代码块。"""

SUMMARY_SYSTEM = """你是结果总结助手。根据抽取结果写简短中文总结，并说明是否完整、有无遗留问题。"""


def run_single_loop(query: str, config: dict[str, Any]) -> LoopResult:
    model = ModelClient(config["model"])
    loop_cfg = config.get("loop", {})
    task_cfg = config.get("task", {})

    task_type = loop_cfg.get("task_type", "contract-parse")
    task_name = loop_cfg.get("task_name", task_type)
    max_attempts = int(loop_cfg.get("max_attempts", 3))
    expected_fields = list(task_cfg.get("expected_fields", []))
    output_schema = task_cfg.get("output_schema", "")

    evaluator = EVALUATORS.get(task_type)
    if not evaluator:
        raise ValueError(f"未知 task_type: {task_type}，请在 shared/evaluators.py 注册")

    history: list[AttemptRecord] = []
    failure_points: dict | None = None
    best_record: AttemptRecord | None = None

    for attempt in range(1, max_attempts + 1):
        execute_prompt = _build_execute_prompt(
            query=query,
            task_name=task_name,
            output_schema=output_schema,
            expected_fields=expected_fields,
            failure_points=failure_points,
            attempt=attempt,
        )

        raw = model.chat(EXECUTE_SYSTEM, execute_prompt)
        output = parse_output(raw)
        summary = _quick_summary(output, expected_fields)
        eval_result = evaluator(output, expected_fields, summary=summary)

        record = AttemptRecord(
            attempt=attempt,
            prompt=execute_prompt,
            raw_response=raw,
            output=output,
            summary=summary,
            eval_result=eval_result,
        )
        history.append(record)

        if best_record is None or eval_result.get("score", 0) >= best_record.eval_result.get("score", 0):
            best_record = record

        _append_log(config, query, task_type, record, expected_fields)

        if eval_result.get("passed"):
            final_summary = _summarize(model, query, output, eval_result, status="optimal")
            return LoopResult(
                status="optimal",
                attempts=attempt,
                query=query,
                task_type=task_type,
                best_output=output,
                best_summary=final_summary,
                best_eval=eval_result,
                history=history,
            )

        failure_points = eval_result.get("failure_points", {})

        if attempt >= 2 and not _score_improved(history):
            break

    assert best_record is not None
    final_summary = _summarize(
        model,
        query,
        best_record.output,
        best_record.eval_result,
        status="best_effort",
    )
    return LoopResult(
        status="best_effort",
        attempts=len(history),
        query=query,
        task_type=task_type,
        best_output=best_record.output,
        best_summary=final_summary,
        best_eval=best_record.eval_result,
        history=history,
    )


def _build_execute_prompt(
    *,
    query: str,
    task_name: str,
    output_schema: str,
    expected_fields: list[str],
    failure_points: dict | None,
    attempt: int,
) -> str:
    parts = [
        f"【任务】{task_name}",
        f"【用户输入】\n{query}",
        f"【输出要求】{output_schema}",
        f"【必须包含字段】{', '.join(expected_fields)}",
    ]
    if failure_points and attempt > 1:
        parts.extend(
            [
                "",
                "【上次执行问题】",
                json.dumps(failure_points, ensure_ascii=False, indent=2),
                "",
                "【重试要求】",
                "1. 针对上述问题修正",
                "2. 必须补全所有缺失字段",
                f"3. 输出格式: {output_schema}",
            ]
        )
    return "\n".join(parts)


def _quick_summary(output: dict, expected_fields: list[str]) -> str:
    parts = []
    for f in expected_fields:
        v = output.get(f)
        if v is not None and str(v).strip():
            parts.append(f"{f}={v}")
    return "；".join(parts) if parts else "暂无有效字段"


def _summarize(
    model: ModelClient,
    query: str,
    output: dict,
    eval_result: dict,
    status: str,
) -> str:
    user = (
        f"原始问题：{query}\n"
        f"抽取结果：{json.dumps(output, ensure_ascii=False)}\n"
        f"检查状态：{status}\n"
        f"评分：{json.dumps(eval_result, ensure_ascii=False)}\n"
        "请用 2-4 句话总结结果。"
    )
    return model.chat(SUMMARY_SYSTEM, user)


def _score_improved(history: list[AttemptRecord]) -> bool:
    if len(history) < 2:
        return True
    return history[-1].eval_result.get("score", 0) > history[-2].eval_result.get("score", 0)


def _append_log(
    config: dict[str, Any],
    query: str,
    task_type: str,
    record: AttemptRecord,
    expected_fields: list[str],
) -> None:
    log_cfg = config.get("logging", {})
    run_logs_path = Path(log_cfg.get("run_logs", "../data/run_logs.jsonl"))
    if not run_logs_path.is_absolute():
        run_logs_path = (Path(__file__).parent / run_logs_path).resolve()

    run_logs_path.parent.mkdir(parents=True, exist_ok=True)

    eval_result = record.eval_result
    row = {
        "case_id": f"local_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_id": task_type,
        "task_type": task_type,
        "agent_id": "single-loop-local",
        "entry_ref": None,
        "attempt": record.attempt,
        "input": {"query": query},
        "output": record.output,
        "summary": record.summary,
        "plan_trace": [],
        "expected_fields": expected_fields,
        "ground_truth": None,
        "eval": {
            "passed": eval_result.get("passed"),
            "score": eval_result.get("score"),
            "field_score": eval_result.get("field_score"),
            "summary_score": eval_result.get("summary_score"),
            "failure_points": eval_result.get("failure_points", {}),
            "scored_by": "local_rules",
        },
        "tags": ["local", "passed" if eval_result.get("passed") else "failed"],
        "source": "single-loop-local",
    }

    with run_logs_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if not eval_result.get("passed"):
        failure_path = Path(log_cfg.get("failure_cases", "../data/failure_cases.jsonl"))
        if not failure_path.is_absolute():
            failure_path = (Path(__file__).parent / failure_path).resolve()
        failure_row = {
            "case_id": row["case_id"],
            "source": "single-loop-local",
            "timestamp": row["timestamp"],
            "target_id": task_type,
            "input": {"query": query},
            "output": record.output,
            "summary": record.summary,
            "failure_points": eval_result.get("failure_points", {}),
            "eval_score": eval_result.get("score"),
            "ground_truth": None,
            "tags": ["local", "failed", task_type],
            "weight": 1.2,
            "tune_import_ready": False,
        }
        with failure_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(failure_row, ensure_ascii=False) + "\n")
