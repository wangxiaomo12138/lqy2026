# run-log-mcp

收集平台每次运行的 `output` / `summary`，自动评分并写入 jsonl。

## 启动

```bash
cd run-log-mcp
pip install -r requirements.txt
python server.py
# http://127.0.0.1:8300
```

## 工具

| 工具 | 作用 |
|------|------|
| `run.log` | 记录本次运行，自动评分，失败写入 failure_cases.jsonl |
| `run.stats` | 查看近期通过率 |

## 数据文件

- `data/run_logs.jsonl` — 全部记录
- `data/failure_cases.jsonl` — 失败记录（可导入 Tune Engine）

## 导入 Tune Engine

```bash
cd tune-engine
python scripts/import_failure_cases.py --file ../data/failure_cases.jsonl
```
