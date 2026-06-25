"""
MCP 工具接口（薄封装，转调内部 API）

总 Agent 通过 POST /mcp/tools/call 调用这些工具。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.engine.orchestrator import create_tune_session, get_session_status, run_session
from app.models.tune_models import TuneSession
from app.schemas.tune_schemas import TuneSessionCreate

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPCallRequest(BaseModel):
    tool: str
    arguments: dict = {}


MCP_TOOLS = [
    {
        "name": "tune.start",
        "description": "启动自动调优。达标返回 optimal，否则循环调优直到停止条件。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "async": {"type": "boolean", "default": False},
            },
            "required": ["target_id"],
        },
    },
    {
        "name": "tune.status",
        "description": "查询调优进度",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "include_iters": {"type": "boolean", "default": True},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "tune.get_result",
        "description": "获取调优最终结果",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
]


@router.get("/tools")
def list_tools():
    return {"tools": MCP_TOOLS}


@router.post("/tools/call")
def call_tool(body: MCPCallRequest, db: Session = Depends(get_db)):
    args = body.arguments

    if body.tool == "tune.start":
        req = TuneSessionCreate(target_id=args["target_id"], async_mode=args.get("async", False))
        session = create_tune_session(
            db,
            target_id=req.target_id,
            mode=req.mode,
            entry_ref=req.entry_ref,
            success_criteria_override=req.success_criteria_override,
            constraints_override=req.constraints_override,
        )
        if req.async_mode:
            import threading
            from app.database import SessionLocal
            from app.engine.orchestrator import run_session as rs

            def bg(sid):
                sdb = SessionLocal()
                try:
                    rs(sdb, sid)
                finally:
                    sdb.close()

            threading.Thread(target=bg, args=(session.session_id,), daemon=True).start()
            return {"session_id": session.session_id, "status": "running", "target_id": req.target_id}
        else:
            result = run_session(db, session.session_id)
            return result

    if body.tool == "tune.status":
        return get_session_status(db, args["session_id"], include_iters=args.get("include_iters", True))

    if body.tool == "tune.get_result":
        session = db.query(TuneSession).filter(TuneSession.session_id == args["session_id"]).first()
        if not session:
            return {"error": "Session 不存在"}
        if session.status in ("pending", "running"):
            return {"session_id": session.session_id, "status": session.status, "message": "仍在运行"}
        from app.api.tune_sessions import get_result
        return get_result(args["session_id"], db).model_dump()

    return {"error": f"未知工具: {body.tool}"}
