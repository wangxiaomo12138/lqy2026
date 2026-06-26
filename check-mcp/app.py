"""
check-mcp Flask API 服务（推荐，对接平台 API/工作流节点）

启动：
  cd check-mcp && pip install -r requirements.txt
  python app.py
  默认 http://0.0.0.0:8200

API：
  POST /api/v1/check/evaluate
  GET  /api/v1/tasks
  GET  /health

MCP SSE 请用 server_mcp.py（需 FastAPI）
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from core import CHECK_EVALUATE_TOOL_SCHEMA, list_tasks, run_evaluate

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "framework": "flask",
        "api": {
            "evaluate": "POST /api/v1/check/evaluate",
            "tasks": "GET /api/v1/tasks",
        },
    })


@app.get("/")
def root():
    return jsonify({
        "service": "check-mcp",
        "version": "0.4.0",
        "framework": "flask",
        "api": {
            "evaluate": "POST /api/v1/check/evaluate",
            "tasks": "GET /api/v1/tasks",
        },
        "legacy": {"tools": "GET /mcp/tools", "call": "POST /mcp/tools/call"},
        "mcp_sse": "python server_mcp.py（可选）",
        "health": "/health",
    })


@app.get("/api/v1/tasks")
def api_list_tasks():
    return jsonify(list_tasks())


@app.post("/api/v1/check/evaluate")
def api_evaluate():
    body = request.get_json(silent=True) or {}
    if "output" not in body:
        return jsonify({"error": "缺少字段 output"}), 400
    result = run_evaluate(body)
    if "error" in result:
        return jsonify({"error": result["error"]}), 400
    return jsonify(result)


@app.get("/mcp/tools")
def list_tools_legacy():
    return jsonify({"tools": [CHECK_EVALUATE_TOOL_SCHEMA]})


@app.post("/mcp/tools/call")
def call_tool_legacy():
    body = request.get_json(silent=True) or {}
    if body.get("tool") != "check.evaluate":
        return jsonify({"error": f"unknown tool: {body.get('tool')}"}), 400
    result = run_evaluate(body.get("arguments", {}))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8200, debug=False)
