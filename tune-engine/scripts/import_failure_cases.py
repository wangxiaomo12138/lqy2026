"""
将线上单次循环收集的失败 case 导入 Tune Engine benchmark。

用法：
  python scripts/import_failure_cases.py --file ../data/failure_cases.jsonl --suite-id contract_bench_v1

failure_cases.jsonl 每行一个 JSON：
{
  "case_id": "online_001",
  "input": {"query": "解析以下合同……"},
  "ground_truth": {"party_a": "甲公司", "party_b": "乙公司", "amount": 500000, "sign_date": "2024-01-15"},
  "tags": ["online", "hard"],
  "weight": 1.2
}

case_id 可省略，会自动生成 online_<timestamp>_<n>
ground_truth 必填（离线评分需要标准答案）
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db
from app.models.tune_models import BenchmarkCase


def load_jsonl(path: Path) -> list[dict]:
    cases = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"⚠ 跳过第 {i} 行（JSON 解析失败）: {e}")
    return cases


def import_cases(file_path: str, suite_id: str, dry_run: bool = False) -> int:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    raw_cases = load_jsonl(path)
    if not raw_cases:
        print("没有可导入的 case")
        return 0

    init_db()
    db = SessionLocal()
    imported = 0
    skipped = 0

    for i, case in enumerate(raw_cases, 1):
        ground_truth = case.get("ground_truth")
        if not ground_truth:
            print(f"⚠ 跳过第 {i} 条：缺少 ground_truth")
            skipped += 1
            continue

        query = case.get("input", {}).get("query") or case.get("query")
        if not query:
            print(f"⚠ 跳过第 {i} 条：缺少 input.query")
            skipped += 1
            continue

        case_id = case.get("case_id") or f"online_{path.stem}_{i:03d}"
        input_json = case.get("input") if case.get("input") else {"query": query}
        if "query" not in input_json:
            input_json["query"] = query

        row_data = {
            "suite_id": suite_id,
            "case_id": case_id,
            "input_json": input_json,
            "ground_truth_json": ground_truth,
            "weight": case.get("weight", 1.0),
            "tags": case.get("tags", ["online"]),
        }

        if dry_run:
            print(f"  [dry-run] 将导入: {case_id}")
            imported += 1
            continue

        existing = (
            db.query(BenchmarkCase)
            .filter(BenchmarkCase.suite_id == suite_id, BenchmarkCase.case_id == case_id)
            .first()
        )
        if existing:
            existing.input_json = row_data["input_json"]
            existing.ground_truth_json = row_data["ground_truth_json"]
            existing.weight = row_data["weight"]
            existing.tags = row_data["tags"]
            print(f"  ✓ 更新: {case_id}")
        else:
            db.add(BenchmarkCase(**row_data))
            print(f"  ✓ 新增: {case_id}")
        imported += 1

    if not dry_run:
        db.commit()
    db.close()

    print(f"\n完成：导入 {imported} 条，跳过 {skipped} 条，suite_id={suite_id}")
    if imported > 0 and not dry_run:
        print("下一步: python scripts/run_demo.py  或  curl POST /api/v1/tune/sessions")
    return imported


def main():
    parser = argparse.ArgumentParser(description="导入线上失败 case 到 Tune Engine benchmark")
    parser.add_argument("--file", "-f", required=True, help="failure_cases.jsonl 路径")
    parser.add_argument("--suite-id", "-s", default="contract_bench_v1", help="benchmark 套件 ID")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入数据库")
    args = parser.parse_args()
    import_cases(args.file, args.suite_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
