"""JWT 注册 / 登录 / 刷新 API"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from sqlmodel import Session, select

from ..db import get_session
from ..models import User, UserCreate, UserRead
from ..security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
SessionDep = Annotated[Session, Depends(get_session)]


# ──────────────────────────────────────────────────────────────────────────────
# 依赖：获取当前用户（可选 — 未登录返回 None）
# ──────────────────────────────────────────────────────────────────────────────

def get_current_user_optional(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: SessionDep,
) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        username: str = payload.get("sub", "")
        user = session.exec(select(User).where(User.username == username)).first()
        return user if (user and user.is_active) else None
    except JWTError:
        return None


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或 Token 已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ──────────────────────────────────────────────────────────────────────────────
# 路由
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserRead, status_code=201)
def register(user_in: UserCreate, session: SessionDep):
    existing = session.exec(select(User).where(User.username == user_in.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info(f"新用户注册: {user.username}")
    return user


@router.post("/login")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep):
    user = session.exec(select(User).where(User.username == form.username)).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")
    return {
        "access_token": create_access_token(user.username),
        "refresh_token": create_refresh_token(user.username),
        "token_type": "bearer",
        "username": user.username,
    }


@router.post("/refresh")
def refresh_token(refresh_token: str, session: SessionDep):
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="无效的刷新 Token")
        username = payload.get("sub", "")
        user = session.exec(select(User).where(User.username == username)).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 解析失败")

    return {
        "access_token": create_access_token(username),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserRead)
def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
