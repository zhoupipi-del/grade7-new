"""
core/tenant_context.py — 三级组织架构 TenantContext 中间件 + AccessScope + 级联配置服务

核心能力:
  1. TenantContext — 请求级中间件，自动注入 access_scope（用户能访问的所有 school_ids）
  2. get_accessible_school_ids(user) — 根据 Role 和 Org/Branch 计算权限范围
  3. get_effective_config(module_key, school_id) — 级联配置查找链 School→Branch→Org→DEFAULT

向下兼容原则:
  - MS_ADMIN / CLASS_TEACHER / GRADE_LEADER / PARENT / STUDENT: access_scope = [user.school_id]
    （逻辑完全不变， WHERE school_id = :id → WHERE school_id IN :access_scope 仍然只查 1 个 ID）
  - GROUP_ADMIN: access_scope = 该集团所有 school_ids
  - BRANCH_ADMIN: access_scope = 该片区所有 school_ids
  - verify_entity_ownership 护城河不妥协 — 任何架构调整不破坏 18/18 PASS 安全基线
"""

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    CascadingConfig,
    School,
    ScopeType,
    User,
    UserRole,
)

# ═══════════════════════════════════════════════════════════════
# AccessScope — 用户可访问的 school_ids 列表
# ═══════════════════════════════════════════════════════════════


async def get_accessible_school_ids(user: User, db: AsyncSession) -> list[int]:
    """
    根据用户角色和组织归属，计算该用户能访问的所有 school_ids。

    向下兼容:
      - MS_ADMIN / 单校角色: 返回 [user.school_id]（1 个 ID，逻辑不变）
      - GROUP_ADMIN: 返回该集团所有 school_ids
      - BRANCH_ADMIN: 返回该片区所有 school_ids

    返回的 access_scope 用于 WHERE school_id IN :access_scope 替换 WHERE school_id = :id。
    当 access_scope 只有 1 个 ID 时，IN 列表等价于硬匹配，零破坏。
    """
    role = user.role if isinstance(user.role, UserRole) else UserRole(user.role)

    # ── 单校角色（向下兼容，逻辑完全不变）──
    single_school_roles = {
        UserRole.MS_ADMIN,
        UserRole.GRADE_LEADER,
        UserRole.CLASS_TEACHER,
        UserRole.TEACHER,
        UserRole.PARENT,
        UserRole.STUDENT,
    }

    if role in single_school_roles:
        return [user.school_id]

    # ── GROUP_ADMIN: 该集团所有学校 ──
    if role == UserRole.GROUP_ADMIN:
        org_id = user.org_id
        if org_id is None:
            # 兜底：没有 org_id 的 GROUP_ADMIN 退化为单校
            return [user.school_id]
        result = await db.execute(
            select(School.id).where(School.org_id == org_id, School.is_active == True)
        )
        return [row[0] for row in result.all()]

    # ── BRANCH_ADMIN: 该片区所有学校 ──
    if role == UserRole.BRANCH_ADMIN:
        branch_id = user.branch_id
        if branch_id is None:
            # 兜底：没有 branch_id 的 BRANCH_ADMIN 退化为单校
            return [user.school_id]
        result = await db.execute(
            select(School.id).where(School.branch_id == branch_id, School.is_active == True)
        )
        return [row[0] for row in result.all()]

    # ── 兜底 ──
    return [user.school_id]


# ═══════════════════════════════════════════════════════════════
# 级联配置查找链 — get_effective_config
# ═══════════════════════════════════════════════════════════════

# 模块默认配置兜底（当三级查找全部无命中时使用）
DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "attendance": {"enabled": True, "auto_notify": True, "threshold_days": 5},
    "evaluation": {"enabled": True, "base_score": 100, "fallback_strategy": "base_score"},
    "discipline": {"enabled": True, "auto_escalation": True, "window_days": 30},
    "risk_models": {"enabled": True, "scan_frequency": "daily", "sensitivity": "normal"},
    "red_flag": {"enabled": True, "scoring_method": "weighted_sum"},
    "notifications": {"enabled": True, "channels": ["in_app", "push"]},
    "reports": {"enabled": True, "formats": ["pdf", "excel"]},
    "ai_prescription": {"enabled": True, "model": "deepseek", "max_tokens": 2000},
    "dashboard": {"enabled": True, "refresh_interval": 300},
    "growth": {"enabled": True, "timeline_max_items": 50},
    "policy_engine": {"enabled": True, "hot_reload": True},
    "approval": {"enabled": True, "timeout_hours": 48, "auto_escalate": True},
    "teach_math": {"enabled": True, "independence_threshold": 0.5},
    "parent_portal": {"enabled": True, "features": ["timeline", "scores", "notifications"]},
    "behavior": {"enabled": True, "auto_score": True, "window_days": 30},
    "grades": {"enabled": True, "pass_threshold": 60.0},
    "lineage": {"enabled": True, "track_changes": True},
    "core": {"enabled": True},
}


