"""
psych_profiles/services.py — 心理档案 + 筛查快照 + 双轨预警 Nexus 业务层

核心引擎:
  1. CRUD — psy_profiles / psy_screening_records
  2. recompute_profile_stats — 从子表聚合统计 (咨询次数/筛查次数/干预次数)
  3. get_comprehensive_risks — 学业x心理双轨预警合成 (联表4张异构表)
  4. get_student_nexus_detail — 单个学生双轨详细画像
  5. get_dashboard_stats — 仪表盘聚合统计
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import get_local_now
from modules.psych_profiles.models import PsyProfile, PsyScreeningRecord


# ============================================================
# 风险等级工具
# ============================================================
_RISK_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
_RISK_LABEL = {"green": "GREEN", "yellow": "YELLOW", "orange": "ORANGE", "red": "RED"}


def _risk_rank(level: str) -> int:
    return _RISK_ORDER.get((level or "green").lower(), 0)


def _highest_risk(a: str, b: str) -> str:
    return a if _risk_rank(a) >= _risk_rank(b) else b


def _classify_priority(academic_level: str, psy_level: str) -> tuple:
    """合成行动优先级: (priority, co_trigger, actions)"""
    a_rank = _risk_rank(academic_level)
    p_rank = _risk_rank(psy_level)

    # 映射学业预警到心理四级 (student_risk_alerts 用 red/yellow)
    a_psy_equivalent = "red" if academic_level == "RED" else ("yellow" if academic_level == "YELLOW" else "green")

    co_trigger = a_rank >= 1 and p_rank >= 2  # 学业黄+心理橙 以上

    if a_rank >= 3 and p_rank >= 2:  # 学业红 + 心理橙/红
        return "CRITICAL", True, ["班主任+心理老师联合约谈", "家长联动告知", "启动危机干预流程", "持续追踪"]
    if a_rank >= 3 and p_rank >= 1:  # 学业红 + 心理黄
        return "URGENT", True, ["心理老师约谈", "班主任密切关注", "家长沟通"]
    if a_rank >= 1 and p_rank >= 3:  # 学业黄/红 + 心理红
        return "CRITICAL", True, ["立刻危机干预", "心理老师+班主任联合", "家长紧急告知"]
    if a_rank >= 1 and p_rank >= 2:  # 学业黄 + 心理橙
        return "URGENT", True, ["心理老师约谈", "班主任关注学业波动", "家长沟通"]
    if a_rank >= 1 or p_rank >= 2:  # 单侧预警
        return "WATCH", False, ["班主任关注", "定期复查"]
    return "NORMAL", False, ["常规关注"]


# ============================================================
# 一、心理档案 CRUD
# ============================================================
async def get_or_create_profile(
    db: AsyncSession, school_id: int, student_id: int,
) -> PsyProfile:
    """获取或自动创建学生心理档案"""
    stmt = select(PsyProfile).where(
        and_(PsyProfile.school_id == school_id, PsyProfile.student_id == student_id)
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = PsyProfile(
            school_id=school_id,
            student_id=student_id,
            risk_level="green",
            risk_level_source="auto",
            tags=[],
        )
        db.add(profile)
        await db.flush()
    return profile


async def get_profile(
    db: AsyncSession, school_id: int, student_id: int,
) -> Optional[PsyProfile]:
    stmt = select(PsyProfile).where(
        and_(PsyProfile.school_id == school_id, PsyProfile.student_id == student_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_profiles(
    db: AsyncSession,
    school_id: int,
    risk_level: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple:
    """档案列表 — 支持风险等级/标签筛选"""
    conditions = [PsyProfile.school_id == school_id]
    if risk_level:
        conditions.append(PsyProfile.risk_level == risk_level)

    where_clause = and_(*conditions)

    # 总数
    count_stmt = select(func.count(PsyProfile.id)).where(where_clause)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页查询
    stmt = (
        select(PsyProfile)
        .where(where_clause)
        .order_by(desc(_risk_rank_col(PsyProfile.risk_level)), desc(PsyProfile.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    profiles = result.scalars().all()

    # 内存中过滤标签 (JSON 无法高效 WHERE)
    if tag:
        profiles = [p for p in profiles if p.tags and tag in p.tags]

    return profiles, total


def _risk_rank_col(col):
    """SQL表达式: 将风险等级映射为排序权重 (MySQL CASE)"""
    return func.field(col, "red", "orange", "yellow", "green")


async def update_profile(
    db: AsyncSession, school_id: int, student_id: int, data: dict,
) -> Optional[PsyProfile]:
    profile = await get_profile(db, school_id, student_id)
    if profile is None:
        return None

    # 风险等级变更时记录更新时间和来源
    if "risk_level" in data and data["risk_level"] != profile.risk_level:
        data["risk_level_updated_at"] = get_local_now()
        # 更新历史最高风险
        if _risk_rank(data["risk_level"]) > _risk_rank(profile.highest_risk_level):
            data["highest_risk_level"] = data["risk_level"]

        # 🔌 事件总线盲发: 心理风险等级变更 (fire-and-forget)
        _previous_level = profile.risk_level
        _new_level = data["risk_level"]
        try:
            from core.event_bus import EventBus
            EventBus().publish("psych.risk_changed", {
                "school_id": school_id,
                "student_id": student_id,
                "previous_level": _previous_level,
                "current_level": _new_level,
                "source": "profile_update",
                "trigger": "manual",
            })
        except Exception:
            pass

    for key, val in data.items():
        if hasattr(profile, key) and val is not None:
            setattr(profile, key, val)

    await db.flush()
    return profile


async def update_tags(
    db: AsyncSession, school_id: int, student_id: int, tags: List[str],
) -> Optional[PsyProfile]:
    profile = await get_profile(db, school_id, student_id)
    if profile is None:
        return None
    profile.tags = tags
    await db.flush()
    return profile


async def delete_profile(
    db: AsyncSession, school_id: int, student_id: int,
) -> bool:
    profile = await get_profile(db, school_id, student_id)
    if profile is None:
        return False
    await db.delete(profile)
    await db.flush()
    return True


async def recompute_profile_stats(
    db: AsyncSession, school_id: int, student_id: int,
) -> Optional[PsyProfile]:
    """从子表重新聚合统计 — 咨询次数/筛查次数/干预次数/最近活动"""
    profile = await get_or_create_profile(db, school_id, student_id)
    now = get_local_now()

    # 1. 筛查次数 (psy_screening_records)
    screening_count_stmt = select(func.count(PsyScreeningRecord.id)).where(
        and_(
            PsyScreeningRecord.school_id == school_id,
            PsyScreeningRecord.student_id == student_id,
        )
    )
    profile.total_screening_count = (await db.execute(screening_count_stmt)).scalar() or 0

    # 最近筛查
    latest_screening_stmt = (
        select(PsyScreeningRecord)
        .where(and_(
            PsyScreeningRecord.school_id == school_id,
            PsyScreeningRecord.student_id == student_id,
        ))
        .order_by(desc(PsyScreeningRecord.test_date))
        .limit(1)
    )
    latest_screening = (await db.execute(latest_screening_stmt)).scalar_one_or_none()
    if latest_screening:
        profile.last_screening_date = latest_screening.test_date
        # 如果筛查风险高于档案风险, 自动提升
        if _risk_rank(latest_screening.risk_level) > _risk_rank(profile.risk_level):
            _prev_level = profile.risk_level
            profile.risk_level = latest_screening.risk_level
            profile.risk_level_source = "screening"
            profile.risk_level_updated_at = now

            # 🔌 事件总线盲发: 心理风险等级变更 (fire-and-forget)
            try:
                from core.event_bus import EventBus
                EventBus().publish("psych.risk_changed", {
                    "school_id": school_id,
                    "student_id": student_id,
                    "previous_level": _prev_level,
                    "current_level": latest_screening.risk_level,
                    "source": "screening_recompute",
                    "trigger": "auto_aggregate",
                })
            except Exception:
                pass

    # 2. 咨询次数 (psy_consult_records) — 延迟导入避免循环
    try:
        from modules.psych_counseling.models import PsyConsultRecord
        counsel_count_stmt = select(func.count(PsyConsultRecord.id)).where(
            and_(
                PsyConsultRecord.school_id == school_id,
                PsyConsultRecord.student_id == student_id,
            )
        )
        profile.total_counseling_count = (await db.execute(counsel_count_stmt)).scalar() or 0

        latest_counsel_stmt = (
            select(PsyConsultRecord)
            .where(and_(
                PsyConsultRecord.school_id == school_id,
                PsyConsultRecord.student_id == student_id,
            ))
            .order_by(desc(PsyConsultRecord.created_at))
            .limit(1)
        )
        latest_counsel = (await db.execute(latest_counsel_stmt)).scalar_one_or_none()
        if latest_counsel:
            profile.last_counseling_date = latest_counsel.created_at
            # 咨询风险等级也可能提升档案风险
            if _risk_rank(latest_counsel.risk_level) > _risk_rank(profile.highest_risk_level):
                profile.highest_risk_level = latest_counsel.risk_level
            if latest_counsel.is_referred:
                profile.is_referred = True
                if not profile.referral_status:
                    profile.referral_status = "completed"
                if latest_counsel.referral_target and not profile.referral_target:
                    profile.referral_target = latest_counsel.referral_target
    except ImportError:
        pass  # psych_counseling 模块未安装时跳过

    # 3. 干预次数 (intervention_records) — 延迟导入
    try:
        from modules.psych_screening.models import InterventionRecord
        interv_count_stmt = select(func.count(InterventionRecord.id)).where(
            and_(
                InterventionRecord.school_id == school_id,
                InterventionRecord.student_id == student_id,
            )
        )
        profile.total_intervention_count = (await db.execute(interv_count_stmt)).scalar() or 0

        latest_interv_stmt = (
            select(InterventionRecord)
            .where(and_(
                InterventionRecord.school_id == school_id,
                InterventionRecord.student_id == student_id,
            ))
            .order_by(desc(InterventionRecord.intervention_date))
            .limit(1)
        )
        latest_interv = (await db.execute(latest_interv_stmt)).scalar_one_or_none()
        if latest_interv and latest_interv.intervention_date:
            profile.last_intervention_date = latest_interv.intervention_date
    except ImportError:
        pass

    await db.flush()
    return profile


# ============================================================
# 二、筛查快照 CRUD
# ============================================================
async def create_screening(
    db: AsyncSession, school_id: int, operator_id: int, data: dict,
) -> PsyScreeningRecord:
    record = PsyScreeningRecord(
        school_id=school_id,
        operator_id=operator_id,
        **data,
    )
    db.add(record)
    await db.flush()

    # 自动更新心理档案
    profile = await get_or_create_profile(db, school_id, data["student_id"])
    profile.total_screening_count = (profile.total_screening_count or 0) + 1
    profile.last_screening_date = data.get("test_date", get_local_now())
    if _risk_rank(data.get("risk_level", "green")) > _risk_rank(profile.risk_level):
        _prev_level = profile.risk_level
        profile.risk_level = data["risk_level"]
        profile.risk_level_source = "screening"
        profile.risk_level_updated_at = get_local_now()

        # 🔌 事件总线盲发: 心理风险等级变更 (fire-and-forget)
        try:
            from core.event_bus import EventBus
            EventBus().publish("psych.risk_changed", {
                "school_id": school_id,
                "student_id": data["student_id"],
                "previous_level": _prev_level,
                "current_level": data["risk_level"],
                "source": "screening_create",
                "trigger": "new_screening",
            })
        except Exception:
            pass
    if _risk_rank(data.get("risk_level", "green")) > _risk_rank(profile.highest_risk_level):
        profile.highest_risk_level = data["risk_level"]
    await db.flush()

    return record


async def list_screenings(
    db: AsyncSession,
    school_id: int,
    student_id: Optional[int] = None,
    scale_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple:
    conditions = [PsyScreeningRecord.school_id == school_id]
    if student_id:
        conditions.append(PsyScreeningRecord.student_id == student_id)
    if scale_name:
        conditions.append(PsyScreeningRecord.scale_name == scale_name)

    where_clause = and_(*conditions)
    count_stmt = select(func.count(PsyScreeningRecord.id)).where(where_clause)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(PsyScreeningRecord)
        .where(where_clause)
        .order_by(desc(PsyScreeningRecord.test_date))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return result.scalars().all(), total


async def get_student_screenings(
    db: AsyncSession, school_id: int, student_id: int, limit: int = 10,
) -> List[PsyScreeningRecord]:
    stmt = (
        select(PsyScreeningRecord)
        .where(and_(
            PsyScreeningRecord.school_id == school_id,
            PsyScreeningRecord.student_id == student_id,
        ))
        .order_by(desc(PsyScreeningRecord.test_date))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ============================================================
# 三、双轨预警 Nexus — 核心引擎
# ============================================================
async def get_comprehensive_risks(
    db: AsyncSession,
    school_id: int,
    co_trigger_only: bool = False,
    min_priority: str = "WATCH",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
    学业×心理双轨预警合成视图 (四源 union 引擎)

    联表:
      1. student_risk_alerts (data_adapter) — Z-Score 学业预警
      2. risk_warnings (risk_models) — RDI 四维预警
      3. psy_profiles — 心理档案风险等级
      4. psy_screening_records — 最新筛查结果
      5. students + classes — 基本信息
    """
    # ── Step 1: 四源 union 收集所有风险学生 IDs ──
    all_student_ids: set = set()

    # 1a. psy_profiles (心理档案)
    profile_id_stmt = select(PsyProfile.student_id).where(PsyProfile.school_id == school_id)
    for (sid,) in (await db.execute(profile_id_stmt)).all():
        all_student_ids.add(sid)

    # 1b. student_risk_alerts (学业预警)
    try:
        from modules.data_adapter.models import StudentRiskAlert
        alert_ids_stmt = (
            select(StudentRiskAlert.student_id)
            .where(and_(
                StudentRiskAlert.school_id == school_id,
                StudentRiskAlert.status == "active",
            ))
            .distinct()
        )
        for (sid,) in (await db.execute(alert_ids_stmt)).all():
            all_student_ids.add(sid)
    except ImportError:
        pass

    # 1c. risk_warnings (RDI 四维预警)
    try:
        from modules.risk_models.models import RiskWarning
        rdi_ids_stmt = (
            select(RiskWarning.student_id)
            .where(and_(
                RiskWarning.school_id == school_id,
                RiskWarning.status == "active",
            ))
            .distinct()
        )
        for (sid,) in (await db.execute(rdi_ids_stmt)).all():
            all_student_ids.add(sid)
    except ImportError:
        pass

    # 1d. psy_screening_records (心理筛查)
    screening_ids_stmt = (
        select(PsyScreeningRecord.student_id)
        .where(PsyScreeningRecord.school_id == school_id)
        .distinct()
    )
    for (sid,) in (await db.execute(screening_ids_stmt)).all():
        all_student_ids.add(sid)

    if not all_student_ids:
        return {"total": 0, "critical_count": 0, "urgent_count": 0, "watch_count": 0, "items": []}

    # ── Step 1.5: 批量获取心理档案 (部分学生可能没有档案) ──
    profile_stmt = select(PsyProfile).where(
        and_(
            PsyProfile.school_id == school_id,
            PsyProfile.student_id.in_(all_student_ids),
        )
    )
    profile_result = await db.execute(profile_stmt)
    profiles = {p.student_id: p for p in profile_result.scalars().all()}

    # ── Step 2: 批量获取学业预警 (student_risk_alerts) ──
    academic_alerts: Dict[int, list] = {}
    try:
        from modules.data_adapter.models import StudentRiskAlert
        alert_stmt = (
            select(StudentRiskAlert)
            .where(
                and_(
                    StudentRiskAlert.school_id == school_id,
                    StudentRiskAlert.student_id.in_(all_student_ids),
                    StudentRiskAlert.status == "active",
                )
            )
            .order_by(desc(StudentRiskAlert.created_at))
        )
        alert_result = await db.execute(alert_stmt)
        for alert in alert_result.scalars().all():
            academic_alerts.setdefault(alert.student_id, []).append(alert)
    except ImportError:
        pass

    # ── Step 3: 批量获取 RDI 预警 (risk_warnings) ──
    rdi_warnings: Dict[int, Any] = {}
    try:
        from modules.risk_models.models import RiskWarning
        rdi_stmt = (
            select(RiskWarning)
            .where(
                and_(
                    RiskWarning.school_id == school_id,
                    RiskWarning.student_id.in_(all_student_ids),
                    RiskWarning.status == "active",
                )
            )
            .order_by(desc(RiskWarning.warned_at))
        )
        rdi_result = await db.execute(rdi_stmt)
        for rw in rdi_result.scalars().all():
            if rw.student_id not in rdi_warnings:  # 只取最新一条
                rdi_warnings[rw.student_id] = rw
    except ImportError:
        pass

    # ── Step 4: 批量获取学生基本信息 ──
    from core.models import Student, Class
    student_ids = list(all_student_ids)
    student_stmt = (
        select(Student, Class)
        .outerjoin(Class, Student.class_id == Class.id)
        .where(Student.id.in_(student_ids))
    )
    student_result = await db.execute(student_stmt)
    student_info: Dict[int, dict] = {}
    for student, class_ in student_result.all():
        student_info[student.id] = {
            "name": student.name,
            "student_no": student.student_no,
            "class_name": class_.name if class_ else None,
        }

    # ── Step 5: 合成预警 ──
    items = []
    for sid in student_ids:
        profile = profiles.get(sid)  # 可能为 None
        info = student_info.get(sid, {})

        # 学业侧
        alerts = academic_alerts.get(sid, [])
        if alerts:
            latest_alert = alerts[0]
            academic_level = "RED" if latest_alert.risk_level == "red" else "YELLOW"
            trigger_reason = latest_alert.trigger_reason or ""
            # 从 lineage_graph 提取触发学科
            trigger_subjects = []
            if latest_alert.lineage_graph:
                try:
                    graph = latest_alert.lineage_graph
                    if isinstance(graph, dict):
                        for node in graph.get("aggregation_metrics", {}).get("nodes", []):
                            if node.get("z_score", 0) <= -1.0:
                                trigger_subjects.append(node.get("subject", ""))
                except Exception:
                    pass
            academic = {
                "level": academic_level,
                "z_score": None,
                "trigger_subjects": [s for s in trigger_subjects if s],
                "trigger_reason": trigger_reason,
                "source": "student_risk_alerts",
            }
        else:
            academic = {
                "level": "NONE",
                "z_score": None,
                "trigger_subjects": [],
                "trigger_reason": None,
                "source": "student_risk_alerts",
            }

        # 心理侧 — 无档案默认 green
        if profile:
            psy_level = profile.risk_level
            # 从最新筛查补充因子
            psy_factors = []
            latest_screening_scale = None
            latest_screening_date = profile.last_screening_date
            try:
                screening_stmt = (
                    select(PsyScreeningRecord)
                    .where(and_(
                        PsyScreeningRecord.school_id == school_id,
                        PsyScreeningRecord.student_id == sid,
                    ))
                    .order_by(desc(PsyScreeningRecord.test_date))
                    .limit(1)
                )
                screening = (await db.execute(screening_stmt)).scalar_one_or_none()
                if screening:
                    psy_factors = screening.risk_factors or []
                    latest_screening_scale = screening.scale_name
                    latest_screening_date = screening.test_date
            except Exception:
                pass

            psy = {
                "level": _RISK_LABEL.get(psy_level, "GREEN"),
                "factors": psy_factors,
                "last_screening_date": latest_screening_date,
                "scale_name": latest_screening_scale,
                "source": "psy_profiles + psy_screening_records",
            }
        else:
            psy_level = "green"
            psy = {
                "level": "GREEN",
                "factors": [],
                "last_screening_date": None,
                "scale_name": None,
                "source": "psy_profiles (none)",
            }

        # RDI 四维
        rw = rdi_warnings.get(sid)
        if rw:
            rdi = {
                "score": rw.rdi_score,
                "level": rw.risk_level,
                "psych_deviation": rw.psych_deviation,
                "score_deviation": rw.score_deviation,
                "behavior_deviation": rw.behavior_deviation,
                "attendance_deviation": rw.attendance_deviation,
                "is_escalating": rw.is_escalating,
                "source": "risk_warnings",
            }
        else:
            rdi = {
                "score": None, "level": None,
                "psych_deviation": None, "score_deviation": None,
                "behavior_deviation": None, "attendance_deviation": None,
                "is_escalating": False,
                "source": "risk_warnings",
            }

        # 合成优先级
        academic_for_classify = academic["level"]
        psy_for_classify = psy_level
        priority, co_trigger, actions = _classify_priority(academic_for_classify, psy_for_classify)

        # 最低优先级过滤
        priority_rank = {"NORMAL": 0, "WATCH": 1, "URGENT": 2, "CRITICAL": 3}
        if priority_rank.get(priority, 0) < priority_rank.get(min_priority, 0):
            continue

        # co_trigger 过滤
        if co_trigger_only and not co_trigger:
            continue

        items.append({
            "student_id": sid,
            "student_name": info.get("name"),
            "class_name": info.get("class_name"),
            "academic_risk": academic,
            "psy_risk": psy,
            "rdi_risk": rdi,
            "co_trigger": co_trigger,
            "action_priority": priority,
            "recommended_actions": actions,
        })

    # 按优先级排序
    items.sort(key=lambda x: priority_rank.get(x["action_priority"], 0), reverse=True)

    # 分页
    total = len(items)
    start = (page - 1) * page_size
    items_page = items[start:start + page_size]

    return {
        "total": total,
        "critical_count": sum(1 for i in items if i["action_priority"] == "CRITICAL"),
        "urgent_count": sum(1 for i in items if i["action_priority"] == "URGENT"),
        "watch_count": sum(1 for i in items if i["action_priority"] == "WATCH"),
        "items": items_page,
    }

