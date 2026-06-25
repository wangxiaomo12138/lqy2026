"""全局配置"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite 数据库文件（零配置，开箱即用）
DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'tune.db'}"

# True = 用模拟客户端（不需要你们平台也能跑演示）
# False = 调真实 Agent 平台
USE_MOCK_AGENT = True
AGENT_PLATFORM_URL = "http://127.0.0.1:9000"

# 调优默认约束
DEFAULT_MAX_ITERS = 8
DEFAULT_MIN_DELTA = 0.02
DEFAULT_STAGNATION_WINDOW = 3
