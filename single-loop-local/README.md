# single-loop-local — 本地单次循环（不依赖 Agent 平台）

平台 MCP 不通时，用这个目录在本地跑完整的 **执行 → 检查 → 重试 → 总结** 循环。

直接调用你们封装的模型服务，评估规则复用 `shared/evaluators.py`（与 check-mcp 一致）。

---

## 和平台方案的关系

| | 平台方案 | 本目录 |
|--|----------|--------|
| 执行 | 工作流 / Agent | **你的模型 API** |
| 检查 | check-mcp MCP | **本地 evaluators** |
| 重试策略 | Skill 教规划 | **Python 循环** |
| 记录 | run-log-mcp | **写 run_logs.jsonl** |

逻辑等价，只是不经过平台。

---

## 快速开始

### 1. 安装依赖

```bash
cd single-loop-local
pip install -r requirements.txt
```

### 2. 配置模型服务

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填你们的模型地址和 key
```

**OpenAI 兼容接口**（最常见）：

```yaml
model:
  style: openai
  base_url: "http://你的模型服务/v1"
  api_key: "你的key"
  model: "模型名"
```

**自定义 HTTP 接口**：

```yaml
model:
  style: http_json
  http_json:
    endpoint: "http://你的服务/api/chat"
    body_template:
      query: "{query}"
    response_text_path: "data.answer"   # 响应 JSON 里文本字段路径
```

### 3. 运行

```bash
# 命令行直接传 query
python run.py --query "解析合同：甲公司、乙公司，金额10万，日期2026-01-15"

# 从示例文件读
python run.py --file examples/contract.txt

# 只输出 JSON
python run.py --file examples/contract.txt --json
```

---

## 循环逻辑

```
第 1 轮：模型抽取 → 规则评估
         ├─ passed → 总结 → 结束 (optimal)
         └─ 未通过 → 把 failure_points 写入下一轮 prompt

第 2~N 轮：带失败信息重试 → 再评估
         ├─ passed → optimal
         └─ 仍失败或分数不再提升 → best_effort + 总结
```

默认最多 3 轮，可在 `config.yaml` 的 `loop.max_attempts` 修改。

---

## 配置说明

| 配置段 | 作用 |
|--------|------|
| `model` | 模型服务地址、鉴权、调用风格 |
| `loop` | task_type、最大重试次数 |
| `task` | expected_fields、output_schema |
| `logging` | 运行日志写入路径 |

新业务：改 `task.expected_fields` 和 `loop.task_type`；若需新评估器，在 `shared/evaluators.py` 注册。

---

## 输出示例

```
状态: optimal  |  尝试次数: 2  |  分数: 0.95
------------------------------------------------------------
最终结果:
{
  "party_a": "北京甲科技有限公司",
  "party_b": "上海乙贸易有限公司",
  "amount": 100000,
  "sign_date": "2026-01-15"
}
------------------------------------------------------------
总结:
...
```

日志自动追加到 `data/run_logs.jsonl`，失败记录写入 `data/failure_cases.jsonl`（可导入 Tune Engine）。

---

## 对接你们模型服务

把 `config.yaml` 里这三项改成实际值即可：

1. `base_url` 或 `http_json.endpoint`
2. `api_key`（如需）
3. `model` 名称

若接口格式特殊，改 `model_client.py` 的 `_chat_http_json` 或新增 `style`。

---

## 目录结构

```
single-loop-local/
├── config.yaml.example   # 配置模板
├── config.py             # 配置加载
├── model_client.py       # 模型服务客户端
├── loop.py               # 单次循环编排
├── run.py                # CLI 入口
├── examples/             # 示例输入
└── README.md
```
