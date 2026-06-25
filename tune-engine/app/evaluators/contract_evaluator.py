"""评估器：判断 Agent 输出好不好"""

from typing import Any


def normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value).replace(".0", "") if float(value) == int(value) else str(value)
    return str(value).strip().lower()


def contract_field_eval(output: dict, ground_truth: dict) -> dict:
    """
    合同解析评估器：逐字段对比。
    返回 score(0~1), passed(bool), failures(list)
    """
    if not output:
        return {"score": 0.0, "passed": False, "failures": [{"field": "*", "reason": "无输出"}]}

    fields = list(ground_truth.keys())
    if not fields:
        return {"score": 1.0, "passed": True, "failures": []}

    correct = 0
    failures = []
    for field in fields:
        pred = normalize(output.get(field))
        truth = normalize(ground_truth.get(field))
        if pred == truth:
            correct += 1
        else:
            failures.append({
                "field": field,
                "expected": ground_truth.get(field),
                "actual": output.get(field),
            })

    score = correct / len(fields)
    passed = score >= 0.8 and len(failures) <= 1
    return {"score": round(score, 4), "passed": passed, "failures": failures}


# 评估器注册表：新增技能时在这里加一行
EVALUATORS = {
    "contract_field_eval": contract_field_eval,
}


def evaluate_output(evaluator_id: str, output: dict, ground_truth: dict) -> dict:
    fn = EVALUATORS.get(evaluator_id)
    if not fn:
        raise ValueError(f"未知评估器: {evaluator_id}")
    return fn(output, ground_truth)


def aggregate_eval_results(case_results: list[dict]) -> dict:
    """把多个 case 的评估聚合成整体指标"""
    if not case_results:
        return {
            "aggregate_score": 0.0,
            "pass_rate": 0.0,
            "metrics": {"field_f1": 0.0, "case_count": 0},
            "failures_summary": [],
        }

    total_weight = sum(r.get("weight", 1.0) for r in case_results)
    weighted_score = sum(r["score"] * r.get("weight", 1.0) for r in case_results)
    aggregate_score = weighted_score / total_weight

    passed_count = sum(1 for r in case_results if r["passed"])
    pass_rate = passed_count / len(case_results)

    all_failures = []
    for r in case_results:
        for f in r.get("failures", []):
            all_failures.append({**f, "case_id": r.get("case_id")})

    return {
        "aggregate_score": round(aggregate_score, 4),
        "pass_rate": round(pass_rate, 4),
        "metrics": {
            "field_f1": round(aggregate_score, 4),
            "case_count": len(case_results),
            "passed_count": passed_count,
        },
        "failures_summary": all_failures[:20],
        "case_results": case_results,
    }


def criteria_met(eval_result: dict, success_criteria: dict) -> bool:
    """检查是否达到 optimal 标准"""
    if not success_criteria:
        return eval_result.get("pass_rate", 0) >= 0.9

    pass_rate = eval_result.get("pass_rate", 0)
    field_f1 = eval_result.get("metrics", {}).get("field_f1", 0)

    if "min_pass_rate" in success_criteria and pass_rate < success_criteria["min_pass_rate"]:
        return False
    if "min_field_f1" in success_criteria and field_f1 < success_criteria["min_field_f1"]:
        return False
    return True
