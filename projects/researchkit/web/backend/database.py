"""SQLAlchemy 数据库（web/backend 专用）

支持通过环境变量 DATABASE_URL 切换数据库后端：
  - 默认：SQLite（开发 / 单机部署）
  - 生产：设置 DATABASE_URL=postgresql://user:pass@host/db 以使用 PostgreSQL
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_DB_DIR = Path.home() / ".researchkit"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "researchkit_web.db"

# 读取环境变量；默认回退到本地 SQLite
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{_DB_PATH}",
)

# SQLite 需要 check_same_thread=False；PostgreSQL 不需要
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