async def get_effective_config_with_source(
    module_key: str,
    school_id: int,
    db: AsyncSession,
    branch_id: int | None = None,
    org_id: int | None = None,
) -> tuple:
    """
    级联配置查找链（带来源标识）— 优先级: School → Branch → Org → DEFAULT_CONFIG

    与 get_effective_config 相同的查找逻辑，但额外返回命中的层级。

    Returns:
        (config_dict, source_level) — source_level 为 "school" / "branch" / "org" / "default"
    """
    # ── 自动补齐 org_id/branch_id ──
    if branch_id is None or org_id is None:
        school = await db.execute(select(School).where(School.id == school_id))
        school_obj = school.scalar_one_or_none()
        if school_obj:
            if branch_id is None:
                branch_id = school_obj.branch_id
            if org_id is None:
                org_id = school_obj.org_id

    # ── L1: School 级查找 ──
    if school_id is not None:
        result = await db.execute(
            select(CascadingConfig.config_data).where(
                and_(
                    CascadingConfig.module_key == module_key,
                    CascadingConfig.scope_type == ScopeType.SCHOOL,
                    CascadingConfig.scope_id == school_id,
                    CascadingConfig.is_enabled == True,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row, "school"

    # ── L2: Branch 级查找 ──
    if branch_id is not None:
        result = await db.execute(
            select(CascadingConfig.config_data).where(
                and_(
                    CascadingConfig.module_key == module_key,
                    CascadingConfig.scope_type == ScopeType.BRANCH,
                    CascadingConfig.scope_id == branch_id,
                    CascadingConfig.is_enabled == True,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row, "branch"

    # ── L3: Org 级查找 ──
    if org_id is not None:
        result = await db.execute(
            select(CascadingConfig.config_data).where(
                and_(
                    CascadingConfig.module_key == module_key,
                    CascadingConfig.scope_type == ScopeType.ORG,
                    CascadingConfig.scope_id == org_id,
                    CascadingConfig.is_enabled == True,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row, "org"

    # ── L4: DEFAULT 兜底 ──
    return DEFAULT_CONFIGS.get(module_key, {"enabled": False}), "default"


async def get_effective_config(
    module_key: str,
    school_id: int,
    db: AsyncSession,
    branch_id: int | None = None,
    org_id: int | None = None,
) -> dict[str, Any]:
    """
    级联配置查找链 — 优先级: School → Branch → Org → DEFAULT_CONFIG

    查找逻辑:
      1. 查 school 级 → 有且 is_enabled=True 则返回
      2. 查 branch 级 → 有且 is_enabled=True 则返回
      3. 查 org 级   → 有且 is_enabled=True 则返回
      4. 返回 DEFAULT_CONFIGS[module_key] 兜底

    如果 branch_id/org_id 未传入，自动从 School 表反查。
    """
    config, _ = await get_effective_config_with_source(module_key, school_id, db, branch_id, org_id)
    return config


# ═══════════════════════════════════════════════════════════════
# TenantContext — 请求级上下文注入
# ═══════════════════════════════════════════════════════════════


class TenantContext:
    """
    请求级 TenantContext — 在每个 API 请求处理时注入。

    使用方式 (FastAPI Depends):
        @router.get("/...")
        async def endpoint(ctx: TenantContext = Depends(get_tenant_context)):
            access_scope = ctx.access_scope
            config = await ctx.get_config("attendance")

    核心字段:
      - user: 当前登录用户 ORM 对象
      - access_scope: 该用户能访问的所有 school_ids 列表
      - db: AsyncSession 数据库会话

    向下兼容:
      - MS_ADMIN/单校角色的 access_scope = [user.school_id]
      - WHERE school_id IN access_scope 等价于 WHERE school_id = :id
    """

    def __init__(self, user: User, access_scope: list[int], db: AsyncSession):
        self.user = user
        self.access_scope = access_scope
        self.db = db

    async def get_config(self, module_key: str) -> dict[str, Any]:
        """快捷方法: 获取当前用户所在学校的级联配置"""
        return await get_effective_config(
            module_key=module_key,
            school_id=self.user.school_id,
            db=self.db,
        )

    def is_single_school(self) -> bool:
        """判断是否为单校角色（access_scope 只有 1 个 ID）"""
        return len(self.access_scope) == 1

    def is_cross_school(self) -> bool:
        """判断是否为跨校角色（access_scope > 1 个 ID）"""
        return len(self.access_scope) > 1


async def build_tenant_context(user: User, db: AsyncSession) -> TenantContext:
    """
    构建 TenantContext — FastAPI Depends 的工厂函数。

    使用:
        from fastapi import Depends
        from core.tenant_context import build_tenant_context

        @router.get("/...")
        async def endpoint(ctx: TenantContext = Depends(lambda: build_tenant_context(current_user, db))):
            ...
    """
    access_scope = await get_accessible_school_ids(user, db)
    return TenantContext(user=user, access_scope=access_scope, db=db)


# ═══════════════════════════════════════════════════════════════
# 辅助函数 — 面向 Service 层的 scope 查询生成器
# ═══════════════════════════════════════════════════════════════


def build_scope_filter(model_class, access_scope: list[int]):
    """
    根据 access_scope 生成 SQLAlchemy WHERE 条件。

    向下兼容:
      - access_scope = [1] → model_class.school_id == 1（硬匹配，不变）
      - access_scope = [1,2,3] → model_class.school_id.in_([1,2,3])（跨校聚合）

    使用:
        from core.tenant_context import build_scope_filter
        query = select(Student).where(build_scope_filter(Student, ctx.access_scope))
    """
    if len(access_scope) == 1:
        return model_class.school_id == access_scope[0]
    else:
        return model_class.school_id.in_(access_scope)
