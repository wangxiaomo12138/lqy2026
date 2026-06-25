"""
check-mcp：给 Agent 用的「执行结果检查」工具（无需改平台底层）

传输方式：
  - 标准 MCP SSE（平台接入用这个）
    GET  /sse              建立 SSE 连接
    POST /messages/?session_id=...  客户端发 JSON-RPC
  - 兼容旧版 REST（curl / 自测）
    GET  /mcp/tools
    POST /mcp/tools/call

启动：
  cd check-mcp && pip install -r requirements.txt
  python server.py
  默认 http://127.0.0.1:8200
  平台挂 MCP 地址：http://HOST:8200/sse
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from mcp import types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.responses import Response
from starlette.routing import Mount

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.evaluators import EVALUATORS, parse_output  # noqa: E402

CHECK_EVALUATE_TOOL = types.Tool(
    name="check.evaluate",
    description="检查工作流输出是否达标。passed=false 时返回 failure_points 供重规划。",
    inputSchema={
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
)

mcp_server = Server("check-mcp")
sse_transport = SseServerTransport("/messages/")

app = FastAPI(title="check-mcp", version="0.2.0")


def run_evaluate(arguments: dict[str, Any]) -> dict[str, Any]:
    task_type = arguments.get("task_type", "contract-parse")
    output = parse_output(arguments.get("output", {}))
    expected_fields = arguments.get("expected_fields", [])
    summary = arguments.get("summary", "")

    fn = EVALUATORS.get(task_type)
    if not fn:
        return {"error": f"unknown task_type: {task_type}"}

    return fn(output, expected_fields, summary=summary)


@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [CHECK_EVALUATE_TOOL]


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name != "check.evaluate":
        raise ValueError(f"unknown tool: {name}")

    result = run_evaluate(arguments)
    if "error" in result:
        raise ValueError(result["error"])

    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


@app.get("/health")
def health():
    return {"status": "ok", "transport": "sse", "sse_url": "/sse"}


@app.get("/")
def root():
    return {
        "service": "check-mcp",
        "mcp_sse": "/sse",
        "mcp_messages": "/messages/",
        "legacy": {"tools": "/mcp/tools", "call": "/mcp/tools/call"},
        "health": "/health",
    }


@app.get("/sse")
async def handle_sse(request: Request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())
    return Response()


app.router.routes.append(Mount("/messages", app=sse_transport.handle_post_message))


@app.get("/mcp/tools")
def list_tools_legacy():
    tool = CHECK_EVALUATE_TOOL.model_dump(by_alias=True, exclude_none=True)
    return {"tools": [tool]}


@app.post("/mcp/tools/call")
def call_tool_legacy(body: dict):
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool != "check.evaluate":
        return {"error": f"unknown tool: {tool}"}

    return run_evaluate(args)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8200)
