# 小白手把手教程（10 分钟跑通）

## 你要做的事，就 4 步

```
第1步 安装
第2步 初始化数据
第3步 跑演示（看到自动循环调优）
第4步 换成你们真实平台
```

---

## 第 1 步：安装（2 分钟）

打开终端，复制粘贴：

```bash
cd /Users/wanghanbing/Documents/文本资料/l/tune-engine

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## 第 2 步：初始化数据（30 秒）

```bash
python scripts/init_demo.py
```

你会看到：
```
✓ 创建 target: contract-parse
✓ 导入 5 条 benchmark 样本
```

这步做了两件事：
1. **注册**「合同解析」为可调优对象
2. **导入** 5 份合同样本 + 标准答案

---

## 第 3 步：跑演示（1 分钟）

```bash
python scripts/run_demo.py
```

你会看到类似输出：

```
▶ 启动调优 session: ts_20250624_xxx
  起始版本: wf_contract_parse@v1
  目标: pass_rate >= 0.9

  迭代轨迹:
    第1轮: v1  score=35%  → 晋升
    第2轮: v2  score=56%  → 晋升
    第3轮: v3  score=78%  → 晋升
    第4轮: v4  score=95%  → 晋升

  状态: optimal ✓ 达标
  最优版本: wf_contract_parse@v4
```

**这就是自动循环调优**：不够好就改配置再跑，好了就返回。

---

## 第 4 步：启动 HTTP 服务（给总 Agent 调用）

```bash
python -m uvicorn app.main:app --reload --port 8100
```

浏览器打开 http://127.0.0.1:8100/docs 可以看到 API。

### 用 curl 触发调优

```bash
# 先重置数据
python scripts/init_demo.py

# 同步调优（等它跑完）
curl -X POST http://127.0.0.1:8100/api/v1/tune/sessions \
  -H "Content-Type: application/json" \
  -d '{"target_id": "contract-parse", "async": false}'
```

### MCP 方式（总 Agent 调用）

```bash
curl -X POST http://127.0.0.1:8100/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "tune.start", "arguments": {"target_id": "contract-parse", "async": false}}'
```

---

## 第 5 步：换成你们真实 Agent 平台（最关键）

现在用的是**模拟客户端**，不需要你们平台也能演示。

上线时只改 **1 个文件**：

### 文件：`app/clients/agent_platform.py`

找到 `RealAgentPlatformClient.run()`，改成你们平台的 HTTP 地址。

### 文件：`app/config.py`

```python
USE_MOCK_AGENT = False                              # 改成 False
AGENT_PLATFORM_URL = "http://你们平台地址:端口"
```

你们平台需要提供一个接口：

```http
POST /internal/agent/run
Content-Type: application/json

{
  "entry_ref": "wf_contract_parse@v3",
  "input": { "file_url": "..." },
  "trace_enabled": true
}
```

返回：

```json
{
  "run_id": "run_xxx",
  "status": "success",
  "output": { "party_a": "...", "amount": 500000 },
  "plan_trace": [...],
  "summary": "解析完成",
  "latency_ms": 3200,
  "cost_tokens": 4500
}
```

---

## 代码怎么看？（按这个顺序读）

| 顺序 | 文件 | 干什么 |
|------|------|--------|
| 1 | `scripts/run_demo.py` | 入口，一键演示 |
| 2 | `app/engine/orchestrator.py` | **心脏**：循环逻辑 |
| 3 | `app/evaluators/contract_evaluator.py` | 怎么打分 |
| 4 | `app/engine/patch_proposer.py` | 失败了改什么 |
| 5 | `app/clients/agent_platform.py` | 调你们平台 |
| 6 | `app/mcp/tools.py` | 给总 Agent 用的 MCP 工具 |

### 循环逻辑就在 `orchestrator.py` 的 `run_session()`：

```
for 每一轮:
    1. 跑全部测试样本 (run_benchmark)
    2. 打分 (evaluate)
    3. 达标了？→ 返回 optimal
    4. 到上限了？→ 返回 best_effort
    5. 归因 + 生成补丁 (diagnose + propose_patch)
    6. 应用补丁，版本 v1→v2→v3...，继续下一轮
```

---

## 新增一个技能怎么调优？

### 1. 写 Target 配置

复制 `examples/contract-parse-target.json`，改：
- `target_id`：新技能 ID
- `entry_ref`：你们工作流地址
- `evaluator_id`：评估器名

### 2. 写评估器

在 `app/evaluators/contract_evaluator.py` 的 `EVALUATORS` 字典里加：

```python
def my_skill_eval(output, ground_truth):
    # 你的打分逻辑
    return {"score": 0.85, "passed": True, "failures": []}

EVALUATORS["my_skill_eval"] = my_skill_eval
```

### 3. 导入样本 + 注册

```bash
curl -X POST http://127.0.0.1:8100/api/v1/targets -H "Content-Type: application/json" -d @你的target.json
curl -X POST http://127.0.0.1:8100/api/v1/benchmarks/你的suite_id/cases -H "Content-Type: application/json" -d @你的cases.json
```

### 4. 开始调优

```bash
curl -X POST http://127.0.0.1:8100/api/v1/tune/sessions \
  -H "Content-Type: application/json" \
  -d '{"target_id": "你的技能ID", "async": false}'
```

---

## 接到总 Agent 上

总 Agent 配置里：

1. **添加 MCP**：`http://你的服务器:8100/mcp`
2. **添加 Skill**（内容示例）：

```markdown
当用户说「调优」「优化到xx%」时：
1. 识别 target_id（如 contract-parse）
2. 调用 MCP 工具 tune.start
3. 调用 tune.get_result 获取最终结果
4. 向用户报告：是否达标、最优版本、分数
```

3. **工作流**（可选）：解析意图 → tune.start → tune.get_result → 总结

---

## 常见问题

**Q: `optimal` 和 `best_effort` 区别？**
- `optimal` = 达标了，可以放心用
- `best_effort` = 跑满了还没达标，返回目前最好的版本

**Q: 每轮自动改了什么？**
- MVP 阶段：给 skill 加一条规则（模拟）
- 接真实平台后：调 `apply_patch` 接口改 workflow/skill 配置

**Q: 怎么重新演示？**
```bash
python scripts/init_demo.py   # 重置到 v1
python scripts/run_demo.py    # 再跑一遍
```

**Q: 数据库在哪？**
- `tune-engine/data/tune.db`（SQLite，自动创建）
