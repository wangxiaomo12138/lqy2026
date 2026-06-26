# auto-retry-replan-api Skill（API / Flask 版）

当平台 **MCP 接入不通** 时，用本 Skill 替代 `auto-retry-replan`。  
检查与记录通过 **工作流 API 节点** 调用 Flask HTTP 接口，不依赖 MCP。

## 服务框架

check-mcp / run-log-mcp 默认以 **Flask** 启动：

```bash
cd check-mcp && python app.py      # :8200
cd run-log-mcp && python app.py    # :8300
```

API 路径与通用 HTTP 客户端完全兼容，平台 API 节点直接 POST 即可。

## 适用场景

- 合同解析、信息抽取、结构化输出
- 平台支持工作流/API 节点，但不支持或不稳定支持 MCP SSE
- 需要「执行 → 检查 → 记录 → 重试」单次循环
- 需要积累运行数据供 Tune Engine 离线调优

## 核心原则

1. **执行完必须检查**：调用 `POST /api/v1/check/evaluate`
2. **检查后必须记录**：调用 `POST /api/v1/run/log`
3. **失败要带 failure_points 重试**：下一轮 query = 原始任务 + 上次问题
4. **最多 3 次执行**（或受平台步数限制）
5. **输出最优一次**：`optimal` 或 `best_effort`

## 依赖 HTTP 服务（非 MCP）

| 服务 | 地址 | 用途 |
|------|------|------|
| check-mcp | `http://YOUR_HOST:8200/api/v1/check/evaluate` | 检查 output |
| run-log-mcp | `http://YOUR_HOST:8300/api/v1/run/log` | 记录每次运行 |

将 `YOUR_HOST` 替换为实际服务器 IP 或域名。

---

## 5 步工作流分配（配合 wf_retry_wrapper_api）

| 步数 | 动作 | API |
|------|------|-----|
| Step 1 | 执行业务工作流 | — |
| Step 2 | 检查 + 记录 | check.evaluate + run.log（attempt=1） |
| Step 3 | 条件重试 | passed=false 时带 failure_points 重跑 Step 1 |
| Step 4 | 再检查 + 记录 | check.evaluate + run.log（attempt=2） |
| Step 5 | 总结 | optimal / best_effort |

工作流模板见：`integrations/workflows/wf_retry_wrapper_api.json`

---

## API 1：检查（check.evaluate）

```http
POST http://YOUR_HOST:8200/api/v1/check/evaluate
Content-Type: application/json

{
  "task_type": "contract-parse",
  "output": <上一步工作流输出>,
  "expected_fields": ["party_a", "party_b", "amount", "sign_date"],
  "summary": <总结文本，尚未总结可传 "">
}
```

**关键响应字段：**

- `passed`：是否通过
- `score` / `field_score` / `summary_score`
- `failure_points`：重试时带入下一轮
- `recommendation`：给规划模型的提示

---

## API 2：记录（run.log）——检查后必调

```http
POST http://YOUR_HOST:8300/api/v1/run/log
Content-Type: application/json

{
  "target_id": "contract-parse",
  "task_type": "contract-parse",
  "query": <用户原始 query>,
  "output": <工作流输出>,
  "summary": <总结，可为 "">,
  "expected_fields": ["party_a", "party_b", "amount", "sign_date"],
  "attempt": 1,
  "agent_id": <当前 Agent ID，可选>,
  "entry_ref": <工作流版本，可选>,
  "check_result": <上一步 check 返回的完整 JSON，推荐传入>
}
```

`check_result` 传入时可复用评分，避免重复计算。

---

## 重试 query 模板

```text
【原始任务】
{original_query}

【上次执行问题】
{将 failure_points 转为自然语言或 JSON}

【重试要求】
1. 针对上述问题修正
2. 必须补全缺失字段
3. 输出格式: {output_schema}
```

---

## 停止条件

- `passed: true` → 进入总结（最后一次 run.log 仍要调用）
- 已达最大尝试次数 → `best_effort` 总结
- 连续两次 score 无提升 → 提前停止

## 最终输出格式

```json
{
  "status": "optimal",
  "attempts": 2,
  "result": { },
  "issues": []
}
```

---

## 新业务接入

只需改 `task_type` 和 `expected_fields`，无需改 API 服务：

```yaml
task_type: invoice-parse
expected_fields: [seller, buyer, amount, tax_id, invoice_date]
```

参考 `integrations/task-registry.yaml`。

---

## 与 MCP 版 Skill 的关系

| | MCP 版 | API 版（本 Skill） |
|--|--------|-------------------|
| Skill | `auto-retry-replan` | `auto-retry-replan-api` |
| 工作流 | `wf_retry_wrapper` | `wf_retry_wrapper_api` |
| 检查 | MCP `check.evaluate` | `POST /api/v1/check/evaluate` |
| 记录 | MCP `run.log` | `POST /api/v1/run/log` |
| 循环逻辑 | 相同 | 相同 |
