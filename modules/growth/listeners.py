"""
modules/growth/listeners.py - 成长档案 4 路事件接收站

跨模块事件自动注入管道: 4 个事件源的异常事件通过 Redis pub/sub
流入 growth 模块的时光轴，使成长档案从"被动展示柜"升级为
"主动汇聚神经中枢"。

4 路接收站:
  1. error_funnel.critical        - 知识断层 critical → 学业 CRITICAL
  2. behavior.disciplined         - 违纪处分 → 行为 WARNING/CRITICAL
  3. psych.risk_changed           - 心理风险等级变更 → 心理维度
  4. attendance.consecutive_absent - 连续缺勤 → 考勤 CRITICAL

每个接收站:
  - 开启独立 DB Session (不复用请求生命周期 Session)
  - 调用 GrowthAggregationPipeline.inject_timeline_event() 写入时光轴
  - commit + close (异常自动 rollback)
"""

import hashlib
import logging
from datetime import datetime
from typing import Any

from core.event_bus import EventBus
from core.redis_client import get_redis
from modules.growth.cep_interceptor import (
    TRIGGER_ATTENDANCE,
    TRIGGER_ERROR_FUNNEL,
    ComplexEventInterceptor,
)
from modules.growth.models import EventSeverity, GrowthDimension
from modules.growth.pipeline import GrowthAggregationPipeline
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  频道名常量 — 与上游模块 publish 的 channel 保持一致
# ═══════════════════════════════════════════════════════════════

CH_ERROR_FUNNEL_CRITICAL = "error_funnel.critical"
CH_BEHAVIOR_DISCIPLINED = "behavior.disciplined"
CH_PSYCH_RISK_CHANGED = "psych.risk_changed"
CH_ATTENDANCE_CONSECUTIVE_ABSENT = "attendance.consecutive_absent"

# ═════ Wings 3.2 新接入频道 ═════
CH_HOMEWORK_SUBMISSION_LATE = "homework.submission_late"
CH_TIMETABLE_SCHEDULE_CHANGE = "timetable.schedule_change"
CH_HABIT_CARD_ISSUED = "habit_cards.card_issued"
CH_HABIT_BLINDBOX_OPENED = "habit_cards.blindbox_opened"

# ═════ Wings 3.2 见字如面频道 ═════
CH_PARENT_MEETING_LETTER = "moral.parent_meeting_letter"

# ═══════════════════════════════════════════════════════════════
#  Session 工厂 (由 app.py lifespan 注入)
# ═══════════════════════════════════════════════════════════════

_session_factory: async_sessionmaker | None = None

# CEP 复合事件拦截器实例 (在 initialize_growth_events 中初始化)
_cep_interceptor: ComplexEventInterceptor | None = None


# ═══════════════════════════════════════════════════════════════
#  分布式去重锁 — 防止 4 Workers pub/sub 广播导致 4x 重复注入
# ═══════════════════════════════════════════════════════════════

_DEDUP_TTL = 300  # 5 分钟


async def _try_dedup(event_data: dict[str, Any]) -> bool:
    """
    分布式去重: Redis SETNX 锁。

    4 Workers 都会收到 pub/sub 广播，但只有第一个 SETNX 成功的 Worker
    才执行注入，其余跳过。Redis 不可用时放行 (宁重复不丢失)。

    Returns:
        True = 首次获取锁, 应该注入
        False = 重复事件, 跳过
    """
    redis = get_redis()
    if redis is None:
        return True  # Redis 不可用 → 放行 (降级模式宁重复不丢失)

    # 用关键字段计算唯一指纹 — 不含 occurred_at (各 Worker 独立生成, 微秒不同)
    fingerprint = "|".join(
        [
            str(event_data.get("school_id", "")),
            str(event_data.get("student_id", "")),
            str(event_data.get("event_type", "")),
            str(event_data.get("title", "")),
        ]
    )
    key = f"growth:dedup:{hashlib.md5(fingerprint.encode()).hexdigest()}"  # nosec B324

    try:
        result = await redis.set(key, "1", ex=_DEDUP_TTL, nx=True)
        return bool(result)
    except Exception as e:
        logger.warning(f"[growth-listeners] 去重锁异常, 放行: {e}")
        return True


