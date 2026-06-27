"""
modules/growth/services.py — 成长时间轴数据融合服务

只读聚合服务：
  discipline_records   → 日常行为事件
  discipline_sanctions → 行政处分事件（生效 + 撤销）
  attendance_records   → 考勤异常事件

所有文案经脱敏柔化处理，家长端展示用"成长记录"语言。
"""
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

# ── 核心模型导入 ───────────────────────────────────────────────────────────────────
from core.models import Student, Class, User, UserRole
from modules.behavior.models import DisciplineRecord
from modules.discipline.models import (
    DisciplineSanction, DisciplineLevel, DisciplineStatus,
    LEVEL_LABELS as SANCTION_LEVEL_LABELS,
)
from modules.attendance.models import AttendanceRecord
from .schemas import TimelineItem, GrowthTimelineResponse


# ═══════════════════════════════════════════════════════════════
#  违纪类型 → 家长端柔化文案映射
# ═══════════════════════════════════════════════════════════════

BEHAVIOR_TYPE_LABELS = {
    "warning": "行为提醒",
    "minor":   "行为记录",
    "major":   "严重行为提醒",
    "serious": "严重违纪提醒",
}

CATEGORY_LABELS = {
    "打架": "同学冲突提醒",
    "吸烟": "健康行为提醒",
    "迟到": "到校时间提醒",
    "仪容": "仪容仪表提醒",
    "课堂": "课堂行为提醒",
    "作业": "作业完成提醒",
    "其他": "行为提醒",
}

ATTENDANCE_LABELS = {
    "late":   "到校时间提醒（迟到）",
    "absent": "出勤提醒（缺勤）",
    "early":  "早退提醒",
    "leave":  "请假记录",
}


# ═══════════════════════════════════════════════════════════════
#  核心融合服务
# ═══════════════════════════════════════════════════════════════

async def get_growth_timeline(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> GrowthTimelineResponse:
    """
    构建学生成长时间轴 — 全量数据融合聚合。

    参数:
        db:           异步数据库会话
        school_id:    学校 ID（多租户隔离）
        student_id:   目标学生 ID
        semester:     学期过滤（可选，格式: 2025-2026-1）

    返回:
        GrowthTimelineResponse — 含学生信息和按时间倒序的时间轴列表
    """
    # ── 1. 获取学生基本信息 ───────────────────────────────────────
    stu_result = await db.execute(
        select(Student)
        .options(selectinload(Student.class_))
        .where(
            Student.id == student_id,
            Student.school_id == school_id,
        )
    )
    student = stu_result.scalar_one_or_none()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="学生不存在")

    class_name = student.class_.name if student.class_ else f"班级#{student.class_id}"

    # ── 2. 并发查询三类数据源 ─────────────────────────────────────
    import asyncio

    behavior_task = _query_behavior_records(db, school_id, student_id, semester)
    sanction_task = _query_sanctions(db, school_id, student_id, semester)
    attendance_task = _query_attendance(db, school_id, student_id, semester)

    behavior_items, sanction_items, attendance_items = await asyncio.gather(
        behavior_task, sanction_task, attendance_task
    )

    # ── 3. 合并 + 按时间倒序排序 ─────────────────────────────────
    all_items: List[TimelineItem] = []
    all_items.extend(behavior_items)
    all_items.extend(sanction_items)
    all_items.extend(attendance_items)

    all_items.sort(key=lambda x: x.occurred_at, reverse=True)

    return GrowthTimelineResponse(
        student_id=student.id,
        student_name=student.name,
        class_name=class_name,
        total_events=len(all_items),
        timeline=all_items,
    )


# ═══════════════════════════════════════════════════════════════
#  子查询：违纪行为记录
# ═══════════════════════════════════════════════════════════════

