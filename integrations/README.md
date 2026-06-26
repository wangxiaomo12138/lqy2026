# 开箱即用接入包（integrations/）

别人**不用写代码**，按下面做即可使用。

## 两套能力都可通用接入

| 能力 | 引用 Agent | 引用工作流 | 接入方式 |
|------|------------|------------|----------|
| **单次循环（在线重试）** | `agents/retry-assistant.json` | `workflows/wf_retry_wrapper.json` | MCP :8200 + :8300 |
| **单次循环（API 版）** ★ MCP 不通时 | `agents/retry-assistant-api.json` | `workflows/wf_retry_wrapper_api.json` | HTTP API |
| **批量调优（Tune Engine）** | `agents/tune-assistant.json` | `workflows/wf_tune_generic.json` | MCP :8100 |

## 目录

```
integrations/
├── agents/
│   ├── tune-assistant.json      # 「调优助手」Agent 模板
│   ├── retry-assistant.json     # 「在线重试」Agent 模板（MCP）
│   └── retry-assistant-api.json # 「在线重试」Agent 模板（API 版）
├── workflows/
│   ├── wf_tune_generic.json     # 通用调优工作流（可引用）
│   ├── wf_retry_wrapper.json    # 在线重试包装工作流（MCP）
│   └── wf_retry_wrapper_api.json # 在线重试包装工作流（API，含 URL/body）
├── skills/
│   └── auto-tune-operator/      # 调优专用 Skill
└── master-agent-hook.json       # 总 Agent 追加配置清单
```

## 别人怎么用

| 需求 | 文档 |
|------|------|
| 批量调优 | `docs/他人接入指南.md` |
| **单次循环** | **`docs/单次循环-他人接入指南.md`** |
| 业务 task 配置 | `integrations/task-registry.yaml` |

### 单次循环（3 选 1）

1. 引用 **在线重试助手 Agent** → `agents/retry-assistant.json`（MCP）
2. 引用 **在线重试助手 API 版** → `agents/retry-assistant-api.json`（**MCP 不通时**）
3. 引用 **重试包装工作流** → `wf_retry_wrapper.json` 或 `wf_retry_wrapper_api.json`
4. 业务 Agent 直接挂 Skill + 两个服务（MCP 或 API）

### 批量调优（3 选 1）

1. 部署服务：`bash scripts/start-all.sh` 或 `docker compose up -d`
2. 平台新建 Agent，导入 `agents/tune-assistant.json` 内容
3. 把 `YOUR_HOST` 改成实际 IP
4. 总 Agent **引用** `调优助手 Agent`

用户说：「帮我把合同解析调到 90%」→ 自动走调优。

### 方式 B：引用「通用调优工作流」

1. 部署服务
2. 平台导入 `workflows/wf_tune_generic.json`
3. 总 Agent 挂 MCP tune-mcp + Skill `auto-tune-operator`
4. 规划时路由到 `wf_tune_generic`

### 方式 C：只加 MCP（最轻）

总 Agent 只挂 `http://HOST:8100/mcp`，Skill 里写：调优时调 `tune.start`。

## 详细文档

见 `docs/他人接入指南.md`
