"""认证路由（web/backend 专用）

包含：
- 用户注册 / 登录 / 刷新 Token / 登出
- 邮箱注册 + 密码重置（无状态 JWT 重置令牌）
- Google OAuth 2.0 登录
- 飞书（Lark）OAuth 2.0 登录
"""
import logging
import os
import re
import secrets
from typing import Annotated, Optional

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OrgRole, User, UserPlan
from ..auth import (
    create_access_token,
    create_refresh_token,
    create_reset_token,
    decode_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# ── OAuth 环境变量 ──────────────────────────────────────────────────────────
_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
)

_FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
_FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
_FEISHU_REDIRECT_URI = os.environ.get(
    "FEISHU_REDIRECT_URI", "http://localhost:8000/api/auth/feishu/callback"
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    email: str
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少8位")
        return v


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    plan: str

    model_config = {"from_attributes": True}


class RefreshBody(BaseModel):
    refresh_token: str


class ForgotPasswordBody(BaseModel):
    email: str


class ResetPasswordBody(BaseModel):
    reset_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少8位")
        return v


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


# ── 辅助：生成 Token 响应 ──────────────────────────────────────────────────────

def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token({"sub": user.email}),
        "refresh_token": create_refresh_token({"sub": user.email}),
        "token_type": "bearer",
    }


def _upsert_oauth_user(
    db: Session,
    *,
    provider: str,
    oauth_sub: str,
    email: str,
    username_hint: str,
) -> User:
    """查找或创建 OAuth 用户。email 为主键匹配字段。"""
    user = db.query(User).filter(User.email == email).first()
    if user:
        # 补全 OAuth 信息（如果之前是密码注册）
        if not user.oauth_sub:
            user.oauth_provider = provider
            user.oauth_sub = oauth_sub
            db.commit()
            db.refresh(user)
        return user

    # 确保用户名唯一
    base = re.sub(r"[^a-zA-Z0-9_]", "", username_hint)[:20] or "user"
    username = base
    suffix = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base}{suffix}"
        suffix += 1

    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(secrets.token_hex(32)),  # 随机密码，OAuth 用户无需密码登录
        oauth_provider=provider,
        oauth_sub=oauth_sub,
        plan=UserPlan.personal,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── 注册 / 登录 / 刷新 ─────────────────────────────────────────────────────────

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
        plan=UserPlan.personal,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """支持邮箱或用户名登录"""
    user = db.query(User).filter(
        (User.email == form.username) | (User.username == form.username)
    ).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名/邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")
    return _token_response(user)


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


# ── 密码重置 ──────────────────────────────────────────────────────────────────

@router.post("/forgot-password", status_code=200)
def forgot_password(body: ForgotPasswordBody, db: Session = Depends(get_db)):
    """
    生成密码重置令牌（生产环境应将链接发送到用户邮箱）。
    此处直接返回 reset_token，供前端或 CLI 调用 /reset-password 使用。
    """
    user = db.query(User).filter(User.email == body.email).first()
    # 不泄露用户是否存在
    if not user:
        return {"message": "如果该邮箱已注册，重置链接已发送"}
    reset_token = create_reset_token(user.email, expires_minutes=60)
    # 生产环境：通过 SMTP 发送 reset_token
    return {"message": "如果该邮箱已注册，重置链接已发送", "reset_token": reset_token}


@router.post("/reset-password", status_code=200)
def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    """使用重置令牌更新密码"""
    try:
        payload = decode_token(body.reset_token)
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="无效的重置令牌")
        email = payload.get("sub", "")
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=400, detail="用户不存在或已禁用")
    except JWTError:
        raise HTTPException(status_code=400, detail="重置令牌无效或已过期")

    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "密码重置成功"}


# ── Google OAuth 2.0 ──────────────────────────────────────────────────────────

@router.get("/google/login")
def google_login():
    """返回 Google 授权 URL（前端重定向用）"""
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth 未配置（需设置 GOOGLE_CLIENT_ID）")
    params = {
        "client_id": _GOOGLE_CLIENT_ID,
        "redirect_uri": _GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    return {"auth_url": auth_url}


@router.get("/google/callback")
def google_callback(code: str = Query(...), db: Session = Depends(get_db)):
    """
    Google OAuth 回调：用 code 换取 access_token，获取用户信息，
    创建或登录用户，返回 JWT。
    """
    if not _GOOGLE_CLIENT_ID or not _GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=501, detail="Google OAuth 未配置")

    # 1. 用 code 换 token
    token_resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": _GOOGLE_CLIENT_ID,
            "client_secret": _GOOGLE_CLIENT_SECRET,
            "redirect_uri": _GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Google Token 交换失败")
    google_token = token_resp.json().get("access_token")

    # 2. 获取用户信息
    user_resp = http_requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {google_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="获取 Google 用户信息失败")
    info = user_resp.json()

    user = _upsert_oauth_user(
        db,
        provider="google",
        oauth_sub=info["id"],
        email=info["email"],
        username_hint=info.get("name", info["email"].split("@")[0]),
    )
    return _token_response(user)


# ── 飞书 OAuth 2.0 ────────────────────────────────────────────────────────────

@router.get("/feishu/login")
def feishu_login():
    """返回飞书授权 URL（前端重定向用）"""
    if not _FEISHU_APP_ID:
        raise HTTPException(status_code=501, detail="飞书 OAuth 未配置（需设置 FEISHU_APP_ID）")
    auth_url = (
        f"https://open.feishu.cn/open-apis/authen/v1/index"
        f"?redirect_uri={_FEISHU_REDIRECT_URI}"
        f"&app_id={_FEISHU_APP_ID}"
        f"&state=researchkit"
    )
    return {"auth_url": auth_url}


@router.get("/feishu/callback")
def feishu_callback(code: str = Query(...), db: Session = Depends(get_db)):
    """
    飞书 OAuth 回调：用 code 换取 user_access_token，获取用户信息，
    创建或登录用户，返回 JWT。
    """
    if not _FEISHU_APP_ID or not _FEISHU_APP_SECRET:
        raise HTTPException(status_code=501, detail="飞书 OAuth 未配置")

    # 1. 获取 app_access_token
    app_token_resp = http_requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
        json={"app_id": _FEISHU_APP_ID, "app_secret": _FEISHU_APP_SECRET},
        timeout=10,
    )
    if app_token_resp.status_code != 200 or app_token_resp.json().get("code") != 0:
        raise HTTPException(status_code=400, detail="飞书 app_access_token 获取失败")
    app_token = app_token_resp.json()["app_access_token"]

    # 2. 用 code 换 user_access_token
    user_token_resp = http_requests.post(
        "https://open.feishu.cn/open-apis/authen/v1/access_token",
        json={"grant_type": "authorization_code", "code": code},
        headers={"Authorization": f"Bearer {app_token}"},
        timeout=10,
    )
    if user_token_resp.status_code != 200 or user_token_resp.json().get("code") != 0:
        raise HTTPException(status_code=400, detail="飞书 user_access_token 换取失败")
    user_data = user_token_resp.json().get("data", {})

    user = _upsert_oauth_user(
        db,
        provider="feishu",
        oauth_sub=user_data.get("open_id", ""),
        email=user_data.get("email") or user_data.get("enterprise_email", ""),
        username_hint=user_data.get("name", "feishu_user"),
    )
    return _token_response(user)
