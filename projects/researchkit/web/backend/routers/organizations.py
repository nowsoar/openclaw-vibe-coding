"""组织（团队）管理路由

权限控制：
  - 个人用户（plan=personal）：独立使用，数据不共享
  - 团队用户（plan=team）：通过 Organization 共享任务/数据源/报告

角色：owner > admin > member
"""
import re
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OrgRole, Organization, User, UserOrganization, UserPlan
from .auth import require_user

router = APIRouter(prefix="/api/orgs", tags=["organizations"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class OrgCreate(BaseModel):
    name: str
    slug: Optional[str] = None  # 不提供时自动生成


class OrgResponse(BaseModel):
    id: int
    name: str
    slug: str
    plan: str
    owner_id: int

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    user_id: int
    username: str
    email: str
    role: str


class InviteBody(BaseModel):
    email: str
    role: OrgRole = OrgRole.member


class RoleUpdateBody(BaseModel):
    role: OrgRole


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", name.lower().strip())[:40].strip("-") or "org"


def _get_org_or_404(org_id: int, db: Session) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    return org


def _require_role(user: User, org: Organization, db: Session, min_role: OrgRole = OrgRole.member):
    """检查用户在组织内的角色是否满足最低要求"""
    role_order = [OrgRole.member, OrgRole.admin, OrgRole.owner]
    membership = db.query(UserOrganization).filter(
        UserOrganization.user_id == user.id,
        UserOrganization.org_id == org.id,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="您不是该组织成员")
    if role_order.index(membership.role) < role_order.index(min_role):
        raise HTTPException(status_code=403, detail=f"需要 {min_role.value} 权限")
    return membership


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=OrgResponse, status_code=201)
def create_org(
    body: OrgCreate,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    """创建组织；创建者自动成为 owner，账户升级为团队版"""
    slug = body.slug or _slugify(body.name)
    # 确保 slug 唯一
    base_slug = slug
    suffix = 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    org = Organization(name=body.name, slug=slug, owner_id=current_user.id)
    db.add(org)
    db.flush()  # 获取 org.id

    membership = UserOrganization(user_id=current_user.id, org_id=org.id, role=OrgRole.owner)
    db.add(membership)

    # 升级账户类型
    current_user.plan = UserPlan.team
    db.commit()
    db.refresh(org)
    return org


@router.get("", response_model=List[OrgResponse])
def list_orgs(
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    """列出当前用户所在的所有组织"""
    memberships = db.query(UserOrganization).filter(
        UserOrganization.user_id == current_user.id
    ).all()
    org_ids = [m.org_id for m in memberships]
    return db.query(Organization).filter(Organization.id.in_(org_ids)).all()


@router.get("/{org_id}", response_model=OrgResponse)
def get_org(
    org_id: int,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    org = _get_org_or_404(org_id, db)
    _require_role(current_user, org, db)
    return org


@router.delete("/{org_id}", status_code=204)
def delete_org(
    org_id: int,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    """仅 owner 可解散组织"""
    org = _get_org_or_404(org_id, db)
    _require_role(current_user, org, db, min_role=OrgRole.owner)
    db.query(UserOrganization).filter(UserOrganization.org_id == org_id).delete()
    db.delete(org)
    db.commit()


@router.get("/{org_id}/members", response_model=List[MemberResponse])
def list_members(
    org_id: int,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    org = _get_org_or_404(org_id, db)
    _require_role(current_user, org, db)
    memberships = db.query(UserOrganization).filter(UserOrganization.org_id == org_id).all()
    result = []
    for m in memberships:
        u = db.query(User).filter(User.id == m.user_id).first()
        if u:
            result.append(MemberResponse(
                user_id=u.id, username=u.username, email=u.email, role=m.role.value
            ))
    return result


@router.post("/{org_id}/invite", status_code=201)
def invite_member(
    org_id: int,
    body: InviteBody,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    """admin/owner 可邀请成员"""
    org = _get_org_or_404(org_id, db)
    _require_role(current_user, org, db, min_role=OrgRole.admin)

    invitee = db.query(User).filter(User.email == body.email).first()
    if not invitee:
        raise HTTPException(status_code=404, detail="用户不存在（需先注册）")

    existing = db.query(UserOrganization).filter(
        UserOrganization.user_id == invitee.id,
        UserOrganization.org_id == org_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户已是组织成员")

    membership = UserOrganization(user_id=invitee.id, org_id=org_id, role=body.role)
    db.add(membership)
    invitee.plan = UserPlan.team
    db.commit()
    return {"message": f"已邀请 {invitee.username} 加入组织"}


@router.put("/{org_id}/members/{user_id}/role", status_code=200)
def update_member_role(
    org_id: int,
    user_id: int,
    body: RoleUpdateBody,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    """owner 可修改成员角色（不能修改自己）"""
    org = _get_org_or_404(org_id, db)
    _require_role(current_user, org, db, min_role=OrgRole.owner)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    membership = db.query(UserOrganization).filter(
        UserOrganization.user_id == user_id,
        UserOrganization.org_id == org_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="成员不存在")
    membership.role = body.role
    db.commit()
    return {"message": "角色已更新"}


@router.delete("/{org_id}/members/{user_id}", status_code=204)
def remove_member(
    org_id: int,
    user_id: int,
    current_user: Annotated[User, Depends(require_user)],
    db: Session = Depends(get_db),
):
    """admin/owner 可移除成员；成员也可自行退出"""
    org = _get_org_or_404(org_id, db)
    if user_id != current_user.id:
        _require_role(current_user, org, db, min_role=OrgRole.admin)
    membership = db.query(UserOrganization).filter(
        UserOrganization.user_id == user_id,
        UserOrganization.org_id == org_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.delete(membership)
    db.commit()