# ═══════════════════════════════════════════════════════════════
#  通用注入器 — 独立 Session 写入时光轴
# ═══════════════════════════════════════════════════════════════


async def _enrich_timetable_context(
    session: AsyncSession,
    event_data: dict[str, Any],
) -> None:
    """
    Wings 3.1 时空上下文升维中枢 — 在事件注入前注入课表上下文。

    通过 student_id → class_id → TimetableEnricher.enrich_telemetry_event()
    将孤立的时间戳富集为 (节次, 学科, 教师) 三维坐标，
    写入 event_data["payload"]["_timetable"]。

    降级策略: 任何异常均静默跳过，绝不阻塞主事件流。
    """
    student_id = event_data.get("student_id")
    school_id = event_data.get("school_id")

    if not student_id or not school_id:
        return

    # 获取学生班级 (缓存友好: Student 表极小且常驻内存)
    try:
        from core.models import Student

        result = await session.execute(
            sa_select(Student.class_id).where(
                Student.id == student_id,
                Student.school_id == school_id,
            )
        )
        class_id = result.scalar()
    except Exception as e:
        logger.debug(f"[growth-listeners] 获取学生班级失败 student={student_id}: {e}")
        return

    if not class_id:
        logger.debug(f"[growth-listeners] 学生无班级 student={student_id}")
        return

    # 调用时空富集网关
    try:
        from modules.timetable.enricher import TimetableEnricher

        occurred_at = event_data.get("occurred_at", datetime.utcnow())
        enriched = await TimetableEnricher.enrich_telemetry_event(
            school_id=school_id,
            class_id=class_id,
            occurred_at=occurred_at,
            db=session,
        )

        # 写入 payload（持久化到时光轴） + 顶层（供 CEP 消费）
        if isinstance(event_data.get("payload"), dict):
            event_data["payload"]["_timetable"] = enriched
        event_data["_timetable_context"] = enriched
        logger.debug(
            f"[growth-listeners] 时空上下文已升维: "
            f"student={student_id} class={class_id} "
            f"in_lesson={enriched.get('in_lesson')} "
            f"period={enriched.get('period_index')} "
            f"subject={enriched.get('subject_id')}"
        )
    except Exception as e:
        logger.debug(f"[growth-listeners] 时空富集跳过 student={student_id}: {e}")


async def _enrich_cep_event_with_timetable(event: dict[str, Any]) -> None:
    """
    CEP 专用时空上下文注入 — 为不经过 _inject_event() 的 CEP 事件补充课表信息。

    典型场景: on_error_funnel_critical 中 CEP 调用使用原始 event dict，
    而非已富集的 inject_data。此函数在原位为 event dict 注入 class_id
    和 _timetable_context，供 CEP 的 trigger_meta 捕获。

    降级策略: 任何异常静默跳过，不阻塞 CEP 主流程。
    """
    student_id = event.get("student_id")
    school_id = event.get("school_id")

    if not student_id or not school_id or _session_factory is None:
        return

    try:
        from core.models import Student

        async with _session_factory() as session:
            result = await session.execute(
                sa_select(Student.class_id).where(
                    Student.id == student_id,
                    Student.school_id == school_id,
                )
            )
            class_id = result.scalar()

            if not class_id:
                return

            # 注入 class_id (CEP trigger_meta 会捕获此字段)
            event["class_id"] = class_id

            # 调用 Enricher 获取完整时空上下文
            from modules.timetable.enricher import TimetableEnricher

            occurred_at = event.get("occurred_at", datetime.utcnow())
            enriched = await TimetableEnricher.enrich_telemetry_event(
                school_id=school_id,
                class_id=class_id,
                occurred_at=occurred_at,
                db=session,
            )
            event["_timetable_context"] = enriched
            logger.debug(
                f"[growth-listeners] CEP事件时空上下文已注入: "
                f"student={student_id} class={class_id} "
                f"in_lesson={enriched.get('in_lesson')} "
                f"subject={enriched.get('subject_id')}"
            )
    except Exception as e:
        logger.debug(f"[growth-listeners] CEP时空富集跳过: {e}")


