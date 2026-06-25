"""失败归因 + 补丁生成"""

from typing import Any


def diagnose(eval_result: dict) -> dict:
    """
    根据评估结果判断问题类型。
    MVP 阶段用简单规则，后续可接 LLM。
    """
    failures = eval_result.get("failures_summary", [])
    pass_rate = eval_result.get("pass_rate", 0)

    if not failures:
        return {"tags": ["NO_FAILURE"], "summary": "无失败"}

    # 统计哪个字段错最多
    field_counts: dict[str, int] = {}
    for f in failures:
        field = f.get("field", "unknown")
        field_counts[field] = field_counts.get(field, 0) + 1

    top_field = max(field_counts, key=field_counts.get)

    tags = []
    if pass_rate < 0.5:
        tags.append("LOW_PASS_RATE")
    if any("amount" in str(f.get("field", "")) for f in failures):
        tags.append("AMOUNT_ERROR")
    if any("date" in str(f.get("field", "")) for f in failures):
        tags.append("DATE_ERROR")
    tags.append("FIELD_MISMATCH")

    return {
        "tags": tags,
        "top_field": top_field,
        "field_counts": field_counts,
        "summary": f"通过率 {pass_rate:.0%}，最多错误字段: {top_field}",
    }


# 字段 → 补丁建议映射
FIELD_PATCH_HINTS = {
    "amount": "金额字段必须提取纯数字，去掉逗号和货币符号",
    "sign_date": "日期统一输出 YYYY-MM-DD 格式",
    "party_a": "甲方名称必须与合同首页一致，不要简称",
    "party_b": "乙方名称必须与合同首页一致，不要简称",
    "payment_terms": "付款条款需完整提取，包含结算周期",
    "penalty_clause": "违约责任条款需完整提取原文关键句",
}


def propose_patch(diagnosis: dict, patchable_components: list[str]) -> dict:
    """
    生成一个补丁（每轮只改一个旋钮）。
    MVP：改 skill 的 prompt 规则。
    """
    top_field = diagnosis.get("top_field", "")
    hint = FIELD_PATCH_HINTS.get(top_field, f"请准确提取字段 {top_field}")

    # 优先改 skill
    if "skill" in patchable_components:
        return {
            "target_type": "skill",
            "type": "skill",
            "component_id": "contract-parse-skill",
            "action": "append_rule",
            "content": hint,
            "rationale": diagnosis.get("summary", ""),
        }

    if "workflow" in patchable_components:
        return {
            "target_type": "workflow",
            "type": "workflow",
            "action": "add_validation_step",
            "field": top_field,
            "rationale": diagnosis.get("summary", ""),
        }

    return {
        "target_type": "none",
        "type": "none",
        "action": "noop",
        "rationale": "无可补丁组件",
    }
