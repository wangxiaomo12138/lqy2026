# 不改平台底层，实现 Agent 内单次循环重规划

你们只能**接入使用**平台，不能改底层代码。  
做法：**用平台已有能力拼出循环**——Skill 教规划怎么循环，MCP 负责检查，工作流负责执行。

---

## 核心思路：用「5 步规划」当循环，而不是写循环代码

你们 Agent 已有：

```text
query → 规划模型（最多5步）→ 工作流执行 → 总结模型 → 答案
```

不能改底层，就让**规划模型按 Skill 指示**，把 5 步分成：

```text
Step1  第一次执行工作流
Step2  调用 MCP 检查结果
Step3  不好 → 带问题点重跑工作流
Step4  再检查 / 再修正
Step5  总结输出（最优一次）
```

**循环逻辑在 Skill + MCP 里，不在平台底层。**

---

## 你要接入的 3 样东西

| 组件 | 作用 | 你怎么弄 |
|------|------|----------|
| **Skill** `auto-retry-replan` | 教规划模型：何时检查、何时重试 | 复制 `skills/auto-retry-replan/SKILL.md` 到平台 |
| **MCP** `check-mcp` | 执行后检查，返回 failure_points | 部署 `check-mcp/server.py`，挂到 Agent |
| **工作流描述** | 让规划知道如何路由到业务工作流 | 在平台里改描述文案 |

---

## 操作步骤（按顺序做）

### 第 1 步：部署检查 MCP（10 分钟）

```bash
cd /Users/wanghanbing/Documents/文本资料/l/check-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

服务地址：`http://你的服务器:8200`

在平台里给总 Agent **添加 MCP**：`check-mcp`  
工具名：`check.evaluate`

### 第 2 步：给总 Agent 挂上 Skill

把 `skills/auto-retry-replan/SKILL.md` 的内容，在平台里创建 Skill 并绑到总 Agent。

### 第 3 步：改工作流描述（让规划能路由）

在合同解析工作流的描述里写清楚，例如：

```text
【工作流名称】合同解析
【触发条件】用户要求解析合同、抽取字段、输出JSON
【输入】合同正文或 query 中的合同内容
【输出】JSON，字段：party_a, party_b, amount, sign_date
【注意】若 query 中含【上次执行问题】，必须优先修正这些问题
```

### 第 4 步：配置总结模型 prompt（加一句）

```text
最终输出必须包含：
- status: optimal 或 best_effort
- attempts: 尝试次数
- result: 结构化 JSON 结果
若未完全通过检查，在 issues 中说明遗留问题
```

### 第 5 步：测试

用一个故意容易出错的 query 测试：

```text
解析以下合同，输出JSON字段 party_a, party_b, amount, sign_date：
【短合同正文……】
```

观察规划是否：
1. 先跑工作流
2. 调 `check.evaluate`
3. 未通过则带 failure_points 再跑
4. 最后总结

---

## 一次请求的完整链路

```text
用户 query
    ↓
总 Agent + auto-retry-replan Skill
    ↓
Step1 规划 → 路由到「合同解析工作流」→ 得到 output_v1
    ↓
Step2 规划 → 调 MCP check.evaluate(output_v1)
    ↓
    ├─ passed=true  → Step5 总结输出 optimal
    └─ passed=false → 拿到 failure_points
            ↓
Step3 规划 → 构造「原始query + 上次问题」→ 再跑工作流 → output_v2
    ↓
Step4 规划 → 再 check.evaluate(output_v2)
    ↓
Step5 总结 → 选最优 output 作为最终结果
```

---

## failure_points 长什么样

MCP `check.evaluate` 返回示例：

```json
{
  "passed": false,
  "score": 0.75,
  "failure_points": {
    "missing_fields": ["amount"],
    "failures": [
      {"type": "missing_field", "field": "amount"}
    ]
  },
  "recommendation": "补全缺失字段后重试"
}
```

规划模型在 Step3 应把上述信息写进重试 query，例如：

```text
【原始任务】
解析以下合同，输出 JSON：party_a, party_b, amount, sign_date
【合同正文】……

【上次执行问题】
- 缺失字段: amount
- 评分: 0.75

【重试要求】
必须补全 amount 字段，金额提取为纯数字
```

---

## 平台能力对照：每步用什么

| 循环步骤 | 用平台什么能力 |
|----------|----------------|
| 执行工作流 | Agent 规划 → 工作流 |
| 检查结果 | MCP `check.evaluate` |
| 记录不好点 | MCP 返回值 → 规划上下文（不用另建库） |
| 重规划 | 规划模型 Step3/4（Skill 约束） |
| 最终输出 | 总结模型 Step5 |

**不需要改平台代码，只需要会配 Agent / Skill / MCP / 工作流描述。**

---

## limitations（诚实说）

| 限制 | 应对 |
|------|------|
| 规划模型不一定严格按 Skill 走 | Skill 写死步数模板；多测几次调 prompt |
| 5 步可能不够复杂任务 | 优先保证「执行→检查→重试→总结」4 步闭环 |
| 检查规则太简单 | 扩展 `check-mcp` 里对应 task_type 的评估逻辑 |
| 规划偶尔不调 MCP | 在工作流描述里加：「执行后必须调用 check.evaluate」 |

---

## 和 Tune Engine 的关系

| 能力 | 放哪 | 何时用 |
|------|------|--------|
| 单次 query 当场重试 | Agent + Skill + check-mcp | 用户每次提问 |
| 长期把配置调好 | Tune Engine | 定期/批量调优 |

建议：**先接 Skill + check-mcp**，单次体验立刻变好；再用 Tune Engine 离线优化工作流配置。

---

## 文件位置

```text
skills/auto-retry-replan/SKILL.md   ← 复制到平台 Skill
check-mcp/server.py                 ← 部署为 MCP 服务
```

---

## 你现在就可以做的最小验证

1. 启动 `check-mcp`
2. 总 Agent 挂 MCP + Skill
3. 发一个合同解析 query
4. 看规划轨迹里有没有出现 `check.evaluate` 和第二次工作流执行

如果没有，把你们平台里**一次请求的规划轨迹**贴给我，我帮你看 Skill 要怎么改才能稳住重规划。