async def _query_behavior_records(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 discipline_records，转换为 TimelineItem。

    过滤条件:
      - school_id 隔离
      - student_id 精确匹配
      - status 为 active 或 resolved（appealed 记录不展示给家长）
      - semester 过滤（如有）
    """
    stmt = (
        select(DisciplineRecord)
        .where(
            DisciplineRecord.school_id == school_id,
            DisciplineRecord.student_id == student_id,
            DisciplineRecord.status.in_(["active", "resolved"]),
        )
        .order_by(DisciplineRecord.created_at.desc())
        .limit(100)
    )

    if semester:
        # semester 格式: 2025-2026-1 → 过滤 created_at 在对应学期
        stmt = _apply_semester_filter(stmt, semester, DisciplineRecord.created_at)

    result = await db.execute(stmt)
    records = result.scalars().all()

    items: List[TimelineItem] = []
    for r in records:
        # 柔化文案
        category = r.category or "其他"
        soft_category = CATEGORY_LABELS.get(category, category + "提醒")
        title = f"{soft_category}"
        if r.description:
            desc = r.description[:80] + ("..." if len(r.description) > 80 else "")
        else:
            desc = f"行为类型：{r.type}"

        # severity 映射
        severity_map = {
            "warning": "info",
            "minor":   "info",
            "major":   "warning",
            "serious": "danger",
        }
        severity = severity_map.get(r.type, "info")

        occurred = r.incident_date or r.created_at.date() if r.incident_date else r.created_at.date()
        items.append(TimelineItem(
            event_id=f"behavior_{r.id}",
            event_type="behavior",
            occurred_at=r.created_at,
            event_date=occurred,
            title=title,
            description=desc,
            severity=severity,
            related_id=r.id,
            source_table="discipline_records",
        ))

    return items


# ═══════════════════════════════════════════════════════════════
#  子查询：行政处分记录（生效 + 撤销）
# ═══════════════════════════════════════════════════════════════

async def _query_sanctions(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 discipline_sanctions，转换为 TimelineItem。

    包含:
      - ACTIVE 状态的处分（展示为中文柔化文案）
      - REVOKED 状态的处分（展示为"处分已撤销，继续加油"，severity=success）
    """
    stmt = (
        select(DisciplineSanction)
        .where(
            DisciplineSanction.school_id == school_id,
            DisciplineSanction.student_id == student_id,
            DisciplineSanction.status.in_([
                DisciplineStatus.ACTIVE,
                DisciplineStatus.REVOKED,
            ]),
        )
        .order_by(DisciplineSanction.created_at.desc())
        .limit(50)
    )

    if semester:
        stmt = _apply_semester_filter(stmt, semester, DisciplineSanction.created_at)

    result = await db.execute(stmt)
    sanctions = result.scalars().all()

    items: List[TimelineItem] = []
    for s in sanctions:
        level_label = SANCTION_LEVEL_LABELS.get(s.level, s.level.value)

        if s.status == DisciplineStatus.ACTIVE:
            title = f"德育处分：{level_label}"
            description = s.reason or "经德育处审批，正式生效"
            severity = "danger"
            event_type = "sanction"
        elif s.status == DisciplineStatus.REVOKED:
            title = f"处分已撤销：{level_label}（已解除）"
            description = s.revoke_reason or "表现良好，处分已正式撤销。继续加油！"
            severity = "success"
            event_type = "sanction_revoked"
        else:
            continue  # 不应该到这里

        items.append(TimelineItem(
            event_id=f"sanction_{s.id}",
            event_type=event_type,
            occurred_at=s.created_at,
            event_date=s.punish_date or s.created_at.date(),
            title=title,
            description=description,
            severity=severity,
            related_id=s.id,
            source_table="discipline_sanctions",
        ))

    return items


# ═══════════════════════════════════════════════════════════════
#  子查询：考勤异常记录
# ═══════════════════════════════════════════════════════════════

async def _query_attendance(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 attendance_records，仅返回异常记录（late/absent/early，不含 present）。

    家长端展示为柔化文案。
    """
    stmt = (
        select(AttendanceRecord)
        .where(
            AttendanceRecord.school_id == school_id,
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.status.in_(["late", "absent", "early"]),
        )
        .order_by(AttendanceRecord.record_date.desc())
        .limit(50)
    )

    if semester:
        # AttendanceRecord 用 record_date 而非 created_at
        from datetime import date as date_type
        if semester:
            parts = semester.split("-")
            if len(parts) >= 2:
                year_start = int(parts[0])
                term = parts[-1] if len(parts) == 3 else "1"
                if term == "1":
                    date_start = date_type(year_start, 9, 1)
                    date_end = date_type(year_start + 1, 2, 28)
                else:
                    date_start = date_type(year_start, 2, 1)
                    date_end = date_type(year_start, 8, 31)
                stmt = stmt.where(
                    AttendanceRecord.record_date >= date_start,
                    AttendanceRecord.record_date <= date_end,
                )

    result = await db.execute(stmt)
    records = result.scalars().all()

    items: List[TimelineItem] = []
    for r in records:
        label = ATTENDANCE_LABELS.get(r.status, r.status)
        title = label
        description = r.note or f"{r.record_date.strftime('%Y年%m月%d日')} 考勤记录"
        severity = "warning" if r.status == "late" else "danger"

        items.append(TimelineItem(
            event_id=f"attendance_{r.id}",
            event_type="attendance",
            occurred_at=datetime.combine(r.record_date, datetime.min.time().replace(hour=7)),
            event_date=r.record_date,
            title=title,
            description=description,
            severity=severity,
            related_id=r.id,
            source_table="attendance_records",
        ))

    return items


# ═══════════════════════════════════════════════════════════════
#  学期过滤辅助函数
# ═══════════════════════════════════════════════════════════════

def _apply_semester_filter(stmt, semester: str, date_column):
    """
    将 semester 字符串（如 '2025-2026-1'）转换为日期范围过滤。

    学期定义:
      - 上学期（1）: 当年 9月1日 ~ 次年 2月28日
      - 下学期（2）: 当年 3月1日 ~ 当年 8月31日
    """
    from datetime import date as date_type
    parts = semester.split("-")
    if len(parts) < 2:
        return stmt

    year_start = int(parts[0])
    term = parts[-1] if len(parts) == 3 else "1"

    if term == "1":
        date_start = date_type(year_start, 9, 1)
        date_end = date_type(year_start + 1, 2, 28)
    else:
        date_start = date_type(year_start, 3, 1)
        date_end = date_type(year_start, 8, 31)

    return stmt.where(
        date_column >= date_start,
        date_column <= date_end,
    )
