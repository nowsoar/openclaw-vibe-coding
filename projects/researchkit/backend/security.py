"""JWT + 密码安全工具"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("RESEARCHKIT_SECRET", "researchkit-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24      # 24 小时
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode({"sub": subject, "exp": expire, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": subject, "exp": expire, "type": "refresh"}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT，失败时抛出 JWTError"""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
