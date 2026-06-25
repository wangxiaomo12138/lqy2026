"""数据库连接与建表"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# 确保 data 目录存在
DATABASE_URL.replace("sqlite:///", "").rsplit("/", 1)[0]  # noqa: just path hint
from pathlib import Path  # noqa: E402

db_path = DATABASE_URL.replace("sqlite:///", "")
Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖注入：每个请求一个数据库 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表"""
    from app.models import tune_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
