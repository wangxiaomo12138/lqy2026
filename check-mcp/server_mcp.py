"""
check-mcp MCP SSE 服务（可选，仅平台 MCP 接入时需要）

启动：
  python server_mcp.py
  MCP 地址：http://HOST:8200/sse

日常 API 接入请用：python app.py（Flask）
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from mcp import types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from pydantic import BaseModel, Field
from starlette.responses import Response
from starlette.routing import Mount

from core import CHECK_EVALUATE_TOOL_SCHEMA, list_tasks, run_evaluate

CHECK_EVALUATE_TOOL = types.Tool(**CHECK_EVALUATE_TOOL_SCHEMA)

mcp_server = Server("check-mcp")
sse_transport = SseServerTransport("/messages/")

app = FastAPI(title="check-mcp-mcp", version="0.4.0")


class EvaluateRequest(BaseModel):
    task_type: str = Field(default="contract-parse")
    output: dict | str
    expected_fields: list[str] = Field(default_factory=list)
    summary: str = Field(default="")
    rules: list[str] = Field(default_factory=list)


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


@app.get("/sse")
async def handle_sse(request: Request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())
    return Response()


app.router.routes.append(Mount("/messages", app=sse_transport.handle_post_message))


@app.post("/api/v1/check/evaluate")
def api_evaluate(req: EvaluateRequest):
    from fastapi import HTTPException

    result = run_evaluate(req.model_dump())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/v1/tasks")
def api_list_tasks():
    return list_tasks()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8200)