async def _inject_event(event_data: dict[str, Any]):
    """
    通用事件注入器 — 开启独立 DB Session 写入成长时光轴。

    核心设计:
      - 使用 _session_factory 创建全新 AsyncSession
      - 不复用请求生命周期 Session (避免 Session 销毁问题)
      - 写入成功 commit, 失败 rollback
    """
    if not await _try_dedup(event_data):
        logger.debug(f"[growth-listeners] 去重命中, 跳过: type={event_data.get('event_type')}")
        return

    if _session_factory is None:
        logger.warning("[growth-listeners] session_factory 未初始化, 跳过注入")
        return

    async with _session_factory() as session:
        try:
            # ⚡ Wings 3.1: 时空上下文升维 (13路流 x 课表网格合体)
            await _enrich_timetable_context(session, event_data)

            pipeline = GrowthAggregationPipeline(session)
            await pipeline.inject_timeline_event(event_data)
            await session.commit()
            logger.info(
                f"[growth-listeners] 事件已注入: "
                f"type={event_data.get('event_type')} "
                f"student={event_data.get('student_id')} "
                f"dim={event_data.get('dimension')} "
                f"severity={event_data.get('severity')}"
            )
        except Exception as e:
            await session.rollback()
            logger.error(
                f"[growth-listeners] 事件注入失败 type={event_data.get('event_type')}: {e}",
                exc_info=True,
            )


# ═══════════════════════════════════════════════════════════════
#  4 路接收站
# ═══════════════════════════════════════════════════════════════


async def on_error_funnel_critical(event: dict[str, Any]):
    """
    接收站 1: 错题断层 critical → 学业维度 CRITICAL

    上游: error_funnel/services.py _aggregate_gaps()
    触发条件: consecutive_errors >= 3 or error_count >= 5

    事件载荷:
      school_id, student_id, knowledge_point,
      consecutive_errors, error_count
    """
    await _inject_event(
        {
            "school_id": event.get("school_id"),
            "student_id": event.get("student_id"),
            "dimension": GrowthDimension.ACADEMIC.value,
            "severity": EventSeverity.CRITICAL.value,
            "event_type": "gap_critical",
            "title": f"知识断层预警: {event.get('knowledge_point', '未知知识点')}",
            "occurred_at": datetime.utcnow(),
            "payload": {
                "knowledge_point": event.get("knowledge_point"),
                "consecutive_errors": event.get("consecutive_errors"),
                "error_count": event.get("error_count"),
                "gap_level": "critical",
                "source": "error_funnel",
            },
        }
    )

    # ── CEP 复合事件拦截: 学业断层入站, 探测考勤窗口是否同时亮着 ──
    if _cep_interceptor:
        try:
            # ⚡ Wings 3.1: 为 CEP 注入时空上下文 (class_id → Enricher → subject/teacher)
            await _enrich_cep_event_with_timetable(event)
            await _cep_interceptor.process_event(TRIGGER_ERROR_FUNNEL, event)
        except Exception as e:
            logger.warning("[growth-listeners] CEP触发失败(error_funnel), 不影响主流程: %s", e)


async def on_behavior_disciplined(event: dict[str, Any]):
    """
    接收站 2: 违纪处分 → 行为维度

    上游: behavior/services.py create_record() post-commit
    严重等级映射:
      serious/major → CRITICAL
      warning/minor → WARNING

    事件载荷:
      school_id, student_id, category, level, deduction, title
    """
    level = event.get("level", "minor")
    severity = (
        EventSeverity.CRITICAL.value
        if level in ("serious", "major")
        else EventSeverity.WARNING.value
    )

    await _inject_event(
        {
            "school_id": event.get("school_id"),
            "student_id": event.get("student_id"),
            "dimension": GrowthDimension.BEHAVIOR.value,
            "severity": severity,
            "event_type": "discipline_punish",
            "title": event.get("title", "行为记录"),
            "occurred_at": datetime.utcnow(),
            "payload": {
                "category": event.get("category"),
                "level": level,
                "deduction": event.get("deduction"),
                "source": "behavior",
            },
        }
    )


