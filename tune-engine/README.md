# Tune Engine - 通用 Agent 循环调优（Python MVP）

## 这是什么？

一个**独立后台服务**，帮你自动做这件事：

```
跑测试 → 打分 → 不够好就改配置 → 再跑 → 好了就返回结果
```

你的合同解析工作流不用改，只要**注册**进来就能被自动调优。

---

## 第一步：安装（复制粘贴即可）

打开终端，进入项目目录：

```bash
cd /Users/wanghanbing/Documents/文本资料/l/tune-engine

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate   # Windows 用: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

---

## 第二步：初始化数据（注册合同解析 + 测试样本）

```bash
python scripts/init_demo.py
```

你会看到：
- 注册了 `contract-parse` 这个调优对象
- 导入了 5 条合同样本

---

## 第三步：启动服务

```bash
python -m uvicorn app.main:app --reload --port 8100
```

浏览器打开：http://127.0.0.1:8100/docs  可以看到所有 API。

---

## 第四步：触发一次自动调优

**新开一个终端**，执行：

```bash
# 1. 启动调优
curl -X POST http://127.0.0.1:8100/api/v1/tune/sessions \
  -H "Content-Type: application/json" \
  -d '{"target_id": "contract-parse", "async": false}'

# 如果 async=true（默认），会立刻返回 session_id，然后用下面命令查结果：
curl http://127.0.0.1:8100/api/v1/tune/sessions/你的session_id/result
```

或者直接跑演示脚本（最简单）：

```bash
python scripts/run_demo.py
```

脚本会自动：启动调优 → 等待完成 → 打印最终结果。

---

## 整体架构（你要做的就这一块）

```
你的总 Agent（以后接入）
    ↓ 调用 MCP 工具 tune.start
tune-engine（本项目，Python 后台）
    ↓ 反复调用
你们现有的 Agent 平台（执行合同解析工作流）
```

**现阶段**：用 `MockAgentClient` 模拟你们平台，先跑通循环。
**上线时**：只改一个文件 `app/clients/agent_platform.py`，换成真实 HTTP 调用。

---

## 目录说明（每个文件夹干啥）

```
tune-engine/
├── app/
│   ├── main.py              # 程序入口，启动 FastAPI
│   ├── config.py            # 配置（数据库路径等）
│   ├── database.py          # 数据库连接
│   ├── models/              # 数据表对应的 Python 类
│   ├── schemas/             # API 请求/响应格式
│   ├── api/                 # HTTP 接口（给 MCP 或前端调）
│   ├── engine/              # ★ 核心：调优循环逻辑
│   ├── evaluators/          # ★ 评分器（合同解析怎么算分）
│   ├── clients/             # ★ 调你们 Agent 平台的客户端
│   └── mcp/                 # MCP 工具定义（给总 Agent 用）
├── scripts/
│   ├── init_demo.py         # 初始化演示数据
│   └── run_demo.py          # 一键跑演示
├── examples/                # 示例配置 JSON
└── spec/                    # 设计文档（之前生成的）
```

---

## 接入你们真实平台（最重要的一步）

打开 `app/clients/agent_platform.py`，找到 `RealAgentPlatformClient`，把 `run` 方法改成调你们平台的 HTTP 接口：

```python
def run(self, entry_ref: str, input_data: dict) -> dict:
  response = httpx.post(
      "http://你们的平台地址/internal/agent/run",
      json={"entry_ref": entry_ref, "input": input_data, "trace_enabled": True},
      timeout=120,
  )
  return response.json()
```

然后在 `app/config.py` 里设：

```python
USE_MOCK_AGENT = False
AGENT_PLATFORM_URL = "http://你们的平台地址"
```

---

## 新增一个技能怎么调优？（3 步）

### 1. 写 Target 配置

复制 `examples/contract-parse-target.json`，改 `target_id`、 `entry_ref` 等。

### 2. 准备测试样本

复制 `examples/contract-bench-cases.sample.json`，填真实输入和标准答案。

### 3. 注册

```bash
curl -X POST http://127.0.0.1:8100/api/v1/targets -H "Content-Type: application/json" -d @你的target.json
curl -X POST http://127.0.0.1:8100/api/v1/benchmarks/你的suite_id/cases -H "Content-Type: application/json" -d @你的cases.json
```

然后 `tune.start(target_id="你的技能ID")` 即可。

---

## MCP 接入总 Agent

总 Agent 配置里添加 MCP 服务地址：`http://127.0.0.1:8100/mcp`

可用工具：
| 工具 | 作用 |
|------|------|
| `tune.start` | 开始调优 |
| `tune.status` | 查进度 |
| `tune.get_result` | 拿最终结果 |

---

## 常见问题

**Q: 调优循环跑了几轮？**
A: 看 `constraints.max_tune_iters`，默认 8 轮。达标提前停。

**Q: 什么叫 optimal？**
A: 达到 `success_criteria` 里设的通过率等指标。

**Q: 什么叫 best_effort？**
A: 跑满轮数或停滞了，但没达标，返回当前最好的版本。

**Q: 现在自动改了什么？**
A: MVP 阶段模拟改 `skill` 的 prompt（每次加一条规则），真实环境可扩展改 workflow 等。

---

## 2 周上线计划

| 天 | 做什么 |
|----|--------|
| 1 | 跑通本 MVP，理解循环 |
| 2-3 | 换成真实 Agent 平台客户端 |
| 4-5 | 导入真实合同样本 + 评估器微调 |
| 6-7 | 接 MCP 到总 Agent |
| 8-10 | patch 逻辑对接真实配置版本系统 |
