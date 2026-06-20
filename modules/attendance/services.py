"""
modules/attendance/services.py — 考勤业务逻辑

封装考勤录入、查询、统计、请假审批等核心操作。
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AttendanceRecord, LeaveRequest
from core.models import Student, Class, Grade


class AttendanceService:
    """考勤管理服务"""

    STATUS_LABELS = {
        "present": "出勤",
        "late": "迟到",
        "early": "早退",
        "absent": "缺勤",
        "leave": "请假",
    }

    VALID_STATUSES = frozenset(STATUS_LABELS.keys())

    # ── 考勤录入 ──

    @classmethod
    async def batch_record(
        cls,
        db: AsyncSession,
        school_id: int,
        class_id: int,
        grade_id: int,
        record_date: date,
        records: List[Dict],  # [{"student_id": 1, "status": "present", "note": ""}]
    ) -> int:
        """
        批量录入某班级某日的考勤数据。

        幂等设计: 先清除当日已有记录，再写入新记录。
        返回写入的记录数。
        """
        # 验证状态值
        for rec in records:
            if rec["status"] not in cls.VALID_STATUSES:
                raise ValueError(f"无效考勤状态: {rec['status']}")

        student_ids = [r["student_id"] for r in records]

        # 幂等: 删除当日已有记录
        await db.execute(
            delete(AttendanceRecord).where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.class_id == class_id,
                AttendanceRecord.record_date == record_date,
                AttendanceRecord.student_id.in_(student_ids),
            )
        )

        # 批量写入
        now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
        new_records = []
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

        db.add_all(new_records)
        await db.commit()

        return len(new_records)

    # ── 考勤查询 ──

    @classmethod
    async def get_class_attendance(
        cls,
        db: AsyncSession,
        school_id: int,
        class_id: int,
        record_date: date,
    ) -> List[Dict]:
        """获取某班级某日的考勤详情"""
        result = await db.execute(
            select(AttendanceRecord, Student.name, Student.student_no)
            .join(Student, AttendanceRecord.student_id == Student.id)
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.class_id == class_id,
                AttendanceRecord.record_date == record_date,
            )
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
                "note": r.note,
            }
            for r in records
        ]

    # ── 考勤统计 ──

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
        异常预警: 检测近 N 天内
        - 连续缺勤 ≥ 3 天
        - 或周迟到 ≥ 3 次
        的学生
        """
        since = date.today() - timedelta(days=days)

        # 查询异常学生
        result = await db.execute(
            select(
                AttendanceRecord.student_id,
                AttendanceRecord.status,
                func.count(AttendanceRecord.id).label("cnt"),
            )
            .where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.record_date >= since,
                AttendanceRecord.status.in_(["absent", "late"]),
            )
            .group_by(AttendanceRecord.student_id, AttendanceRecord.status)
        )

        student_alerts: Dict[int, Dict] = defaultdict(lambda: {"absent": 0, "late": 0})
        for student_id, status, cnt in result.all():
            student_alerts[student_id][status] = cnt

        # 筛选达到阈值的
        alerts = []
        for student_id, counts in student_alerts.items():
            if counts["absent"] >= 3 or counts["late"] >= 3:
                alerts.append({
                    "student_id": student_id,
                    "absent_days": counts["absent"],
                    "late_count": counts["late"],
                    "period_days": days,
                })

        # 补充学生姓名
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

    # ── 请假管理 ──

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
        """家长提交请假申请"""
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
            raise ValueError(f"请假申请不存在: {leave_id}")

        now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

        if approver_role == "class_teacher":
            leave.status = "class_approved"
            leave.approved_by_class = approver_id
            leave.approved_at_class = now
        elif approver_role == "grade_leader":
            leave.status = "grade_approved"
            leave.approved_by_grade = approver_id
            leave.approved_at_grade = now

            # 审批通过后自动创建考勤记录
            current = leave.start_date
            att_records = []
            while current <= leave.end_date:
                att = AttendanceRecord(
                    school_id=leave.school_id,
                    student_id=leave.student_id,
                    class_id=leave.class_id,
                    grade_id=leave.grade_id,
                    status="leave",
                    record_date=current,
                    note=f"请假: {leave.reason[:50]}",
                )
                att_records.append(att)
                current += timedelta(days=1)

            db.add_all(att_records)

        await db.commit()
        await db.refresh(leave)
        return leave