async def on_psych_risk_changed(event: dict[str, Any]):
    """
    接收站 3: 心理风险等级变更 → 心理维度

    上游: psych_profiles/services.py
      - update_profile() risk_level 变更
      - recompute_profile_stats() risk_level 变更
      - create_screening() risk_level 变更

    严重等级映射:
      red    → CRITICAL
      orange → WARNING
      yellow → WARNING
      green  → BONUS (恢复正常)

    事件载荷:
      school_id, student_id, previous_level, current_level, source, trigger
    """
    risk_level = event.get("current_level", "")
    severity_map = {
        "red": EventSeverity.CRITICAL.value,
        "orange": EventSeverity.WARNING.value,
        "yellow": EventSeverity.WARNING.value,
        "green": EventSeverity.BONUS.value,
        # 兼容 low/medium/high 体系
        "high": EventSeverity.CRITICAL.value,
        "medium": EventSeverity.WARNING.value,
        "low": EventSeverity.BONUS.value,
    }
    severity = severity_map.get(
        risk_level.lower() if isinstance(risk_level, str) else "",
        EventSeverity.INFO.value,
    )

    await _inject_event(
        {
            "school_id": event.get("school_id"),
            "student_id": event.get("student_id"),
            "dimension": GrowthDimension.PSYCHOLOGY.value,
            "severity": severity,
            "event_type": "psych_risk_change",
            "title": f"心理风险评估更新: {risk_level}",
            "occurred_at": datetime.utcnow(),
            "payload": {
                "previous_level": event.get("previous_level"),
                "current_level": risk_level,
                "source": event.get("source", "psych_profiles"),
                "trigger": event.get("trigger"),
            },
        }
    )


async def on_attendance_consecutive_absent(event: dict[str, Any]):
    """
    接收站 4: 连续缺勤 → 考勤维度 CRITICAL

    上游: attendance/services.py batch_record() post-commit
    监听器内部查询最近 7 天考勤记录，判断连续缺勤 >= 3 天才注入。

    设计: batch_record 只发轻量事件 (school_id + student_id)，
    监听器负责查 DB 判断连续缺勤天数，避免拖慢请求。

    事件载荷:
      school_id, student_id, class_id
    """
    school_id = event.get("school_id")
    student_id = event.get("student_id")
    class_id = event.get("class_id")

    if not school_id or not student_id:
        return

    if _session_factory is None:
        logger.warning("[growth-listeners] session_factory 未初始化, 跳过连续缺勤检测")
        return

    async with _session_factory() as session:
        try:
            from datetime import date, timedelta

            from modules.attendance.models import AttendanceRecord
            from sqlalchemy import and_, desc, select

            today = date.today()
            week_ago = today - timedelta(days=7)

            result = await session.execute(
                select(AttendanceRecord.record_date, AttendanceRecord.status)
                .where(
                    and_(
                        AttendanceRecord.school_id == school_id,
                        AttendanceRecord.student_id == student_id,
                        AttendanceRecord.record_date >= week_ago,
                        AttendanceRecord.record_date <= today,
                    )
                )
                .order_by(desc(AttendanceRecord.record_date))
            )
            records = result.all()

            # 计算从今天往回的连续缺勤天数
            consecutive = 0
            absent_dates = []
            for rec_date, status in records:
                if status == "absent":
                    consecutive += 1
                    absent_dates.append(rec_date.isoformat())
                else:
                    break  # 遇到非 absent 记录, 连续中断

            if consecutive >= 3:
                inject_data = {
                    "school_id": school_id,
                    "student_id": student_id,
                    "dimension": GrowthDimension.ATTENDANCE.value,
                    "severity": EventSeverity.CRITICAL.value,
                    "event_type": "consecutive_absent",
                    "title": f"连续缺勤预警 ({consecutive}天)",
                    "occurred_at": datetime.utcnow(),
                    "payload": {
                        "absent_count": consecutive,
                        "absent_dates": absent_dates,
                        "class_id": class_id,
                        "source": "attendance",
                    },
                }
                if not await _try_dedup(inject_data):
                    logger.debug(f"[growth-listeners] 连续缺勤去重命中, 跳过: student={student_id}")
                    return
                # ⚡ Wings 3.1: 时空上下文升维
                await _enrich_timetable_context(session, inject_data)
                pipeline = GrowthAggregationPipeline(session)
                await pipeline.inject_timeline_event(inject_data)
                await session.commit()
                logger.info(
                    f"[growth-listeners] 连续缺勤事件已注入: "
                    f"student={student_id} count={consecutive}"
                )

                # ── CEP 复合事件拦截: 考勤危机入站, 探测学业断层窗口是否同时亮着 ──
                if _cep_interceptor:
                    try:
                        await _cep_interceptor.process_event(TRIGGER_ATTENDANCE, inject_data)
                    except Exception as e:
                        logger.warning(
                            "[growth-listeners] CEP触发失败(attendance), 不影响主流程: %s", e
                        )
        except Exception as e:
            await session.rollback()
            logger.error(
                f"[growth-listeners] 连续缺勤检测失败 student={student_id}: {e}",
                exc_info=True,
            )


