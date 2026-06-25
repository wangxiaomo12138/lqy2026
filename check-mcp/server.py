"""
check-mcp：给 Agent 用的「执行结果检查」工具（无需改平台底层）

Agent 在工作流执行后调用 check.evaluate：
  - passed=true  → 可以总结输出了
  - passed=false → 返回 failure_points，供下一轮重规划

启动：
  cd check-mcp && pip install -r requirements.txt
  python server.py
  默认 http://127.0.0.1:8200
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="check-mcp", version="0.1.0")


class EvaluateRequest(BaseModel):
    task_type: str = Field(description="任务类型，如 contract-parse")
    output: dict | str = Field(description="工作流/总结输出，dict 或文本")
    expected_fields: list[str] = Field(default_factory=list, description="期望有的字段")
    rules: list[str] = Field(default_factory=list, description="额外规则")


def _normalize(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _parse_output(output: dict | str) -> dict:
    """尽量从输出里拿到 dict"""
    if isinstance(output, dict):
        return output
    text = str(output)
    # 尝试从文本里抠 JSON（简化版）
    import json
    import re
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"_raw_text": text}


def evaluate_contract(output: dict, expected_fields: list[str]) -> dict:
    failures = []
    missing = []
    for f in expected_fields:
        val = output.get(f)
        if val is None or _normalize(val) == "":
            missing.append(f)
            failures.append({"type": "missing_field", "field": f})

    # 日期格式
    if "sign_date" in output and output.get("sign_date"):
        sd = str(output["sign_date"])
        if len(sd) != 10 or sd[4] != "-" or sd[7] != "-":
            failures.append({"type": "format_error", "field": "sign_date", "message": "应为 YYYY-MM-DD"})

    # 金额应为数字
    if "amount" in output and output.get("amount") is not None:
        try:
            float(output["amount"])
        except (TypeError, ValueError):
            failures.append({"type": "format_error", "field": "amount", "message": "应为数字"})

    total = len(expected_fields) or 1
    correct = total - len(missing)
    score = round(correct / total, 4)
    passed = len(failures) == 0 and score >= 0.8

    return {
        "passed": passed,
        "score": score,
        "failure_points": {
            "missing_fields": missing,
            "failures": failures,
        },
        "recommendation": "补全缺失字段后重试" if not passed else "可进入最终总结",
    }


EVALUATORS = {
    "contract-parse": evaluate_contract,
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/mcp/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": "check.evaluate",
                "description": "检查工作流输出是否达标。passed=false 时返回 failure_points 供重规划。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_type": {"type": "string"},
                        "output": {},
                        "expected_fields": {"type": "array", "items": {"type": "string"}},
                        "rules": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["task_type", "output"],
                },
            }
        ]
    }


@app.post("/mcp/tools/call")
def call_tool(body: dict):
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool != "check.evaluate":
        return {"error": f"unknown tool: {tool}"}

    task_type = args.get("task_type", "contract-parse")
    output = _parse_output(args.get("output", {}))
    expected_fields = args.get("expected_fields", [])

    fn = EVALUATORS.get(task_type)
    if not fn:
        return {"error": f"unknown task_type: {task_type}"}

    result = fn(output, expected_fields)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8200)
