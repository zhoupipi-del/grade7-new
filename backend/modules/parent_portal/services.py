"""
modules/parent_portal/services.py — 家长门户只读聚合网关 + 反馈/申诉独立写操作

架构定位:
  - ParentPortalService: 跨模块聚合网关 — 直连已有模块 Service 内部方法
  - FeedbackService: 反馈 CRUD（家长提交 + 班主任处理）
  - AppealProxyService: 申诉代理追踪（Facade 路由到 discipline/behavior）

越权铁闸:
  - 所有 Service 方法入口必须校验 parent_id → bound_student_id 绑定关系
  - 校验函数 verify_parent_binding() 是绝对红线，不可绕过
"""

import logging
import time
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ParentFeedback, ParentAppealsProxy,
    FeedbackType, FeedbackStatus, AppealTargetModule,
    FEEDBACK_TYPE_LABELS, FEEDBACK_STATUS_LABELS,
)
from .schemas import (
    FeedbackItem, FeedbackListResponse, ChildOverview, ParentDashboard,
    AppealProxyResult, TimelineEvent, FeedbackTypeEnum, FeedbackStatusEnum,
    AppealTargetModuleEnum, fill_labels,
)

from core.models import User, Student, Class, Grade, UserRole

logger = logging.getLogger("parent_portal")


# ═══════════════════════════════════════════════════════════════
# 越权铁闸 — parent_id → bound_student_id 绑定校验
# ═══════════════════════════════════════════════════════════════