# ═══════════════════════════════════════════════════════════════
#  Wings 3.2 新接入接收站 — 作业迟交 + 课表变轨
# ═══════════════════════════════════════════════════════════════


async def on_homework_submission_late(event: dict[str, Any]):
    """
    接收站 5: 作业迟交 → 学业维度 WARNING

    上游: homework_mgmt/services.py submit_homework()
    触发条件: submitted_at > assignment.due_date

    事件载荷:
      school_id, student_id, assignment_id, subject_id,
      grade_id, class_id, late_minutes, title
    """
    await _inject_event(
        {
            "school_id": event.get("school_id"),
            "student_id": event.get("student_id"),
            "dimension": GrowthDimension.ACADEMIC.value,
            "severity": EventSeverity.WARNING.value,
            "event_type": "homework_late",
            "title": event.get("title", "作业迟交"),
            "occurred_at": datetime.utcnow(),
            "payload": {
                "assignment_id": event.get("assignment_id"),
                "subject_id": event.get("subject_id"),
                "late_minutes": event.get("late_minutes"),
                "source": "homework_mgmt",
            },
        }
    )


async def on_timetable_schedule_change(event: dict[str, Any]):
    """
    接收站 6: 课表变轨 → 考勤/行为维度 INFO (时空锚点)

    上游: timetable/services.py create_slot() / delete_slot()
    不直接触发预警，而是作为时空参照系注入时光轴，
    供后续 CEP 复合事件检测时定位变轨日的课程上下文。

    事件载荷:
      school_id, slot_id, class_id, course_id, teacher_id,
      subject_id, day_of_week, slot_number, change_type,
      has_conflicts, title
    """
    await _inject_event(
        {
            "school_id": event.get("school_id"),
            "student_id": 0,  # 课表变轨是班级级事件，非个体
            "dimension": GrowthDimension.ATTENDANCE.value,
            "severity": EventSeverity.INFO.value,
            "event_type": "timetable_change",
            "title": event.get("title", "课表变动"),
            "occurred_at": datetime.utcnow(),
            "payload": {
                "slot_id": event.get("slot_id"),
                "class_id": event.get("class_id"),
                "course_id": event.get("course_id"),
                "teacher_id": event.get("teacher_id"),
                "subject_id": event.get("subject_id"),
                "day_of_week": event.get("day_of_week"),
                "slot_number": event.get("slot_number"),
                "change_type": event.get("change_type"),
                "has_conflicts": event.get("has_conflicts"),
                "source": "timetable",
            },
        }
    )


# ═══════════════════════════════════════════════════════════════
#  Wings 3.2 Phase 2 新接入 — 习惯卡片双向事件
# ═══════════════════════════════════════════════════════════════


