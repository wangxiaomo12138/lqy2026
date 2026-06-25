# Agent 自调优套件（开箱即用）

> 别人**不用写代码**：部署服务 → 平台引用 Agent/工作流 → 说话就能调优。

## 别人怎么用（2 步）

### 1. 运维部署一次

```bash
bash scripts/start-all.sh
# 或 docker compose up -d
```

### 2. 业务方在平台引用

| 方式 | 配置文件 |
|------|----------|
| **引用调优 Agent**（推荐） | `integrations/agents/tune-assistant.json` |
| **引用调优工作流** | `integrations/workflows/wf_tune_generic.json` |
| **总 Agent 追加配置** | `integrations/master-agent-hook.json` |

详细步骤：**[docs/他人接入指南.md](docs/他人接入指南.md)**

## 服务端口

| 服务 | 端口 | 给别人挂 MCP |
|------|------|-------------|
| Tune Engine | 8100 | `http://HOST:8100/mcp` |
| check-mcp | 8200 | `http://HOST:8200/sse`（SSE） |
| run-log-mcp | 8300 | `http://HOST:8300/mcp` |

## 文档

| 文档 | 内容 |
|------|------|
| [他人接入指南](docs/他人接入指南.md) | Tune Engine 给别人用 |
| **[单次循环-他人接入指南](docs/单次循环-他人接入指南.md)** | **在线重试给别人用** |
| [技术方案总览](docs/Agent自调优技术方案总览.md) | 架构全貌 |
| **[技术路线图与业务流程图](docs/技术路线图与业务流程图.md)** | **路线图 + 业务流程图** |
| [批量 vs 真实案例](docs/批量调优与真实案例对比.md) | 两种调优方式对比 |

## 目录

```
integrations/     ← 开箱即用 Agent/工作流模板
tune-engine/      ← 调优后台
check-mcp/        ← 在线检查
run-log-mcp/      ← 运行记录收集
skills/           ← Skill 正文
docs/             ← 文档
```
