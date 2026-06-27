"""
modules/growth/routers.py — 成长时间轴 API 路由

注册路径: /api/v1/growth/*

═══════════════════════════════════════════════════════════════
  防越权铁壁（Anti-Leak Defense）
═══════════════════════════════════════════════════════════════

家长端极易遭受「ID 遍历攻击」——
  攻击者将 URL 中 student_id=154 篡改为 155，试图偷窥其他学生档案。

本模块 RBAC 守卫策略:
  1. Parent Token:
      强制比对 current_user.bound_student_id == path_student_id
      不匹配 → 403 Forbidden（硬核熔断）

  2. Class Teacher Token:
      查询 student.class_id == current_user.class_id
      非本班 → 403

  3. Grade Leader Token:
      查询 student.grade_id == current_user.grade_id
      非本年级 → 403

  4. MS Admin Token:
      全量通行（多租户隔离仍生效：school_id 必须匹配）

所有端点统一经过 `_verify_student_access()` 守卫工厂。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, UserRole, Student
from core.routers import get_db, get_current_user
from .services import get_growth_timeline as build_growth_timeline
from .schemas import GrowthTimelineResponse

router = APIRouter(tags=["growth"])


# ═══════════════════════════════════════════════════════════════
#   RBAC 守卫工厂：防 ID 遍历越权
# ═══════════════════════════════════════════════════════════════

async def _verify_student_access(
    student_id: int,
    current_user: User,
    db: AsyncSession,
) -> Student:
    """
    防越权 ID 遍历守卫 —— 返回已验证的学生 ORM 对象。

    逻辑:
      - Parent:    bound_student_id 必须精确匹配，否则 403
      - ClassTeacher: 学生必须在本班，否则 403
      - GradeLeader: 学生必须在本年级，否则 403
      - MS Admin:   全量通行（school_id 隔离仍生效）

    返回: Student ORM 对象（已加载 class_ 关系）
    异常: 404（学生不存在）/ 403（越权）/ 400（家长未绑定学生）
    """
    # ── 1. 查询学生基本信息（含 class_ 关系）────────────────────
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    result = await db.execute(
        select(Student)
        .options(selectinload(Student.class_))
        .where(
            Student.id == student_id,
            Student.school_id == current_user.school_id,
        )
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在或无访问权限")

    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)

    # ── 2. Parent 铁壁 ─────────────────────────────────────────
    if role == UserRole.PARENT:
        if not current_user.bound_student_id:
            raise HTTPException(
                status_code=400,
                detail="当前账号未绑定学生，请联系班主任绑定后查看成长记录"
            )
        if current_user.bound_student_id != student_id:
            # 记录越权尝试日志（可接 ELK/Sentry）
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[越权尝试] Parent user_id={current_user.id} "
                f"尝试访问非绑定学生 student_id={student_id} "
                f"(绑定: {current_user.bound_student_id})"
            )
            raise HTTPException(
                status_code=403,
                detail="无权查看该学生的成长记录"
            )

    # ── 3. Class Teacher 守卫 ─────────────────────────────────
    elif role == UserRole.CLASS_TEACHER:
        if not current_user.class_id:
            raise HTTPException(status_code=403, detail="班主任账号未配置班级")
        if student.class_id != current_user.class_id:
            raise HTTPException(status_code=403, detail="无权查看其他班级学生的成长记录")

    # ── 4. Grade Leader 守卫 ───────────────────────────────────
    elif role == UserRole.GRADE_LEADER:
        if not current_user.grade_id:
            raise HTTPException(status_code=403, detail="年级组长账号未配置年级")
        if student.grade_id != current_user.grade_id:
            raise HTTPException(status_code=403, detail="无权查看其他年级学生的成长记录")

    # ── 5. MS Admin / Teacher / Student: 全量通行 ─────────────
    # （多租户隔离已由 school_id 过滤保证）

    return student


# ═══════════════════════════════════════════════════════════════
#   核心端点：成长时间轴
# ═══════════════════════════════════════════════════════════════

@router.get(
    "/timeline/{student_id}",
    response_model=GrowthTimelineResponse,
    summary="查询学生成长时间轴",
    description=(
        "家长端核心 API：返回学生成长时间轴（违纪/处分/考勤聚合）。\n\n"
        "⚠️ 防越权：家长 Token 只能访问自己绑定的学生 ID；"
        "班主任/年级组长 Token 按角色范围自动过滤。"
    ),
)
async def read_growth_timeline(
    student_id: int,
    semester: Optional[str] = Query(None, description="学期过滤，格式: 2025-2026-1（上学期）/ 2025-2026-2（下学期）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    成长时间轴聚合端点

    数据来源:
      - discipline_records   （日常行为记录，已柔化文案）
      - discipline_sanctions （行政处分记录，含撤销）
      - attendance_records   （考勤异常记录）

    时间轴按 occurred_at DESC 排序。
    """
    # ── 防越权守卫（硬核熔断）──────────────────────────────────
    await _verify_student_access(student_id, current_user, db)

    # ── 调用融合服务 ─────────────────────────────────────────────
    timeline = await build_growth_timeline(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        semester=semester,
    )

    return timeline


# ═══════════════════════════════════════════════════════════════
#   便捷端点：当前家长绑定学生的成长时间轴（无需传 student_id）
# ═══════════════════════════════════════════════════════════════

@router.get(
    "/my-timeline",
    response_model=GrowthTimelineResponse,
    summary="查询当前家长绑定学生的成长时间轴（便捷端点）",
    description=(
        "家长登录后直接访问，无需指定 student_id。\n"
        "自动使用 Token 中绑定的 bound_student_id。"
    ),
)
async def get_my_timeline(
    semester: Optional[str] = Query(None, description="学期过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    便捷端点：家长查看自己孩子的成长时间轴。

    自动从 JWT Token 中提取 bound_student_id，无需手动传参。
    非家长角色访问此端点返回 403。
    """
    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)

    if role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="此端点仅限家长使用")

    if not current_user.bound_student_id:
        raise HTTPException(
            status_code=400,
            detail="当前账号未绑定学生，请联系班主任完成绑定"
        )

    timeline = await build_growth_timeline(
        db=db,
        school_id=current_user.school_id,
        student_id=current_user.bound_student_id,
        semester=semester,
    )

    return timeline