async def verify_parent_binding(
    db: AsyncSession,
    parent_user: User,
    requested_student_id: int,
) -> Student:
    """
    越权铁闸 — 校验当前家长与请求学生 ID 的绑定关系。

    规则:
      1. parent_user 必须是 PARENT 角色
      2. parent_user.bound_student_id 必须等于 requested_student_id
      3. 两者不一致 → 403（横向穿透是绝对红线）

    返回: Student ORM 对象（校验通过后可用于后续聚合查询）
    """
    user_role = parent_user.role
    if isinstance(user_role, str):
        user_role = UserRole(user_role)

    if user_role != UserRole.PARENT:
        raise ValueError(f"越权铁闸: 用户角色 {user_role} 不是家长，无法通过绑定校验")

    bound_id = parent_user.bound_student_id
    if bound_id is None:
        raise ValueError("越权铁闸: 家长账号未绑定任何学生（bound_student_id=NULL）")

    if bound_id != requested_student_id:
        raise ValueError(
            f"越权铁闸: 家长绑定学生 {bound_id} ≠ 请求学生 {requested_student_id}，横向穿透拦截"
        )

    # 查询学生对象（后续聚合查询需要）
    result = await db.execute(
        select(Student).where(Student.id == requested_student_id, Student.is_active == True)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise ValueError(f"学生 {requested_student_id} 不存在或已离校")

    return student


# ═══════════════════════════════════════════════════════════════
# ParentPortalService — 跨模块聚合网关
# ═══════════════════════════════════════════════════════════════

class ParentPortalService:
    """
    只读聚合网关 — 仪表盘和概览数据直连已有模块 Service 内部方法。

    不重复存储任何聚合数据，只在请求时实时聚合。
    性能基准: 概览 < 0.5s / 仪表盘 < 0.5s
    """

    @staticmethod
    async def get_child_overview(
        db: AsyncSession,
        student: Student,
        school_id: int,
    ) -> ChildOverview:
        """
        孩子概览 — 五维分数 + 考勤 + 违纪 + 时间轴 + 风险等级

        聚合源:
          1. StudentScore (evaluation) — 五维分数
          2. Attendance stats (attendance) — 考勤正常/异常计数
          3. BehaviorRecord count (behavior) — 违纪记录数
          4. PositiveScore total (evaluation) — 正面加分总计
          5. Timeline events (growth) — 最近时间轴
          6. RiskAssessment (risk_models) — 风险等级
        """
        start = time.time()

        # ── 基本信息 ──
        student_id = student.id

        # 查班级/年级名称
        cls_result = await db.execute(select(Class).where(Class.id == student.class_id))
        cls = cls_result.scalar_one_or_none()
        class_name = cls.name if cls else "未知班级"

        grade_result = await db.execute(select(Grade).where(Grade.id == student.grade_id))
        grade_obj = grade_result.scalar_one_or_none()
        grade_name = grade_obj.name if grade_obj else "未知年级"

        overview = ChildOverview(
            student_id=student_id,
            student_name=student.name,
            student_no=student.student_no,
            class_name=class_name,
            grade_name=grade_name,
        )

        # ── 评价快照（五维分数）— 直连 evaluation.StudentScore ──
        try:
            from modules.evaluation.models import StudentScore
            score_result = await db.execute(
                select(StudentScore).where(
                    StudentScore.student_id == student_id,
                    StudentScore.school_id == school_id,
                ).order_by(desc(StudentScore.created_at)).limit(1)
            )
            score = score_result.scalar_one_or_none()
            if score:
                overview.total_score = score.total_score
                overview.moral_score = score.moral_score
                overview.academic_score = score.academic_score
                overview.health_score = score.health_score
                overview.art_score = score.art_score
                overview.social_score = score.social_score
        except Exception as e:
            logger.warning(f"评价数据聚合失败 (student={student_id}): {e}")

        # ── 考勤统计 — 直连 attendance ──
        try:
            from modules.attendance.models import AttendanceRecord
            normal_result = await db.execute(
                select(func.count()).select_from(AttendanceRecord).where(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.status == "normal",
                )
            )
            overview.attendance_normal_count = normal_result.scalar() or 0

            abnormal_result = await db.execute(
                select(func.count()).select_from(AttendanceRecord).where(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.status != "normal",
                )
            )
            overview.attendance_abnormal_count = abnormal_result.scalar() or 0
        except Exception as e:
            logger.warning(f"考勤数据聚合失败 (student={student_id}): {e}")

        # ── 违纪记录数 — 直连 behavior ──
        try:
            from modules.behavior.models import BehaviorRecord
            behavior_result = await db.execute(
                select(func.count()).select_from(BehaviorRecord).where(
                    BehaviorRecord.student_id == student_id,
                    BehaviorRecord.school_id == school_id,
                )
            )
            overview.behavior_record_count = behavior_result.scalar() or 0
        except Exception as e:
            logger.warning(f"违纪数据聚合失败 (student={student_id}): {e}")

        # ── 正面加分总计 — 直连 evaluation.EvaluationScore ──
        try:
            from modules.evaluation.models import EvaluationScore
            positive_result = await db.execute(
                select(func.coalesce(func.sum(EvaluationScore.score), 0)).select_from(
                    EvaluationScore
                ).where(
                    EvaluationScore.student_id == student_id,
                    EvaluationScore.school_id == school_id,
                    EvaluationScore.score > 0,
                )
            )
            overview.positive_score_total = int(positive_result.scalar() or 0)
        except Exception as e:
            logger.warning(f"正面加分聚合失败 (student={student_id}): {e}")

        # ── 风险等级 — 直连 risk_models ──
        try:
            from modules.risk_models.models import RiskAssessment
            risk_result = await db.execute(
                select(RiskAssessment).where(
                    RiskAssessment.student_id == student_id,
                    RiskAssessment.school_id == school_id,
                ).order_by(desc(RiskAssessment.assessed_at)).limit(1)
            )
            risk = risk_result.scalar_one_or_none()
            if risk:
                overview.risk_level = risk.risk_level
                overview.risk_label = risk.risk_label
        except Exception as e:
            logger.warning(f"风险数据聚合失败 (student={student_id}): {e}")

        # ── 时间轴 — 合成最近 5 条事件 ──
        overview.recent_timeline = await ParentPortalService._build_timeline(
            db, student_id, school_id, limit=5
        )

        elapsed = time.time() - start
        logger.info(f"孩子概览聚合完成 (student={student_id}, elapsed={elapsed:.3f}s)")
        return overview

    @staticmethod
    async def _build_timeline(
        db: AsyncSession,
        student_id: int,
        school_id: int,
        limit: int = 5,
    ) -> List[TimelineEvent]:
        """
        合成时间轴 — 从评价、违纪、考勤、风险事件中提取最近 N 条。

        每种数据源最多取 limit 条，合并后按 occurred_at 降序排列，返回 top limit。
        """
        events: List[TimelineEvent] = []

        # ── 评价事件 ──
        try:
            from modules.evaluation.models import ScoreLog
            log_result = await db.execute(
                select(ScoreLog).where(
                    ScoreLog.student_id == student_id,
                    ScoreLog.school_id == school_id,
                ).order_by(desc(ScoreLog.created_at)).limit(limit)
            )
            for log in log_result.scalars().all():
                events.append(TimelineEvent(
                    event_id=f"score_log_{log.id}",
                    event_type="score_log",
                    occurred_at=log.created_at.isoformat() if log.created_at else "",
                    title=f"{log.dimension or '综合'} {log.change_type or '变更'} {log.change_value or ''}",
                    description=log.reason or None,
                    severity="success" if (log.change_value or 0) > 0 else "warning",
                ))
        except Exception as e:
            logger.warning(f"评价时间轴聚合失败: {e}")

        # ── 违纪事件 ──
        try:
            from modules.behavior.models import BehaviorRecord
            behavior_result = await db.execute(
                select(BehaviorRecord).where(
                    BehaviorRecord.student_id == student_id,
                    BehaviorRecord.school_id == school_id,
                ).order_by(desc(BehaviorRecord.recorded_at)).limit(limit)
            )
            for rec in behavior_result.scalars().all():
                events.append(TimelineEvent(
                    event_id=f"behavior_{rec.id}",
                    event_type="behavior",
                    occurred_at=rec.recorded_at.isoformat() if rec.recorded_at else "",
                    title=f"行为记录: {rec.description or rec.type or '违纪'}",
                    description=rec.description or None,
                    severity="warning",
                ))
        except Exception as e:
            logger.warning(f"违纪时间轴聚合失败: {e}")

        # ── 考勤异常事件 ──
        try:
            from modules.attendance.models import AttendanceRecord
            attendance_result = await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.status != "normal",
                ).order_by(desc(AttendanceRecord.recorded_at)).limit(limit)
            )
            for att in attendance_result.scalars().all():
                events.append(TimelineEvent(
                    event_id=f"attendance_{att.id}",
                    event_type="attendance",
                    occurred_at=att.recorded_at.isoformat() if att.recorded_at else "",
                    title=f"考勤异常: {att.status or '缺勤'}",
                    description=att.remark or None,
                    severity="danger",
                ))
        except Exception as e:
            logger.warning(f"考勤时间轴聚合失败: {e}")

        # 按时间降序排列，取 top limit
        events.sort(key=lambda e: e.occurred_at, reverse=True)
        return events[:limit]

    @staticmethod
    async def get_dashboard(
        db: AsyncSession,
        parent_user: User,
    ) -> ParentDashboard:
        """
        家长仪表盘 — 聚合孩子概览 + 未读通知 + 待处理反馈 + 最近反馈
        """
        start = time.time()

        # 越权铁闸: 校验绑定关系
        student = await verify_parent_binding(
            db, parent_user, parent_user.bound_student_id
        )

        # 孩子概览
        child_overview = await ParentPortalService.get_child_overview(
            db, student, parent_user.school_id
        )

        # 待处理反馈数
        pending_result = await db.execute(
            select(func.count()).select_from(ParentFeedback).where(
                ParentFeedback.parent_id == parent_user.id,
                ParentFeedback.school_id == parent_user.school_id,
                ParentFeedback.status == FeedbackStatus.PENDING.value,
            )
        )
        pending_feedbacks = pending_result.scalar() or 0

        # 最近反馈
        recent_result = await db.execute(
            select(ParentFeedback).where(
                ParentFeedback.parent_id == parent_user.id,
                ParentFeedback.school_id == parent_user.school_id,
            ).order_by(desc(ParentFeedback.created_at)).limit(3)
        )
        recent_feedbacks = [
            fill_labels(FeedbackItem.model_validate(fb)) for fb in recent_result.scalars().all()
        ]

        # 未读通知数（直连 notifications 模块）
        unread_notifications = 0
        try:
            from modules.notifications.models import Notification
            notif_result = await db.execute(
                select(func.count()).select_from(Notification).where(
                    Notification.user_id == parent_user.id,
                    Notification.school_id == parent_user.school_id,
                    Notification.is_read == False,
                )
            )
            unread_notifications = notif_result.scalar() or 0
        except Exception as e:
            logger.warning(f"通知聚合失败: {e}")

        elapsed = time.time() - start
        dashboard = ParentDashboard(
            child=child_overview,
            unread_notifications=unread_notifications,
            pending_feedbacks=pending_feedbacks,
            recent_feedbacks=recent_feedbacks,
            _meta={"elapsed_ms": round(elapsed * 1000, 1)},
        )
        logger.info(f"家长仪表盘聚合完成 (parent={parent_user.id}, elapsed={elapsed:.3f}s)")
        return dashboard


