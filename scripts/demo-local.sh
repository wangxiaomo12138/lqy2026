#!/usr/bin/env bash
# 本地演示脚本：案例 A（缺字段）→ 记录 → 案例 B（补全）→ 统计
# 用法：bash scripts/demo-local.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_URL="${CHECK_URL:-http://127.0.0.1:8200}"
LOG_URL="${LOG_URL:-http://127.0.0.1:8300}"

echo "=============================================="
echo "  Agent 循环调优 — 本地 API 演示"
echo "  check: $CHECK_URL"
echo "  run-log: $LOG_URL"
echo "=============================================="
echo ""

check_health() {
  curl -sf "$CHECK_URL/health" >/dev/null || {
    echo "❌ check-mcp 未启动。请先运行："
    echo "   cd check-mcp && python app.py"
    exit 1
  }
  curl -sf "$LOG_URL/health" >/dev/null || {
    echo "❌ run-log-mcp 未启动。请先运行："
    echo "   cd run-log-mcp && python app.py"
    exit 1
  }
  echo "✓ 服务健康检查通过"
  echo ""
}

check_health

echo "【案例 A】第一次解析 — 缺少 amount / sign_date"
echo "----------------------------------------------"
CHECK_A=$(curl -s -X POST "$CHECK_URL/api/v1/check/evaluate" \
  -H 'Content-Type: application/json' \
  -d '{
    "task_type": "contract-parse",
    "output": {
      "party_a": "北京甲科技有限公司",
      "party_b": "上海乙贸易有限公司"
    },
    "expected_fields": ["party_a", "party_b", "amount", "sign_date"],
    "summary": "已识别甲乙双方，缺少金额和日期"
  }')
echo "$CHECK_A" | python3 -m json.tool
echo ""

echo "【记录】第 1 次运行 → run.log"
echo "----------------------------------------------"
LOG_A=$(curl -s -X POST "$LOG_URL/api/v1/run/log" \
  -H 'Content-Type: application/json' \
  -d "{
    \"target_id\": \"contract-parse\",
    \"task_type\": \"contract-parse\",
    \"query\": \"解析合同：北京甲科技有限公司、上海乙贸易有限公司\",
    \"output\": {
      \"party_a\": \"北京甲科技有限公司\",
      \"party_b\": \"上海乙贸易有限公司\"
    },
    \"summary\": \"已识别甲乙双方，缺少金额和日期\",
    \"expected_fields\": [\"party_a\", \"party_b\", \"amount\", \"sign_date\"],
    \"attempt\": 1,
    \"check_result\": $CHECK_A
  }")
echo "$LOG_A" | python3 -m json.tool
echo ""

echo "【案例 B】重试后补全 — 应 passed=true"
echo "----------------------------------------------"
CHECK_B=$(curl -s -X POST "$CHECK_URL/api/v1/check/evaluate" \
  -H 'Content-Type: application/json' \
  -d '{
    "task_type": "contract-parse",
    "output": {
      "party_a": "北京甲科技有限公司",
      "party_b": "上海乙贸易有限公司",
      "amount": 100000,
      "sign_date": "2026-01-15"
    },
    "expected_fields": ["party_a", "party_b", "amount", "sign_date"],
    "summary": "party_a 北京甲科技 party_b 上海乙贸易 amount 100000 sign_date 2026-01-15"
  }')
echo "$CHECK_B" | python3 -m json.tool
echo ""

echo "【记录】第 2 次运行 → run.log"
echo "----------------------------------------------"
curl -s -X POST "$LOG_URL/api/v1/run/log" \
  -H 'Content-Type: application/json' \
  -d "{
    \"target_id\": \"contract-parse\",
    \"task_type\": \"contract-parse\",
    \"query\": \"解析合同：北京甲科技有限公司、上海乙贸易有限公司\",
    \"output\": {
      \"party_a\": \"北京甲科技有限公司\",
      \"party_b\": \"上海乙贸易有限公司\",
      \"amount\": 100000,
      \"sign_date\": \"2026-01-15\"
    },
    \"summary\": \"解析完成\",
    \"expected_fields\": [\"party_a\", \"party_b\", \"amount\", \"sign_date\"],
    \"attempt\": 2,
    \"check_result\": $CHECK_B
  }" | python3 -m json.tool
echo ""

echo "【统计】近期运行情况"
echo "----------------------------------------------"
curl -s "$LOG_URL/api/v1/run/stats?target_id=contract-parse" | python3 -m json.tool
echo ""
echo "=============================================="
echo "  演示完成"
echo "  平台通后：同上 URL/body 配进工作流 API 节点"
echo "  详见：docs/演示指南-平台与本地.md"
echo "=============================================="
