"""
modules/dashboard/routers.py — 大数据看板 API 端点

三端点 RBAC 权限视窗：
  MS_ADMIN      → 全校上帝视角
  GRADE_LEADER  → 本年级战术视角
  CLASS_TEACHER → 仅本班微观视角（严禁横向窥探）
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.routers import get_current_user, get_db
from core.models import User, UserRole
from .services import (
    get_class_radar,
    get_trends,
    get_correlation_scatter,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# RBAC scope 构建 — 根据角色限定数据可见范围
# ═══════════════════════════════════════════════════════════════

def _build_scope(user: User) -> dict:
    """
    返回 {grade_id, class_id} 限定范围。
    MS_ADMIN → 均不限定
    GRADE_LEADER → 限定 grade_id
    CLASS_TEACHER → 限定 class_id
    """
    role = user.role
    if isinstance(role, str):
        role = UserRole(role)

    if role == UserRole.MS_ADMIN:
        return {"grade_id": None, "class_id": None}
    elif role == UserRole.GRADE_LEADER:
        return {"grade_id": user.grade_id, "class_id": None}
    elif role == UserRole.CLASS_TEACHER:
        return {"grade_id": None, "class_id": user.class_id}
    else:
        # PARENT/STUDENT/TEACHER 默认无看板权限
        raise HTTPException(status_code=403, detail="无权访问大数据看板")


# ═══════════════════════════════════════════════════════════════
# 端点一：班级万字违纪率晴雨表
# ═══════════════════════════════════════════════════════════════

@router.get("/class-radar")
async def class_radar(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """班级横向红黑榜 — 万字违纪率 + 正面对冲比 + 滑窗红线"""
    scope = _build_scope(user)
    data = await get_class_radar(
        db,
        school_id=user.school_id,
        grade_id=scope["grade_id"],
        class_id=scope["class_id"],
    )
    return {"status": "success", "data": data}


# ═══════════════════════════════════════════════════════════════
# 端点二：违纪严重度堆叠收敛趋势
# ═══════════════════════════════════════════════════════════════

@router.get("/trends")
async def trends(
    time_frame: str = Query("30d", regex="^(7d|30d|90d)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """违纪频次收敛曲线 — 轻微/普通/严重堆叠面积图"""
    scope = _build_scope(user)
    data = await get_trends(
        db,
        school_id=user.school_id,
        time_frame=time_frame,
        grade_id=scope["grade_id"],
        class_id=scope["class_id"],
    )
    return {"status": "success", "data": data}


# ═══════════════════════════════════════════════════════════════
# 端点三：德育 X 成绩四象限散点图（王牌）
# ═══════════════════════════════════════════════════════════════

@router.get("/correlation-scatter")
async def correlation_scatter(
    semester: str = Query("2025-2026-2"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """德育积分与学业成绩关联散点图 — 跨库桥接"""
    scope = _build_scope(user)
    data = await get_correlation_scatter(
        db,
        school_id=user.school_id,
        grade_id=scope["grade_id"],
        class_id=scope["class_id"],
        semester=semester,
    )
    return {"status": "success", "data": data}
