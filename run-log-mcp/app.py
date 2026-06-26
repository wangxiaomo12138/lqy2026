"""
run-log-mcp Flask API 服务（推荐）

启动：
  cd run-log-mcp && pip install -r requirements.txt
  python app.py
  默认 http://0.0.0.0:8300

API：
  POST /api/v1/run/log
  GET  /api/v1/run/stats
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from core import FAILURE_CASES_FILE, RUN_LOGS_FILE, get_stats, log_run

app = Flask(__name__)

RUN_LOG_TOOL_SCHEMA = {
    "name": "run.log",
    "description": "记录运行结果，失败写入 failure_cases.jsonl",
    "inputSchema": {
        "type": "object",
        "properties": {
            "target_id": {"type": "string"},
            "task_type": {"type": "string"},
            "query": {"type": "string"},
            "output": {},
            "summary": {"type": "string"},
            "expected_fields": {"type": "array", "items": {"type": "string"}},
            "attempt": {"type": "integer"},
            "check_result": {"type": "object"},
        },
        "required": ["target_id", "query"],
    },
}


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "framework": "flask",
        "run_logs": str(RUN_LOGS_FILE),
        "failure_cases": str(FAILURE_CASES_FILE),
        "api": {
            "log": "POST /api/v1/run/log",
            "stats": "GET /api/v1/run/stats",
        },
    })


@app.get("/")
def root():
    return jsonify({
        "service": "run-log-mcp",
        "version": "0.3.0",
        "framework": "flask",
        "api": {
            "log": "POST /api/v1/run/log",
            "stats": "GET /api/v1/run/stats",
        },
        "legacy": {"tools": "GET /mcp/tools", "call": "POST /mcp/tools/call"},
        "health": "/health",
    })


@app.post("/api/v1/run/log")
def api_log_run():
    body = request.get_json(silent=True) or {}
    result = log_run(body)
    if "error" in result:
        return jsonify({"error": result["error"]}), 400
    return jsonify(result)


@app.get("/api/v1/run/stats")
def api_run_stats():
    target_id = request.args.get("target_id")
    limit = request.args.get("limit", 100, type=int)
    limit = max(1, min(limit, 1000))
    return jsonify(get_stats(target_id, limit))


@app.get("/mcp/tools")
def list_tools_legacy():
    return jsonify({
        "tools": [
            RUN_LOG_TOOL_SCHEMA,
            {
                "name": "run.stats",
                "description": "查看近期运行统计",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 100},
                    },
                },
            },
        ]
    })


@app.post("/mcp/tools/call")
def call_tool_legacy():
    body = request.get_json(silent=True) or {}
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool == "run.stats":
        return jsonify(get_stats(args.get("target_id"), args.get("limit", 100)))

    if tool != "run.log":
        return jsonify({"error": f"unknown tool: {tool}"}), 400

    result = log_run(args)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8300, debug=False)
