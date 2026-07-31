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
from sqlalchemy import select, func

from core.routers import get_current_user, get_db, verify_entity_ownership
from core.models import User, UserRole, Student, Class as SchoolClass
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


# ═══ 班级下钻明细端点 ═══

@router.get("/class-drilldown/{class_id}")
async def get_class_drilldown(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班级下钻明细 — 按学生聚合德育分+违纪数+草稿数+处分数"""
    # P0 多租户隔离：校验 class_id 是否属于当前用户学校
    await verify_entity_ownership(db, SchoolClass, class_id, current_user, '班级不存在')

    from modules.behavior.models import DisciplineRecord
    from modules.evaluation.models import StudentScore
    from modules.discipline.models import DisciplineSanction, DisciplineStatus
    from sqlalchemy import func

    school_id = current_user.school_id

    # RBAC: 班主任只能看本班
    if current_user.role == UserRole.CLASS_TEACHER and current_user.class_id != class_id:
        raise HTTPException(status_code=403, detail="无权调阅其他班级明细")

    # 学生基础信息
    students_q = await db.execute(
        select(Student.id, Student.name).where(
            Student.class_id == class_id,
            Student.school_id == school_id,
            Student.is_active == True,
        ).order_by(Student.id)
    )
    students = {r[0]: {"student_id": r[0], "student_name": r[1]} for r in students_q.all()}
    if not students:
        return {"class_id": class_id, "roster": []}

    sids = list(students.keys())

    # 德育分
    semester = "2025-2026-2"
    score_q = await db.execute(
        select(StudentScore.student_id, StudentScore.total_score).where(
            StudentScore.student_id.in_(sids),
            StudentScore.semester == semester,
        )
    )
    for r in score_q.all():
        if r[0] in students:
            students[r[0]]["moral_score"] = round(float(r[1] or 0), 1)

    # 违纪统计（按type分组计数）
    behavior_q = await db.execute(
        select(
            DisciplineRecord.student_id,
            DisciplineRecord.type,
            func.count(DisciplineRecord.id),
        ).where(
            DisciplineRecord.student_id.in_(sids),
            DisciplineRecord.status == "active",
        ).group_by(DisciplineRecord.student_id, DisciplineRecord.type)
    )
    for r in behavior_q.all():
        sid, vtype, cnt = r[0], r[1], int(r[2])
        if sid in students:
            students[sid].setdefault("behavior_counts", {})
            students[sid]["behavior_counts"][vtype] = cnt

    # 草稿数 + ACTIVE处分数
    sanction_q = await db.execute(
        select(
            DisciplineSanction.student_id,
            DisciplineSanction.status,
            func.count(DisciplineSanction.id),
        ).where(
            DisciplineSanction.student_id.in_(sids),
        ).group_by(DisciplineSanction.student_id, DisciplineSanction.status)
    )
    for r in sanction_q.all():
        sid, status, cnt = r[0], r[1], int(r[2])
        if sid in students:
            if status == DisciplineStatus.DRAFT_PENDING:
                students[sid]["draft_pending"] = cnt
            elif status == DisciplineStatus.ACTIVE:
                students[sid]["active_sanctions"] = cnt

    # 组装roster + 风险排序
    roster = []
    for sid, info in students.items():
        bc = info.get("behavior_counts", {})
        roster.append({
            "student_id": sid,
            "student_name": info["student_name"],
            "moral_score": info.get("moral_score", None),
            "serious_count": bc.get("serious", 0),
            "major_count": bc.get("major", 0),
            "minor_count": bc.get("minor", 0),
            "warning_count": bc.get("warning", 0),
            "total_violations": sum(bc.values()),
            "draft_pending": info.get("draft_pending", 0),
            "active_sanctions": info.get("active_sanctions", 0),
        })

    # 风险排序：严重违纪多 + 德育分低 → 前
    roster.sort(key=lambda x: (
        -(x["serious_count"] * 10 + x["major_count"] * 5 + x["total_violations"]),
        x["moral_score"] or 999,
    ))

    return {"class_id": class_id, "roster": roster}
