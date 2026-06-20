"""考勤服务层 — 封装考勤/请假 CRUD，注入 school_id 多租户隔离。

从 ms.py / grade.py / class_.py / parent_portal.py 四蓝图抽取。
消灭 N+1 查询，统一异常处理，为 SaaS 模块化奠基。
"""

from datetime import date, timedelta
from collections import OrderedDict, defaultdict

from models import db, Attendance, LeaveRequest, Student, Class
from services.base import BaseService


class AttendanceService(BaseService):
    """考勤管理服务。

    Usage:
        svc = AttendanceService(school_id=session.get("school_id", 1))
        result = svc.get_class_attendance(class_id=5)
    """

    # ─────────────────────────────────────────────
    #  考勤录入
    # ─────────────────────────────────────────────

    def record_class_attendance(self, class_id, grade_id, status_map,
                                 record_date=None, note_map=None, user_id=None):
        """批量录入班级考勤（替代 class_.py:588-620 和 grade.py:385-423）。

        Args:
            class_id: 班级ID
            grade_id: 年级ID
            status_map: {student_id: status} — "present"/"late"/"early"/"absent"/"leave"
            record_date: 考勤日期，默认今天
            note_map: {student_id: note_text} 可选备注
            user_id: 操作人ID（用于通知）

        Returns:
            dict: {"created": N, "absent_ids": [...], "late_ids": [...]}
        """
        if record_date is None:
            record_date = date.today()

        # 批量删除当日已有记录（幂等覆盖）
        student_ids = list(status_map.keys())
        if student_ids:
            Attendance.query.filter(
                Attendance.student_id.in_(student_ids),
                Attendance.record_date == record_date,
                Attendance.school_id == self.school_id,
            ).delete(synchronize_session=False)

        absent_ids = []
        late_ids = []
        created = 0

        for sid, status_val in status_map.items():
            db.session.add(Attendance(
                student_id=sid,
                class_id=class_id,
                grade_id=grade_id,
                status=status_val,
                record_date=record_date,
                note=(note_map or {}).get(sid, ""),
                school_id=self.school_id,
            ))
            created += 1

            if status_val == "absent":
                absent_ids.append(sid)
            elif status_val == "late":
                late_ids.append(sid)

        self.commit()

        self.logger.info(
            "考勤录入完成 class=%d date=%s created=%d absent=%d late=%d",
            class_id, record_date.isoformat(), created, len(absent_ids), len(late_ids)
        )

        return {
            "created": created,
            "absent_ids": absent_ids,
            "late_ids": late_ids,
            "record_date": record_date,
        }

    # ─────────────────────────────────────────────
    #  考勤查询
    # ─────────────────────────────────────────────

    def get_class_attendance(self, class_id, record_date=None):
        """获取某班级某日考勤（返回 {student_id: status} 字典）。

        替代: class_.py:622-624 的 today_records 局部查询
        """
        if record_date is None:
            record_date = date.today()

        records = (Attendance.query
                   .filter(Attendance.class_id == class_id,
                           Attendance.record_date == record_date,
                           Attendance.school_id == self.school_id)
                   .all())
        return {r.student_id: r.status for r in records}

    def get_attendance_history(self, class_id, days=30):
        """获取班级考勤历史（按日期分组 + 统计）。

        替代: class_.py:631-672 attendance_history()
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        # 一次性查询 + joinedload 消灭 N+1
        records = (Attendance.query
                   .filter(Attendance.class_id == class_id,
                           Attendance.record_date >= start_date,
                           Attendance.record_date <= end_date,
                           Attendance.school_id == self.school_id)
                   .order_by(Attendance.record_date.desc())
                   .all())

        # 按日期分组
        records_by_date = OrderedDict()
        for r in records:
            d = r.record_date
            if d not in records_by_date:
                records_by_date[d] = []
            records_by_date[d].append(r)

        # 统计
        stats = {"present": 0, "late": 0, "early": 0, "absent": 0, "leave": 0}
        for r in records:
            stats[r.status] = stats.get(r.status, 0) + 1

        # 批量加载学生信息（消灭 N+1）
        student_map = self.batch_load(
            Student,
            list(set(r.student_id for r in records)),
            school_id=self.school_id,
        )

        return {
            "records_by_date": records_by_date,
            "stats": stats,
            "total": len(records),
            "students": student_map,
        }

    def get_grade_attendance_summary(self, grade_id, record_date=None):
        """获取年级考勤概览（各班统计汇总）。

        替代: grade.py:139-148 attendance_overview()
        """
        if record_date is None:
            record_date = date.today()

        records = (Attendance.query
                   .filter(Attendance.grade_id == grade_id,
                           Attendance.record_date == record_date,
                           Attendance.school_id == self.school_id)
                   .all())

        # 按班级汇总
        from collections import Counter
        class_stats = defaultdict(lambda: Counter())
        for r in records:
            class_stats[r.class_id][r.status] += 1

        return {
            "record_date": record_date,
            "class_stats": dict(class_stats),
            "total": len(records),
        }

    # ─────────────────────────────────────────────
    #  请假管理
    # ─────────────────────────────────────────────

    def get_class_leaves(self, class_id, status_filter=None, page=1, per_page=20):
        """获取班级请假列表（分页）。

        替代: class_.py:677-687 leave_list()
        """
        q = (LeaveRequest.query
             .filter(LeaveRequest.class_id == class_id,
                     LeaveRequest.school_id == self.school_id)
             .order_by(LeaveRequest.created_at.desc()))

        if status_filter:
            q = q.filter(LeaveRequest.status == status_filter)

        pagination = q.paginate(page=page, per_page=per_page, error_out=False)

        # 批量加载学生信息
        student_ids = [leave.student_id for leave in pagination.items]
        students = self.batch_load(Student, list(set(student_ids)), school_id=self.school_id)

        return {
            "leaves": pagination.items,
            "pagination": pagination,
            "students": students,
        }

    def approve_leave(self, leave_id, approver_role, approved=True):
        """审批请假（班主任初审 / 年级组长终审）。

        替代: class_.py:688-... approve_leave() + grade.py:160-... approve_leave()
        """
        leave = (LeaveRequest.query
                 .filter(LeaveRequest.id == leave_id,
                         LeaveRequest.school_id == self.school_id)
                 .first())
        if not leave:
            raise ValueError(f"请假记录不存在: #{leave_id}")

        if approver_role == "class_teacher":
            leave.status = "class_approved" if approved else "rejected"
            leave.class_approved_at = self.now()
        elif approver_role == "grade_leader":
            leave.status = "grade_approved" if approved else "rejected"
            leave.grade_approved_at = self.now()

        self.commit()

        self.logger.info(
            "请假审批 leave=%d role=%s approved=%s status=%s",
            leave_id, approver_role, approved, leave.status
        )

        return leave

    def create_leave_attendance(self, leave):
        """请假批准后自动创建考勤记录。

        替代: grade.py:427-464 _create_leave_attendance()
        """
        if leave.status != "grade_approved":
            return 0

        # 获取已有考勤日期（批量查询，避免 N+1）
        existing_dates = set(
            r[0] for r in db.session.query(Attendance.record_date).filter(
                Attendance.student_id == leave.student_id,
                Attendance.record_date >= leave.start_date,
                Attendance.record_date <= leave.end_date,
                Attendance.school_id == self.school_id,
            ).all()
        )

        count = 0
        current = leave.start_date
        while current <= leave.end_date:
            if current not in existing_dates:
                db.session.add(Attendance(
                    student_id=leave.student_id,
                    class_id=leave.class_id,
                    grade_id=leave.grade_id,
                    status="leave",
                    record_date=current,
                    note=f"请假：{(leave.reason or '')[:50]}",
                    school_id=self.school_id,
                ))
                count += 1
            current += timedelta(days=1)

        if count > 0:
            self.commit()
            self.logger.info(
                "请假# %d 批准 → 自动创建 %d 条考勤记录", leave.id, count
            )

        return count

    # ─────────────────────────────────────────────
    #  家长端
    # ─────────────────────────────────────────────

    def get_student_attendance(self, student_id, days=30):
        """获取单个学生考勤历史（家长端）。

        替代: parent_portal.py:124-... attendance()
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        records = (Attendance.query
                   .filter(Attendance.student_id == student_id,
                           Attendance.record_date >= start_date,
                           Attendance.record_date <= end_date,
                           Attendance.school_id == self.school_id)
                   .order_by(Attendance.record_date.desc())
                   .all())

        stats = {"present": 0, "late": 0, "early": 0, "absent": 0, "leave": 0}
        for r in records:
            stats[r.status] = stats.get(r.status, 0) + 1

        total_days = max(len(records), 1)
        attendance_rate = round(stats["present"] / total_days * 100, 1)

        return {
            "records": records,
            "stats": stats,
            "attendance_rate": attendance_rate,
            "total_days": total_days,
        }
