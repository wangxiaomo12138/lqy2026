"""初始化演示数据：注册合同解析 target + 5 条测试样本"""

import json
import sys
from pathlib import Path

# 把项目根目录加入 Python 路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db
from app.models.tune_models import BenchmarkCase, TargetRegistry
from app.clients.agent_platform import MockAgentClient

BENCH_CASES = [
    {
        "case_id": "contract_case_01",
        "input": {"file_url": "bench/standard_01.pdf"},
        "ground_truth": {
            "party_a": "北京甲科技有限公司",
            "party_b": "上海乙贸易有限公司",
            "amount": 500000,
            "sign_date": "2024-01-15",
        },
        "weight": 1.0,
        "tags": ["easy"],
    },
    {
        "case_id": "contract_case_02",
        "input": {"file_url": "bench/standard_02.pdf"},
        "ground_truth": {
            "party_a": "广州丙建设集团有限公司",
            "party_b": "深圳丁装饰工程有限公司",
            "amount": 2800000,
            "sign_date": "2023-11-08",
            "payment_terms": "按月结算，次月15日前支付",
        },
        "weight": 1.0,
        "tags": ["medium"],
    },
    {
        "case_id": "contract_case_03",
        "input": {"file_url": "bench/nested_table_03.pdf"},
        "ground_truth": {
            "party_a": "杭州戊信息技术有限公司",
            "party_b": "南京己网络科技有限公司",
            "amount": 960000,
            "sign_date": "2024-06-01",
            "penalty_clause": "逾期付款按日万分之五计收违约金",
        },
        "weight": 1.2,
        "tags": ["hard"],
    },
    {
        "case_id": "contract_case_04",
        "input": {"file_url": "bench/scan_04.pdf"},
        "ground_truth": {
            "party_a": "成都庚物流有限公司",
            "party_b": "重庆辛运输有限公司",
            "amount": 150000,
            "sign_date": "2024-03-20",
        },
        "weight": 1.0,
        "tags": ["scan"],
    },
    {
        "case_id": "contract_case_05",
        "input": {"file_url": "bench/long_05.pdf"},
        "ground_truth": {
            "party_a": "武汉壬咨询有限公司",
            "party_b": "长沙癸企业管理有限公司",
            "amount": 3200000,
            "sign_date": "2023-08-10",
            "payment_terms": "分期支付，签约付30%",
        },
        "weight": 1.5,
        "tags": ["hard", "long"],
    },
]


def main():
    init_db()
    db = SessionLocal()

    target_config = {
        "target_id": "contract-parse",
        "name": "合同解析",
        "description": "从合同中抽取结构化字段",
        "type": "workflow",
        "entry_ref": "wf_contract_parse@v1",
        "benchmark_suite_id": "contract_bench_v1",
        "evaluator_id": "contract_field_eval",
        "patchable_components": ["skill", "workflow", "agent"],
        "success_criteria": {
            "min_pass_rate": 0.90,
            "min_field_f1": 0.88,
        },
        "constraints": {
            "max_tune_iters": 8,
            "single_knob_per_iter": True,
            "stagnation_window": 3,
            "min_delta": 0.02,
        },
        "enabled": True,
        "version": 1,
    }

    existing = db.query(TargetRegistry).filter(TargetRegistry.target_id == "contract-parse").first()
    if existing:
        existing.config_json = target_config
        existing.entry_ref = "wf_contract_parse@v1"  # 每次初始化重置到 v1
        print("✓ 更新 target: contract-parse（已重置为 v1）")
    else:
        db.add(TargetRegistry(
            target_id="contract-parse",
            name="合同解析",
            description="从合同中抽取结构化字段",
            type="workflow",
            entry_ref="wf_contract_parse@v1",
            config_json=target_config,
            benchmark_suite_id="contract_bench_v1",
            evaluator_id="contract_field_eval",
        ))
        print("✓ 创建 target: contract-parse")

    for case in BENCH_CASES:
        row = (
            db.query(BenchmarkCase)
            .filter(BenchmarkCase.suite_id == "contract_bench_v1", BenchmarkCase.case_id == case["case_id"])
            .first()
        )
        if row:
            row.input_json = case["input"]
            row.ground_truth_json = case["ground_truth"]
        else:
            db.add(BenchmarkCase(
                suite_id="contract_bench_v1",
                case_id=case["case_id"],
                input_json=case["input"],
                ground_truth_json=case["ground_truth"],
                weight=case.get("weight", 1.0),
                tags=case.get("tags"),
            ))

    db.commit()
    db.close()

    # 重置模拟客户端内存状态
    MockAgentClient._version_configs = {}

    print(f"✓ 导入 {len(BENCH_CASES)} 条 benchmark 样本")
    print("\n下一步: python -m uvicorn app.main:app --reload --port 8100")
    print("然后:   python scripts/run_demo.py")


if __name__ == "__main__":
    main()
