"""
modules/growth/services.py — 成长时间轴数据融合服务

只读聚合服务 — 7 路数据源并发融合：

  Phase 1 (已稳定):
    discipline_records   → 日常行为事件
    discipline_sanctions → 行政处分事件（生效 + 撤销）
    attendance_records   → 考勤异常事件

  Phase 2 (二期打通):
    score_logs           → 评分流水变动（扣分/加分溯源，含 policy_tag）
    recovery_state       → 回血进展（正向里程碑，幂律衰减可视化）
    risk_warnings        → RDI 风险预警里程碑（系统智能，≥1.0 展示）
    evaluation_scores    → 素质评价得分变动（含指标名称）

所有文案经脱敏柔化处理，家长端展示用"成长记录"语言。
Phase 2 采用 return_exceptions=True 抗压设计：单个数据源查询失败不阻塞整体时间轴。
"""
from datetime import datetime, date, timedelta
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
from modules.evaluation.models import ScoreLog, RecoveryState, EvaluationScore, EvaluationIndicator
from modules.risk_models.models import RiskWarning
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
    构建学生成长时间轴 — 7 路数据源并发融合聚合 (Phase 2)。

    参数:
        db:           异步数据库会话
        school_id:    学校 ID（多租户隔离）
        student_id:   目标学生 ID
        semester:     学期过滤（可选，格式: 2025-2026-1）

    返回:
        GrowthTimelineResponse — 含学生信息和按时间倒序的时间轴列表

    抗压设计:
        Phase 1 数据源 (behavior/sanction/attendance) — 硬失败，异常上抛
        Phase 2 数据源 (score_log/recovery/risk/evaluation) — 软失败，跳过不阻塞
    """
    import asyncio
    import logging

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

    # ── 2. 七路并发查询 ───────────────────────────────────────────
    #       Phase 1 (硬失败) + Phase 2 (软失败)
    phase1_tasks = [
        _query_behavior_records(db, school_id, student_id, semester),
        _query_sanctions(db, school_id, student_id, semester),
        _query_attendance(db, school_id, student_id, semester),
    ]
    phase2_tasks = [
        _query_score_logs(db, school_id, student_id, semester),
        _query_recovery_states(db, school_id, student_id, semester),
        _query_risk_warnings(db, school_id, student_id, semester),
        _query_evaluation_scores(db, school_id, student_id, semester),
    ]

    # Phase 1: 核心数据源 — 异常上抛（硬失败）
    p1_labels = ["behavior", "sanction", "attendance"]
    phase1_results = await asyncio.gather(*phase1_tasks, return_exceptions=True)
    p1_items = []
    for label, result in zip(p1_labels, phase1_results):
        if isinstance(result, Exception):
            logging.exception(f"[growth] Phase 1 子查询 {label} 异常: student_id={student_id}")
            raise result
        p1_items.append(result)

    # Phase 2: 新增数据源 — 异常跳过不阻塞（软失败）
    p2_labels = ["score_log", "recovery", "risk_warning", "evaluation"]
    phase2_results = await asyncio.gather(*phase2_tasks, return_exceptions=True)
    p2_items = []
    for label, result in zip(p2_labels, phase2_results):
        if isinstance(result, Exception):
            logging.warning(f"[growth] Phase 2 子查询 {label} 异常(已跳过): student_id={student_id}, error={type(result).__name__}")
            p2_items.append([])  # 空列表替代，不阻塞
        else:
            p2_items.append(result)

    # ── 3. 合并 + 按时间倒序排序 ─────────────────────────────────
    behavior_items, sanction_items, attendance_items = p1_items
    score_log_items, recovery_items, risk_items, eval_items = p2_items

    all_items: List[TimelineItem] = []
    all_items.extend(behavior_items)
    all_items.extend(sanction_items)
    all_items.extend(attendance_items)
    all_items.extend(score_log_items)
    all_items.extend(recovery_items)
    all_items.extend(risk_items)
    all_items.extend(eval_items)

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

        occurred = r.incident_date or r.created_at.date() if r.incident_date else (r.created_at or datetime.utcnow()).date()
        items.append(TimelineItem(
            event_id=f"behavior_{r.id}",
            event_type="behavior",
            occurred_at=r.created_at or datetime.utcnow(),  # fallback if created_at is NULL
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

        occurred = s.created_at or datetime.utcnow()  # fallback if created_at is NULL
        items.append(TimelineItem(
            event_id=f"sanction_{s.id}",
            event_type=event_type,
            occurred_at=occurred,
            event_date=s.punish_date or occurred.date(),
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
#  Phase 2 子查询：评分流水变动
# ═══════════════════════════════════════════════════════════════

async def _query_score_logs(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 score_logs，转换为 TimelineItem。

    设计约束:
      - LIMIT 50，防止海量流水阻塞
      - 30 天窗口（created_at >= 30 天前）
      - 投影查询：只选择前端展示所需字段

    policy_tag 展示:
      - repairable → "可补救"
      - non_repairable → "不可恢复"
      - recovered → "已回血"
      - permanent → "永久"
    """
    cutoff = datetime.utcnow() - timedelta(days=30)

    # 投影查询 — 只 SELECT 前端展示所需字段
    stmt = (
        select(
            ScoreLog.id,
            ScoreLog.dimension,
            ScoreLog.change_amount,
            ScoreLog.reason,
            ScoreLog.source_type,
            ScoreLog.policy_tag,
            ScoreLog.created_at,
        )
        .where(
            ScoreLog.school_id == school_id,
            ScoreLog.student_id == student_id,
            ScoreLog.created_at >= cutoff,
        )
        .order_by(ScoreLog.created_at.desc())
        .limit(50)
    )

    if semester:
        stmt = _apply_semester_filter(stmt, semester, ScoreLog.created_at)

    result = await db.execute(stmt)
    rows = result.all()

    POLICY_TAG_LABELS = {
        "repairable": "可补救",
        "non_repairable": "不可恢复",
        "recovered": "已回血",
        "permanent": "永久",
    }

    items: List[TimelineItem] = []
    for row in rows:
        change = row.change_amount
        # 扣分显示负数，加分显示正数
        direction = "扣分" if change < 0 else "加分"
        abs_change = abs(change)
        reason_detail = row.reason or f"{direction}变动"
        tag_label = POLICY_TAG_LABELS.get(row.policy_tag, row.policy_tag or "")

        title = f"{direction}：{reason_detail}"
        description = f"分数变动 {change:+.1f} · 联动维度：{row.dimension or '综合'} · {tag_label}"
        severity = "danger" if change < 0 else "info"

        occurred = row.created_at or datetime.utcnow()
        items.append(TimelineItem(
            event_id=f"score_log_{row.id}",
            event_type="score_log",
            occurred_at=occurred,
            event_date=occurred.date() if isinstance(occurred, datetime) else occurred,
            title=title,
            description=description,
            severity=severity,
            related_id=row.id,
            source_table="score_logs",
        ))

    return items