async def on_habit_card_issued(event: dict[str, Any]):
    """
    接收站 7: 教师发卡 → 行为维度 BONUS (正向激励)

    上游: habit_cards/services.py issue_cards_to_students()
    教师批量向学生派发萌卡时，为每个学生注入一条正向成长事件。

    事件载荷:
      school_id, teacher_id, card_id, card_name, card_rarity,
      card_category, student_ids, issued_count, note, occurred_at
    """
    school_id = event.get("school_id")
    student_ids = event.get("student_ids", [])
    card_name = event.get("card_name", "未知卡牌")
    card_rarity = event.get("card_rarity", "common")
    card_category = event.get("card_category", "habit")

    # 稀有度 → 严重度映射 (传说/史诗 = BONUS, 稀有/普通 = INFO)
    rarity_severity = {
        "legendary": EventSeverity.BONUS.value,
        "epic": EventSeverity.BONUS.value,
        "rare": EventSeverity.INFO.value,
        "common": EventSeverity.INFO.value,
    }
    severity = rarity_severity.get(card_rarity, EventSeverity.INFO.value)

    # 类别映射
    cat_dim_map = {
        "habit": GrowthDimension.BEHAVIOR.value,
        "academic": GrowthDimension.ACADEMIC.value,
        "social": GrowthDimension.BEHAVIOR.value,
        "sports": GrowthDimension.BEHAVIOR.value,
        "art": GrowthDimension.BEHAVIOR.value,
    }
    dimension = cat_dim_map.get(card_category, GrowthDimension.BEHAVIOR.value)

    for sid in student_ids:
        await _inject_event(
            {
                "school_id": school_id,
                "student_id": sid,
                "dimension": dimension,
                "severity": severity,
                "event_type": "habit_card_issued",
                "title": f"获得萌卡: {card_name}",
                "occurred_at": datetime.utcnow(),
                "payload": {
                    "card_name": card_name,
                    "card_rarity": card_rarity,
                    "card_category": card_category,
                    "teacher_id": event.get("teacher_id"),
                    "note": event.get("note", ""),
                    "source": "habit_cards",
                },
            }
        )


async def on_habit_blindbox_opened(event: dict[str, Any]):
    """
    接收站 8: 家长盲盒翻牌 → 行为维度 BONUS (家校联动)

    上游: habit_cards/services.py open_blindbox_for_parent()
    家长通过盲盒查看孩子卡牌资产时注入，记录家校联动的正向时刻。

    事件载荷:
      school_id, student_id, parent_user_id, card_id, card_name,
      card_rarity, card_category, is_first_open, occurred_at
    """
    school_id = event.get("school_id")
    student_id = event.get("student_id")
    card_name = event.get("card_name", "未知卡牌")
    is_first_open = event.get("is_first_open", False)

    await _inject_event(
        {
            "school_id": school_id,
            "student_id": student_id,
            "dimension": GrowthDimension.BEHAVIOR.value,
            "severity": EventSeverity.BONUS.value,
            "event_type": "habit_blindbox_opened",
            "title": f"{'首次' if is_first_open else ''}家长盲盒开启: {card_name}",
            "occurred_at": datetime.utcnow(),
            "payload": {
                "card_name": card_name,
                "card_rarity": event.get("card_rarity"),
                "card_category": event.get("card_category"),
                "is_first_open": is_first_open,
                "parent_user_id": event.get("parent_user_id"),
                "source": "habit_cards",
            },
        }
    )


# ═══════════════════════════════════════════════════════════════
#  Wings 3.2 见字如面 · 家长会书信事件
# ═══════════════════════════════════════════════════════════════


