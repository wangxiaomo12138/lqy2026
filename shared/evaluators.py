"""合同解析等任务的评分逻辑（check-mcp / run-log-mcp 共用）"""

import json
import re


def normalize(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def parse_output(output: dict | str) -> dict:
    if isinstance(output, dict):
        return output
    text = str(output)
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"_raw_text": text}


def evaluate_summary(summary: str, expected_fields: list[str], output: dict) -> dict:
    """评估总结是否提及关键字段 / 是否承认缺失"""
    if not summary:
        return {"summary_score": 0.0, "summary_issues": ["总结为空"]}

    text = str(summary).lower()
    issues = []
    mentioned = 0
    for f in expected_fields:
        if f.lower() in text or normalize(output.get(f)):
            mentioned += 1
        elif f in (output or {}) and output.get(f) is not None:
            mentioned += 1
        else:
            issues.append(f"总结未体现字段 {f}")

    total = len(expected_fields) or 1
    score = round(mentioned / total, 4)
    return {"summary_score": score, "summary_issues": issues}


def evaluate_contract(output: dict, expected_fields: list[str], summary: str = "") -> dict:
    failures = []
    missing = []
    for f in expected_fields:
        val = output.get(f)
        if val is None or normalize(val) == "":
            missing.append(f)
            failures.append({"type": "missing_field", "field": f})

    if "sign_date" in output and output.get("sign_date"):
        sd = str(output["sign_date"])
        if len(sd) != 10 or sd[4] != "-" or sd[7] != "-":
            failures.append({"type": "format_error", "field": "sign_date", "message": "应为 YYYY-MM-DD"})

    if "amount" in output and output.get("amount") is not None:
        try:
            float(output["amount"])
        except (TypeError, ValueError):
            failures.append({"type": "format_error", "field": "amount", "message": "应为数字"})

    total = len(expected_fields) or 1
    correct = total - len(missing)
    field_score = round(correct / total, 4)

    summary_eval = evaluate_summary(summary, expected_fields, output)
    summary_score = summary_eval["summary_score"]

    # 综合分：字段 70% + 总结 30%
    combined_score = round(0.7 * field_score + 0.3 * summary_score, 4)
    passed = len(failures) == 0 and field_score >= 0.8 and summary_score >= 0.6

    return {
        "passed": passed,
        "score": combined_score,
        "field_score": field_score,
        "summary_score": summary_score,
        "failure_points": {
            "missing_fields": missing,
            "failures": failures,
            "summary_issues": summary_eval["summary_issues"],
        },
        "recommendation": "补全缺失字段后重试" if not passed else "可进入最终总结",
    }


EVALUATORS = {
    "contract-parse": evaluate_contract,
}
