"""
modules/behavior/services.py — 违纪行为业务逻辑层

核心功能:
  - 违纪记录 CRUD
  - 累计扣分自动升级 (check_escalation)
  - 违纪统计 (按类型/分类/班级/月份)
  - 申诉处理
"""

import logging
from datetime import date, datetime, timedelta, timezone

# 🔌 跨模块 Hook: behavior → discipline 处分熔焊
# 放在函数内部延迟导入避免循环依赖，此处仅声明类型引用
from typing import TYPE_CHECKING

from core.models import Class, Student
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import DisciplineAppeal, DisciplineRecord

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 违纪类型映射
TYPE_MAP = {"warning": "警告", "minor": "轻微", "major": "重大", "serious": "严重"}

# 累计扣分升级阈值 (按扣分从高到低匹配)
ESCALATION_THRESHOLDS = [
    (50, "serious"),
    (30, "major"),
    (20, "minor"),
    (10, "warning"),
]

# 违纪扣分值映射
DEFAULT_POINTS = {"warning": 1, "minor": 3, "major": 10, "serious": 20}


def get_local_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


class BehaviorService:
    """违纪行为管理服务"""

    # ═══ CRUD ═══

    @staticmethod
    async def create_record(
        db: AsyncSession,
        school_id: int,
        data: dict,
        created_by: int,
        creator_role: str = "class_teacher",
    ) -> DisciplineRecord:
        """创建违纪记录 — 自动填入 student/class/grade 信息并设置默认扣分"""
        # 查找学生信息
        student = await db.scalar(
            select(Student).where(
                Student.id == data["student_id"],
                Student.school_id == school_id,
            )
        )
        if not student:
            raise ValueError(f"学生不存在: id={data['student_id']}")

        # 自动计算扣分（如未指定）
        points = data.get("points", 0)
        if points <= 0 and data.get("type") in DEFAULT_POINTS:
            points = DEFAULT_POINTS[data["type"]]

        record = DisciplineRecord(
            school_id=school_id,
            student_id=student.id,
            class_id=student.class_id,
            grade_id=student.grade_id,
            type=data["type"],
            category=data.get("category"),
            description=data["description"],
            action_taken=data.get("action_taken"),
            points=points,
            status="active",
            verify_status="DRAFT",
            incident_date=data.get("incident_date") or date.today(),
            created_by=created_by,
        )
        db.add(record)
        await db.flush()

        # 🔌 处分滑窗 Hook: 严重违纪落库 → 自动检测并孵化 DRAFT_PENDING 草稿
        # 放在 _check_escalation 之前执行，确保处分草稿先生成
        if data.get("type") == "serious":
            try:
                # 延迟导入避免循环依赖（behavior ↔ discipline 双向 import）
                from modules.discipline.services import DisciplineService

                trigger = await DisciplineService.detect_escalation_trigger(db, student.id)
                if trigger["triggered"]:
                    await DisciplineService.create_escalation_draft(
                        db,
                        student.id,
                        trigger["evidence"],
                        db_session_for_commit=False,  # 不独立 commit，由外层统一提交
                    )
                    logger.warning(
                        f"🔺 处分滑窗自动触发: student_id={student.id} "
                        f"serious_count={trigger['serious_count']}"
                    )
            except Exception as e:
                # 异常隔离：Hook 失败不影响违纪记录正常入库
                logger.error(
                    f"处分滑窗Hook异常(已隔离): student_id={student.id} error={e}", exc_info=True
                )

        # 检查累计升级
        await BehaviorService._check_escalation(db, student, created_by)

        await db.commit()

        # 🔌 事件总线盲发: 违纪处分 → growth 时光轴 (fire-and-forget)
        try:
            from core.event_bus import EventBus

            EventBus().publish(
                "behavior.disciplined",
                {
                    "school_id": school_id,
                    "student_id": student.id,
                    "category": data.get("category"),
                    "level": data.get("type"),
                    "deduction": points,
                    "title": f"{TYPE_MAP.get(data.get('type'), '行为记录')}: {data.get('description', '')[:50]}",
                },
            )
        except Exception:
            pass  # 事件总线不可用时静默降级

        # ═══ PolicyEngine Hook-2: 违纪→评价决策闭环 ═══
        # 铁律1: 违纪记录已commit，绝对优先
        # 铁律2: try/except隔离，Hook失败不阻塞主业务
        # 铁律3: 审批工单+ScoreLog在同一flush/commit块中
        # 铁律4: 多租户审批链优先 → PolicyEngine 降级
        try:
            from modules.policy_engine import get_engine

            engine = get_engine()
            if engine:
                # 1. 事件分类 → severity / dimension / penalty
                #    优先使用 data["type"] (与 policy.yaml 事件类型一致), 兜底使用 category 映射
                _CATEGORY_MAP = {
                    "打架": "fighting",
                    "吸烟": "smoking",
                    "作弊": "cheating",
                    "迟到": "lateness",
                    "缺勤": "absence",
                    "表扬": "good_job",
                }
                behavior_type = data.get("type") or _CATEGORY_MAP.get(
                    data.get("category", ""), "other"
                )
                classification = engine.classify(behavior_type)

                # 2. 审批链解析: L1 多租户 → L2 PolicyEngine
                chain_config = None
                approval_mode = "parallel_or"

                # L1: 尝试多租户审批链
                biz_type_map = {
                    "minor": "behavior_minor",
                    "major": "behavior_major",
                    "critical": "behavior_critical",
                }
                biz_type = biz_type_map.get(classification.severity, "behavior_minor")
                try:
                    from modules.approval.services import resolve_chain_async

                    chain_config = await resolve_chain_async(db, school_id, biz_type)
                    if chain_config:
                        approval_mode = chain_config.get("approval_mode", "serial_and")
                        logger.info(
                            "[PolicyEngine Hook-2] 使用多租户审批链 | school=%s biz=%s chain_id=%s",
                            school_id,
                            biz_type,
                            chain_config.get("chain_id"),
                        )
                except Exception as chain_err:
                    logger.warning(
                        "[PolicyEngine Hook-2] 多租户审批链查询失败(降级PolicyEngine): %s",
                        chain_err,
                    )

                # L2: Fallback — PolicyEngine
                if not chain_config:
                    chain = engine.route(behavior_type, creator_role)
                    chain_config = chain.model_dump()
                    approval_mode = chain.mode

                # 3. 写审批工单 (approval_requests)
                from modules.evaluation.models import ApprovalRequest

                approval_req = ApprovalRequest(
                    school_id=school_id,
                    student_id=student.id,
                    event_type=behavior_type,
                    source_type="behavior",
                    source_id=record.id,
                    severity=classification.severity,
                    approval_mode=approval_mode,
                    chain_config=chain_config,
                    current_status="pending",
                    current_step=0,
                )
                db.add(approval_req)

                # 4. 调 EvaluationService.apply_deduction() — 同事务写 ScoreLog
                #    discipline_type 传 severity 以匹配 deduction_map keys (warning/minor/major/serious)
                #    penalty_override 传 PolicyEngine 精确扣分 (base_penalty)
                from modules.evaluation.services import EvaluationService

                log = await EvaluationService.apply_deduction(
                    db=db,
                    student_id=student.id,
                    class_id=student.class_id,
                    grade_id=student.grade_id,
                    school_id=school_id,
                    discipline_type=classification.severity,
                    discipline_id=record.id,
                    created_by=created_by,
                    source_type="behavior",
                    penalty_override=classification.base_penalty,
                    policy_tag="repairable",
                )

                await db.flush()
                await db.commit()
                logger.info(
                    f"[PolicyEngine Hook-2] 违纪→评价闭环成功: "
                    f"student={student.id} type={behavior_type} "
                    f"severity={classification.severity} mode={approval_mode} "
                    f"chain_source={'tenant' if chain_config.get('chain_id') else 'policy_engine'}"
                )
        except Exception as e:
            # 铁律2: 异常隔离 — rollback Hook写入，违纪记录已commit不受影响
            await db.rollback()
            logger.error(
                f"[PolicyEngine Hook-2] 异常(已隔离，违纪记录已保存): "
                f"student_id={student.id} error={e}",
                exc_info=True,
            )

        # 重新查询以加载关系（async 不能用 refresh + lazy load）
        record = await db.scalar(
            select(DisciplineRecord)
            .options(
                selectinload(DisciplineRecord.student).selectinload(Student.class_),
                selectinload(DisciplineRecord.creator),
            )
            .where(DisciplineRecord.id == record.id)
        )
        return record

    @staticmethod
    async def get_record(db: AsyncSession, record_id: int) -> DisciplineRecord | None:
        return await db.scalar(
            select(DisciplineRecord)
            .options(
                selectinload(DisciplineRecord.student).selectinload(Student.class_),
                selectinload(DisciplineRecord.creator),
            )
            .where(DisciplineRecord.id == record_id)
        )

    @staticmethod
    async def list_records(
        db: AsyncSession,
        school_id: int,
        class_id: int | None = None,
        grade_id: int | None = None,
        student_id: int | None = None,
        type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DisciplineRecord], int]:
        """分页查询违纪记录，返回 (records, total)"""
        conditions = [DisciplineRecord.school_id == school_id]
        if class_id:
            conditions.append(DisciplineRecord.class_id == class_id)
        if grade_id:
            conditions.append(DisciplineRecord.grade_id == grade_id)
        if student_id:
            conditions.append(DisciplineRecord.student_id == student_id)
        if type:
            conditions.append(DisciplineRecord.type == type)
        if status:
            conditions.append(DisciplineRecord.status == status)
        if start_date:
            conditions.append(DisciplineRecord.incident_date >= start_date)
        if end_date:
            conditions.append(DisciplineRecord.incident_date <= end_date)

        cnt = await db.scalar(select(func.count()).select_from(DisciplineRecord).where(*conditions))
        total = int(cnt or 0)

        stmt = (
            select(DisciplineRecord)
            .options(selectinload(DisciplineRecord.student).selectinload(Student.class_))
            .options(selectinload(DisciplineRecord.creator))
            .where(*conditions)
            .order_by(DisciplineRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def update_record(
        db: AsyncSession, record_id: int, data: dict
    ) -> DisciplineRecord | None:
        record = await BehaviorService.get_record(db, record_id)
        if not record:
            return None
        for key in ("type", "category", "description", "action_taken", "points", "incident_date"):
            if key in data and data[key] is not None:
                setattr(record, key, data[key])
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def delete_record(db: AsyncSession, record_id: int) -> bool:
        record = await BehaviorService.get_record(db, record_id)
        if not record:
            return False
        await db.delete(record)
        await db.commit()
        return True

    @staticmethod
    async def resolve_record(db: AsyncSession, record_id: int) -> DisciplineRecord | None:
        record = await BehaviorService.get_record(db, record_id)
        if not record or record.status != "active":
            return None
        record.status = "resolved"
        record.resolved_at = get_local_now()
        await db.commit()
        await db.refresh(record)
        return record

    # ═══ 累计升级 ═══

    @staticmethod
    async def _check_escalation(db: AsyncSession, student: Student, triggered_by: int):
        """累计扣分自动升级：学生总扣分超过阈值自动生成升级违纪记录"""
        total_points_result = await db.scalar(
            select(func.sum(DisciplineRecord.points)).where(
                DisciplineRecord.student_id == student.id,
                DisciplineRecord.status == "active",
            )
        )
        total_points = int(total_points_result or 0)

        for threshold, level in ESCALATION_THRESHOLDS:
            if total_points >= threshold:
                # 检查是否已经生成了此级别的升级记录（幂等）
                existing = await db.scalar(
                    select(func.count())
                    .select_from(DisciplineRecord)
                    .where(
                        DisciplineRecord.student_id == student.id,
                        DisciplineRecord.type == level,
                        DisciplineRecord.category == "系统自动",
                        DisciplineRecord.status == "active",
                    )
                )
                if existing and existing > 0:
                    continue  # 已存在，跳过

                escalate = DisciplineRecord(
                    school_id=student.school_id,
                    student_id=student.id,
                    class_id=student.class_id,
                    grade_id=student.grade_id,
                    type=level,
                    category="系统自动",
                    description=f"[累计扣分自动升级] 累计扣分已达 {total_points} 分，自动升级为「{TYPE_MAP[level]}」级违纪",
                    points=0,
                    status="active",
                    verify_status="DRAFT",
                    incident_date=date.today(),
                    created_by=triggered_by,
                )
                db.add(escalate)
                logger.warning(
                    f"学生 [{student.name}] 累计扣分 {total_points}，自动升级为 {TYPE_MAP[level]}"
                )
                break  # 只触发最高级别

    @staticmethod
    async def get_escalation_risk(db: AsyncSession, student_id: int) -> dict:
        """获取学生当前的升级风险状态"""
        result = await db.execute(
            select(
                func.sum(DisciplineRecord.points).label("total_points"),
                func.count(DisciplineRecord.id).label("record_count"),
            ).where(
                DisciplineRecord.student_id == student_id,
                DisciplineRecord.status == "active",
            )
        )
        row = result.one()
        total_points = int(row.total_points or 0)
        record_count = int(row.record_count or 0)

        next_threshold = None
        for threshold, _ in ESCALATION_THRESHOLDS:
            if total_points < threshold:
                next_threshold = threshold
            else:
                break

        return {
            "total_points": total_points,
            "record_count": record_count,
            "next_threshold": next_threshold,
            "escalation_thresholds": ESCALATION_THRESHOLDS,
        }

    # ═══ 统计 ═══

    @staticmethod
    async def get_stats(
        db: AsyncSession,
        school_id: int,
        grade_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        """违纪统计概览"""
        conditions = [DisciplineRecord.school_id == school_id]
        if grade_id:
            conditions.append(DisciplineRecord.grade_id == grade_id)
        if start_date:
            conditions.append(DisciplineRecord.incident_date >= start_date)
        if end_date:
            conditions.append(DisciplineRecord.incident_date <= end_date)

        # 总数
        total = await db.scalar(
            select(func.count()).select_from(DisciplineRecord).where(*conditions)
        )
        total = int(total or 0)

        # 按类型分组
        type_rows = await db.execute(
            select(
                DisciplineRecord.type,
                func.count(DisciplineRecord.id),
            )
            .where(*conditions)
            .group_by(DisciplineRecord.type)
        )
        by_type = {row[0]: row[1] for row in type_rows.all()}

        # 按分类分组
        cat_rows = await db.execute(
            select(
                DisciplineRecord.category,
                func.count(DisciplineRecord.id),
            )
            .where(*conditions)
            .group_by(DisciplineRecord.category)
        )
        by_category = {row[0]: row[1] for row in cat_rows.all()}

        # 按班级分组
        class_rows = await db.execute(
            select(
                DisciplineRecord.class_id,
                Class.name,
                func.count(DisciplineRecord.id),
            )
            .join(Class, DisciplineRecord.class_id == Class.id)
            .where(*conditions)
            .group_by(DisciplineRecord.class_id, Class.name)
        )
        by_class = {}
        for row in class_rows.all():
            by_class[row[1]] = row[2]

        # 总扣分
        total_points = await db.scalar(select(func.sum(DisciplineRecord.points)).where(*conditions))
        total_points = int(total_points or 0)

        # 月度趋势（最近 6 个月）
        six_months_ago = date.today().replace(day=1) - timedelta(days=180)
        trend_rows = await db.execute(
            select(
                func.year(DisciplineRecord.incident_date).label("year"),
                func.month(DisciplineRecord.incident_date).label("month"),
                func.count(DisciplineRecord.id),
            )
            .where(
                DisciplineRecord.school_id == school_id,
                DisciplineRecord.incident_date >= six_months_ago,
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )
        monthly_trend = [
            {"year": r.year, "month": f"{r.month:02d}", "count": r[2]} for r in trend_rows.all()
        ]

        return {
            "total": total,
            "by_type": by_type,
            "by_category": by_category,
            "by_class": by_class,
            "total_points": total_points,
            "monthly_trend": monthly_trend,
        }

    # ═══ 申诉 ═══

    @staticmethod
    async def create_appeal(
        db: AsyncSession,
        school_id: int,
        data: dict,
        applicant_id: int,
        student_id: int,
        class_id: int,
        grade_id: int,
    ) -> DisciplineAppeal:
        """家长提交申诉"""
        record = await BehaviorService.get_record(db, data["discipline_id"])
        if not record or record.student_id != student_id:
            raise ValueError("违纪记录不存在或不属于该学生")

        appeal = DisciplineAppeal(
            school_id=school_id,
            discipline_id=data["discipline_id"],
            student_id=student_id,
            class_id=class_id,
            grade_id=grade_id,
            applicant_id=applicant_id,
            reason=data["reason"],
            status="pending",
        )
        db.add(appeal)
        record.status = "appealed"
        await db.commit()
        await db.refresh(appeal)
        return appeal

    @staticmethod
    async def review_appeal(
        db: AsyncSession, appeal_id: int, status: str, comment: str, reviewer_id: int
    ) -> DisciplineAppeal | None:
        """班主任/年级组长/德育处审核申诉"""
        appeal = await db.scalar(select(DisciplineAppeal).where(DisciplineAppeal.id == appeal_id))
        if not appeal or appeal.status != "pending":
            return None

        appeal.status = status
        appeal.review_comment = comment
        appeal.reviewed_by = reviewer_id
        appeal.reviewed_at = get_local_now()

        # 恢复违纪状态
        record = await BehaviorService.get_record(db, appeal.discipline_id)
        if record:
            record.status = "resolved" if status == "approved" else "active"

        await db.commit()
        await db.refresh(appeal)
        return appeal

    @staticmethod
    async def list_appeals(
        db: AsyncSession,
        school_id: int,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DisciplineAppeal], int]:
        conditions = [DisciplineAppeal.school_id == school_id]
        if status:
            conditions.append(DisciplineAppeal.status == status)

        cnt = await db.scalar(select(func.count()).select_from(DisciplineAppeal).where(*conditions))
        total = int(cnt or 0)

        stmt = (
            select(DisciplineAppeal)
            .where(*conditions)
            .order_by(DisciplineAppeal.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all()), total