async def on_parent_meeting_letter(event: dict[str, Any]):
    """
    接收站 9: 见字如面 · 家长回信 → 行为维度 BONUS (家校纽带黄金事件)

    上游: habit_cards/services.py (家长在家长会现场完成回信时触发)
    业务场景: 2026年5月29日"见字如面·成长有你"初一年级家长会

    当家长完成回信 (status=replied) 时:
      1. 写入 Growth Timeline 黄金事件 (GOLDEN_BOND)
      2. 反哺班主任德育管理活跃度 +5

    事件载荷:
      school_id, student_id, parent_user_id, status,
      meeting_id, letter_id
    """
    status = event.get("status", "")
    student_id = event.get("student_id")
    school_id = event.get("school_id")

    if status != "replied":
        # 只在家长回信时注入黄金事件, sent/read 不注入
        return

    if not student_id or not school_id:
        logger.warning("[growth-listeners] 见字如面事件缺少 student_id/school_id, 跳过")
        return

    # 1. 写入成长时光轴 — 家校纽带黄金事件
    await _inject_event(
        {
            "school_id": school_id,
            "student_id": student_id,
            "dimension": GrowthDimension.BEHAVIOR.value,
            "severity": EventSeverity.BONUS.value,
            "event_type": "GOLDEN_BOND",
            "title": "见字如面 \u00b7 收到家长的温情回信",
            "occurred_at": datetime.utcnow(),
            "payload": {
                "parent_user_id": event.get("parent_user_id"),
                "meeting_id": event.get("meeting_id", ""),
                "letter_id": event.get("letter_id"),
                "source": "parent_meeting_letter",
                "description": "在初一年级家长会上，家长拆开盲盒并留下了写给你的字条。",
            },
        }
    )

    # 2. 反哺班主任德育管理活跃度 +5
    if _session_factory is None:
        logger.warning("[growth-listeners] session_factory 未初始化, 跳过班主任活跃度加权")
        return

    try:
        async with _session_factory() as session:
            from core.models import Student
            from sqlalchemy import select as sa_select

            # 查学生的班级 -> 查该班的班主任
            result = await session.execute(
                sa_select(Student.class_id).where(
                    Student.id == student_id,
                    Student.school_id == school_id,
                )
            )
            class_id = result.scalar()

            if not class_id:
                logger.debug(
                    f"[growth-listeners] 见字如面: 学生 {student_id} 无班级, 跳过班主任加权"
                )
                return

            # 查班主任 (class_teacher 角色)
            from core.models import UserClassMapping

            result = await session.execute(
                sa_select(UserClassMapping.user_id).where(
                    UserClassMapping.class_id == class_id,
                    UserClassMapping.school_id == school_id,
                )
            )
            teacher_id = result.scalar()

            if teacher_id:
                logger.info(
                    f"[growth-listeners] 见字如面: 班主任 {teacher_id} "
                    f"德育管理活跃度 +5 (student={student_id})"
                )
                # TODO: 当 teacher_mgmt 模块支持活跃度积分时, 调用 increment_teacher_intensity()
            else:
                logger.debug(f"[growth-listeners] 见字如面: 班级 {class_id} 无班主任映射")

    except Exception as e:
        logger.warning(
            f"[growth-listeners] 见字如面班主任加权失败 (非致命): {e}",
            exc_info=True,
        )


# ═══════════════════════════════════════════════════════════════
#  并网函数 — 在 app.py lifespan 中调用
# ═══════════════════════════════════════════════════════════════


async def initialize_growth_events(
    session_factory: async_sessionmaker,
):
    """
    挂载 4 路事件监听器 — 在 app.py lifespan 启动时调用。

    Args:
        session_factory: AsyncSessionLocal 工厂 (来自 app.py)
    """
    global _session_factory, _cep_interceptor
    _session_factory = session_factory

    # 初始化 CEP 复合事件拦截器
    _cep_interceptor = ComplexEventInterceptor()

    bus = EventBus()
    await bus.subscribe(CH_ERROR_FUNNEL_CRITICAL, on_error_funnel_critical)
    await bus.subscribe(CH_BEHAVIOR_DISCIPLINED, on_behavior_disciplined)
    await bus.subscribe(CH_PSYCH_RISK_CHANGED, on_psych_risk_changed)
    await bus.subscribe(CH_ATTENDANCE_CONSECUTIVE_ABSENT, on_attendance_consecutive_absent)
    await bus.subscribe(CH_HOMEWORK_SUBMISSION_LATE, on_homework_submission_late)
    await bus.subscribe(CH_TIMETABLE_SCHEDULE_CHANGE, on_timetable_schedule_change)
    await bus.subscribe(CH_HABIT_CARD_ISSUED, on_habit_card_issued)
    await bus.subscribe(CH_HABIT_BLINDBOX_OPENED, on_habit_blindbox_opened)
    await bus.subscribe(CH_PARENT_MEETING_LETTER, on_parent_meeting_letter)

    logger.info("[growth-listeners] 9 路事件接收站 + CEP 拦截器已并网")


async def shutdown_growth_events():
    """关闭事件监听 — 在 app.py lifespan shutdown 中调用"""
    bus = EventBus()
    await bus.shutdown()
    logger.info("[growth-listeners] 事件接收站已关闭")
