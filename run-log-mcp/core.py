"""run-log-mcp 核心逻辑（Flask / FastAPI 共用）"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.evaluators import EVALUATORS, parse_output  # noqa: E402

DATA_DIR = ROOT / "data"
RUN_LOGS_FILE = DATA_DIR / "run_logs.jsonl"
FAILURE_CASES_FILE = DATA_DIR / "failure_cases.jsonl"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, record: dict):
    _ensure_data_dir()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_compare(a, b) -> bool:
    if a is None or b is None:
        return False
    sa, sb = str(a).strip().lower(), str(b).strip().lower()
    try:
        if float(sa) == float(sb):
            return True
    except ValueError:
        pass
    return sa == sb


def _score_with_ground_truth(output: dict, ground_truth: dict) -> dict:
    fields = list(ground_truth.keys())
    correct = sum(1 for f in fields if normalize_compare(output.get(f), ground_truth.get(f)))
    score = round(correct / len(fields), 4) if fields else 0.0
    failures = [
        {"field": f, "expected": ground_truth.get(f), "actual": output.get(f)}
        for f in fields
        if not normalize_compare(output.get(f), ground_truth.get(f))
    ]
    return {
        "passed": score >= 0.8 and len(failures) <= 1,
        "score": score,
        "field_score": score,
        "summary_score": 1.0,
        "failure_points": {"failures": failures, "missing_fields": []},
        "scored_by": "ground_truth",
    }


def log_run(data: dict[str, Any]) -> dict[str, Any]:
    target_id = data.get("target_id")
    query = data.get("query")
    if not target_id or not query:
        return {"error": "缺少 target_id 或 query"}

    task_type = data.get("task_type", "contract-parse")
    parsed_output = parse_output(data.get("output", {}))
    expected = data.get("expected_fields") or list((data.get("ground_truth") or {}).keys())
    check_result = data.get("check_result")

    if check_result and "passed" in check_result:
        eval_result = {
            "passed": check_result["passed"],
            "score": check_result.get("score", 0),
            "field_score": check_result.get("field_score", check_result.get("score", 0)),
            "summary_score": check_result.get("summary_score", 1.0),
            "failure_points": check_result.get("failure_points", {}),
            "scored_by": "check_result",
        }
    elif data.get("ground_truth"):
        eval_result = _score_with_ground_truth(parsed_output, data["ground_truth"])
    else:
        fn = EVALUATORS.get(task_type)
        if not fn:
            return {"error": f"unknown task_type: {task_type}"}
        eval_result = fn(parsed_output, expected, data.get("summary", ""))
        eval_result["scored_by"] = "auto_rules"

    case_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    record = {
        "case_id": case_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_id": target_id,
        "task_type": task_type,
        "agent_id": data.get("agent_id"),
        "entry_ref": data.get("entry_ref"),
        "attempt": data.get("attempt", 1),
        "input": {"query": query},
        "output": parsed_output,
        "summary": data.get("summary", ""),
        "plan_trace": data.get("plan_trace", []),
        "expected_fields": expected,
        "ground_truth": data.get("ground_truth"),
        "eval": {
            "passed": eval_result["passed"],
            "score": eval_result["score"],
            "field_score": eval_result.get("field_score"),
            "summary_score": eval_result.get("summary_score"),
            "failure_points": eval_result.get("failure_points", {}),
            "scored_by": eval_result.get("scored_by"),
        },
        "tags": ["online", "passed" if eval_result["passed"] else "failed"],
    }

    _append_jsonl(RUN_LOGS_FILE, record)

    saved_to = ["run_logs.jsonl"]
    tune_importable = False

    if not eval_result["passed"]:
        failure_record = {
            "case_id": case_id,
            "source": "run-log-mcp",
            "timestamp": record["timestamp"],
            "target_id": target_id,
            "input": {"query": query},
            "output": parsed_output,
            "summary": data.get("summary", ""),
            "failure_points": eval_result.get("failure_points", {}),
            "eval_score": eval_result["score"],
            "ground_truth": data.get("ground_truth"),
            "tags": ["online", "failed", task_type],
            "weight": 1.2,
            "tune_import_ready": data.get("ground_truth") is not None,
        }
        _append_jsonl(FAILURE_CASES_FILE, failure_record)
        saved_to.append("failure_cases.jsonl")
        tune_importable = data.get("ground_truth") is not None

    return {
        "logged": True,
        "case_id": case_id,
        "passed": eval_result["passed"],
        "score": eval_result["score"],
        "failure_points": eval_result.get("failure_points", {}),
        "saved_to": saved_to,
        "tune_import_ready": tune_importable,
        "note": (
            "无 ground_truth 的失败记录需人工补标准答案后再导入 Tune Engine"
            if not tune_importable and not eval_result["passed"]
            else ""
        ),
    }


def get_stats(target_id: str | None, limit: int) -> dict:
    if not RUN_LOGS_FILE.exists():
        return {"total": 0, "pass_rate": 0, "message": "暂无运行记录"}

    rows = []
    for line in RUN_LOGS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if target_id and row.get("target_id") != target_id:
            continue
        rows.append(row)

    rows = rows[-limit:]
    if not rows:
        return {"total": 0, "pass_rate": 0}

    passed = sum(1 for r in rows if r.get("eval", {}).get("passed"))
    return {
        "total": len(rows),
        "passed_count": passed,
        "pass_rate": round(passed / len(rows), 4),
        "target_id": target_id,
        "recent_failures": [
            {"case_id": r["case_id"], "score": r["eval"]["score"], "query": r["input"]["query"][:80]}
            for r in rows
            if not r.get("eval", {}).get("passed")
        ][-5:],
    }
