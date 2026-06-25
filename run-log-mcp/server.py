"""
run-log-mcp：收集平台每次运行的 output / summary，自动评分并写入 jsonl。

用途：
  - 记录每次 Agent 跑的结果（成功 + 失败）
  - 失败 case 自动写入 failure_cases.jsonl，供 Tune Engine 导入
  - 与 check-mcp 配合：check 决定是否重试，run.log 负责存档

启动：
  cd run-log-mcp && pip install -r requirements.txt
  python server.py
  默认 http://127.0.0.1:8300

数据文件（自动创建）：
  ../data/run_logs.jsonl        全部运行记录
  ../data/failure_cases.jsonl   仅 passed=false，可导入 Tune Engine
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.evaluators import EVALUATORS, parse_output

app = FastAPI(title="run-log-mcp", version="0.1.0")

DATA_DIR = ROOT / "data"
RUN_LOGS_FILE = DATA_DIR / "run_logs.jsonl"
FAILURE_CASES_FILE = DATA_DIR / "failure_cases.jsonl"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, record: dict):
    _ensure_data_dir()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class RunLogRequest(BaseModel):
    target_id: str = Field(description="如 contract-parse")
    task_type: str = Field(default="contract-parse")
    query: str = Field(description="用户原始 query")
    output: dict | str = Field(default_factory=dict, description="工作流结构化输出")
    summary: str = Field(default="", description="总结模型最终输出")
    plan_trace: list = Field(default_factory=list)
    expected_fields: list[str] = Field(default_factory=list)
    ground_truth: dict | None = Field(default=None, description="若已知标准答案可传入")
    attempt: int = Field(default=1, description="第几次尝试")
    agent_id: str | None = None
    entry_ref: str | None = None
    check_result: dict | None = Field(default=None, description="check.evaluate 的返回，可复用")


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


@app.get("/health")
def health():
    _ensure_data_dir()
    return {
        "status": "ok",
        "run_logs": str(RUN_LOGS_FILE),
        "failure_cases": str(FAILURE_CASES_FILE),
    }


@app.get("/mcp/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": "run.log",
                "description": "记录本次 Agent 运行的 query/output/summary，自动评分。失败时写入 failure_cases.jsonl 供 Tune Engine 调优。每次工作流执行并检查后必须调用。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string"},
                        "task_type": {"type": "string"},
                        "query": {"type": "string"},
                        "output": {},
                        "summary": {"type": "string"},
                        "plan_trace": {"type": "array"},
                        "expected_fields": {"type": "array", "items": {"type": "string"}},
                        "ground_truth": {"type": "object"},
                        "attempt": {"type": "integer"},
                        "agent_id": {"type": "string"},
                        "entry_ref": {"type": "string"},
                        "check_result": {"type": "object"},
                    },
                    "required": ["target_id", "query"],
                },
            },
            {
                "name": "run.stats",
                "description": "查看近期运行统计（通过率、样本数）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 100},
                    },
                },
            },
        ]
    }


@app.post("/mcp/tools/call")
def call_tool(body: dict):
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool == "run.stats":
        return get_stats(args.get("target_id"), args.get("limit", 100))

    if tool != "run.log":
        return {"error": f"unknown tool: {tool}"}

    return log_run(RunLogRequest(**args))


def log_run(req: RunLogRequest) -> dict:
    case_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    parsed_output = parse_output(req.output)
    expected = req.expected_fields or list((req.ground_truth or {}).keys())

    if req.check_result and "passed" in req.check_result:
        eval_result = {
            "passed": req.check_result["passed"],
            "score": req.check_result.get("score", 0),
            "field_score": req.check_result.get("score", 0),
            "summary_score": 1.0,
            "failure_points": req.check_result.get("failure_points", {}),
            "scored_by": "check_result",
        }
    elif req.ground_truth:
        eval_result = _score_with_ground_truth(parsed_output, req.ground_truth)
    else:
        fn = EVALUATORS.get(req.task_type)
        if not fn:
            return {"error": f"unknown task_type: {req.task_type}"}
        eval_result = fn(parsed_output, expected, req.summary)
        eval_result["scored_by"] = "auto_rules"

    record = {
        "case_id": case_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_id": req.target_id,
        "task_type": req.task_type,
        "agent_id": req.agent_id,
        "entry_ref": req.entry_ref,
        "attempt": req.attempt,
        "input": {"query": req.query},
        "output": parsed_output,
        "summary": req.summary,
        "plan_trace": req.plan_trace,
        "expected_fields": expected,
        "ground_truth": req.ground_truth,
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
            "target_id": req.target_id,
            "input": {"query": req.query},
            "output": parsed_output,
            "summary": req.summary,
            "failure_points": eval_result.get("failure_points", {}),
            "eval_score": eval_result["score"],
            "ground_truth": req.ground_truth,
            "tags": ["online", "failed", req.task_type],
            "weight": 1.2,
            "tune_import_ready": req.ground_truth is not None,
        }
        _append_jsonl(FAILURE_CASES_FILE, failure_record)
        saved_to.append("failure_cases.jsonl")
        tune_importable = req.ground_truth is not None

    return {
        "logged": True,
        "case_id": case_id,
        "passed": eval_result["passed"],
        "score": eval_result["score"],
        "failure_points": eval_result.get("failure_points", {}),
        "saved_to": saved_to,
        "tune_import_ready": tune_importable,
        "note": "无 ground_truth 的失败记录需人工补标准答案后再导入 Tune Engine" if not tune_importable and not eval_result["passed"] else "",
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
            for r in rows if not r.get("eval", {}).get("passed")
        ][-5:],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8300)
