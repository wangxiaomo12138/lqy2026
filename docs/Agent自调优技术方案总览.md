# Agent 自调优技术方案总览

> 版本：v1.0  
> 适用：仅能接入使用 Agent 平台、无法修改平台底层代码的场景  
> 项目根目录：`/Users/wanghanbing/Documents/文本资料/l/`

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [总体架构](#2-总体架构)
3. [方案一：单次循环重规划（在线）](#3-方案一单次循环重规划在线)
4. [方案二：Tune Engine（离线批量调优）](#4-方案二tune-engine离线批量调优)
5. [两套方案对比](#5-两套方案对比)
6. [推荐落地顺序](#6-推荐落地顺序)
7. [文档与代码清单](#7-文档与代码清单)
8. [方案一详细接入步骤](#8-方案一详细接入步骤)
9. [方案二详细接入步骤](#9-方案二详细接入步骤)
10. [与你们 Agent 平台的关系](#10-与你们-agent-平台的关系)
11. [常见问题](#11-常见问题)
12. [联合使用方案](#12-联合使用方案)

另见：
- **[他人接入指南](他人接入指南.md)** — 给别人直接用（Agent/工作流引用）
- **[批量调优与真实案例对比](批量调优与真实案例对比.md)**

---

## 1. 背景与目标

### 1.1 你们平台现状

```text
用户 query
    ↓
Agent 规划模型（按工作流描述规划，最多 5 步）
    ↓
路由到某个工作流执行
    ↓
工作流返回结果
    ↓
Agent 总结模型输出最终答案
```

平台能力：可配置 **Agent / 工作流 / Skill / MCP / API**，但不能改底层执行引擎。

### 1.2 要解决的两个问题

| 问题 | 场景 | 期望 |
|------|------|------|
| **问题 A** | 用户发 1 个 query，第一次效果不好 | 记录问题点 → 重规划 → 再执行 → 直到输出最优结果 |
| **问题 B** | 合同解析等工作流长期准确率不够 | 自动批量测试 → 自动改配置 → 达标后固定最优版本 |

### 1.3 解决方案

| 方案 | 名称 | 解决 |
|------|------|------|
| **方案一** | 单次循环重规划（在线） | 问题 A |
| **方案二** | Tune Engine（离线调优） | 问题 B |

两套方案**互补**，可同时使用。

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                        用户 / 总 Agent                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┴───────────────────┐
         │                                       │
         ▼                                       ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│  方案一：在线单次循环      │         │  方案二：Tune Engine     │
│  Skill + check-mcp       │         │  独立 Python 后台服务    │
│  （不改平台底层）          │         │  （批量调优 + 改配置）    │
└───────────┬─────────────┘         └───────────┬─────────────┘
            │                                   │
            └──────────────┬────────────────────┘
                           ▼
            ┌──────────────────────────────┐
            │      你们的 Agent 平台         │
            │  规划 → 工作流 → 总结           │
            └──────────────────────────────┘
```

**分工原则：**

- **平台**：只负责「规划 → 工作流 → 总结」（不变）
- **方案一**：在单次请求内，用 Skill + MCP 实现「执行 → 检查 → 重试」
- **方案二**：在平台外，用测试集反复调用 Agent，自动提升配置版本

---

## 3. 方案一：单次循环重规划（在线）

### 3.1 是什么

用户每次提问时，Agent 在**同一次请求内**：

```text
第1次执行工作流 → 检查结果 → 不好 → 记录 failure_points
    → 重规划 → 第2次执行 → 再检查 → … → 输出最优答案
```

最多利用平台已有的 **5 步规划** 完成循环。

### 3.2 核心思路

**不能写 for 循环代码**，就把 5 步规划当作循环：

| 步数 | 动作 |
|------|------|
| Step 1 | 首次执行目标工作流 |
| Step 2 | 调用 MCP `check.evaluate` 检查结果 |
| Step 3 | 未通过 → 带 failure_points 重跑工作流 |
| Step 4 | 再次检查（或最后一次修正） |
| Step 5 | 总结模型输出最终结果（optimal / best_effort） |

### 3.3 组成组件

| 组件 | 文件 | 作用 |
|------|------|------|
| Skill | `skills/auto-retry-replan/SKILL.md` | 教规划模型如何分配 5 步、何时检查、何时重试、**跑完必调 run.log** |
| check-mcp | `check-mcp/server.py` | 提供 `check.evaluate` 工具（`:8200`） |
| run-log-mcp | `run-log-mcp/server.py` | 提供 `run.log` 工具（`:8300`），收集 output/summary 写 jsonl |
| `data/run_logs.jsonl` | 全部真实运行记录 | run.log 自动写入 |
| `data/failure_cases.jsonl` | 失败 case | run.log 失败时写入，供 Tune 导入 |
| 工作流描述 | 平台 UI 配置 | 让规划模型知道何时路由、重试时如何修正 |
| 总结 prompt | 平台 UI 配置 | 要求输出 status / attempts / result |

### 3.4 数据流

```text
query
  → Step1: 工作流执行 → output_v1
  → Step2: check.evaluate(output_v1) → {passed:false, failure_points:{...}}
  → Step3: 构造「原始query + 上次问题」→ 工作流 → output_v2
  → Step4: check.evaluate(output_v2) → {passed:true}
  → Step5: 总结 → {status:"optimal", result:{...}}
```

### 3.5 停止条件

- `check.evaluate` 返回 `passed: true` → 立即总结输出
- 已达第 5 步 → 输出当前最优结果（`best_effort`）
- 连续两次分数无提升 → 提前停止（由 Skill 约束）

---

## 4. 方案二：Tune Engine（离线批量调优）

### 4.1 是什么

独立的 **Python 后台服务**，对某个 Agent/工作流做**批量自动调优**：

```text
for 每一轮（最多 8 轮）:
    用测试集批量调用 Agent
    → 评估打分
    → 达标？返回 optimal
    → 未达标？自动改配置（工作流/Skill 版本）
    → 继续下一轮
```

### 4.2 核心思路

把要调优的对象注册为 **Tunable Target**（可调优对象），包含：

- 调谁（agent_id / workflow entry_ref）
- 怎么测（benchmark 测试集）
- 怎么评分（evaluator）
- 什么叫好（success_criteria）
- 能改什么（patchable_components）

### 4.3 组成组件

| 组件 | 路径 | 作用 |
|------|------|------|
| 调优引擎 | `tune-engine/app/engine/orchestrator.py` | 主循环：跑测 → 评分 → 补丁 → 晋升 |
| 评估器 | `tune-engine/app/evaluators/contract_evaluator.py` | 逐字段比对，计算 pass_rate / score |
| 补丁生成 | `tune-engine/app/engine/patch_proposer.py` | 失败归因 + 生成配置补丁 |
| 平台客户端 | `tune-engine/app/clients/agent_platform.py` | 调用你们 Agent 平台执行 query |
| MCP 工具 | `tune-engine/app/mcp/tools.py` | 暴露 tune.start / status / get_result |
| 数据库 | `tune-engine/data/tune.db` | 存 session、迭代记录、测试样本 |

### 4.4 数据流

```text
tune.start(target_id="contract-parse")
  → iter1: 调 Agent(v1) × 5条测试query → 评分 35%
  → 自动补丁 → v2
  → iter2: 调 Agent(v2) × 5条测试query → 评分 78%
  → 自动补丁 → v3
  → iter3: 调 Agent(v3) × 5条测试query → 评分 100%
  → optimal，返回 best_entry_ref=v3
```

### 4.5 停止条件

| 状态 | 含义 |
|------|------|
| `optimal` | 达到 success_criteria，调优成功 |
| `best_effort` | 跑满轮数或停滞，返回当前最优版本 |
| `failed` | 异常失败 |

---

## 5. 两套方案对比

| 维度 | 方案一：单次循环 | 方案二：Tune Engine |
|------|------------------|---------------------|
| **触发时机** | 用户每次正常提问 | 调优任务 / 人工触发 / MCP tune.start |
| **输入** | 1 个 query | 一批测试 query + 标准答案 |
| **改什么** | 不改配置，同请求内重试 | 改 Agent/工作流/Skill 配置版本 |
| **输出** | 本次最优答案 | 最优配置版本 + 指标 |
| **部署** | check-mcp + Skill | tune-engine 服务 |
| **是否改平台代码** | 否 | 否 |
| **见效速度** | 立刻（当次请求） | 需准备测试集，批量跑 |
| **长期价值** | 单次兜底 | 系统性提升基线能力 |

**关系：** 方案一减少单次失败；方案二减少需要重试的次数。方案一产生的失败 case 可导入方案二做长期调优。

---

## 6. 推荐落地顺序

```text
阶段 0（准备）    理解文档，确认平台 Agent 运行接口
    ↓
阶段 1（优先）    方案一：check-mcp + Skill → 用户立刻能感受重试
    ↓
阶段 2            方案二：本地跑通 tune-engine 演示
    ↓
阶段 3            方案二：对接真实 Agent 平台 API
    ↓
阶段 4            总 Agent 挂 tune-mcp，支持「帮我调优到 90%」
    ↓
阶段 5（持续）    方案一失败 case → 导入 Tune Engine benchmark
```

**原则：先用方案一，再用方案二。**

---

## 7. 文档与代码清单

### 7.1 总览文档（你现在看的）

| 文件 | 干什么 | 给谁看 |
|------|--------|--------|
| `docs/Agent自调优技术方案总览.md` | **主文档**：架构、对比、接入总流程 | 所有人，先看这个 |
| `docs/agent内单次循环-仅接入版.md` | 方案一专项教程 | 做在线重试的人 |

### 7.2 方案一相关

| 文件 | 干什么 | 用到哪里 |
|------|--------|----------|
| `skills/auto-retry-replan/SKILL.md` | 重规划 Skill 正文（含 run.log 必调） | **复制到平台** → 绑到总 Agent |
| `check-mcp/server.py` | 检查 MCP 服务 | **部署为 MCP** → 总 Agent 挂载 |
| `check-mcp/requirements.txt` | check-mcp 依赖 | 部署时 `pip install` |
| `run-log-mcp/server.py` | 收集 output/summary（:8300） | **部署** → 总 Agent 挂载 |
| `run-log-mcp/requirements.txt` | run-log-mcp 依赖 | 部署时 pip install |
| `shared/evaluators.py` | 共用评分逻辑 | check-mcp / run-log-mcp 内部 |
| `data/run_logs.jsonl` | 全部运行记录 | run.log 自动写入 |
| `data/failure_cases.jsonl` | 失败 case | 供 Tune Engine 导入 |
| `docs/批量调优与真实案例对比.md` | 批量 vs 真实案例对比 + 案例 | 选型与运营 |

### 7.3 方案二相关 — 使用文档

| 文件 | 干什么 | 给谁看 |
|------|--------|--------|
| `tune-engine/README.md` | 项目说明、快速开始 | 开发入门 |
| `tune-engine/TUTORIAL.md` | 手把手教程（10 分钟跑通） | **小白首选** |

### 7.4 方案二相关 — 设计规范（spec）

| 文件 | 干什么 | 什么时候看 |
|------|--------|------------|
| `spec/01-tunable-target-template.yaml` | Tunable Target 配置模板 + 示例 | 注册新技能时 |
| `spec/02-tune-mcp-tools.json` | tune.start/status/get_result 接口定义 | 对接 MCP / 总 Agent 时 |
| `spec/03-database-schema.sql` | 数据库表结构 | 上线部署 / DBA |
| `spec/04-state-machine.md` | 调优循环状态机 + 伪代码 | 理解引擎逻辑 |
| `spec/05-api-and-directory.md` | REST API + 项目目录 + 2周计划 | 开发排期 |

### 7.5 方案二相关 — 示例数据

| 文件 | 干什么 | 什么时候用 |
|------|--------|------------|
| `examples/contract-parse-target.json` | 合同解析 Target 配置样例 | 注册调优对象时复制修改 |
| `examples/contract-bench-cases.sample.json` | 3 条测试样本样例 | 导入 benchmark 时参考 |

### 7.6 方案二相关 — 核心代码

| 文件 | 干什么 | 你需要改吗 |
|------|--------|------------|
| `app/main.py` | FastAPI 入口 | 一般不改 |
| `app/config.py` | 配置（Mock/真实平台切换） | **要改**：对接时改 URL |
| `app/clients/agent_platform.py` | 调你们 Agent 平台 | **要改**：对接时改 HTTP 调用 |
| `app/engine/orchestrator.py` | 调优主循环 | 一般不改 |
| `app/evaluators/contract_evaluator.py` | 合同解析评分 | 新技能时扩展 |
| `app/mcp/tools.py` | tune MCP 工具 | 一般不改 |
| `scripts/init_demo.py` | 初始化演示数据 | 跑演示前执行 |
| `scripts/run_demo.py` | 一键跑调优演示 | 验证方案二 |
| `scripts/import_failure_cases.py` | 导入线上失败 case 到 benchmark | **联合使用**：方案一 → 方案二 |
| `data/failure_cases.jsonl` | 线上失败 case 样例 | 收集失败 query 时参考格式 |

---

## 8. 方案一详细接入步骤

> **目标**：用户发 query，第一次不好会自动重规划再执行，直到输出最优结果。  
> **前提**：平台支持挂 MCP、挂 Skill，Agent 有最多 5 步规划。

### 步骤 1：部署 check-mcp

```bash
cd check-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
# 默认 http://0.0.0.0:8200
```

验证：

```bash
curl http://127.0.0.1:8200/health
# 应返回 {"status":"ok"}
```

**用到文件：** `check-mcp/server.py`、`check-mcp/requirements.txt`

---

### 步骤 2：平台挂 MCP

在总 Agent（或合同解析 Agent）配置中：

- 添加 MCP **check-mcp**：`http://你的服务器:8200` → 工具 `check.evaluate`
- 添加 MCP **run-log-mcp**：`http://你的服务器:8300` → 工具 `run.log`、`run.stats`

**用到文件：** 无（平台 UI 操作）

---

### 步骤 3：创建并绑定 Skill

1. 打开 `skills/auto-retry-replan/SKILL.md`
2. 全文复制到平台 → 新建 Skill（名称如 `auto-retry-replan`）
3. 将该 Skill 绑到总 Agent

**用到文件：** `skills/auto-retry-replan/SKILL.md`  
**详细说明：** `docs/agent内单次循环-仅接入版.md`

---

### 步骤 4：配置工作流描述

在「合同解析」工作流的描述中加入：

```text
【工作流名称】合同解析
【触发条件】用户要求解析合同、抽取字段、输出JSON
【输入】query 中的合同正文
【输出】JSON：party_a, party_b, amount, sign_date
【重试注意】若 query 含【上次执行问题】，必须优先修正后再输出
```

**用到哪里：** 平台工作流配置 UI → 供规划模型路由和重试时使用

---

### 步骤 5：配置总结模型 prompt（可选但推荐）

```text
最终输出 JSON 必须包含：
- status: "optimal" 或 "best_effort"
- attempts: 尝试次数
- result: 结构化结果
- issues: 未解决问题（若有）
```

---

### 步骤 6：测试验证

发测试 query：

```text
解析以下合同，输出JSON字段 party_a, party_b, amount, sign_date：
【合同正文……】
```

检查规划轨迹是否包含：

1. 第一次工作流执行
2. 调用 `check.evaluate`
3. （若失败）第二次工作流执行
4. 最终总结

---

### 方案一接入关系图

```text
skills/auto-retry-replan/SKILL.md  ──复制──>  平台 Skill  ──绑定──>  总 Agent
check-mcp/server.py               ──部署──>  MCP 服务    ──挂载──>  总 Agent
工作流描述 / 总结 prompt           ──填写──>  平台 UI
```

---

## 9. 方案二详细接入步骤

> **目标**：批量自动调优合同解析，达标后返回最优配置版本。  
> **前提**：能通过网络 API 调用你们 Agent（agent_id + query → answer）。

### 步骤 1：本地跑通演示（Mock 模式，不需要真实平台）

```bash
cd tune-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/init_demo.py    # 注册 target + 5条样本
python scripts/run_demo.py     # 一键看调优循环
```

期望输出：`status: optimal`，有 3 轮左右迭代轨迹。

**用到文件：**
- `scripts/init_demo.py` — 初始化
- `scripts/run_demo.py` — 演示
- `TUTORIAL.md` — 遇到问题看这个

---

### 步骤 2：启动 HTTP 服务

```bash
python -m uvicorn app.main:app --reload --port 8100
```

- API 文档：http://127.0.0.1:8100/docs
- MCP 工具：http://127.0.0.1:8100/mcp/tools

**用到文件：** `app/main.py`

---

### 步骤 3：对接真实 Agent 平台

#### 3.1 改配置

文件：`tune-engine/app/config.py`

```python
USE_MOCK_AGENT = False
AGENT_PLATFORM_URL = "http://你们平台地址"
```

#### 3.2 改客户端

文件：`tune-engine/app/clients/agent_platform.py`

把 `RealAgentPlatformClient.run()` 改成你们真实接口，例如：

```python
resp = client.post(
    f"{self.base_url}/api/agent/run",  # 你们的真实路径
    json={"agent_id": agent_id, "query": query},
)
```

返回需转换为引擎认识的格式：

```python
{
    "status": "success",
    "output": ...,       # 从 answer 解析出的结构化结果
    "summary": answer,   # 总结模型原文
    "plan_trace": [...],
}
```

**参考文档：** `spec/05-api-and-directory.md` 里的内部回调格式

---

### 步骤 4：准备真实测试集

1. 复制 `examples/contract-parse-target.json`，按实际修改
2. 准备 benchmark：每条 = `query` + `ground_truth`

```json
{
  "case_id": "case_01",
  "input": {
    "query": "解析以下合同，输出JSON：party_a, party_b, amount, sign_date\n【正文】"
  },
  "ground_truth": {
    "party_a": "北京甲公司",
    "party_b": "上海乙公司",
    "amount": 500000,
    "sign_date": "2024-01-15"
  }
}
```

注册：

```bash
curl -X POST http://127.0.0.1:8100/api/v1/targets \
  -H "Content-Type: application/json" \
  -d @examples/contract-parse-target.json

curl -X POST http://127.0.0.1:8100/api/v1/benchmarks/contract_bench_v1/cases \
  -H "Content-Type: application/json" \
  -d @你的cases.json
```

**用到文件：**
- `examples/contract-parse-target.json`
- `spec/01-tunable-target-template.yaml`

---

### 步骤 5：触发调优

```bash
# 同步执行（等跑完）
curl -X POST http://127.0.0.1:8100/api/v1/tune/sessions \
  -H "Content-Type: application/json" \
  -d '{"target_id": "contract-parse", "async": false}'

# 查结果
curl http://127.0.0.1:8100/api/v1/tune/sessions/{session_id}/result
```

---

### 步骤 6：总 Agent 挂 tune-mcp（可选）

总 Agent 添加 MCP：`http://你的服务器:8100/mcp`

| 工具 | 用途 |
|------|------|
| `tune.start` | 开始调优 |
| `tune.status` | 查进度 |
| `tune.get_result` | 拿最终结果 |

用户可说：「把合同解析调到 90% 准确率」

**参考：** `spec/02-tune-mcp-tools.json`

---

### 步骤 7：新增其他技能

1. 复制 Target 模板 → 改 `target_id`、evaluator
2. 在 `app/evaluators/contract_evaluator.py` 的 `EVALUATORS` 注册新评分函数
3. 导入 benchmark → `tune.start`

---

### 方案二接入关系图

```text
examples/contract-parse-target.json  ──>  POST /api/v1/targets
benchmark cases JSON                 ──>  POST /api/v1/benchmarks/.../cases
app/clients/agent_platform.py        ──>  对接你们 Agent API
app/config.py                        ──>  USE_MOCK_AGENT=False
scripts/run_demo.py                  ──>  验证
总 Agent                             ──>  挂 MCP tune.start
```

---

## 10. 与你们 Agent 平台的关系

```text
┌────────────────────────────────────────────────────────┐
│  你们 Agent 平台（不修改底层）                            │
│                                                        │
│  query → 规划(≤5步) → 工作流 → 总结 → answer            │
│                                                        │
│  可配置：Agent / 工作流 / Skill / MCP / API             │
└────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
    方案一 Skill         方案一 check-mcp    方案二 HTTP 调用
    (教规划重试)          (检查结果)           (批量跑 query)
```

**你们平台需要提供的最小能力：**

| 能力 | 方案一 | 方案二 |
|------|--------|--------|
| 挂 MCP | 需要（check-mcp） | 可选（tune-mcp） |
| 挂 Skill | 需要 | 可选 |
| Agent 运行 API（query → answer） | 不必须（走规划链路即可） | **必须** |

---

## 11. 常见问题

**Q1：先做哪个？**  
A：先做方案一（1～2 天），再做方案二（1～2 周）。

**Q2：两套会冲突吗？**  
A：不会。方案一管单次体验，方案二管长期配置。详见 [第 12 节 联合使用方案](#12-联合使用方案)。

**Q3：平台没有 Agent 运行 API 怎么办？**  
A：方案二需要能程序化触发 Agent；若只有 UI，需平台方提供内部接口或先用 Mock 验证流程。

**Q4：check.evaluate 和 tune 的 evaluator 区别？**  
A：check 用于在线单次检查（快）；tune evaluator 用于离线批量评分（可更严）。

**Q5：失败 case 怎么复用？**  
A：方案一里 `passed=false` 的 query + failure_points，整理后导入 Tune Engine benchmark。见 [12.4 失败 case 回流](#124-失败-case-回流在线--离线)。

**Q6：文档太多看哪个？**

```text
只想快速上手方案一  → docs/agent内单次循环-仅接入版.md
只想快速上手方案二  → tune-engine/TUTORIAL.md
想了解全貌         → 本文档（Agent自调优技术方案总览.md）
两套怎么一起用     → 本文档第 12 节
批量 vs 真实案例   → docs/批量调优与真实案例对比.md
要注册新技能       → spec/01-tunable-target-template.yaml
要对接 MCP        → spec/02-tune-mcp-tools.json
要理解引擎逻辑     → spec/04-state-machine.md
```

---

## 12. 联合使用方案

> **结论：两套方案可以同时使用，且推荐联合部署。**  
> 单次循环负责「这一次答好」；Tune Engine 负责「以后默认更好」。二者互补，不抢职责。

### 12.1 联合架构

```text
                         用户 query
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     「普通提问」                      「调优指令」
     解析这份合同…                    把合同解析调到90%
              │                             │
              ▼                             ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│  方案一：单次循环（在线）   │   │  方案二：Tune Engine     │
│  Skill + check-mcp       │   │  tune.start / get_result │
│  执行→检查→重试→输出      │   │  批量测试→改配置版本      │
└────────────┬────────────┘   └────────────┬────────────┘
             │                             │
             │    使用当前生产配置版本 vN    │
             └──────────────┬──────────────┘
                            ▼
             ┌──────────────────────────────┐
             │     你们的 Agent 平台          │
             │  规划 → 工作流(vN) → 总结      │
             └──────────────────────────────┘
                            │
             ┌──────────────┴──────────────┐
             │  失败 case 回流（定期）         │
             └──────────────┬──────────────┘
                            ▼
             ┌──────────────────────────────┐
             │  Tune Engine benchmark 库    │
             └──────────────────────────────┘
```

### 12.2 职责边界（避免冲突）

| 维度 | 方案一：单次循环 | 方案二：Tune Engine |
|------|------------------|---------------------|
| 触发 | 每次用户提问自动生效 | 手动 / 定时 / MCP `tune.start` |
| 改配置版本 | **不改** | **改**（v1→v2→v3…） |
| 改当次答案 | **改**（重规划重执行） | 不改 |
| 依赖组件 | Skill + check-mcp | tune-engine 服务 |
| 评估工具 | `check.evaluate`（快） | evaluator（可更严） |

**禁止混用：**

- 单次循环里不要触发 `tune.start`（成本高、用户等待久）
- Tune Engine 里不要用 `check.evaluate` 代替 evaluator（离线需更完整指标）
- 用户每个 query 不要都跑 Tune Engine

### 12.3 三个结合点

#### 结合点 A：Tune 产出的最优版本 → 单次循环直接用

```text
Tune Engine 调优完成
  → best_entry_ref = wf_contract_parse@v5
  → 在平台将生产 Agent 指向 v5
  → 用户后续 query 走单次循环时：
       第一次成功率更高，重试次数更少
```

**操作步骤：**

1. `tune.get_result` 拿到 `best_entry_ref` 和 `criteria_met`
2. 若 `status=optimal`，在平台手动或 API 晋升该版本为生产配置
3. 单次循环无需任何改动，自动使用新配置

#### 结合点 B：单次循环失败 case → 回流 Tune Engine（run-log-mcp 自动收集）

单次循环中每次 `check.evaluate` 后调用 **`run.log`**（run-log-mcp），自动：

- 评分（字段 70% + 总结 30%）
- 写入 `data/run_logs.jsonl`（全部记录）
- `passed=false` 时写入 `data/failure_cases.jsonl`

无需手工从日志里抠数据。失败记录格式：

```json
{
  "case_id": "online_20250624_001",
  "source": "online_retry",
  "input": {
    "query": "解析以下合同，输出JSON：party_a, party_b, amount, sign_date\n【正文】"
  },
  "failure_points": {
    "missing_fields": ["amount"],
    "score": 0.75
  },
  "ground_truth": {
    "party_a": "北京甲公司",
    "party_b": "上海乙公司",
    "amount": 500000,
    "sign_date": "2024-01-15"
  },
  "tags": ["online", "hard"]
}
```

定期导入 Tune Engine benchmark，下次 `tune.start` 会覆盖这些真实失败场景。

**操作步骤：**

1. 从线上日志 / check-mcp 响应 / 总结输出收集失败记录
2. 人工或脚本补全 `ground_truth`（标准答案）
3. 执行导入脚本（见 12.5）
4. 每周或积累满 N 条后执行 `tune.start`

#### 结合点 C：总 Agent 统一入口，按意图分流

总 Agent 同时挂两个 MCP：

| MCP 服务 | 地址 | 工具 | 触发场景 |
|----------|------|------|----------|
| check-mcp | `:8200` | `check.evaluate` | 每次任务执行后（由 Skill 驱动） |
| tune-mcp | `:8100` | `tune.start` 等 | 用户说「调优」「优化到 xx%」 |

**意图分流规则（写在总 Agent Skill 里）：**

```text
若用户意图是调优（含：调优 / 优化到 / 提升到 / 自动迭代）：
  → 调用 tune.start(target_id=对应技能)
  → 轮询 tune.get_result
  → 汇报最优版本和指标

否则（普通业务提问）：
  → 走 auto-retry-replan Skill
  → 执行 → check.evaluate → 必要时重试 → 输出
```

### 12.4 失败 case 回流（在线 → 离线）

```text
线上单次循环
  check.evaluate → passed=false
        │
        ▼
  写入 failure_cases.jsonl（追加一条）
        │
        ▼（每周 / 满 20 条）
  python scripts/import_failure_cases.py
        │
        ▼
  Tune Engine benchmark 库更新
        │
        ▼
  tune.start → 针对真实失败场景调优
        │
        ▼
  新版本晋升 → 单次循环基线能力提升
```

### 12.5 失败 case 导入脚本

**自动收集：** `run-log-mcp` 的 `run.log` 在 `passed=false` 时自动追加 `data/failure_cases.jsonl`。

**人工补全：** 无 `ground_truth` 的记录需补标准答案后，方可导入 Tune Engine。

项目脚本：`tune-engine/scripts/import_failure_cases.py`

**failure_cases.jsonl 每行格式：**

```json
{"case_id":"online_001","input":{"query":"..."},"ground_truth":{"party_a":"..."},"tags":["online"]}
```

**导入命令：**

```bash
cd tune-engine
source .venv/bin/activate

# 先初始化过 target 和数据库
python scripts/init_demo.py

# 导入线上收集的失败 case
python scripts/import_failure_cases.py \
  --file ../data/failure_cases.jsonl \
  --suite-id contract_bench_v1

# 触发调优
python scripts/run_demo.py
# 或 curl POST /api/v1/tune/sessions
```

### 12.6 联合使用运行节奏（推荐）

| 频率 | 动作 | 方案 |
|------|------|------|
| **实时** | 用户提问，自动重试 | 方案一 |
| **每天** | 收集 `passed=false` 的记录 | 方案一 → 回流 |
| **每周** | 导入失败 case + `tune.start` | 方案二 |
| **晋升后** | 平台切换到新 `entry_ref` | 方案二 → 方案一 |

### 12.7 联合使用生命周期示例

```text
【第 1 周】只部署方案一
  - 挂 check-mcp + auto-retry-replan Skill
  - 用户问合同解析：第一次 70 分 → 重试 → 90 分
  - 开始记录失败 case 到 failure_cases.jsonl

【第 2 周】部署 Tune Engine，首次联合调优
  - 导入第 1 周积累的 15 条失败 case
  - tune.start → v1→v3，benchmark 通过率 72%→88%
  - 平台生产环境晋升 v3

【第 3 周】联合运行
  - 用户提问：第一次 85 分（比以前高），重试 1 次到 98 分
  - 新失败 case 继续积累

【第 4 周起】常态化
  - 方案一：一直开着（在线兜底）
  - 方案二：每周 tune.start 一次（离线提升基线）
  - 形成「在线兜底 + 离线进化」闭环
```

### 12.8 联合部署检查清单

**方案一（在线）**

- [ ] check-mcp 已部署（`:8200`）
- [ ] 总 Agent 已挂 check-mcp
- [ ] auto-retry-replan Skill 已绑定
- [ ] 工作流描述含重试说明
- [ ] 已验证规划轨迹含 `check.evaluate`

**方案二（离线）**

- [ ] tune-engine 已部署（`:8100`）
- [ ] `agent_platform.py` 已对接真实平台
- [ ] target + benchmark 已注册
- [ ] 已跑通 `run_demo.py` 或 `tune.start`

**联合**

- [ ] 总 Agent 同时挂 check-mcp + tune-mcp
- [ ] Skill 里有意图分流规则（普通提问 vs 调优指令）
- [ ] 失败 case 收集机制已建立（jsonl / 日志）
- [ ] 定期导入脚本已加入周报任务
- [ ] Tune 晋升后有版本切换流程（谁负责、怎么回滚）

### 12.9 联合使用的预期效果

| 指标 | 只用方案一 | 只用方案二 | 联合使用 |
|------|------------|------------|----------|
| 单次成功率 | 中（靠重试拉高） | 低（首次无重试） | **高** |
| 重试次数 | 多 | N/A | **少**（基线已调高） |
| 长期准确率 | 涨得慢 | 涨得快 | **最快** |
| 真实场景覆盖 | 好（线上 case） | 取决于测试集 | **最好** |

---

## 附录：快速命令索引

### 方案一

```bash
cd check-mcp && python server.py      # :8200
cd run-log-mcp && python server.py    # :8300  收集每次运行
# 然后在平台挂 MCP + Skill
```

### 方案二

```bash
cd tune-engine
source .venv/bin/activate
python scripts/init_demo.py
python scripts/run_demo.py
python -m uvicorn app.main:app --port 8100
```

### 联合使用（失败 case 回流）

```bash
cd tune-engine
source .venv/bin/activate
python scripts/import_failure_cases.py \
  --file ../data/failure_cases.jsonl \
  --suite-id contract_bench_v1
python scripts/run_demo.py
```

---

*文档维护：随项目代码更新。核心代码路径见第 7 节清单。*
