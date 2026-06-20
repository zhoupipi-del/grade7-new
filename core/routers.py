"""
core/routers.py — Wings 3.0 核心路由

提供认证、租户管理、组织架构查询等系统级 API。
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from .services import AuthService, OrgService
from .schemas import (
    LoginRequest, LoginResponse, UserOut,
    SchoolOut, SchoolCreate,
    StudentOut, MessageResponse,
)
from .models import User, UserRole

router = APIRouter(prefix="/api/v1", tags=["core"])
security = HTTPBearer()


# ═══════════════════════════════════════════════════════════════
# 依赖注入
# ═══════════════════════════════════════════════════════════════

async def get_db() -> AsyncSession:
    """获取数据库会话 — 由 app.py 的依赖覆盖实现"""
    raise NotImplementedError("DB session must be injected by app.py")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT 中解析当前登录用户"""
    try:
        payload = AuthService.decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="无效的认证令牌")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的认证令牌")

    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.id == int(user_id), User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return user


def require_role(*roles: UserRole):
    """角色守卫工厂 — 确保当前用户拥有指定角色之一"""

    async def _guard(current_user: User = Depends(get_current_user)):
        user_role = current_user.role
        if isinstance(user_role, str):
            user_role = UserRole(user_role)
        if user_role not in roles:
            raise HTTPException(status_code=403, detail="无权访问此资源")
        return current_user

    return _guard


# ═══════════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════════

@router.get("/health", response_model=MessageResponse)
async def health_check():
    return MessageResponse(message="ok", detail="Wings 3.0 Core Online")


# ═══════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════

@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user, error = await AuthService.authenticate(db, body.username, body.password)
    if error:
        raise HTTPException(status_code=401, detail=error)

    token = AuthService.create_token(user)
    user_out = await AuthService.get_user_out(db, user)

    return LoginResponse(access_token=token, user=user_out)


@router.get("/auth/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await AuthService.get_user_out(db, current_user)


# ═══════════════════════════════════════════════════════════════
# 学校（租户）管理 — 仅德育处管理员
# ═══════════════════════════════════════════════════════════════

@router.post("/schools", response_model=SchoolOut, status_code=201)
async def create_school(
    body: SchoolCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    school = await OrgService.create_school(db, body.name)
    return SchoolOut.model_validate(school)


@router.get("/schools/{school_id}", response_model=SchoolOut)
async def get_school(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    school = await OrgService.get_school(db, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="学校不存在")
    return SchoolOut.model_validate(school)


# ═══════════════════════════════════════════════════════════════
# 模块管理
# ═══════════════════════════════════════════════════════════════

@router.get("/schools/{school_id}/modules")
async def get_school_modules(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取某学校的所有模块状态"""
    from sqlalchemy import select
    from .models import SchoolModule
    result = await db.execute(
        select(SchoolModule).where(SchoolModule.school_id == school_id)
    )
    modules = result.scalars().all()
    return [
        {
            "module_code": m.module_code,
            "enabled": m.enabled,
            "config": m.config,
            "enabled_at": m.enabled_at.isoformat() if m.enabled_at else None,
            "disabled_at": m.disabled_at.isoformat() if m.disabled_at else None,
        }
        for m in modules
    ]
