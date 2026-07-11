"""
modules/attendance/services.py — 考勤业务逻辑 (V2)

封装考勤录入、查询、统计、请假审批等核心操作。
V2 扩展: 仪表盘聚合 / 班级排行 / 日历热力图 / 异常预警增强 / 全局视图 / 数据导出
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Tuple, Set
from collections import defaultdict, OrderedDict
import logging

from sqlalchemy import select, func, and_, or_, delete, desc, update, case
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AttendanceRecord, LeaveRequest
from .exceptions import (
    AttendanceError,
    StudentLeaveConflictError,
    ScopePermissionDeniedError,
    NoPermissionError,
    InvalidStatusError,
    LeaveNotFoundError,
    DateRangeError,
)
from core.models import Student, Class, Grade, User, UserRole, get_local_now

logger = logging.getLogger(__name__)


class AttendanceService:
    """考勤管理服务"""

    STATUS_LABELS = {
        "present": "出勤",
        "late": "迟到",
        "early": "早退",
        "absent": "缺勤",
        "leave": "请假",
    }

    STATUS_COLORS = {
        "present": "#28a745",
        "late": "#ffc107",
        "absent": "#dc3545",
        "leave": "#17a2b8",
        "early": "#fd7e14",
    }

    VALID_STATUSES = frozenset(STATUS_LABELS.keys())

    # ═══════════════════════════════════════════════════════════
    #  角色白名单 — 操作权限矩阵
    #  斩断 HTTPException 长臂管辖：Service 层定义权限常量
    #  Router 层仅做 check_access() 调用，异常由全局处理器映射
    # ═══════════════════════════════════════════════════════════

    ROLE_ACTIONS = {
        "batch_record":    {UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER},
        "view_ranking":    {UserRole.MS_ADMIN, UserRole.GRADE_LEADER},
        "view_overview":   {UserRole.MS_ADMIN},
        "export_data":     {UserRole.MS_ADMIN, UserRole.GRADE_LEADER},
        "submit_leave":    {UserRole.PARENT},
        "approve_leave":   {UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER},
        "list_leaves":     {UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.PARENT},
        "batch_process_leaves": {UserRole.MS_ADMIN, UserRole.GRADE_LEADER},
    }

    @staticmethod
    def resolve_scope(user: User) -> dict:
        """
        根据用户角色解析数据访问范围。
        
        支持角色兼任场景（如某教师同时担任班主任+年级组长）：
        返回 accessible_roles 集合 + 各维度的自动限定值。

        返回:
          {
            "role": UserRole,           # 主角色
            "school_id": int,
            "grade_id": int | None,     # 年级组长自动限定为本年级
            "class_id": int | None,     # 班主任自动限定为本班
            "student_id": int | None,   # 家长自动限定为绑定学生
            "accessible_roles": set,    # 用户所有可用角色（含兼任）
            "is_ms_admin": bool,
            "is_grade_leader": bool,
            "is_class_teacher": bool,
            "is_parent": bool,
            "is_student": bool,
          }
        """
        role = user.role if isinstance(user.role, UserRole) else UserRole(user.role)
        
        scope = {
            "role": role,
            "school_id": user.school_id,
            "grade_id": None,
            "class_id": None,
            "student_id": None,
            "accessible_roles": {role},
            "is_ms_admin": role == UserRole.MS_ADMIN,
            "is_grade_leader": role == UserRole.GRADE_LEADER,
            "is_class_teacher": role == UserRole.CLASS_TEACHER,
            "is_parent": role == UserRole.PARENT,
            "is_student": role == UserRole.STUDENT,
        }

        # 自动限定数据范围
        if role == UserRole.GRADE_LEADER:
            scope["grade_id"] = getattr(user, "grade_id", None)
        elif role == UserRole.CLASS_TEACHER:
            scope["class_id"] = getattr(user, "class_id", None)
        elif role == UserRole.PARENT:
            scope["student_id"] = getattr(user, "bound_student_id", None)

        return scope

    @staticmethod
    def check_access(action: str, user: User):
        """
        校验用户是否有权限执行指定操作。

        抛出 NoPermissionError 若权限不足。
        不返回任何值 — 通过即放行，不通过即抛异常。
        """
        role = user.role if isinstance(user.role, UserRole) else UserRole(user.role)
        allowed = AttendanceService.ROLE_ACTIONS.get(action, set())
        
        if role not in allowed:
            detail_map = {
                "batch_record":  "无权录入考勤",
                "view_ranking":  "无权查看班级排名",
                "view_overview": "仅德育处管理员可查看全局视图",
                "export_data":   "无权导出考勤数据",
                "submit_leave":  "仅家长可提交请假申请",
                "approve_leave": "仅班主任或年级组长可审批请假",
                "list_leaves":   "无权查看请假列表",
                "batch_process_leaves": "仅年级组长可批量审批请假",
            }
            raise NoPermissionError(detail_map.get(action, "无权执行此操作"))

    # ═══════════════════════════════════════════════════════════
    #  考勤录入
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def batch_record(
        cls,
        db: AsyncSession,
        school_id: int,
        class_id: int,
        grade_id: int,
        record_date: date,
        records: List[Dict],  # [{"student_id": 1, "status": "present", "note": ""}]
        created_by: int = 0,
        creator_role: str = "class_teacher",
    ) -> Tuple[int, List[Dict]]:
        """
        批量录入某班级某日的考勤数据。V2 增强返回通知目标。

        幂等设计: 先清除当日已有记录，再写入新记录。
        返回 (写入记录数, 需通知学生列表)。

        PolicyEngine Hook-1: 考勤异常(late/absent)→评价扣分闭环
        铁律1: 考勤记录已commit，绝对优先
        铁律2: try/except隔离，Hook失败不阻塞主业务
        铁律3: 审批工单+ScoreLog在同一flush/commit块中
        """
        # 验证状态值
        for rec in records:
            if rec["status"] not in cls.VALID_STATUSES:
                raise InvalidStatusError(rec["status"])

        student_ids = [r["student_id"] for r in records]

        # 批量预加载学生信息（用于通知）
        student_map = {}
        stu_result = await db.execute(
            select(Student.id, Student.name, Student.student_no, Student.class_id)
            .where(Student.id.in_(student_ids))
        )
        for row in stu_result.all():
            student_map[row[0]] = {"name": row[1], "student_no": row[2], "class_id": row[3]}

        # 幂等: 删除当日已有记录
        await db.execute(
            delete(AttendanceRecord).where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.class_id == class_id,
                AttendanceRecord.record_date == record_date,
                AttendanceRecord.student_id.in_(student_ids),
            )
        )

        # 批量写入 + 收集通知目标
        now = get_local_now()
        new_records = []
        notification_targets = []

        for rec in records:
            att = AttendanceRecord(
                school_id=school_id,
                student_id=rec["student_id"],
                class_id=class_id,
                grade_id=grade_id,
                status=rec["status"],
                record_date=record_date,
                note=rec.get("note", ""),
                created_at=now,
            )
            new_records.append(att)

            # 收集缺勤/迟到学生用于通知
            if rec["status"] in ("absent", "late"):
                stu = student_map.get(rec["student_id"], {})
                notification_targets.append({
                    "student_id": rec["student_id"],
                    "student_name": stu.get("name", ""),
                    "student_no": stu.get("student_no", ""),
                    "class_id": class_id,
                    "status": rec["status"],
                    "status_label": cls.STATUS_LABELS.get(rec["status"], rec["status"]),
                    "note": rec.get("note", ""),
                })

        db.add_all(new_records)
        await db.flush()  # 获取自增ID，供Hook使用

        # 收集Hook目标（在commit前收集，避免session过期后访问ORM对象）
        hook_targets = []
        for att in new_records:
            if att.status in ("late", "absent"):
                hook_targets.append({
                    "student_id": att.student_id,
                    "record_id": att.id,
                    "status": att.status,
                })

        # ═══ 主业务commit — 考勤记录绝对优先 ═══
        await db.commit()

        # ═══ PolicyEngine Hook-1: 考勤异常→评价扣分闭环 ═══
        # 铁律1: 考勤记录已commit，绝对优先
        # 铁律2: try/except隔离，Hook失败不阻塞主业务
        # 铁律3: 审批工单+ScoreLog在同一flush/commit块中
        if hook_targets:
            try:
                from modules.policy_engine import get_engine
                engine = get_engine()

                if engine:
                    from modules.evaluation.services import EvaluationService
                    from modules.evaluation.models import ApprovalRequest

                    # 考勤状态 → PolicyEngine behavior_type 映射
                    _STATUS_TYPE_MAP = {
                        "late": "lateness",
                        "absent": "absence",
                    }

                    for target in hook_targets:
                        behavior_type = _STATUS_TYPE_MAP.get(
                            target["status"], target["status"]
                        )

                        # 1. 事件分类 → severity / dimension / penalty
                        classification = engine.classify(behavior_type)

                        # 2. 审批链解析: L1 多租户 → L2 PolicyEngine
                        chain_config = None
                        approval_mode = "parallel_or"

                        # L1: 尝试多租户审批链
                        biz_type = "attendance_absence" if behavior_type == "absence" else "attendance_leave"
                        try:
                            from modules.approval.services import resolve_chain_async
                            chain_config = await resolve_chain_async(db, school_id, biz_type)
                            if chain_config:
                                approval_mode = chain_config.get("approval_mode", "serial_and")
                        except Exception as chain_err:
                            logger.warning(
                                "[Attendance Hook] 多租户审批链查询失败(降级PolicyEngine): %s", chain_err
                            )

                        # L2: Fallback — PolicyEngine
                        if not chain_config:
                            chain = engine.route(behavior_type, creator_role)
                            chain_config = chain.model_dump()
                            approval_mode = chain.mode

                        # 3. 写审批工单 (approval_requests)
                        approval_req = ApprovalRequest(
                            school_id=school_id,
                            student_id=target["student_id"],
                            event_type=behavior_type,
                            source_type="attendance",
                            source_id=target["record_id"],
                            severity=classification.severity,
                            approval_mode=approval_mode,
                            chain_config=chain_config,
                            current_status="pending",
                            current_step=0,
                        )
                        db.add(approval_req)

                        # 4. 调 EvaluationService.apply_deduction() — 同事务写 ScoreLog
                        #    discipline_type 传 severity 级别以匹配 deduction_map
                        log = await EvaluationService.apply_deduction(
                            db=db,
                            student_id=target["student_id"],
                            class_id=class_id,
                            grade_id=grade_id,
                            school_id=school_id,
                            discipline_type=classification.severity,
                            discipline_id=target["record_id"],
                            created_by=created_by,
                            source_type="attendance",
                            penalty_override=classification.base_penalty,
                            policy_tag="repairable",
                        )

                    await db.flush()
                    await db.commit()

                    logger.info(
                        f"[PolicyEngine Hook-1] 考勤异常→评价扣分闭环成功: "
                        f"{len(hook_targets)} 条记录处理完成 "
                        f"class_id={class_id} date={record_date.isoformat()}"
                    )
            except Exception as e:
                # 铁律2: 异常隔离 — rollback Hook写入，考勤记录已commit不受影响
                await db.rollback()
                logger.error(
                    f"[PolicyEngine Hook-1] 异常(已隔离，考勤记录已保存): "
                    f"class_id={class_id} date={record_date.isoformat()} "
                    f"error={e}",
                    exc_info=True,
                )

        return len(new_records), notification_targets

    # ═══════════════════════════════════════════════════════════
    #  考勤查询
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def get_class_attendance(
        cls,
        db: AsyncSession,
        school_id: int,
        class_id: int,
        record_date: Optional[date] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        获取某班级的考勤详情。

        支持两种查询模式:
        ① 单日:  仅提供 record_date
        ② 范围:  提供 start_date + end_date（适合历史查询）
        """
        conditions = [
            AttendanceRecord.school_id == school_id,
            AttendanceRecord.class_id == class_id,
        ]

        if start_date and end_date:
            cls._ensure_valid_date_range(start_date, end_date)
            conditions.append(AttendanceRecord.record_date >= start_date)
            conditions.append(AttendanceRecord.record_date <= end_date)
        elif record_date:
            conditions.append(AttendanceRecord.record_date == record_date)
        else:
            raise DateRangeError("必须提供 record_date 或 start_date+end_date")

        result = await db.execute(
            select(AttendanceRecord, Student.name, Student.student_no)
            .join(Student, AttendanceRecord.student_id == Student.id)
            .where(and_(*conditions))
            .order_by(AttendanceRecord.record_date.asc(), Student.name)
        )
        rows = result.all()
        return [
            {
                "id": att.id,
                "student_id": att.student_id,
                "student_name": student_name,
                "student_no": student_no,
                "status": att.status,
                "status_label": cls.STATUS_LABELS.get(att.status, att.status),
                "note": att.note,
                "record_date": att.record_date.isoformat(),
            }
            for att, student_name, student_no in rows
        ]

    @classmethod
    async def get_student_history(
        cls,
        db: AsyncSession,
        school_id: int,
        student_id: int,
        days: int = 30,
    ) -> List[Dict]:
        """获取某学生近 N 天的考勤历史"""
        since = date.today() - timedelta(days=days)
        result = await db.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.record_date >= since,
            )
            .order_by(AttendanceRecord.record_date.desc())
        )
        records = result.scalars().all()
        return [
            {
                "id": r.id,
                "record_date": r.record_date.isoformat(),
                "status": r.status,
                "status_label": cls.STATUS_LABELS.get(r.status, r.status),
                "status_color": cls.STATUS_COLORS.get(r.status, "#999"),
                "note": r.note,
            }
            for r in records
        ]

    # ═══════════════════════════════════════════════════════════
    #  考勤统计
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def get_grade_summary(
        cls,
        db: AsyncSession,
        school_id: int,
        grade_id: int,
        start_date: date,
        end_date: date,
    ) -> Dict:
        """
        年级考勤概览统计。
        返回各班级的各状态人数汇总。
        """
        result = await db.execute(
            select(
                AttendanceRecord.class_id,
                AttendanceRecord.status,
                func.count(AttendanceRecord.id).label("cnt"),
            )
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.grade_id == grade_id,
                AttendanceRecord.record_date.between(start_date, end_date),
            )
            .group_by(AttendanceRecord.class_id, AttendanceRecord.status)
        )

        # 按班级聚合
        class_stats: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {s: 0 for s in cls.VALID_STATUSES}
        )
        for class_id, status, cnt in result.all():
            class_stats[class_id][status] = cnt

        # 查询班级名称
        class_ids = list(class_stats.keys())
        if class_ids:
            class_result = await db.execute(
                select(Class.id, Class.name).where(Class.id.in_(class_ids))
            )
            class_names = {row[0]: row[1] for row in class_result.all()}
        else:
            class_names = {}

        summary = []
        for class_id, stats in class_stats.items():
            total = sum(stats.values())
            summary.append({
                "class_id": class_id,
                "class_name": class_names.get(class_id, f"班级{class_id}"),
                "total_records": total,
                **stats,
            })

        return {"grade_id": grade_id, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "classes": summary}

    @classmethod
    async def get_anomaly_alerts(
        cls,
        db: AsyncSession,
        school_id: int,
        days: int = 7,
    ) -> List[Dict]:
        """
        异常预警 V2: 三类规则
        ① 连续缺勤 ≥ 3 天 (严格相邻)
        ② 本周迟到 ≥ 3 次
        ③ 本月缺勤 ≥ 5 次
        """
        today = date.today()

        # 窗口: 近 min(60, days) 天用于连续缺勤检测
        since_60 = today - timedelta(days=60)
        result = await db.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.record_date >= since_60,
                AttendanceRecord.status.in_(["absent", "late"]),
            )
            .order_by(AttendanceRecord.student_id, AttendanceRecord.record_date.asc())
        )
        records = result.scalars().all()

        # 按学生分组
        student_records: Dict[int, List[AttendanceRecord]] = defaultdict(list)
        for r in records:
            student_records[r.student_id].append(r)

        alerts: List[Dict] = []
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        for student_id, recs in student_records.items():
            warnings = []

            # ① 连续缺勤检测
            max_consecutive = 0
            current_consecutive = 0
            last_date = None
            for r in recs:
                if r.status == "absent":
                    if last_date and (r.record_date - last_date).days == 1:
                        current_consecutive += 1
                    else:
                        current_consecutive = 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                    last_date = r.record_date
                else:
                    current_consecutive = 0
                    last_date = None

            if max_consecutive >= 3:
                warnings.append({
                    "type": "consecutive_absent",
                    "level": "danger",
                    "text": f"连续缺勤 {max_consecutive} 天",
                    "days_value": max_consecutive,
                })

            # ② 本周迟到 ≥ 3
            week_late = sum(1 for r in recs if r.status == "late" and r.record_date >= week_start)
            if week_late >= 3:
                warnings.append({
                    "type": "weekly_late",
                    "level": "warning",
                    "text": f"本周已迟到 {week_late} 次",
                    "days_value": week_late,
                })

            # ③ 本月缺勤 ≥ 5
            month_absent = sum(1 for r in recs if r.status == "absent" and r.record_date >= month_start)
            if month_absent >= 5:
                warnings.append({
                    "type": "monthly_absent",
                    "level": "warning",
                    "text": f"本月已缺勤 {month_absent} 次",
                    "days_value": month_absent,
                })

            if warnings:
                max_level = "danger" if any(w["level"] == "danger" for w in warnings) else "warning"
                alerts.append({
                    "student_id": student_id,
                    "warnings": warnings,
                    "max_level": max_level,
                })

        # 排序: 危险优先
        alerts.sort(key=lambda a: (0 if a["max_level"] == "danger" else 1))

        # 补充学生姓名/班级
        if alerts:
            sids = [a["student_id"] for a in alerts]
            stu_result = await db.execute(
                select(Student.id, Student.name, Student.student_no, Student.class_id)
                .where(Student.id.in_(sids))
            )
            stu_map = {r[0]: r for r in stu_result.all()}

            for alert in alerts:
                stu = stu_map.get(alert["student_id"])
                if stu:
                    alert["student_name"] = stu[1]
                    alert["student_no"] = stu[2]
                    alert["class_id"] = stu[3]

        return alerts

    # ═══════════════════════════════════════════════════════════
    #  请假管理
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def submit_leave(
        cls,
        db: AsyncSession,
        school_id: int,
        student_id: int,
        class_id: int,
        grade_id: int,
        start_date: date,
        end_date: date,
        reason: str,
        submitted_by: int,
    ) -> LeaveRequest:
        """
        家长提交请假申请。

        前置校验:
          1. 日期范围有效 (start ≤ end)
          2. 同学生不允许存在时间重叠的已批准/审批中请假。
        """
        cls._ensure_valid_date_range(start_date, end_date)

        # 日期重叠校验: 已有请假 start_date <= 新 end_date AND end_date >= 新 start_date
        overlap_result = await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.school_id == school_id,
                LeaveRequest.student_id == student_id,
                LeaveRequest.start_date <= end_date,
                LeaveRequest.end_date >= start_date,
                LeaveRequest.status.in_(["pending", "class_approved", "grade_approved"]),
            )
        )
        existing = overlap_result.scalars().first()
        if existing:
            raise StudentLeaveConflictError(
                existing_start=existing.start_date.isoformat(),
                existing_end=existing.end_date.isoformat(),
                existing_status=existing.status,
            )

        leave = LeaveRequest(
            school_id=school_id,
            student_id=student_id,
            class_id=class_id,
            grade_id=grade_id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status="pending",
            submitted_by=submitted_by,
        )
        db.add(leave)
        await db.commit()
        await db.refresh(leave)
        return leave

    @classmethod
    async def approve_leave(
        cls,
        db: AsyncSession,
        leave_id: int,
        approver_id: int,
        approver_role: str,
    ) -> LeaveRequest:
        """班主任/年级组长审批请假"""
        result = await db.execute(
            select(LeaveRequest).where(LeaveRequest.id == leave_id)
        )
        leave = result.scalar_one_or_none()
        if not leave:
            raise LeaveNotFoundError(leave_id)

        now = get_local_now()

        if approver_role == "class_teacher":
            leave.status = "class_approved"
            leave.approved_by_class = approver_id
            leave.approved_at_class = now
        elif approver_role == "grade_leader":
            leave.status = "grade_approved"
            leave.approved_by_grade = approver_id
            leave.approved_at_grade = now

            # ── 🔥 逆熵冲正: absent → leave ──
            # 将请假日期范围内的"旷课"污点冲正为"合规请假"
            # 精准抹除 GrowthAggregationPipeline 中 CRITICAL(-15分) 惩罚项
            correction_note = f"请假冲正: {leave.reason[:30]}" if leave.reason else "请假冲正"
            correct_result = await db.execute(
                update(AttendanceRecord)
                .where(
                    and_(
                        AttendanceRecord.student_id == leave.student_id,
                        AttendanceRecord.school_id == leave.school_id,
                        AttendanceRecord.record_date >= leave.start_date,
                        AttendanceRecord.record_date <= leave.end_date,
                        AttendanceRecord.status == "absent",
                    )
                )
                .values(status="leave", note=correction_note)
            )
            corrected_count = correct_result.rowcount

            # 审批通过后创建考勤记录（跳过已有记录，含刚冲正的）
            existing_dates_result = await db.execute(
                select(AttendanceRecord.record_date).where(
                    AttendanceRecord.school_id == leave.school_id,
                    AttendanceRecord.student_id == leave.student_id,
                    AttendanceRecord.record_date >= leave.start_date,
                    AttendanceRecord.record_date <= leave.end_date,
                )
            )
            existing_dates = set(r[0] for r in existing_dates_result.all())

            current = leave.start_date
            att_records = []
            while current <= leave.end_date:
                if current not in existing_dates:
                    att = AttendanceRecord(
                        school_id=leave.school_id,
                        student_id=leave.student_id,
                        class_id=leave.class_id,
                        grade_id=leave.grade_id,
                        status="leave",
                        record_date=current,
                        note=f"请假: {leave.reason[:50]}" if leave.reason else "请假",
                    )
                    att_records.append(att)
                current += timedelta(days=1)

            if att_records:
                db.add_all(att_records)

        await db.commit()
        await db.refresh(leave)
        # 逆熵冲正计数挂载（非持久化字段，供 router 层读取）
        leave._corrected_count = corrected_count if approver_role == "grade_leader" else 0
        return leave

    @classmethod
    async def list_leaves(
        cls,
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        class_id: Optional[int] = None,
        student_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict:
        """
        列出请假申请，支持多维度过滤和分页。

        过滤维度（全部可选，组合使用）:
        - grade_id:  年级
        - class_id:  班级
        - student_id: 学生
        - status:    状态筛选 (pending/class_approved/grade_approved/rejected)

        返回:
          {"items": [...], "total": int, "limit": int, "offset": int}
        """
        conditions = [LeaveRequest.school_id == school_id]
        if grade_id:
            conditions.append(LeaveRequest.grade_id == grade_id)
        if class_id:
            conditions.append(LeaveRequest.class_id == class_id)
        if student_id:
            conditions.append(LeaveRequest.student_id == student_id)
        if status:
            conditions.append(LeaveRequest.status == status)

        # 总数
        count_result = await db.execute(
            select(func.count(LeaveRequest.id)).where(and_(*conditions))
        )
        total = count_result.scalar()

        # 带学生信息的分页查询
        result = await db.execute(
            select(LeaveRequest, Student.name, Student.student_no)
            .join(Student, LeaveRequest.student_id == Student.id)
            .where(and_(*conditions))
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = result.all()

        items = []
        for leave, stu_name, stu_no in rows:
            items.append({
                "id": leave.id,
                "student_id": leave.student_id,
                "student_name": stu_name,
                "student_no": stu_no,
                "class_id": leave.class_id,
                "grade_id": leave.grade_id,
                "start_date": leave.start_date.isoformat(),
                "end_date": leave.end_date.isoformat(),
                "reason": leave.reason,
                "status": leave.status,
                "submitted_by": leave.submitted_by,
                "created_at": leave.created_at.isoformat() if leave.created_at else None,
                "approved_at_class": leave.approved_at_class.isoformat() if leave.approved_at_class else None,
                "approved_at_grade": leave.approved_at_grade.isoformat() if leave.approved_at_grade else None,
            })

        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @classmethod
    async def batch_process_leaves(
        cls,
        db: AsyncSession,
        leave_ids: List[int],
        action: str,
        approver_id: int,
        approver_role: str,
    ) -> List[Dict]:
        """
        批量处理请假申请（审批或拒绝）。

        - class_teacher: approve → class_approved; reject → rejected
        - grade_leader:  approve → grade_approved + 自动创建考勤记录; reject → rejected

        返回每项处理结果的列表:
          [{"leave_id": int, "success": bool, "status": str, ...}, ...]
        """
        results = []
        now = get_local_now()

        for leave_id in leave_ids:
            result = await db.execute(
                select(LeaveRequest).where(LeaveRequest.id == leave_id)
            )
            leave = result.scalar_one_or_none()

            if not leave:
                results.append({"leave_id": leave_id, "success": False, "error": "请假申请不存在"})
                continue

            if leave.status != "pending":
                results.append({
                    "leave_id": leave_id,
                    "success": False,
                    "error": f"当前状态 {leave.status} 不允许批量处理",
                })
                continue

            if action == "reject":
                leave.status = "rejected"
                results.append({
                    "leave_id": leave_id,
                    "success": True,
                    "status": "rejected",
                    "student_id": leave.student_id,
                })

            elif action == "approve":
                if approver_role == "class_teacher":
                    leave.status = "class_approved"
                    leave.approved_by_class = approver_id
                    leave.approved_at_class = now
                    results.append({
                        "leave_id": leave_id,
                        "success": True,
                        "status": "class_approved",
                        "student_id": leave.student_id,
                    })

                elif approver_role == "grade_leader":
                    leave.status = "grade_approved"
                    leave.approved_by_grade = approver_id
                    leave.approved_at_grade = now

                    # ── 🔥 逆熵冲正: absent → leave ──
                    correction_note = f"请假冲正: {leave.reason[:30]}" if leave.reason else "请假冲正"
                    correct_result = await db.execute(
                        update(AttendanceRecord)
                        .where(
                            and_(
                                AttendanceRecord.student_id == leave.student_id,
                                AttendanceRecord.school_id == leave.school_id,
                                AttendanceRecord.record_date >= leave.start_date,
                                AttendanceRecord.record_date <= leave.end_date,
                                AttendanceRecord.status == "absent",
                            )
                        )
                        .values(status="leave", note=correction_note)
                    )
                    corrected_count = correct_result.rowcount

                    # 创建考勤记录（跳过已有记录，含刚冲正的）
                    existing_dates_result = await db.execute(
                        select(AttendanceRecord.record_date).where(
                            AttendanceRecord.school_id == leave.school_id,
                            AttendanceRecord.student_id == leave.student_id,
                            AttendanceRecord.record_date >= leave.start_date,
                            AttendanceRecord.record_date <= leave.end_date,
                        )
                    )
                    existing_dates = set(r[0] for r in existing_dates_result.all())

                    current = leave.start_date
                    att_records = []
                    while current <= leave.end_date:
                        if current not in existing_dates:
                            att = AttendanceRecord(
                                school_id=leave.school_id,
                                student_id=leave.student_id,
                                class_id=leave.class_id,
                                grade_id=leave.grade_id,
                                status="leave",
                                record_date=current,
                                note=f"请假: {leave.reason[:50]}" if leave.reason else "请假",
                            )
                            att_records.append(att)
                        current += timedelta(days=1)

                    if att_records:
                        db.add_all(att_records)

                    results.append({
                        "leave_id": leave_id,
                        "success": True,
                        "status": "grade_approved",
                        "student_id": leave.student_id,
                        "attendance_created": len(att_records),
                        "corrected_count": corrected_count,
                    })

        await db.commit()
        return results
    #  所有领域校验集中于此，Router 层不再触碰业务规则。
    #  抛出领域异常 → 全局异常处理器映射到 HTTP 响应。
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _ensure_not_student(scope: dict):
        """
        确保用户不是学生角色。
        学生无权访问聚合分析类功能（仪表盘/排行/全局视图等）。
        """
        if scope.get("is_student"):
            raise NoPermissionError("学生无权查看仪表盘")

    @staticmethod
    def _ensure_valid_date_range(start_date: date, end_date: date):
        """确保日期范围有效（开始 ≤ 结束）"""
        if end_date < start_date:
            raise DateRangeError()

    @staticmethod
    def _resolve_period(today: date, period: str) -> Tuple[date, date]:
        """解析时间周期 → (start_date, end_date)"""
        if period == "today":
            return today, today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end
        elif period == "month":
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            return start, end
        elif period == "semester":
            if today.month >= 9 or today.month <= 1:
                start = today.replace(month=9, day=1)
                end = today.replace(year=today.year + 1, month=1, day=31)
            else:
                start = today.replace(month=2, day=1)
                end = today.replace(month=6, day=30)
            return start, end
        else:
            # 默认周
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end

    @classmethod
    async def get_dashboard(
        cls,
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        class_id: Optional[int] = None,
        student_id: Optional[int] = None,
        period: str = "week",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict:
        """
        仪表盘数据聚合:
        - cards: 概览卡片 (出勤/迟到/缺勤/请假人数)
        - trend: 按日趋势数据 (labels + series)
        - pie: 分布饼图数据

        支持两种时间范围模式:
        ① 自定义: 同时提供 start_date + end_date，精确控制范围
        ② 周期:  仅提供 period (today/week/month/semester)，自动计算
        """
        today = date.today()

        # 优先使用自定义日期范围
        if start_date and end_date:
            cls._ensure_valid_date_range(start_date, end_date)
            date_start, date_end = start_date, end_date
        else:
            date_start, date_end = cls._resolve_period(today, period)

        # 构建查询
        conditions = [
            AttendanceRecord.school_id == school_id,
            AttendanceRecord.record_date >= date_start,
            AttendanceRecord.record_date <= date_end,
        ]
        if grade_id:
            conditions.append(AttendanceRecord.grade_id == grade_id)
        if class_id:
            conditions.append(AttendanceRecord.class_id == class_id)
        if student_id:
            conditions.append(AttendanceRecord.student_id == student_id)

        result = await db.execute(
            select(AttendanceRecord).where(and_(*conditions))
        )
        period_records = result.scalars().all()

        # 概览卡片
        cards = {
            "present": sum(1 for r in period_records if r.status == "present"),
            "late": sum(1 for r in period_records if r.status == "late"),
            "absent": sum(1 for r in period_records if r.status == "absent"),
            "leave_early": sum(1 for r in period_records if r.status in ("leave", "early")),
        }

        # 按日分组
        day_records: Dict[date, List] = defaultdict(list)
        for r in period_records:
            day_records[r.record_date].append(r)

        # 趋势图数据
        trend_labels = []
        trend_series = {
            "present": [],
            "late": [],
            "absent": [],
            "leave_early": [],
        }

        current = date_start
        while current <= date_end:
            trend_labels.append(current.strftime("%m/%d"))
            day_recs = day_records.get(current, [])
            trend_series["present"].append(sum(1 for r in day_recs if r.status == "present"))
            trend_series["late"].append(sum(1 for r in day_recs if r.status == "late"))
            trend_series["absent"].append(sum(1 for r in day_recs if r.status == "absent"))
            trend_series["leave_early"].append(sum(1 for r in day_recs if r.status in ("leave", "early")))
            current += timedelta(days=1)

        # 饼图数据
        pie = [
            {"name": "出勤", "value": cards["present"], "color": "#28a745"},
            {"name": "迟到", "value": cards["late"], "color": "#ffc107"},
            {"name": "缺勤", "value": cards["absent"], "color": "#dc3545"},
            {"name": "请假/早退", "value": cards["leave_early"], "color": "#17a2b8"},
        ]

        total = sum(cards.values())
        attendance_rate = round(cards["present"] / total * 100, 1) if total > 0 else 0

        return {
            "period": period,
            "date_start": date_start.isoformat(),
            "date_end": date_end.isoformat(),
            "cards": cards,
            "attendance_rate": attendance_rate,
            "total_records": total,
            "trend": {
                "labels": trend_labels,
                "series": trend_series,
            },
            "pie": pie,
        }

    # ═══════════════════════════════════════════════════════════
    #  V2 新增: 班级横向对比排行
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def get_class_ranking(
        cls,
        db: AsyncSession,
        school_id: int,
        grade_id: Optional[int] = None,
        record_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        班级横向对比排行: 按今日/指定日期缺勤率排序
        """
        if record_date is None:
            record_date = date.today()

        # 获取要对比的班级
        class_query = select(Class.id, Class.name).where(
            Class.school_id == school_id,
            Class.is_active == True,
        )
        if grade_id:
            class_query = class_query.where(Class.grade_id == grade_id)
        class_result = await db.execute(class_query.order_by(Class.name))
        classes = class_result.all()

        if not classes:
            return []

        class_ids = [c[0] for c in classes]

        # 批量查询当日考勤
        att_result = await db.execute(
            select(AttendanceRecord.class_id, AttendanceRecord.status, func.count(AttendanceRecord.id))
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.class_id.in_(class_ids),
                AttendanceRecord.record_date == record_date,
            )
            .group_by(AttendanceRecord.class_id, AttendanceRecord.status)
        )

        # 按班级聚合
        class_day_stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"present": 0, "absent": 0, "late": 0, "leave_early": 0})
        for cid, status, cnt in att_result.all():
            if status == "present":
                class_day_stats[cid]["present"] = cnt
            elif status == "absent":
                class_day_stats[cid]["absent"] = cnt
            elif status == "late":
                class_day_stats[cid]["late"] = cnt
            elif status in ("leave", "early"):
                class_day_stats[cid]["leave_early"] += cnt

        # 查询各班总人数
        student_counts_result = await db.execute(
            select(Student.class_id, func.count(Student.id))
            .where(
                Student.school_id == school_id,
                Student.class_id.in_(class_ids),
                Student.is_active == True,
            )
            .group_by(Student.class_id)
        )
        student_counts = dict(student_counts_result.all())

        # 组装排名
        ranking = []
        for cls_id, cls_name in classes:
            stats = class_day_stats.get(cls_id, {"present": 0, "absent": 0, "late": 0, "leave_early": 0})
            recorded = sum(stats.values())
            total_students = student_counts.get(cls_id, 0)

            absence_rate = round(stats["absent"] / recorded * 100, 1) if recorded > 0 else 0
            present_rate = round(stats["present"] / recorded * 100, 1) if recorded > 0 else 0
            late_rate = round(stats["late"] / recorded * 100, 1) if recorded > 0 else 0

            ranking.append({
                "class_id": cls_id,
                "class_name": cls_name,
                "total_students": total_students,
                "recorded": recorded,
                "present": stats["present"],
                "absent": stats["absent"],
                "late": stats["late"],
                "leave_early": stats["leave_early"],
                "absence_rate": absence_rate,
                "present_rate": present_rate,
                "late_rate": late_rate,
            })

        # 按缺勤率降序
        ranking.sort(key=lambda x: x["absence_rate"], reverse=True)

        return ranking

    # ═══════════════════════════════════════════════════════════
    #  V2 新增: 学生个人日历热力图
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def get_student_calendar(
        cls,
        db: AsyncSession,
        school_id: int,
        student_id: int,
    ) -> Dict:
        """
        学生考勤日历热力图:
        - 90 天历史记录
        - 30 天日历网格 (按周排列)
        - 状态颜色映射
        """
        today = date.today()
        since_90 = today - timedelta(days=90)

        # 查询 90 天考勤
        result = await db.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.record_date >= since_90,
            )
            .order_by(AttendanceRecord.record_date.desc())
        )
        records = result.scalars().all()

        # date → status 映射
        status_map: Dict[date, str] = {}
        for r in records:
            if r.record_date not in status_map:
                status_map[r.record_date] = r.status

        # 最近 35 天日历网格（对齐到周）
        calendar_start = today - timedelta(days=today.weekday() + 28)  # 4 周前周一
        calendar_days = []
        for i in range(35):
            d = calendar_start + timedelta(days=i)
            calendar_days.append({
                "date": d.isoformat(),
                "weekday": d.weekday(),
                "status": status_map.get(d),
                "color": cls.STATUS_COLORS.get(status_map.get(d), "#e9ecef"),
            })

        # 按周分组
        weeks = []
        for w_start in range(0, 35, 7):
            week_chunk = calendar_days[w_start:w_start + 7]
            weeks.append(week_chunk)

        # 历史记录摘要
        history = [
            {
                "record_date": r.record_date.isoformat(),
                "status": r.status,
                "status_label": cls.STATUS_LABELS.get(r.status, r.status),
                "status_color": cls.STATUS_COLORS.get(r.status, "#999"),
                "note": r.note,
            }
            for r in records[:50]  # 最近 50 条
        ]

        # 统计
        total = len(records)
        stats = {
            "present": sum(1 for r in records if r.status == "present"),
            "late": sum(1 for r in records if r.status == "late"),
            "absent": sum(1 for r in records if r.status == "absent"),
            "leave_early": sum(1 for r in records if r.status in ("leave", "early")),
        }
        attendance_rate = round(stats["present"] / total * 100, 1) if total > 0 else 0

        return {
            "student_id": student_id,
            "total_days": total,
            "attendance_rate": attendance_rate,
            "stats": stats,
            "calendar_weeks": weeks,
            "history": history,
            "colors": cls.STATUS_COLORS,
        }

    # ═══════════════════════════════════════════════════════════
    #  V2 新增: 德育处全局视图
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def get_overview(
        cls,
        db: AsyncSession,
        school_id: int,
        start_date: date,
        end_date: date,
    ) -> Dict:
        """
        德育处全局考勤视图: 所有年级/班级汇总
        """
        # 按年级+状态聚合
        result = await db.execute(
            select(
                AttendanceRecord.grade_id,
                AttendanceRecord.class_id,
                AttendanceRecord.status,
                func.count(AttendanceRecord.id).label("cnt"),
            )
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.record_date.between(start_date, end_date),
            )
            .group_by(AttendanceRecord.grade_id, AttendanceRecord.class_id, AttendanceRecord.status)
        )

        # 聚合结构: grade → class → status → count
        grade_data: Dict[int, Dict[int, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )
        for grade_id, class_id, status, cnt in result.all():
            grade_data[grade_id][class_id][status] = cnt

        # 查询年级、班级名称
        all_grade_ids = list(grade_data.keys())
        all_class_ids = list(set(cid for cids in grade_data.values() for cid in cids))

        grade_map = {}
        class_map = {}
        if all_grade_ids:
            g_result = await db.execute(
                select(Grade.id, Grade.name).where(Grade.id.in_(all_grade_ids))
            )
            grade_map = {r[0]: r[1] for r in g_result.all()}
        if all_class_ids:
            c_result = await db.execute(
                select(Class.id, Class.name, Class.grade_id).where(Class.id.in_(all_class_ids))
            )
            class_map = {r[0]: {"name": r[1], "grade_id": r[2]} for r in c_result.all()}

        # 组装输出
        grades_summary = []
        total = {"present": 0, "late": 0, "absent": 0, "leave_early": 0}

        for grade_id, class_dict in sorted(grade_data.items()):
            grade_total = {"present": 0, "late": 0, "absent": 0, "leave_early": 0}
            class_summaries = []

            for class_id, status_cnt in sorted(class_dict.items()):
                present = status_cnt.get("present", 0)
                absent = status_cnt.get("absent", 0)
                late = status_cnt.get("late", 0)
                leave_early = status_cnt.get("leave", 0) + status_cnt.get("early", 0)
                total_records = sum(status_cnt.values())

                grade_total["present"] += present
                grade_total["absent"] += absent
                grade_total["late"] += late
                grade_total["leave_early"] += leave_early

                cls_info = class_map.get(class_id, {"name": f"班级{class_id}", "grade_id": grade_id})
                absence_rate = round(absent / total_records * 100, 1) if total_records > 0 else 0

                class_summaries.append({
                    "class_id": class_id,
                    "class_name": cls_info["name"],
                    "total_records": total_records,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "leave_early": leave_early,
                    "absence_rate": absence_rate,
                })

            class_summaries.sort(key=lambda x: x["absence_rate"], reverse=True)

            for k in grade_total:
                total[k] += grade_total[k]

            grades_summary.append({
                "grade_id": grade_id,
                "grade_name": grade_map.get(grade_id, f"年级{grade_id}"),
                "classes": class_summaries,
                "grade_total": grade_total,
            })

        grand_total = sum(total.values())

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "grades": grades_summary,
            "summary": {
                **total,
                "total_records": grand_total,
                "attendance_rate": round(total["present"] / grand_total * 100, 1) if grand_total > 0 else 0,
            },
        }

    # ═══════════════════════════════════════════════════════════
    #  V2 新增: 数据导出
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def export_attendance(
        cls,
        db: AsyncSession,
        school_id: int,
        grade_id: int,
        start_date: date,
        end_date: date,
    ) -> List[Dict]:
        """
        导出考勤数据: 扁平化记录，含学生姓名、班级、状态。
        供前端生成 Excel/CSV。
        """
        result = await db.execute(
            select(
                AttendanceRecord.record_date,
                Student.name,
                Student.student_no,
                Class.name,
                AttendanceRecord.status,
                AttendanceRecord.note,
            )
            .join(Student, AttendanceRecord.student_id == Student.id)
            .join(Class, AttendanceRecord.class_id == Class.id)
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.grade_id == grade_id,
                AttendanceRecord.record_date.between(start_date, end_date),
            )
            .order_by(AttendanceRecord.record_date.asc(), Class.name, Student.name)
        )

        rows = []
        for record_date, stu_name, stu_no, class_name, status, note in result.all():
            rows.append({
                "date": record_date.isoformat(),
                "student_name": stu_name,
                "student_no": stu_no,
                "class_name": class_name,
                "status": status,
                "status_label": cls.STATUS_LABELS.get(status, status),
                "note": note or "",
            })

        return rows

    # ═══════════════════════════════════════════════════════════════
    #  GAP-1 & GAP-2: 班级考勤历史聚合矩阵 (CASE WHEN 单次扫描)
    # ═══════════════════════════════════════════════════════════════

    @classmethod
    async def get_class_attendance_history(
        cls,
        db: AsyncSession,
        school_id: int,
        class_id: int,
        start_date: date,
        end_date: date,
    ) -> List[Dict]:
        """
        班级考勤历史聚合 — 按天多态状态矩阵

        利用 CASE WHEN 在数据库端单次扫描完成按天归总：
        date | total | present | absent_critical | warning | leave

        性能足以支撑前端 ECharts 折线大盘瞬时轰击。
        """
        stmt = (
            select(
                AttendanceRecord.record_date.label("date"),
                func.count(AttendanceRecord.id).label("total_students"),
                func.sum(case(
                    (AttendanceRecord.status == "present", 1), else_=0
                )).label("present_count"),
                func.sum(case(
                    (AttendanceRecord.status == "absent", 1), else_=0
                )).label("absent_critical_count"),
                func.sum(case(
                    (AttendanceRecord.status.in_(["late", "early"]), 1), else_=0
                )).label("warning_count"),
                func.sum(case(
                    (AttendanceRecord.status == "leave", 1), else_=0
                )).label("leave_count"),
            )
            .where(
                and_(
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.class_id == class_id,
                    AttendanceRecord.record_date >= start_date,
                    AttendanceRecord.record_date <= end_date,
                )
            )
            .group_by(AttendanceRecord.record_date)
            .order_by(AttendanceRecord.record_date.desc())
        )

        res = await db.execute(stmt)
        rows = res.all()

        return [
            {
                "date": str(row.date) if row.date else None,
                "total_students": int(row.total_students or 0),
                "present_count": int(row.present_count or 0),
                "absent_critical_count": int(row.absent_critical_count or 0),
                "warning_count": int(row.warning_count or 0),
                "leave_count": int(row.leave_count or 0),
            }
            for row in rows
        ]