# ═══════════════════════════════════════════════════════════════
# FeedbackService — 反馈 CRUD
# ═══════════════════════════════════════════════════════════════

class FeedbackService:

    @staticmethod
    async def create_feedback(
        db: AsyncSession,
        parent_user: User,
        payload_data: Dict[str, Any],
    ) -> ParentFeedback:
        """
        家长提交反馈 — 血缘追踪 + 自动通知班主任

        流程:
          1. 越权铁闸校验 student_id
          2. 写入 ParentFeedback 表
          3. 查询班主任 → 创建通知（通知班主任有新反馈）
        """
        student_id = payload_data["student_id"]
        # 越权铁闸
        await verify_parent_binding(db, parent_user, student_id)

        feedback = ParentFeedback(
            school_id=parent_user.school_id,
            parent_id=parent_user.id,
            student_id=student_id,
            parent_name=parent_user.display_name,
            feedback_type=payload_data["feedback_type"],
            title=payload_data["title"],
            content=payload_data["content"],
            attachments=payload_data.get("attachments"),
            status=FeedbackStatus.PENDING.value,
            source_context=payload_data.get("source_context", {
                "channel": "web",
                "action": "submit_feedback",
                "parent_id": parent_user.id,
            }),
        )
        db.add(feedback)
        await db.flush()

        # 自动通知班主任
        try:
            student_result = await db.execute(
                select(Student).where(Student.id == student_id)
            )
            student = student_result.scalar_one_or_none()
            if student and student.class_id:
                cls_result = await db.execute(
                    select(Class).where(Class.id == student.class_id)
                )
                cls = cls_result.scalar_one_or_none()
                if cls and cls.head_teacher_id:
                    from modules.notifications.models import Notification
                    notification = Notification(
                        school_id=parent_user.school_id,
                        user_id=cls.head_teacher_id,
                        title=f"家长反馈: {feedback.title}",
                        content=f"家长 {parent_user.display_name} 提交了关于学生 {student.name} 的反馈，请及时处理。",
                        type="feedback",
                        reference_id=feedback.id,
                        is_read=False,
                    )
                    db.add(notification)
                    await db.flush()
        except Exception as e:
            logger.warning(f"班主任通知创建失败: {e}")

        return feedback

    @staticmethod
    async def list_feedbacks(
        db: AsyncSession,
        current_user: User,
        status_filter: Optional[str] = None,
        feedback_type_filter: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> FeedbackListResponse:
        """
        反馈列表 — 双角色视图:
          - PARENT: 只看自己的反馈（parent_id 限定）
          - 教师/德育处: 看全校反馈
        """
        conditions = [ParentFeedback.school_id == current_user.school_id]

        user_role = current_user.role
        if isinstance(user_role, str):
            user_role = UserRole(user_role)

        if user_role == UserRole.PARENT:
            conditions.append(ParentFeedback.parent_id == current_user.id)
        # 教师/德育处/年级组长看全校

        if status_filter:
            conditions.append(ParentFeedback.status == status_filter)
        if feedback_type_filter:
            conditions.append(ParentFeedback.feedback_type == feedback_type_filter)

        # 总数
        total_result = await db.execute(
            select(func.count()).select_from(ParentFeedback).where(and_(*conditions))
        )
        total = total_result.scalar() or 0

        # 列表
        result = await db.execute(
            select(ParentFeedback).where(and_(*conditions))
            .order_by(desc(ParentFeedback.created_at))
            .offset(offset).limit(limit)
        )
        items = [fill_labels(FeedbackItem.model_validate(fb)) for fb in result.scalars().all()]

        return FeedbackListResponse(items=items, total=total)

    @staticmethod
    async def get_feedback_detail(
        db: AsyncSession,
        feedback_id: int,
        current_user: User,
    ) -> FeedbackItem:
        """反馈详情 — PARENT 只能看自己的，教师可看全校"""
        result = await db.execute(
            select(ParentFeedback).where(ParentFeedback.id == feedback_id)
        )
        feedback = result.scalar_one_or_none()
        if not feedback:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="反馈不存在")

        user_role = current_user.role
        if isinstance(user_role, str):
            user_role = UserRole(user_role)

        # 家长只能看自己的反馈
        if user_role == UserRole.PARENT and feedback.parent_id != current_user.id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="无权查看其他家长的反馈")

        return fill_labels(FeedbackItem.model_validate(feedback))

    @staticmethod
    async def reply_feedback(
        db: AsyncSession,
        feedback_id: int,
        handler: User,
        reply_data: Dict[str, Any],
    ) -> ParentFeedback:
        """
        班主任/德育处处理反馈 — 双向闭环:
          1. 更新反馈状态 + 处理人 + 回复内容
          2. 自动通知家长（"您的反馈已被处理"）
        """
        result = await db.execute(
            select(ParentFeedback).where(ParentFeedback.id == feedback_id)
        )
        feedback = result.scalar_one_or_none()
        if not feedback:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="反馈不存在")

        # 校验 school_id
        if feedback.school_id != handler.school_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="无权处理其他学校的反馈")

        feedback.status = reply_data["status"]
        feedback.handler_id = handler.id
        feedback.handler_name = handler.display_name
        feedback.handler_reply = reply_data["reply"]
        feedback.handled_at = datetime.utcnow()
        await db.flush()

        # 自动通知家长
        try:
            from modules.notifications.models import Notification
            notification = Notification(
                school_id=feedback.school_id,
                user_id=feedback.parent_id,
                title=f"反馈已处理: {feedback.title}",
                content=f"您的反馈已被 {handler.display_name} 处理，请查看回复。",
                type="feedback_reply",
                reference_id=feedback.id,
                is_read=False,
            )
            db.add(notification)
            await db.flush()
        except Exception as e:
            logger.warning(f"家长通知创建失败: {e}")

        return feedback


