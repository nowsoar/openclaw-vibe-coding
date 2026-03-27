"""认证路由（web/backend 专用）"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    email: str
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("密码至少8位")
        return v


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool

    class Config:
        from_attributes = True


class RefreshBody(BaseModel):
    refresh_token: str


# ── 获取当前用户依赖 ──────────────────────────────────────────────────────────

def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> Optional[User]:
    """可选认证：未登录返回 None"""
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        sub: str = payload.get("sub", "")
        user = db.query(User).filter(
            (User.email == sub) | (User.username == sub)
        ).first()
        return user if (user and user.is_active) else None
    except JWTError:
        return None


def require_user(user: Annotated[Optional[User], Depends(get_current_user)]) -> User:
    """强制登录依赖"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或 Token 已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="邮箱已被注册")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    """支持邮箱或用户名登录"""
    user = db.query(User).filter(
        (User.email == form.username) | (User.username == form.username)
    ).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名/邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")
    subject = user.email
    return {
        "access_token": create_access_token({"sub": subject}),
        "refresh_token": create_refresh_token({"sub": subject}),
        "token_type": "bearer",
    }


@router.post("/refresh")
def refresh(body: RefreshBody, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="无效的刷新 Token")
        sub = payload.get("sub", "")
        user = db.query(User).filter(User.email == sub).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 解析失败")
    return {
        "access_token": create_access_token({"sub": sub}),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Annotated[User, Depends(require_user)]):
    return current_user
