# Tune Engine API 与项目目录（栈无关版 + Python 参考）

> 后端语言不限（Java / Go / Python 均可）。下面 API 与表结构是统一的，目录以 **Python(FastAPI)** 为例，其他栈照模块拆分即可。

---

## 1. REST API 草案

### Target 管理

```http
POST   /api/v1/targets
GET    /api/v1/targets
GET    /api/v1/targets/{target_id}
PUT    /api/v1/targets/{target_id}
DELETE /api/v1/targets/{target_id}
```

**POST /api/v1/targets** 请求体：完整 Tunable Target JSON（见 `01-tunable-target-template.yaml`）

---

### Benchmark 管理

```http
POST   /api/v1/benchmarks
POST   /api/v1/benchmarks/{suite_id}/cases
GET    /api/v1/benchmarks/{suite_id}/cases
```

---

### Tune Session（MCP 底层也调这些）

```http
POST   /api/v1/tune/sessions          # 等同 tune.start
GET    /api/v1/tune/sessions/{session_id}           # 等同 tune.status
GET    /api/v1/tune/sessions/{session_id}/result  # 等同 tune.get_result
POST   /api/v1/tune/sessions/{session_id}/stop    # 等同 tune.stop
GET    /api/v1/tune/sessions/{session_id}/iters   # 迭代详情
GET    /api/v1/tune/sessions/{session_id}/runs    # 所有 run 记录
```

#### POST /api/v1/tune/sessions

```json
{
  "target_id": "contract-parse",
  "mode": "full_auto",
  "async": true,
  "entry_ref": "wf_contract_parse@v3",
  "success_criteria_override": { "min_pass_rate": 0.9 },
  "constraints_override": { "max_tune_iters": 8 },
  "input_payload": {}
}
```

响应：

```json
{
  "session_id": "ts_20250624_abc123",
  "status": "running",
  "target_id": "contract-parse",
  "entry_ref": "wf_contract_parse@v3",
  "created_at": "2025-06-24T10:00:00Z"
}
```

---

### 内部回调（Engine 调你们现有 Agent 平台）

```http
POST   /internal/agent/run
```

```json
{
  "entry_ref": "wf_contract_parse@v3",
  "input": { "file_url": "s3://..." },
  "trace_enabled": true
}
```

响应：

```json
{
  "run_id": "run_xxx",
  "status": "success",
  "output": { "party_a": "甲公司", "amount": 1200000 },
  "plan_trace": [ { "step": 1, "intent": "...", "status": "ok" } ],
  "summary": "解析完成...",
  "latency_ms": 3200,
  "cost_tokens": 4500
}
```

> **关键**：Tune Engine 不重复实现 Agent 执行，只通过 `entry_ref` 调用你们现有平台。

---

## 2. 推荐目录结构（Python / FastAPI）

```text
tune-engine/
├── spec/                          # 本目录，协议与表结构文档
│   ├── 01-tunable-target-template.yaml
│   ├── 02-tune-mcp-tools.json
│   ├── 03-database-schema.sql
│   ├── 04-state-machine.md
│   └── 05-api-and-directory.md
│
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py
│   │
│   ├── api/                       # HTTP 层
│   │   ├── targets.py
│   │   ├── benchmarks.py
│   │   └── tune_sessions.py
│   │
│   ├── mcp/                       # MCP 适配层（薄封装，转调 api/service）
│   │   ├── server.py
│   │   └── tools.py               # tune.start / status / get_result
│   │
│   ├── engine/                    # 核心
│   │   ├── orchestrator.py        # run_session 主循环
│   │   ├── state_machine.py
│   │   ├── benchmark_runner.py    # 批量调 Agent 平台
│   │   ├── evaluator.py           # 评估器接口
│   │   ├── diagnoser.py           # 失败归因
│   │   ├── patch_proposer.py      # 生成补丁
│   │   ├── shadow_compare.py      # 沙箱对比
│   │   └── version_registry.py    # config_version 晋升/回滚
│   │
│   ├── evaluators/                # 各业务评估器插件
│   │   ├── base.py
│   │   ├── contract_field_eval.py
│   │   └── invoice_field_eval.py
│   │
│   ├── models/                    # ORM 模型
│   │   ├── target_registry.py
│   │   ├── tune_session.py
│   │   ├── tune_iter.py
│   │   └── tune_run.py
│   │
│   ├── repositories/              # 数据访问
│   │   └── ...
│   │
│   ├── clients/                   # 外部调用
│   │   └── agent_platform.py      # 调你们现有 Agent/工作流执行接口
│   │
│   └── workers/
│       └── tune_worker.py         # 异步执行 run_session（Celery/RQ/内置队列）
│
├── migrations/
├── tests/
│   ├── test_orchestrator.py
│   └── test_contract_evaluator.py
│
├── pyproject.toml
└── README.md
```

---

## 3. Java / Go 对照（模块一一对应）

| Python 模块 | Java (Spring) | Go |
|-------------|---------------|-----|
| `api/` | `controller/` | `handler/` |
| `engine/orchestrator.py` | `service/TuneOrchestrator` | `engine/orchestrator.go` |
| `evaluators/` | `evaluator/impl/` | `evaluator/` |
| `clients/agent_platform.py` | `client/AgentPlatformClient` | `client/agent_platform.go` |
| `mcp/tools.py` | `mcp/TuneToolHandler` | `mcp/tools.go` |
| `workers/` | `@Async` / MQ Consumer | `worker/` goroutine + channel |

---

## 4. 接入你们 Agent 平台的步骤

### Step 1：注册合同解析 Target

```bash
curl -X POST /api/v1/targets -d @contract-parse-target.json
```

### Step 2：导入 benchmark

```bash
curl -X POST /api/v1/benchmarks/contract_bench_v1/cases -d @cases.json
```

### Step 3：把 tune-mcp 挂到总 Agent

总 Agent 配置增加 MCP：`tune-mcp`

### Step 4：总 Agent 挂 Skill `auto-tune`

识别「调优」意图 → 调 `tune.start(target_id=contract-parse)`

### Step 5：总 Agent 走工作流 `WF_TUNE_GENERIC`

```text
解析 target_id → tune.start → 轮询 tune.status → tune.get_result → 模型总结
```

---

## 5. 开工优先级（2 周 MVP）

| 天数 | 任务 | 产出 |
|------|------|------|
| D1-D2 | 建表 + Target/Benchmark CRUD | 能注册 contract-parse |
| D3-D4 | agent_platform client + benchmark_runner | 能批量跑工作流 |
| D5 | contract_field_eval | 能打分 |
| D6-D7 | orchestrator（先无 patch，只 evaluate_only 循环） | 能判断 optimal |
| D8-D9 | patch_proposer + shadow_compare（先只改 skill prompt） | 能自动提升 |
| D10 | tune-mcp 三个工具 | 总 Agent 可调用 |

---

## 6. 与总 Agent 5 步规划的关系

```text
外层 Tune Engine（你要新建）
  iter 1: 调用 wf_contract_parse@v3
            └─ 内层：总 Agent 5步规划 → summary（平台已有）
  iter 2: 调用 wf_contract_parse@v4
  iter 3: 达标 → optimal
```

Tune Engine 管「换哪个版本、何时停」；你们现有 Agent 管「单次怎么执行」。
