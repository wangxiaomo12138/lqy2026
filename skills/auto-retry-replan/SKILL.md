# auto-retry-replan Skill

当用户任务需要**执行 → 检查 → 记录 → 不好就重规划再执行**时，启用本 Skill。

## 适用场景

- 合同解析、信息抽取、结构化输出
- 第一次结果可能不完整，需要当场纠错
- 平台规划步数上限为 5 步
- 需要积累真实运行数据供 Tune Engine 离线调优

## 核心原则

1. **不要一次就结束**：执行完必须检查，检查通过才能总结输出
2. **每次检查后必须记录**：调用 MCP `run.log`，存档 output + summary
3. **失败要记录**：明确写出 missing_fields / format_errors / logic_errors
4. **重规划要带失败信息**：下一轮规划输入 = 原始 query + failure_points
5. **最多 5 步规划**：合理分配步数预算（见下方模板）
6. **最终输出最优一次**：若未全通过，输出分数最高的那次结果，并说明遗留问题

## 依赖 MCP 服务

| MCP | 端口 | 工具 | 用途 |
|-----|------|------|------|
| check-mcp | 8200 | `check.evaluate` | 当场检查是否达标 |
| run-log-mcp | 8300 | `run.log` | **跑完必调**，记录结果与总结 |

---

## 5 步规划分配模板（直接套用）

| 步数 | 动作 | 说明 |
|------|------|------|
| Step 1 | 首次执行 | 按工作流描述，路由到目标工作流，完成任务 |
| Step 2 | 检查 + **记录** | 调 `check.evaluate`；**紧接着调 `run.log`**（attempt=1） |
| Step 3 | 条件重试 | 若 `passed=false`，带 failure_points 重新执行工作流 |
| Step 4 | 再检查 + **记录** | 再调 `check.evaluate`；**再调 `run.log`**（attempt=2） |
| Step 5 | 最终总结 | 选最优一次结果，按输出 schema 总结，写明 attempt 和是否通过 |

---

## 规划器行为规范

### Step 2 / Step 4：检查（check.evaluate）

```
MCP: check.evaluate
参数:
  task_type: "contract-parse"
  output: <上一步工作流输出>
  expected_fields: ["party_a","party_b","amount","sign_date"]
```

### Step 2 / Step 4：记录（run.log）——跑完必调

**每次** `check.evaluate` 之后，**必须**调用 `run.log`：

```
MCP: run.log
参数:
  target_id: "contract-parse"
  task_type: "contract-parse"
  query: <用户原始 query>
  output: <工作流输出>
  summary: <总结模型输出，若尚未总结可传 "">
  plan_trace: <规划轨迹>
  expected_fields: ["party_a","party_b","amount","sign_date"]
  attempt: 1          # 或 2、3…
  agent_id: <当前 Agent ID>
  entry_ref: <当前工作流版本>
  check_result: <上一步 check.evaluate 的完整返回，可选，传入可复用评分>
```

`run.log` 会：

- 自动评分（字段 70% + 总结 30%）
- 写入 `run_logs.jsonl`（全部记录）
- 若 `passed=false`，写入 `failure_cases.jsonl`（供 Tune Engine 导入）

### 若检查未通过，生成 failure_points

```json
{
  "missing_fields": ["amount"],
  "format_errors": ["sign_date 应为 YYYY-MM-DD"],
  "score": 0.6,
  "passed": false
}
```

### 重规划时，必须把 failure_points 传给工作流

```text
【原始任务】
{original_query}

【上次执行问题】
{failure_points 转成自然语言或 JSON}

【重试要求】
1. 针对上述问题修正
2. 必须补全缺失字段
3. 输出格式: {output_schema}
```

---

## 停止条件

满足任一即进入 Step 5 总结：

- `check.evaluate` 返回 `passed: true`（最后一次 run.log 仍要调用）
- 已达第 5 步（必须用当前最优结果总结）
- 连续两次 score 无提升（避免空转）

## 最终总结必须包含

1. `status`: `optimal` 或 `best_effort`
2. `attempts`: 实际尝试次数
3. `result`: 结构化最终结果
4. `issues`: 若 best_effort，列出未解决问题

---

## 完整示例（合同解析）

**用户 query：**
> 解析以下合同，输出 JSON：party_a, party_b, amount, sign_date

| 步数 | 动作 |
|------|------|
| Step 1 | 执行合同解析工作流 → output（缺 amount） |
| Step 2 | `check.evaluate` → passed=false；**`run.log` attempt=1** |
| Step 3 | 带 failure_points 重跑工作流 → 完整 output |
| Step 4 | `check.evaluate` → passed=true；**`run.log` attempt=2** |
| Step 5 | 总结输出 optimal 结果 |

---

## 与 Tune Engine 的数据流

```text
run.log（每次跑完）
  → failure_cases.jsonl（失败记录）
  → import_failure_cases.py
  → Tune Engine benchmark
  → tune.start（批量调优）
```

失败记录若无 `ground_truth`，需人工补标准答案后再导入 Tune Engine。
