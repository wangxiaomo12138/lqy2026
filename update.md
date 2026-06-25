# 更新说明

**日期：** 2026-06-24  
**主题：** check-mcp 接入标准 MCP SSE 流式传输

---

## 背景

原 `check-mcp` 使用自定义 REST 接口（`GET /mcp/tools`、`POST /mcp/tools/call`）模拟 MCP，**不符合** Agent 平台要求的 **HTTP SSE 流式 MCP** 接入方式，无法在平台中正常挂载。

本次更新将 `check-mcp` 改为官方 MCP Python SDK 实现的标准 SSE 传输，同时保留旧 REST 接口用于本地 curl 自测。

---

## 变更摘要

| 类别 | 变更 |
|------|------|
| 传输协议 | REST 伪 MCP → **标准 MCP HTTP+SSE** |
| 平台接入地址 | `http://HOST:8200/mcp` → **`http://HOST:8200/sse`** |
| 评估逻辑 | 内联规则 → 统一引用 `shared/evaluators.py` |
| 服务版本 | `0.1.0` → `0.2.0` |
| 向后兼容 | 保留 `POST /mcp/tools/call` 等旧接口 |

---

## 接入方式（平台侧）

1. 传输类型选择：**HTTP SSE**
2. MCP URL 填写：`http://你的服务器:8200/sse`
3. 可用工具：`check.evaluate`（行为与之前一致）

### 端点一览

| 端点 | 方法 | 用途 |
|------|------|------|
| `/sse` | GET | **平台接入入口**，建立 SSE 长连接 |
| `/messages/?session_id=...` | POST | 客户端发 JSON-RPC（平台自动处理） |
| `/health` | GET | 健康检查 |
| `/` | GET | 服务信息与端点说明 |
| `/mcp/tools` | GET | 旧版 REST，工具列表（自测用） |
| `/mcp/tools/call` | POST | 旧版 REST，直接调用（自测用） |

### 通信流程

```
Agent 平台
  │
  ├─ GET /sse ──────────────────► 建立 SSE 连接
  │                                 │
  │◄── event: endpoint ─────────────┘  返回 /messages/?session_id=xxx
  │
  ├─ POST /messages/?session_id=xxx ─► JSON-RPC（initialize / tools/list / tools/call）
  │
  └◄── event: message ───────────────  SSE 流返回 JSON-RPC 响应
```

---

## 代码变更

### `check-mcp/server.py`

- 引入 `mcp` 官方 SDK：`Server` + `SseServerTransport`
- 注册 MCP 工具 `check.evaluate`（`list_tools` / `call_tool`）
- 新增 `GET /sse`、`Mount /messages` SSE 路由
- 评估逻辑改为调用 `shared.evaluators.EVALUATORS`
- `check.evaluate` 入参新增可选字段 `summary`（参与综合评分）
- 保留 `/mcp/tools`、`/mcp/tools/call` 兼容旧调用方式

### `check-mcp/requirements.txt`

新增依赖：

```
mcp>=1.9.0
sse-starlette>=2.0.0
```

### `check-mcp/Dockerfile`

- 增加 `ENV PYTHONPATH=/app`
- 构建时拷贝 `shared/` 目录（评估逻辑共用）

---

## 评估逻辑变化

评估逻辑从 `check-mcp/server.py` 内联实现，改为与 `run-log-mcp` 共用 `shared/evaluators.py`：

| 项 | 旧版 check-mcp | 新版（shared） |
|----|----------------|----------------|
| 字段完整性 | ✅ | ✅ |
| 格式校验（日期/金额） | ✅ | ✅ |
| 总结评分 | ❌ | ✅（可选 `summary` 参数） |
| 综合分 | 仅字段分 | 字段 70% + 总结 30% |
| 通过条件 | `failures` 为空且 score ≥ 0.8 | 字段分 ≥ 0.8 且总结分 ≥ 0.6 |

> 若不传 `summary`，总结分为 0，可能导致 `passed=false`。建议 Agent 调用时传入当前总结文本，或仅依赖字段分场景下关注 `field_score` 字段。

---

## 文档同步更新

以下文件中的接入地址已改为 `/sse`：

| 文件 | 变更 |
|------|------|
| `README.md` | check-mcp 地址改为 `http://HOST:8200/sse` |
| `docs/Agent自调优技术方案总览.md` | 部署验证与挂 MCP 步骤 |
| `docs/agent内单次循环-仅接入版.md` | 平台挂 MCP 说明 |
| `docs/单次循环-他人接入指南.md` | MCP 1 地址 |
| `skills/auto-retry-replan/SKILL.md` | MCP 端口说明 |
| `scripts/start-all.sh` | 启动后打印 SSE 地址 |

---

## 验证命令

```bash
# 启动服务
cd check-mcp
pip install -r requirements.txt
python server.py

# 健康检查（应含 transport: sse）
curl http://127.0.0.1:8200/health

# SSE 连接（应返回 endpoint 事件）
curl -N --max-time 2 http://127.0.0.1:8200/sse

# 旧版 REST 自测（仍可用）
curl -X POST http://127.0.0.1:8200/mcp/tools/call \
  -H 'Content-Type: application/json' \
  -d '{
    "tool": "check.evaluate",
    "arguments": {
      "task_type": "contract-parse",
      "output": {"party_a": "甲公司", "party_b": "乙公司"},
      "expected_fields": ["party_a", "party_b", "amount", "sign_date"]
    }
  }'
```

---

## 未变更 / 待办

| 服务 | 状态 |
|------|------|
| `run-log-mcp` (:8300) | 仍为 REST 伪 MCP，若平台要求 SSE 需另行改造 |
| `tune-engine` (:8100) | 仍为 REST 伪 MCP |
| `对话记录.md` | 历史导出，未同步修改 |

---

## 升级注意

1. **必须重新安装依赖**：`pip install -r check-mcp/requirements.txt`
2. **平台 MCP 地址必须改为** `http://HOST:8200/sse`，旧地址 `http://HOST:8200` 或 `/mcp` 无法正常接入
3. Docker 部署需重新 build：`docker compose build check-mcp && docker compose up -d check-mcp`