async def get_student_nexus_detail(
    db: AsyncSession, school_id: int, student_id: int,
) -> Optional[dict]:
    """单个学生的双轨详细画像"""
    from core.models import Student, Class, Grade

    # 学生基本信息
    stmt = (
        select(Student, Class, Grade)
        .outerjoin(Class, Student.class_id == Class.id)
        .outerjoin(Grade, Student.grade_id == Grade.id)
        .where(Student.id == student_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        return None
    student, class_, grade = row

    # 心理档案
    profile = await get_profile(db, school_id, student_id)

    # 学业预警历史
    academic_history = []
    try:
        from modules.data_adapter.models import StudentRiskAlert
        alert_stmt = (
            select(StudentRiskAlert)
            .where(and_(
                StudentRiskAlert.school_id == school_id,
                StudentRiskAlert.student_id == student_id,
            ))
            .order_by(desc(StudentRiskAlert.created_at))
            .limit(10)
        )
        for alert in (await db.execute(alert_stmt)).scalars().all():
            academic_history.append({
                "id": alert.id,
                "risk_type": alert.risk_type,
                "risk_level": alert.risk_level,
                "trigger_reason": alert.trigger_reason,
                "status": alert.status,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            })
    except ImportError:
        pass

    # 筛查历史
    screenings = await get_student_screenings(db, school_id, student_id, limit=10)
    screening_history = []
    for s in screenings:
        screening_history.append({
            "id": s.id,
            "scale_name": s.scale_name,
            "total_score": s.total_score,
            "risk_level": s.risk_level,
            "risk_factors": s.risk_factors or [],
            "conclusion": s.conclusion,
            "test_date": s.test_date.isoformat() if s.test_date else None,
        })

    # 咨询摘要
    counseling_summary = None
    try:
        from modules.psych_counseling.models import PsyConsultRecord
        counsel_count_stmt = select(func.count(PsyConsultRecord.id)).where(
            and_(
                PsyConsultRecord.school_id == school_id,
                PsyConsultRecord.student_id == student_id,
            )
        )
        counsel_count = (await db.execute(counsel_count_stmt)).scalar() or 0

        latest_counsel_stmt = (
            select(PsyConsultRecord)
            .where(and_(
                PsyConsultRecord.school_id == school_id,
                PsyConsultRecord.student_id == student_id,
            ))
            .order_by(desc(PsyConsultRecord.created_at))
            .limit(1)
        )
        latest_counsel = (await db.execute(latest_counsel_stmt)).scalar_one_or_none()
        if counsel_count > 0:
            counseling_summary = {
                "total_count": counsel_count,
                "latest_risk_level": latest_counsel.risk_level if latest_counsel else None,
                "latest_category": latest_counsel.consult_category if latest_counsel else None,
                "latest_date": latest_counsel.created_at.isoformat() if latest_counsel and latest_counsel.created_at else None,
                "is_referred": latest_counsel.is_referred if latest_counsel else False,
            }
    except ImportError:
        pass

    # RDI 四维
    rdi_risk = {
        "score": None, "level": None,
        "psych_deviation": None, "score_deviation": None,
        "behavior_deviation": None, "attendance_deviation": None,
        "is_escalating": False, "source": "risk_warnings",
    }
    try:
        from modules.risk_models.models import RiskWarning
        rdi_stmt = (
            select(RiskWarning)
            .where(and_(
                RiskWarning.school_id == school_id,
                RiskWarning.student_id == student_id,
                RiskWarning.status == "active",
            ))
            .order_by(desc(RiskWarning.warned_at))
            .limit(1)
        )
        rw = (await db.execute(rdi_stmt)).scalar_one_or_none()
        if rw:
            rdi_risk = {
                "score": rw.rdi_score,
                "level": rw.risk_level,
                "psych_deviation": rw.psych_deviation,
                "score_deviation": rw.score_deviation,
                "behavior_deviation": rw.behavior_deviation,
                "attendance_deviation": rw.attendance_deviation,
                "is_escalating": rw.is_escalating,
                "source": "risk_warnings",
            }
    except ImportError:
        pass

    # 学业侧
    academic_level = "NONE"
    academic_info = {
        "level": "NONE", "z_score": None, "trigger_subjects": [],
        "trigger_reason": None, "source": "student_risk_alerts",
    }
    try:
        from modules.data_adapter.models import StudentRiskAlert
        alert_stmt = (
            select(StudentRiskAlert)
            .where(and_(
                StudentRiskAlert.school_id == school_id,
                StudentRiskAlert.student_id == student_id,
                StudentRiskAlert.status == "active",
            ))
            .order_by(desc(StudentRiskAlert.created_at))
            .limit(1)
        )
        alert = (await db.execute(alert_stmt)).scalar_one_or_none()
        if alert:
            academic_level = "RED" if alert.risk_level == "red" else "YELLOW"
            academic_info = {
                "level": academic_level,
                "z_score": None,
                "trigger_subjects": [],
                "trigger_reason": alert.trigger_reason,
                "source": "student_risk_alerts",
            }
    except ImportError:
        pass

    # 心理侧
    psy_level = (profile.risk_level if profile else "green")
    psy_info = {
        "level": _RISK_LABEL.get(psy_level, "GREEN"),
        "factors": [],
        "last_screening_date": profile.last_screening_date if profile else None,
        "scale_name": screening_history[0]["scale_name"] if screening_history else None,
        "source": "psy_profiles + psy_screening_records",
    }

    # 合成
    priority, co_trigger, actions = _classify_priority(academic_level, psy_level)

    return {
        "student_id": student_id,
        "student_name": student.name,
        "student_no": student.student_no,
        "class_name": class_.name if class_ else None,
        "grade_name": grade.name if grade else None,
        "academic_risk": academic_info,
        "academic_history": academic_history,
        "psy_risk": psy_info,
        "psy_profile": {
            "risk_level": profile.risk_level if profile else "green",
            "tags": profile.tags if profile else [],
            "guardian_contact_status": profile.guardian_contact_status if profile else "normal",
            "total_counseling_count": profile.total_counseling_count if profile else 0,
            "total_screening_count": profile.total_screening_count if profile else 0,
            "is_referred": profile.is_referred if profile else False,
            "notes": profile.notes if profile else None,
        } if profile else None,
        "psy_screening_history": screening_history,
        "psy_counseling_summary": counseling_summary,
        "rdi_risk": rdi_risk,
        "co_trigger": co_trigger,
        "action_priority": priority,
        "recommended_actions": actions,
    }


# ============================================================
# 四、仪表盘
# ============================================================
async def get_dashboard_stats(db: AsyncSession, school_id: int) -> dict:
    """心理档案仪表盘聚合统计"""
    # 档案总数
    total_profiles = (await db.execute(
        select(func.count(PsyProfile.id)).where(PsyProfile.school_id == school_id)
    )).scalar() or 0

    # 风险分布
    risk_dist = {"green": 0, "yellow": 0, "orange": 0, "red": 0}
    dist_stmt = (
        select(PsyProfile.risk_level, func.count(PsyProfile.id))
        .where(PsyProfile.school_id == school_id)
        .group_by(PsyProfile.risk_level)
    )
    for level, cnt in (await db.execute(dist_stmt)).all():
        if level and level in risk_dist:
            risk_dist[level] = cnt

    # 筛查总数
    total_screenings = (await db.execute(
        select(func.count(PsyScreeningRecord.id)).where(PsyScreeningRecord.school_id == school_id)
    )).scalar() or 0

    # 咨询总数
    total_counselings = 0
    try:
        from modules.psych_counseling.models import PsyConsultRecord
        total_counselings = (await db.execute(
            select(func.count(PsyConsultRecord.id)).where(PsyConsultRecord.school_id == school_id)
        )).scalar() or 0
    except ImportError:
        pass

    # 转介总数
    total_referrals = (await db.execute(
        select(func.count(PsyProfile.id)).where(
            and_(PsyProfile.school_id == school_id, PsyProfile.is_referred == True)
        )
    )).scalar() or 0

    # 双预警学生数
    nexus = await get_comprehensive_risks(db, school_id, co_trigger_only=True, page_size=9999)
    co_trigger_count = nexus["total"]

    # 最近筛查 (5条)
    recent_stmt = (
        select(PsyScreeningRecord)
        .where(PsyScreeningRecord.school_id == school_id)
        .order_by(desc(PsyScreeningRecord.test_date))
        .limit(5)
    )
    recent_screenings = []
    for s in (await db.execute(recent_stmt)).scalars().all():
        recent_screenings.append({
            "id": s.id,
            "student_id": s.student_id,
            "scale_name": s.scale_name,
            "risk_level": s.risk_level,
            "test_date": s.test_date.isoformat() if s.test_date else None,
        })

    # 最高风险学生 (5条)
    top_stmt = (
        select(PsyProfile)
        .where(and_(
            PsyProfile.school_id == school_id,
            PsyProfile.risk_level.in_(["orange", "red"]),
        ))
        .order_by(desc(_risk_rank_col(PsyProfile.risk_level)), desc(PsyProfile.updated_at))
        .limit(5)
    )
    top_risk_students = []
    for p in (await db.execute(top_stmt)).scalars().all():
        top_risk_students.append({
            "student_id": p.student_id,
            "risk_level": p.risk_level,
            "tags": p.tags or [],
            "total_counseling_count": p.total_counseling_count or 0,
            "last_screening_date": p.last_screening_date.isoformat() if p.last_screening_date else None,
        })

    # ── 学业侧统计 (四源union新增) ──
    total_academic_alerts = 0
    academic_red_count = 0
    academic_yellow_count = 0
    total_rdi_warnings = 0
    try:
        from modules.data_adapter.models import StudentRiskAlert
        alert_dist = (
            select(StudentRiskAlert.risk_level, func.count(StudentRiskAlert.id))
            .where(and_(
                StudentRiskAlert.school_id == school_id,
                StudentRiskAlert.status == "active",
            ))
            .group_by(StudentRiskAlert.risk_level)
        )
        for level, cnt in (await db.execute(alert_dist)).all():
            total_academic_alerts += cnt
            if level == "red":
                academic_red_count = cnt
            elif level == "yellow":
                academic_yellow_count = cnt
    except ImportError:
        pass

    try:
        from modules.risk_models.models import RiskWarning
        total_rdi_warnings = (await db.execute(
            select(func.count(RiskWarning.id)).where(
                and_(RiskWarning.school_id == school_id, RiskWarning.status == "active")
            )
        )).scalar() or 0
    except ImportError:
        pass

    return {
        "total_profiles": total_profiles,
        "risk_distribution": risk_dist,
        "co_trigger_count": co_trigger_count,
        "total_screenings": total_screenings,
        "total_counselings": total_counselings,
        "total_referrals": total_referrals,
        "recent_screenings": recent_screenings,
        "top_risk_students": top_risk_students,
        "total_academic_alerts": total_academic_alerts,
        "academic_red_count": academic_red_count,
        "academic_yellow_count": academic_yellow_count,
        "total_rdi_warnings": total_rdi_warnings,
    }


# ============================================================
# 五、标签建议
# ============================================================
async def get_tag_suggestions(db: AsyncSession, school_id: int, limit: int = 30) -> List[dict]:
    """从现有档案中提取高频标签建议"""
    from sqlalchemy import JSON
    # MySQL JSON_LENGTH + JSON_TABLE 过于复杂, 取所有 tags 在内存中统计
    stmt = select(PsyProfile.tags).where(
        and_(PsyProfile.school_id == school_id, PsyProfile.tags.isnot(None))
    )
    result = await db.execute(stmt)
    tag_count: Dict[str, int] = {}
    for row in result.all():
        tags = row[0]
        if isinstance(tags, list):
            for t in tags:
                tag_count[t] = tag_count.get(t, 0) + 1

    sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"tag": t, "count": c} for t, c in sorted_tags]
