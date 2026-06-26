"""check-mcp 核心评估逻辑（Flask / FastAPI 共用）"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.evaluators import EVALUATORS, parse_output  # noqa: E402

CHECK_EVALUATE_TOOL_SCHEMA = {
    "name": "check.evaluate",
    "description": "检查工作流输出是否达标。passed=false 时返回 failure_points 供重规划。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "task_type": {"type": "string", "description": "任务类型，如 contract-parse"},
            "output": {"description": "工作流/总结输出，dict 或文本"},
            "expected_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "期望有的字段",
            },
            "summary": {"type": "string", "description": "总结文本（可选，参与评分）"},
            "rules": {"type": "array", "items": {"type": "string"}, "description": "额外规则（预留）"},
        },
        "required": ["task_type", "output"],
    },
}


def run_evaluate(arguments: dict[str, Any]) -> dict[str, Any]:
    task_type = arguments.get("task_type", "contract-parse")
    output = parse_output(arguments.get("output", {}))
    expected_fields = arguments.get("expected_fields", [])
    summary = arguments.get("summary", "")

    fn = EVALUATORS.get(task_type)
    if not fn:
        return {"error": f"unknown task_type: {task_type}"}

    return fn(output, expected_fields, summary=summary)


def list_tasks() -> dict:
    return {
        "tasks": [
            {
                "task_type": name,
                "tool": "check.evaluate",
                "evaluate_url": "/api/v1/check/evaluate",
            }
            for name in EVALUATORS
        ]
    }
