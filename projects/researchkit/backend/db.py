"""数据库初始化与会话管理"""
from sqlmodel import SQLModel, Session, create_engine
from pathlib import Path

_DB_DIR = Path.home() / ".researchkit"
_DB_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{_DB_DIR}/researchkit.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db():
    """创建所有表（应用启动时调用）"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI 依赖：提供数据库 Session"""
    with Session(engine) as session:
        yield session
