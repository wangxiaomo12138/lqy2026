"""FastAPI 程序入口"""

from fastapi import FastAPI

from app.api import targets, tune_sessions
from app.database import init_db
from app.mcp import tools as mcp_tools

app = FastAPI(
    title="Tune Engine",
    description="通用 Agent 循环调优服务",
    version="0.1.0",
)

app.include_router(targets.router)
app.include_router(tune_sessions.router)
app.include_router(mcp_tools.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {
        "service": "tune-engine",
        "docs": "/docs",
        "mcp_tools": "/mcp/tools",
        "hint": "先运行 python scripts/init_demo.py 初始化数据",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
