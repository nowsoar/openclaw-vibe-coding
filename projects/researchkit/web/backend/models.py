"""SQLAlchemy 模型（web/backend 专用）"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class UserPlan(str, enum.Enum):
    """账户类型：个人版 / 团队版"""
    personal = "personal"
    team = "team"


class OrgRole(str, enum.Enum):
    """组织内角色"""
    owner = "owner"    # 创建者
    admin = "admin"    # 管理员
    member = "member"  # 普通成员


# ── 用户表 ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    plan = Column(Enum(UserPlan), default=UserPlan.personal, nullable=False)

    # OAuth 来源（"local" / "google" / "feishu"）
    oauth_provider = Column(String, default="local")
    oauth_sub = Column(String, nullable=True)  # provider 给出的用户 ID

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    org_memberships = relationship("UserOrganization", back_populates="user")


# ── 组织表 ────────────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)  # URL-friendly ID
    plan = Column(Enum(UserPlan), default=UserPlan.team, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    memberships = relationship("UserOrganization", back_populates="organization")


# ── 用户-组织关系表 ────────────────────────────────────────────────────────────

class UserOrganization(Base):
    __tablename__ = "user_organizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    role = Column(Enum(OrgRole), default=OrgRole.member, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="org_memberships")
    organization = relationship("Organization", back_populates="memberships")