# ═══════════════════════════════════════════════════════════════
#  Phase 2 子查询：回血进展（正向里程碑）
# ═══════════════════════════════════════════════════════════════

async def _query_recovery_states(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 recovery_state，展示回血进展为正向里程碑。

    过滤条件:
      - is_active = True 或已完全回血 (policy_tag = "recovered")
      - recovery_ratio > 0（有实质回血进展才展示）

    内容:
      - 原始扣分 → 已回血 → 剩余扣分 → 回血比例
      - severity = "success"（正向标记）
    """
    stmt = (
        select(RecoveryState)
        .where(
            RecoveryState.school_id == school_id,
            RecoveryState.student_id == student_id,
            RecoveryState.recovery_ratio > 0,
        )
        .order_by(RecoveryState.last_computed_at.desc().nulls_last())
        .limit(20)
    )

    if semester:
        stmt = _apply_semester_filter(stmt, semester, RecoveryState.created_at)

    result = await db.execute(stmt)
    records = result.scalars().all()

    SOURCE_LABELS = {
        "behavior": "行为记录",
        "discipline": "行政处分",
    }

    items: List[TimelineItem] = []
    for r in records:
        source_label = SOURCE_LABELS.get(r.source_type, r.source_type)
        pct = r.recovery_ratio * 100 if r.recovery_ratio else 0

        if r.policy_tag == "recovered":
            title = f"回血完成：{source_label}影响已消除"
            description = f"原始扣分 {r.original_penalty:.0f} 分 → 已回血 {r.recovered_amount:.0f} 分（{pct:.0f}%）· 继续加油！"
        else:
            title = f"回血进展：{source_label}恢复中"
            description = f"原始扣分 {r.original_penalty:.0f} 分 → 已回血 {r.recovered_amount:.0f} 分（{pct:.0f}%）· 剩余 {r.remaining_penalty:.0f} 分 · 观察期至 {r.observation_end}"

        occurred = r.last_computed_at or r.updated_at or r.created_at or datetime.utcnow()
        items.append(TimelineItem(
            event_id=f"recovery_{r.id}",
            event_type="recovery",
            occurred_at=occurred,
            event_date=occurred.date() if isinstance(occurred, datetime) else occurred,
            title=title,
            description=description,
            severity="success",
            related_id=r.id,
            source_table="recovery_state",
        ))

    return items


# ═══════════════════════════════════════════════════════════════
#  Phase 2 子查询：RDI 风险预警里程碑（系统智能）
# ═══════════════════════════════════════════════════════════════

async def _query_risk_warnings(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 risk_warnings，展示 RDI 风险预警为里程碑事件。

    过滤条件:
      - risk_level 为 attention 或 intervention（normal 不展示）
      - status 为 active 或 handled
      - LIMIT 20

    里程碑意义:
      - RDI ≥ 1.0 → attention（关注线）
      - RDI ≥ 2.0 → intervention（干预线）
      - is_escalating → 趋势提示
    """
    stmt = (
        select(RiskWarning)
        .where(
            RiskWarning.school_id == school_id,
            RiskWarning.student_id == student_id,
            RiskWarning.risk_level.in_(["attention", "intervention"]),
            RiskWarning.status.in_(["active", "handled"]),
        )
        .order_by(RiskWarning.warned_at.desc())
        .limit(20)
    )

    if semester:
        stmt = _apply_semester_filter(stmt, semester, RiskWarning.warned_at)

    result = await db.execute(stmt)
    records = result.scalars().all()

    RISK_LABELS = {
        "attention": "需要关注",
        "intervention": "需要干预",
    }

    items: List[TimelineItem] = []
    for r in records:
        risk_label = RISK_LABELS.get(r.risk_level, r.risk_level)
        trend_note = "· 趋势持续上升" if r.is_escalating else ""
        trigger_info = f"· 触发事件：{r.trigger_event_type}" if r.trigger_event_type else ""

        title = f"风险预警：RDI {r.rdi_score:.1f}（{risk_label}）"
        description = f"行为偏离度 {r.behavior_deviation:.1f} · 考勤偏离度 {r.attendance_deviation:.1f} · 评价偏离度 {r.score_deviation:.1f}{trend_note}{trigger_info}"

        severity = "danger" if r.risk_level == "intervention" else "warning"

        occurred = r.warned_at or r.created_at or datetime.utcnow()
        items.append(TimelineItem(
            event_id=f"risk_{r.id}",
            event_type="risk_milestone",
            occurred_at=occurred,
            event_date=occurred.date() if isinstance(occurred, datetime) else occurred,
            title=title,
            description=description,
            severity=severity,
            related_id=r.id,
            source_table="risk_warnings",
        ))

    return items


# ═══════════════════════════════════════════════════════════════
#  Phase 2 子查询：素质评价得分变动
# ═══════════════════════════════════════════════════════════════

async def _query_evaluation_scores(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    semester: Optional[str] = None,
) -> List[TimelineItem]:
    """
    查询 evaluation_scores + evaluation_indicators，展示素质评价得分变动。

    过滤条件:
      - LIMIT 30
      - JOIN evaluation_indicators 获取指标名称

    展示内容:
      - 指标名称 → 得分 → 评分人类型
    """
    stmt = (
        select(EvaluationScore, EvaluationIndicator.name)
        .join(EvaluationIndicator, EvaluationScore.indicator_id == EvaluationIndicator.id)
        .where(
            EvaluationScore.school_id == school_id,
            EvaluationScore.student_id == student_id,
        )
        .order_by(EvaluationScore.created_at.desc())
        .limit(30)
    )

    if semester:
        stmt = _apply_semester_filter(stmt, semester, EvaluationScore.created_at)

    result = await db.execute(stmt)
    rows = result.all()

    items: List[TimelineItem] = []
    for row in rows:
        score_record = row[0]  # EvaluationScore
        indicator_name = row[1]  # EvaluationIndicator.name

        title = f"素质评价：{indicator_name}"
        description = f"得分 {score_record.score:.1f} · 评分来源：{score_record.scorer_type or '未知'}"
        severity = "info"

        occurred = score_record.created_at or datetime.utcnow()
        items.append(TimelineItem(
            event_id=f"evaluation_{score_record.id}",
            event_type="evaluation",
            occurred_at=occurred,
            event_date=occurred.date() if isinstance(occurred, datetime) else occurred,
            title=title,
            description=description,
            severity=severity,
            related_id=score_record.id,
            source_table="evaluation_scores",
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


# ═══════════════════════════════════════════════════════════════
#  P0 新增：成长事件管理 + 快照引擎 + 全息画像
# ═══════════════════════════════════════════════════════════════

from .models import GrowthTimelineEvent, GrowthPeriodicalSnapshot
from .schemas import (
    TimelineEventCreate, TimelineEventResponse,
    GrowthSnapshotResponse, RadarDimensions, SnapshotMetricsSummary,
    StudentHolisticProfile, GrowthDashboard,
    GrowthTimelineResponse as LegacyTimelineResponse,
)
from sqlalchemy import func, and_, desc
from core.models import get_local_now


async def add_timeline_event(
    db: AsyncSession, school_id: int, data: TimelineEventCreate, reporter_id: int = None,
) -> GrowthTimelineEvent:
    """手动/系统注入成长事件"""
    event = GrowthTimelineEvent(
        school_id=school_id,
        student_id=data.student_id,
        dimension=data.dimension,
        severity=data.severity,
        event_type=data.event_type,
        title=data.title,
        occurred_at=data.occurred_at,
        payload=data.payload,
        reporter_id=reporter_id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def list_timeline_events(
    db: AsyncSession, school_id: int,
    student_id: int = None, dimension: str = None, severity: str = None,
    page: int = 1, page_size: int = 20,
) -> tuple:
    """列出成长事件，支持维度/级别筛选"""
    conditions = [GrowthTimelineEvent.school_id == school_id]
    if student_id:
        conditions.append(GrowthTimelineEvent.student_id == student_id)
    if dimension:
        conditions.append(GrowthTimelineEvent.dimension == dimension)
    if severity:
        conditions.append(GrowthTimelineEvent.severity == severity)

    where_clause = and_(*conditions)
    count_result = await db.execute(
        select(func.count(GrowthTimelineEvent.id)).where(where_clause)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(GrowthTimelineEvent)
        .where(where_clause)
        .order_by(desc(GrowthTimelineEvent.occurred_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = result.scalars().all()

    reporter_ids = [e.reporter_id for e in events if e.reporter_id]
    reporter_names = {}
    if reporter_ids:
        rep_result = await db.execute(
            select(User.id, User.display_name).where(User.id.in_(reporter_ids))
        )
        reporter_names = {row[0]: row[1] for row in rep_result}

    items = []
    for e in events:
        items.append(TimelineEventResponse(
            id=e.id, student_id=e.student_id, dimension=e.dimension,
            severity=e.severity, event_type=e.event_type, title=e.title,
            occurred_at=e.occurred_at, payload=e.payload,
            reporter_name=reporter_names.get(e.reporter_id),
            created_at=e.created_at,
        ))
    return items, total


async def generate_snapshot(
    db: AsyncSession, school_id: int, student_id: int,
    snapshot_type: str, period_label: str,
) -> GrowthPeriodicalSnapshot:
    """
    生成周期性成长快照 — 五维归一化引擎

    学术指数: 60%考试均分 + 40%错题健康度(100-critical_gap_ratio*50)
    考勤指数: 100 - 缺勤次数*3 (min 0)
    行为指数: 100 - 违纪次数*5 + 表彰次数*3 (clamp 0-100)
    心理指数: green=100/yellow=80/orange=60/red=40, 默认90
    活动指数: min(参与次数*10, 100)
    """
    import logging
    logger = logging.getLogger(__name__)

    academic_score = 0.0
    attendance_score = 100.0
    behavior_score = 100.0
    psych_score = 90.0
    activity_score = 0.0

    metrics = {
        "total_absent_count": 0,
        "critical_gap_count": 0,
        "behavior_violation_count": 0,
        "honor_count": 0,
    }

    # ── 1. 学业：考试均分 + 错题断层 ──
    try:
        from modules.grades.models import GradeRecord, GradeSubject
        avg_result = await db.execute(
            select(func.avg(GradeRecord.score))
            .where(
                GradeRecord.student_id == student_id,
                GradeRecord.school_id == school_id,
            )
        )
        avg_val = avg_result.scalar()
        if avg_val:
            academic_score = float(avg_val) * 0.6

        try:
            from modules.error_funnel.models import KnowledgeGap
            gap_result = await db.execute(
                select(func.count(KnowledgeGap.id))
                .where(
                    KnowledgeGap.student_id == student_id,
                    KnowledgeGap.gap_level == "critical",
                )
            )
            critical_count = gap_result.scalar() or 0
            total_gap_result = await db.execute(
                select(func.count(KnowledgeGap.id))
                .where(KnowledgeGap.student_id == student_id)
            )
            total_gaps = total_gap_result.scalar() or 1
            gap_ratio = critical_count / total_gaps if total_gaps > 0 else 0
            academic_score += (100 - gap_ratio * 50) * 0.4
            metrics["critical_gap_count"] = critical_count
        except Exception:
            academic_score += 40.0
    except Exception as e:
        logger.warning(f"[growth] 学业数据聚合失败: {e}")

    # ── 2. 考勤：缺勤次数 ──
    try:
        from modules.attendance.models import AttendanceRecord
        absent_result = await db.execute(
            select(func.count(AttendanceRecord.id))
            .where(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.status != "present",
            )
        )
        absent_count = absent_result.scalar() or 0
        attendance_score = max(0.0, 100.0 - absent_count * 3)
        metrics["total_absent_count"] = absent_count
    except Exception as e:
        logger.warning(f"[growth] 考勤数据聚合失败: {e}")

    # ── 3. 行为：违纪次数 + 表彰 ──
    try:
        from modules.behavior.models import DisciplineRecord
        violation_result = await db.execute(
            select(func.count(DisciplineRecord.id))
            .where(
                DisciplineRecord.student_id == student_id,
                DisciplineRecord.school_id == school_id,
            )
        )
        violation_count = violation_result.scalar() or 0
        behavior_score = max(0.0, 100.0 - violation_count * 5)
        metrics["behavior_violation_count"] = violation_count

        try:
            from modules.habit_cards.models import HonorCard
            honor_result = await db.execute(
                select(func.count(HonorCard.id))
                .where(
                    HonorCard.student_id == student_id,
                    HonorCard.school_id == school_id,
                )
            )
            honor_count = honor_result.scalar() or 0
            behavior_score = min(100.0, behavior_score + honor_count * 3)
            metrics["honor_count"] = honor_count
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[growth] 行为数据聚合失败: {e}")

    # ── 4. 心理：psych_profiles risk_level ──
    try:
        from modules.psych_profiles.models import PsychProfile
        psych_result = await db.execute(
            select(PsychProfile.risk_level)
            .where(
                PsychProfile.student_id == student_id,
                PsychProfile.school_id == school_id,
            )
            .order_by(desc(PsychProfile.updated_at))
            .limit(1)
        )
        risk_level = psych_result.scalar()
        if risk_level:
            risk_map = {"green": 100.0, "yellow": 80.0, "orange": 60.0, "red": 40.0,
                        "low": 100.0, "medium": 80.0, "high": 60.0}
            psych_score = risk_map.get(risk_level.lower() if isinstance(risk_level, str) else "low", 90.0)
    except Exception as e:
        logger.warning(f"[growth] 心理数据聚合失败: {e}")

    # ── 5. 活动：教研活动参与 ──
    try:
        from modules.research_activities.models import ActivityParticipant
        act_result = await db.execute(
            select(func.count(ActivityParticipant.id))
            .where(ActivityParticipant.student_id == student_id)
        )
        act_count = act_result.scalar() or 0
        activity_score = min(100.0, float(act_count * 10))
    except Exception as e:
        logger.warning(f"[growth] 活动数据聚合失败: {e}")

    academic_score = min(100.0, max(0.0, round(academic_score, 1)))
    attendance_score = min(100.0, max(0.0, round(attendance_score, 1)))
    behavior_score = min(100.0, max(0.0, round(behavior_score, 1)))
    psych_score = min(100.0, max(0.0, round(psych_score, 1)))
    activity_score = min(100.0, max(0.0, round(activity_score, 1)))

    existing = await db.execute(
        select(GrowthPeriodicalSnapshot)
        .where(
            GrowthPeriodicalSnapshot.student_id == student_id,
            GrowthPeriodicalSnapshot.snapshot_type == snapshot_type,
            GrowthPeriodicalSnapshot.period_label == period_label,
        )
    )
    snap = existing.scalar_one_or_none()
    if snap:
        snap.academic_score = academic_score
        snap.attendance_score = attendance_score
        snap.behavior_score = behavior_score
        snap.psych_score = psych_score
        snap.activity_score = activity_score
        snap.summary_metrics = metrics
    else:
        snap = GrowthPeriodicalSnapshot(
            school_id=school_id, student_id=student_id,
            snapshot_type=snapshot_type, period_label=period_label,
            academic_score=academic_score, attendance_score=attendance_score,
            behavior_score=behavior_score, psych_score=psych_score,
            activity_score=activity_score, summary_metrics=metrics,
        )
        db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return snap


async def get_holistic_profile(
    db: AsyncSession, school_id: int, student_id: int,
) -> dict:
    """全息成长画像 — 快照 + 历史 + 近期事件 + 7路融合时间轴"""
    student_result = await db.execute(
        select(Student)
        .options(selectinload(Student.class_))
        .where(Student.id == student_id, Student.school_id == school_id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        return None

    class_name = student.class_.name if student.class_ else "未分班"

    snap_result = await db.execute(
        select(GrowthPeriodicalSnapshot)
        .where(
            GrowthPeriodicalSnapshot.student_id == student_id,
            GrowthPeriodicalSnapshot.school_id == school_id,
        )
        .order_by(desc(GrowthPeriodicalSnapshot.created_at))
    )
    snapshots = snap_result.scalars().all()

    snapshot_list = []
    for s in snapshots:
        snapshot_list.append(_snapshot_to_response(s))

    events, event_total = await list_timeline_events(
        db, school_id, student_id=student_id, page=1, page_size=20
    )

    return {
        "student_id": student_id,
        "student_name": student.name,
        "class_name": class_name,
        "current_snapshot": snapshot_list[0] if snapshot_list else None,
        "historical_snapshots": snapshot_list[1:] if len(snapshot_list) > 1 else [],
        "recent_events": events,
    }


async def update_teacher_comment(
    db: AsyncSession, school_id: int, snapshot_id: int, comment: str,
) -> GrowthPeriodicalSnapshot:
    """更新班主任评语"""
    result = await db.execute(
        select(GrowthPeriodicalSnapshot)
        .where(
            GrowthPeriodicalSnapshot.id == snapshot_id,
            GrowthPeriodicalSnapshot.school_id == school_id,
        )
    )
    snap = result.scalar_one_or_none()
    if not snap:
        return None
    snap.teacher_comment = comment
    await db.commit()
    await db.refresh(snap)
    return snap


async def get_growth_dashboard(db: AsyncSession, school_id: int) -> dict:
    """成长档案看板统计"""
    total_events_result = await db.execute(
        select(func.count(GrowthTimelineEvent.id))
        .where(GrowthTimelineEvent.school_id == school_id)
    )
    total_events = total_events_result.scalar() or 0

    critical_result = await db.execute(
        select(func.count(GrowthTimelineEvent.id))
        .where(
            GrowthTimelineEvent.school_id == school_id,
            GrowthTimelineEvent.severity == "critical",
        )
    )
    critical_events = critical_result.scalar() or 0

    warning_result = await db.execute(
        select(func.count(GrowthTimelineEvent.id))
        .where(
            GrowthTimelineEvent.school_id == school_id,
            GrowthTimelineEvent.severity == "warning",
        )
    )
    warning_events = warning_result.scalar() or 0

    bonus_result = await db.execute(
        select(func.count(GrowthTimelineEvent.id))
        .where(
            GrowthTimelineEvent.school_id == school_id,
            GrowthTimelineEvent.severity == "bonus",
        )
    )
    bonus_events = bonus_result.scalar() or 0

    total_snaps_result = await db.execute(
        select(func.count(GrowthPeriodicalSnapshot.id))
        .where(GrowthPeriodicalSnapshot.school_id == school_id)
    )
    total_snapshots = total_snaps_result.scalar() or 0

    total_students_result = await db.execute(
        select(func.count(Student.id))
        .where(Student.school_id == school_id)
    )
    total_students = total_students_result.scalar() or 0

    dim_result = await db.execute(
        select(
            GrowthTimelineEvent.dimension,
            func.count(GrowthTimelineEvent.id),
        )
        .where(GrowthTimelineEvent.school_id == school_id)
        .group_by(GrowthTimelineEvent.dimension)
    )
    dimension_distribution = [
        {"dimension": row[0], "count": row[1]} for row in dim_result
    ]

    recent_crit_result = await db.execute(
        select(GrowthTimelineEvent)
        .where(
            GrowthTimelineEvent.school_id == school_id,
            GrowthTimelineEvent.severity == "critical",
        )
        .order_by(desc(GrowthTimelineEvent.occurred_at))
        .limit(5)
    )
    recent_critical = recent_crit_result.scalars().all()
    recent_critical_list = [
        TimelineEventResponse(
            id=e.id, student_id=e.student_id, dimension=e.dimension,
            severity=e.severity, event_type=e.event_type, title=e.title,
            occurred_at=e.occurred_at, payload=e.payload,
            created_at=e.created_at,
        )
        for e in recent_critical
    ]

    return {
        "total_students": total_students,
        "total_events": total_events,
        "total_snapshots": total_snapshots,
        "critical_events": critical_events,
        "warning_events": warning_events,
        "bonus_events": bonus_events,
        "dimension_distribution": dimension_distribution,
        "recent_critical_events": recent_critical_list,
    }


def _snapshot_to_response(s: GrowthPeriodicalSnapshot) -> GrowthSnapshotResponse:
    """ORM → Response 转换"""
    scores = RadarDimensions(
        academic=s.academic_score, attendance=s.attendance_score,
        behavior=s.behavior_score, psychology=s.psych_score,
        activity=s.activity_score,
    )
    metrics = SnapshotMetricsSummary(
        total_absent_count=(s.summary_metrics or {}).get("total_absent_count", 0),
        critical_gap_count=(s.summary_metrics or {}).get("critical_gap_count", 0),
        behavior_violation_count=(s.summary_metrics or {}).get("behavior_violation_count", 0),
        honor_count=(s.summary_metrics or {}).get("honor_count", 0),
        additional_info=(s.summary_metrics or {}).get("additional_info", {}),
    )
    return GrowthSnapshotResponse(
        id=s.id, student_id=s.student_id,
        snapshot_type=s.snapshot_type, period_label=s.period_label,
        scores=scores, metrics_summary=metrics,
        teacher_comment=s.teacher_comment,
        ai_growth_prescription=s.ai_growth_prescription,
        created_at=s.created_at,
    )
