"""一键演示：启动调优 → 等待完成 → 打印结果"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db
from app.engine.orchestrator import create_tune_session, get_session_status, run_session


def main():
    print("=" * 60)
    print("  Tune Engine 演示：合同解析自动调优")
    print("=" * 60)

    init_db()
    db = SessionLocal()

    # 创建并同步执行调优（async=false，当前进程内跑完）
    session = create_tune_session(db, target_id="contract-parse", mode="full_auto")
    print(f"\n▶ 启动调优 session: {session.session_id}")
    print(f"  起始版本: {session.start_entry_ref}")
    print(f"  目标: pass_rate >= {session.success_criteria_json.get('min_pass_rate', 0.9)}")
    print(f"  最多迭代: {session.max_iters} 轮\n")

    result = run_session(db, session.session_id)

    print("=" * 60)
    print("  调优完成!")
    print("=" * 60)
    print(f"  状态:       {result['status']}")
    print(f"  最优版本:   {result['best_entry_ref']}")
    print(f"  最优分数:   {result['score']:.2%}")
    print(f"  总迭代轮数: {result['total_iters']}")
    print(f"  停止原因:   {result['stop_reason']}")
    print(f"  是否达标:   {'✓ 是' if result['criteria_met'] else '✗ 否'}")

    if result.get("artifact"):
        print(f"\n  最优输出样例 ({result['artifact'].get('case_id')}):")
        for k, v in (result["artifact"].get("output") or {}).items():
            print(f"    {k}: {v}")

    # 打印每轮迭代
    status = get_session_status(db, session.session_id, include_iters=True)
    if status.get("iters"):
        print("\n  迭代轨迹:")
        for it in status["iters"]:
            promoted = "→ 晋升" if it.get("promoted") else ""
            print(f"    第{it['iter_no']}轮: {it['entry_ref']}  score={it['score']:.2%}  pass={it['pass_rate']:.2%} {promoted}")

    if result.get("recommendations"):
        print("\n  建议:")
        for r in result["recommendations"]:
            print(f"    - {r}")

    db.close()
    print()


if __name__ == "__main__":
    main()