# ═══════════════════════════════════════════════════════════════
# AppealProxyService — 申诉代理（Facade 路由到 discipline/behavior）
# ═══════════════════════════════════════════════════════════════

class AppealProxyService:

    @staticmethod
    async def proxy_appeal(
        db: AsyncSession,
        parent_user: User,
        payload_data: Dict[str, Any],
    ) -> AppealProxyResult:
        """
        申诉代理 — Facade 模式:
          1. 越权铁闸校验 student_id
          2. 在本模块创建 ParentAppealsProxy 追踪记录
          3. 根据 target_module 路由到已有审批模块
          4. 回填 target_appeal_id
          5. 自动通知班主任
        """
        start = time.time()
        student_id = payload_data["student_id"]

        # 越权铁闸
        await verify_parent_binding(db, parent_user, student_id)

        target_module = payload_data["target_module"]
        target_record_id = payload_data["target_record_id"]

        # 创建代理追踪记录
        proxy = ParentAppealsProxy(
            school_id=parent_user.school_id,
            parent_id=parent_user.id,
            student_id=student_id,
            target_module=target_module,
            target_record_id=target_record_id,
            applicant_name=payload_data["applicant_name"],
            applicant_phone=payload_data.get("applicant_phone"),
            reason=payload_data["reason"],
            proxy_status="submitted",
            source_context={
                "channel": "web",
                "action": "proxy_appeal",
                "parent_id": parent_user.id,
                "target_module": target_module,
            },
        )
        db.add(proxy)
        await db.flush()

        # ── Facade 路由: discipline ──
        target_appeal_id = None
        message = "申诉已提交，等待审核"

        if target_module == AppealTargetModule.DISCIPLINE.value:
            try:
                from modules.discipline.models import DisciplineSanction
                sanction_result = await db.execute(
                    select(DisciplineSanction).where(
                        DisciplineSanction.id == target_record_id,
                        DisciplineSanction.school_id == parent_user.school_id,
                    )
                )
                sanction = sanction_result.scalar_one_or_none()
                if sanction:
                    # 路由到审批模块 — 创建审批工单
                    try:
                        from modules.approval.models import ApprovalRequest
                        approval = ApprovalRequest(
                            school_id=parent_user.school_id,
                            business_type="discipline_appeal",
                            requester_id=parent_user.id,
                            student_id=student_id,
                            current_status="pending",
                            request_data={
                                "sanction_id": sanction.id,
                                "applicant_name": payload_data["applicant_name"],
                                "reason": payload_data["reason"],
                                "proxy_id": proxy.id,
                            },
                        )
                        db.add(approval)
                        await db.flush()
                        target_appeal_id = approval.id
                        proxy.target_appeal_id = target_appeal_id
                        proxy.proxy_status = "routed"
                        message = "处分申诉已提交，已进入审批流程"
                    except Exception as e:
                        logger.warning(f"审批工单创建失败 (discipline): {e}")
                        message = "申诉已记录，审批工单创建待人工处理"
                else:
                    message = "处分记录不存在或不属于当前学校"
                    proxy.proxy_status = "rejected"
            except Exception as e:
                logger.warning(f"处分申诉路由失败: {e}")
                proxy.proxy_status = "rejected"
                message = f"申诉路由失败: {e}"

        # ── Facade 路由: behavior ──
        elif target_module == AppealTargetModule.BEHAVIOR.value:
            try:
                from modules.behavior.models import BehaviorRecord
                behavior_result = await db.execute(
                    select(BehaviorRecord).where(
                        BehaviorRecord.id == target_record_id,
                        BehaviorRecord.school_id == parent_user.school_id,
                    )
                )
                behavior = behavior_result.scalar_one_or_none()
                if behavior:
                    try:
                        from modules.approval.models import ApprovalRequest
                        approval = ApprovalRequest(
                            school_id=parent_user.school_id,
                            business_type="behavior_appeal",
                            requester_id=parent_user.id,
                            student_id=student_id,
                            current_status="pending",
                            request_data={
                                "behavior_id": behavior.id,
                                "applicant_name": payload_data["applicant_name"],
                                "reason": payload_data["reason"],
                                "proxy_id": proxy.id,
                            },
                        )
                        db.add(approval)
                        await db.flush()
                        target_appeal_id = approval.id
                        proxy.target_appeal_id = target_appeal_id
                        proxy.proxy_status = "routed"
                        message = "违纪申诉已提交，已进入审批流程"
                    except Exception as e:
                        logger.warning(f"审批工单创建失败 (behavior): {e}")
                        message = "申诉已记录，审批工单创建待人工处理"
                else:
                    message = "违纪记录不存在或不属于当前学校"
                    proxy.proxy_status = "rejected"
            except Exception as e:
                logger.warning(f"违纪申诉路由失败: {e}")
                proxy.proxy_status = "rejected"
                message = f"申诉路由失败: {e}"

        await db.flush()

        elapsed = time.time() - start
        result = AppealProxyResult(
            success=proxy.proxy_status in ("submitted", "routed"),
            target_module=AppealTargetModuleEnum(target_module),
            target_appeal_id=target_appeal_id,
            message=message,
            source_context=proxy.source_context,
            _meta={"elapsed_ms": round(elapsed * 1000, 1)},
        )
        logger.info(f"申诉代理完成 (proxy={proxy.id}, status={proxy.proxy_status}, elapsed={elapsed:.3f}s)")
        return result
