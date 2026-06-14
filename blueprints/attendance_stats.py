"""考勤统计看板 — 仪表盘/班级对比/每日趋势/异常预警/学生详情"""
from flask import Blueprint, render_template, request, jsonify, session
from models import db, Student, Class, Grade, Attendance, LeaveRequest
from decorators import login_required, require_role
from sqlalchemy import func
from datetime import date, datetime, timedelta
from collections import OrderedDict

attendance_stats_bp = Blueprint("attendance_stats", __name__)


@attendance_stats_bp.before_request
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "parent", "student")
def check_login():
    pass


# ── 首页仪表盘 ──
@attendance_stats_bp.route("/")
def index():
    """概览卡片 + 周趋势柱状图 + 考勤分布饼图"""
    today = date.today()
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    bound_student_id = session.get("bound_student_id")

    # 时间维度筛选
    time_period = request.args.get("period", "week")  # today, week, month, semester
    if time_period == "today":
        date_start = today
        date_end = today
    elif time_period == "week":
        date_start = today - timedelta(days=today.weekday())
        date_end = date_start + timedelta(days=6)
    elif time_period == "month":
        date_start = today.replace(day=1)
        if today.month == 12:
            date_end = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
        else:
            date_end = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    elif time_period == "semester":
        # 假设上学期9-1月，下学期2-6月
        if today.month >= 9 or today.month <= 1:
            date_start = today.replace(month=9, day=1)
            date_end = today.replace(year=today.year+1, month=1, day=31)
        else:
            date_start = today.replace(month=2, day=1)
            date_end = today.replace(month=6, day=30)
    else:
        date_start = today - timedelta(days=today.weekday())
        date_end = date_start + timedelta(days=6)

    # 数据范围过滤
    base_q = Attendance.query.filter(
        Attendance.record_date >= date_start,
        Attendance.record_date <= date_end
    )
    if role == "grade_leader" and grade_id:
        base_q = base_q.filter(Attendance.grade_id == grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        base_q = base_q.filter(Attendance.class_id == class_id)
    elif role == "parent" and bound_student_id:
        base_q = base_q.filter(Attendance.student_id == bound_student_id)
    elif role == "student":
        sid = session.get("student_id")
        if sid:
            base_q = base_q.filter(Attendance.student_id == sid)

    period_records = base_q.all()

    # 统计卡片数据
    cards = {
        "today_present": sum(1 for r in period_records if r.status == "present"),
        "today_late": sum(1 for r in period_records if r.status == "late"),
        "today_absent": sum(1 for r in period_records if r.status == "absent"),
        "today_leave": sum(1 for r in period_records if r.status in ("leave", "early")),
    }

    # 趋势图数据（按天）
    trend_labels = []
    trend_present = []
    trend_absent = []
    trend_late = []
    trend_leave = []

    current = date_start
    while current <= date_end:
        trend_labels.append(current.strftime("%m/%d"))
        day_recs = [r for r in period_records if r.record_date == current]
        trend_present.append(sum(1 for r in day_recs if r.status == "present"))
        trend_absent.append(sum(1 for r in day_recs if r.status == "absent"))
        trend_late.append(sum(1 for r in day_recs if r.status == "late"))
        trend_leave.append(sum(1 for r in day_recs if r.status in ("leave", "early")))
        current += timedelta(days=1)

    # 考勤分布饼图数据
    total_count = len(period_records)
    pie_data = [
        sum(1 for r in period_records if r.status == "present"),
        sum(1 for r in period_records if r.status == "late"),
        sum(1 for r in period_records if r.status == "absent"),
        sum(1 for r in period_records if r.status in ("leave", "early")),
    ]
    pie_labels = ["出勤", "迟到", "缺勤", "请假/早退"]
    pie_colors = ["#28a745", "#ffc107", "#dc3545", "#17a2b8"]

    # 班级对比数据（仅德育处和年级组长）
    class_comparison = []
    if role in ("ms_admin", "grade_leader"):
        if role == "ms_admin":
            classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
        else:
            classes = Class.query.filter_by(grade_id=grade_id, is_active=True).order_by(Class.name).all()

        for cls in classes:
            cls_records = [r for r in period_records if r.class_id == cls.id]
            total_students = Student.query.filter_by(class_id=cls.id, is_active=True).count()
            if total_students == 0:
                continue
            present_rate = round(sum(1 for r in cls_records if r.status == "present") / max(len(cls_records), 1) * 100, 1)
            absent_rate = round(sum(1 for r in cls_records if r.status == "absent") / max(len(cls_records), 1) * 100, 1)
            class_comparison.append({
                "name": cls.name,
                "present_rate": present_rate,
                "absent_rate": absent_rate,
                "total": len(cls_records)
            })
        class_comparison.sort(key=lambda x: x["absent_rate"], reverse=True)

    return render_template("attendance_stats/index.html",
                           cards=cards,
                           time_period=time_period,
                           trend_labels=trend_labels,
                           trend_present=trend_present,
                           trend_absent=trend_absent,
                           trend_late=trend_late,
                           trend_leave=trend_leave,
                           pie_data=pie_data,
                           pie_labels=pie_labels,
                           pie_colors=pie_colors,
                           class_comparison=class_comparison)


# ── 按班级统计 ──
@attendance_stats_bp.route("/class")
@login_required
@require_role("ms_admin", "grade_leader")
def class_stats():
    """缺勤率排行 / 迟到排行"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")

    classes_q = Class.query.filter_by(is_active=True)
    if role == "grade_leader" and grade_id:
        classes_q = classes_q.filter_by(grade_id=grade_id)
    classes = classes_q.order_by(Class.name).all()

    today = date.today()

    class_rows = []
    for cls in classes:
        total_students = Student.query.filter_by(
            class_id=cls.id, is_active=True).count()
        if total_students == 0:
            continue

        # 今日出勤情况
        today_att = Attendance.query.filter(
            Attendance.class_id == cls.id,
            Attendance.record_date == today,
        ).all()

        absent_count = sum(1 for r in today_att if r.status == "absent")
        late_count = sum(1 for r in today_att if r.status == "late")
        present_count = sum(1 for r in today_att if r.status == "present")
        leave_count = sum(1 for r in today_att if r.status in ("leave", "early"))
        recorded = absent_count + late_count + present_count + leave_count

        absence_rate = round(absent_count / recorded * 100, 1) if recorded > 0 else 0
        late_rate = round(late_count / recorded * 100, 1) if recorded > 0 else 0

        class_rows.append({
            "class": cls,
            "total": total_students,
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
            "leave": leave_count,
            "recorded": recorded,
            "absence_rate": absence_rate,
            "late_rate": late_rate,
        })

    # 按缺勤率排序
    class_rows.sort(key=lambda x: x["absence_rate"], reverse=True)

    return render_template("attendance_stats/class.html",
                           class_rows=class_rows, today=today)


# ── 每日考勤趋势 ──
@attendance_stats_bp.route("/daily")
@login_required
@require_role("ms_admin", "grade_leader")
def daily_trend():
    """日期范围选择 + 折线图"""
    today = date.today()
    start_str = request.args.get("start", (today - timedelta(days=30)).isoformat())
    end_str = request.args.get("end", today.isoformat())

    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except ValueError:
        start_date = today - timedelta(days=30)
        end_date = today

    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 查询范围内所有考勤记录
    q = Attendance.query.filter(
        Attendance.record_date >= start_date,
        Attendance.record_date <= end_date,
    )
    if role == "grade_leader" and grade_id:
        q = q.filter(Attendance.grade_id == grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        q = q.filter(Attendance.class_id == class_id)

    records = q.order_by(Attendance.record_date.asc()).all()

    # 按日期聚合
    daily_map = OrderedDict()
    current = start_date
    while current <= end_date:
        daily_map[current] = {"total": 0, "present": 0, "absent": 0, "late": 0}
        current += timedelta(days=1)

    for r in records:
        if r.record_date in daily_map:
            daily_map[r.record_date]["total"] += 1
            if r.status == "present":
                daily_map[r.record_date]["present"] += 1
            elif r.status == "absent":
                daily_map[r.record_date]["absent"] += 1
            elif r.status == "late":
                daily_map[r.record_date]["late"] += 1

    labels = [d.isoformat() for d in daily_map]
    rate_data = []
    for d, v in daily_map.items():
        if v["total"] > 0:
            rate_data.append(round(v["present"] / v["total"] * 100, 1))
        else:
            rate_data.append(None)

    return render_template("attendance_stats/daily.html",
                           labels=labels,
                           rate_data=rate_data,
                           daily_map=daily_map,
                           start_date=start_date,
                           end_date=end_date)


# ── 异常预警 ──
@attendance_stats_bp.route("/anomalies")
def anomalies():
    """连续缺勤>=3天 或 周迟到>=3次的学生列表"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    bound_student_id = session.get("bound_student_id")
    student_id = session.get("student_id")

    # 确定学生查询范围
    students_q = Student.query.filter_by(is_active=True)
    if role == "grade_leader" and grade_id:
        students_q = students_q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        students_q = students_q.filter_by(class_id=class_id)
    elif role == "parent" and bound_student_id:
        students_q = students_q.filter_by(id=bound_student_id)
    elif role == "student" and student_id:
        students_q = students_q.filter_by(id=student_id)
    # ms_admin: 全部学生

    all_students = students_q.all()
    anomaly_list = []
    today = date.today()

    for stu in all_students:
        warnings = []

        # 获取该学生最近60天考勤，按日期排序
        records = Attendance.query.filter(
            Attendance.student_id == stu.id,
            Attendance.record_date >= today - timedelta(days=60),
        ).order_by(Attendance.record_date.asc()).all()

        # 检查连续缺勤 >= 3天
        consecutive = 0
        max_consecutive = 0
        last_date = None
        for r in records:
            if r.status == "absent":
                if last_date and (r.record_date - last_date).days <= 1:
                    consecutive += 1
                else:
                    consecutive = 1
                max_consecutive = max(max_consecutive, consecutive)
                last_date = r.record_date
            else:
                consecutive = 0
                last_date = None

        if max_consecutive >= 3:
            warnings.append({
                "type": "consecutive_absent",
                "level": "danger",
                "text": f"连续缺勤 {max_consecutive} 天",
                "days": max_consecutive,
            })

        # 检查本周迟到次数 >= 3
        week_start = today - timedelta(days=today.weekday())
        week_late = sum(
            1 for r in records
            if r.status == "late" and r.record_date >= week_start
        )
        if week_late >= 3:
            warnings.append({
                "type": "weekly_late",
                "level": "warning",
                "text": f"本周已迟到 {week_late} 次",
                "days": week_late,
            })

        # 检查本月缺勤次数 >= 5
        month_start = today.replace(day=1)
        month_absent = sum(
            1 for r in records
            if r.status == "absent" and r.record_date >= month_start
        )
        if month_absent >= 5:
            warnings.append({
                "type": "monthly_absent",
                "level": "warning",
                "text": f"本月已缺勤 {month_absent} 次",
                "days": month_absent,
            })

        if warnings:
            anomaly_list.append({
                "student": stu,
                "warnings": warnings,
                "max_level": "danger" if any(w["level"] == "danger" for w in warnings) else "warning",
            })

    # 排序：危险优先
    anomaly_list.sort(key=lambda x: (0 if x["max_level"] == "danger" else 1))

    return render_template("attendance_stats/anomalies.html",
                           anomaly_list=anomaly_list)


# ── 学生考勤详情（日历热力图） ──
@attendance_stats_bp.route("/detail/<int:sid>")
def student_detail(sid):
    """日历热力图 + 历史记录表"""
    student = Student.query.get_or_404(sid)

    # 权限检查：只能查看权限范围内的学生
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    bound_student_id = session.get("bound_student_id")

    allowed = False
    if role == "ms_admin":
        allowed = True
    elif role == "grade_leader" and student.grade_id == grade_id:
        allowed = True
    elif role in ("class_teacher", "teacher") and student.class_id == class_id:
        allowed = True
    elif role == "parent" and student.id == bound_student_id:
        allowed = True
    elif role == "student" and student.id == session.get("student_id"):
        allowed = True

    if not allowed:
        from flask import flash as _flash, redirect as _redir, url_for as _url_for
        _flash("无权查看此学生的考勤详情", "danger")
        return _redir(_url_for("attendance_stats.index"))

    today = date.today()
    # 最近90天的考勤记录
    since = today - timedelta(days=90)
    records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= since,
    ).order_by(Attendance.record_date.desc()).all()

    # 构建日期->状态的映射
    status_map = {}
    for r in records:
        status_map[r.record_date] = r.status

    # 日历热力图数据（最近30天，按周排列）
    calendar_start = today - timedelta(days=29)
    calendar_days = []
    for i in range(30):
        d = calendar_start + timedelta(days=i)
        calendar_days.append({
            "date": d,
            "weekday": d.weekday(),
            "status": status_map.get(d),
        })

    # 分成周
    weeks = []
    for w_start in range(0, 30, 7):
        week_chunk = calendar_days[w_start:w_start + 7]
        if week_chunk:
            weeks.append(week_chunk)

    # 状态颜色映射
    status_colors = {
        "present": "#28a745",
        "late": "#ffc107",
        "absent": "#dc3545",
        "leave": "#17a2b8",
        "early": "#fd7e14",
    }

    return render_template("attendance_stats/detail.html",
                           student=student,
                           weeks=weeks,
                           recent_records=records[:50],
                           status_colors=status_colors,
                           today=today)
