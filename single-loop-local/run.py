#!/usr/bin/env python3
"""
本地单次循环 CLI

用法：
  python run.py --query "解析合同：甲公司乙公司，金额10万，签约2026-01-15"
  python run.py --file examples/contract.txt
  python run.py --config config.yaml --query "..."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import load_config
from loop import run_single_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="本地单次循环：执行→检查→重试→总结")
    parser.add_argument("--config", default=None, help="配置文件路径，默认 single-loop-local/config.yaml")
    parser.add_argument("--query", default=None, help="用户问题/待解析文本")
    parser.add_argument("--file", default=None, help="从文件读取 query")
    parser.add_argument("--json", action="store_true", help="只输出 JSON 结果")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    query = args.query
    if args.file:
        query = Path(args.file).read_text(encoding="utf-8").strip()
    if not query:
        parser.error("请提供 --query 或 --file")

    try:
        result = run_single_loop(query, config)
    except Exception as e:
        print(f"运行失败: {e}", file=sys.stderr)
        return 1

    payload = {
        "status": result.status,
        "attempts": result.attempts,
        "task_type": result.task_type,
        "passed": result.best_eval.get("passed"),
        "score": result.best_eval.get("score"),
        "result": result.best_output,
        "summary": result.best_summary,
        "eval": result.best_eval,
        "history": [
            {
                "attempt": h.attempt,
                "passed": h.eval_result.get("passed"),
                "score": h.eval_result.get("score"),
                "output": h.output,
                "failure_points": h.eval_result.get("failure_points"),
            }
            for h in result.history
        ],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)

    return 0 if result.status == "optimal" else 2


def _print_human(payload: dict) -> None:
    print("=" * 60)
    print(f"状态: {payload['status']}  |  尝试次数: {payload['attempts']}  |  分数: {payload['score']}")
    print("-" * 60)
    print("最终结果:")
    print(json.dumps(payload["result"], ensure_ascii=False, indent=2))
    print("-" * 60)
    print("总结:")
    print(payload["summary"])
    print("-" * 60)
    if payload["history"]:
        print("各轮记录:")
        for h in payload["history"]:
            mark = "✓" if h["passed"] else "✗"
            print(f"  第{h['attempt']}轮 {mark} score={h['score']} output={json.dumps(h['output'], ensure_ascii=False)}")
    print("=" * 60)


if __name__ == "__main__":
    raise SystemExit(main())
