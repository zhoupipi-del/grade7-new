"""
班主任四维工作台
────────────────
一屏聚合：学业趋势 + 纪律红黄牌 + 考勤预警 + 心理风险雷达
"""
from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from functools import wraps
from datetime import datetime, timedelta, date
from sqlalchemy import desc

from app import db
from models import Student, Class, Score, Exam, DisciplineRecord, Attendance, MentalHealthAssessment

dashboard_teacher_bp = Blueprint("dashboard_teacher", __name__, template_folder="../templates")

# ── 权限装饰器 ──
def require_teacher(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        role = session.get("role", "")
        if role not in ("class_teacher", "grade_leader", "ms_admin"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper

# ── 工具函数 ──
def _get_scope():
    """返回当前用户可管理的 class_id 列表，None=全部"""
    role = session.get("role", "")
    class_id = session.get("class_id")
    grade_id = session.get("grade_id")
    if role == "ms_admin":
        return None
    elif role == "grade_leader":
        classes = Class.query.filter_by(grade_id=grade_id).all()
        return [c.id for c in classes]
    else:
        return [class_id] if class_id else []

# ═════════════════════════════════════════════════
#  Route 1: 主面板
# ═════════════════════════════════════════════════
@dashboard_teacher_bp.route("/teacher/dashboard")
@require_teacher
def dashboard():
    role = session.get("role", "")
    class_id = session.get("class_id")

    if role in ("grade_leader", "ms_admin"):
        if role == "ms_admin":
            classes = Class.query.filter_by(is_active=True).order_by(Class.grade_id, Class.name).all()
        else:
            classes = Class.query.filter_by(grade_id=session.get("grade_id"), is_active=True).order_by(Class.name).all()
        return render_template("teacher/dashboard.html",
                           classes=classes, current_class=None, role=role, dimension_data=None)

    if not class_id:
        return "未绑定班级，请联系管理员", 403

    current_class = Class.query.get(class_id)
    dimension_data = _get_dimension_data(class_id)
    return render_template("teacher/dashboard.html",
                           classes=[current_class], current_class=current_class,
                           role=role, dimension_data=dimension_data)

@dashboard_teacher_bp.route("/teacher/dashboard/<int:cid>")
@require_teacher
def dashboard_class(cid):
    scope = _get_scope()
    if scope is not None and cid not in scope:
        return "无权查看该班级", 403

    current_class = Class.query.get_or_404(cid)
    dimension_data = _get_dimension_data(cid)
    role = session.get("role", "")

    if role == "ms_admin":
        classes = Class.query.filter_by(is_active=True).order_by(Class.grade_id, Class.name).all()
    elif role == "grade_leader":
        classes = Class.query.filter_by(grade_id=session.get("grade_id"), is_active=True).order_by(Class.name).all()
    else:
        classes = [current_class]

    return render_template("teacher/dashboard.html",
                           classes=classes, current_class=current_class,
                           role=role, dimension_data=dimension_data)

# ═════════════════════════════════════════════════
#  Route 2: JSON 数据接口
# ═════════════════════════════════════════════════
@dashboard_teacher_bp.route("/teacher/api/dashboard_data")
@require_teacher
def api_dashboard_data():
    class_id = request.args.get("class_id", type=int) or session.get("class_id")
    if not class_id:
        return jsonify({"error": "未指定班级"}), 400
    scope = _get_scope()
    if scope is not None and class_id not in scope:
        return jsonify({"error": "无权查看该班级"}), 403
    data = _get_dimension_data(class_id)
    return jsonify(data)

# ═════════════════════════════════════════════════
#  核心：四维数据聚合
# ═════════════════════════════════════════════════
def _get_dimension_data(class_id):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = date(today.year, today.month, 1)

    return {
        "class_id": class_id,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "academic": _get_academic_trend(class_id),
        "discipline": _get_discipline_alerts(class_id, week_start),
        "attendance": _get_attendance_warnings(class_id, month_start),
        "mental": _get_mental_risk_radar(class_id),
    }

def _get_academic_trend(class_id):
    """最近3次考试全班平均分走势"""
    recent_exams = Exam.query.order_by(desc(Exam.exam_date)).limit(3).all()
    if not recent_exams:
        return {"exams": [], "class_avg": {}}

    scores = Score.query.filter(
        Score.class_id == class_id,
        Score.exam_id.in_([e.id for e in recent_exams]),
        Score.verify_status == "VERIFIED"
    ).all()

    class_avg = {}
    for exam in reversed(recent_exams):
        exam_scores = [s for s in scores if s.exam_id == exam.id]
        if not exam_scores:
            class_avg[exam.name] = {}
            continue
        total = sum(s.score for s in exam_scores)
        count = len(exam_scores)
        class_avg[exam.name] = round(total / count, 1) if count > 0 else 0

    return {
        "exams": [e.name for e in reversed(recent_exams)],
        "class_avg": class_avg,
    }

def _get_discipline_alerts(class_id, week_start):
    """本周违纪记录 + 类型分布"""
    week_records = DisciplineRecord.query.filter(
        DisciplineRecord.class_id == class_id,
        DisciplineRecord.created_at >= week_start,
        DisciplineRecord.status == "active"
    ).all()

    type_dist = {}
    for r in week_records:
        t = r.type or "其他"
        type_dist[t] = type_dist.get(t, 0) + 1

    return {
        "total": len(week_records),
        "type_dist": type_dist,
    }

def _get_attendance_warnings(class_id, month_start):
    """本月出勤率 + 连续缺勤预警"""
    students = Student.query.filter_by(class_id=class_id, is_active=True).all()
    warning_students = []

    for stu in students:
        records = Attendance.query.filter(
            Attendance.student_id == stu.id,
            Attendance.record_date >= month_start
        ).all()
        total = len(records)
        if total == 0:
            continue
        present = sum(1 for r in records if r.status == "present")
        rate = round(present / total * 100, 1)

        # 检查最近5天是否连续缺勤
        recent = Attendance.query.filter(
            Attendance.student_id == stu.id
        ).order_by(desc(Attendance.record_date)).limit(5).all()
        consec_absent = 0
        for r in recent:
            if r.status == "absent":
                consec_absent += 1
            else:
                break

        if consec_absent >= 2 or rate < 80:
            warning_students.append({
                "name": stu.name,
                "rate": rate,
                "consec_absent": consec_absent
            })

    return {
        "month": month_start.strftime("%Y-%m"),
        "warning_students": warning_students[:5],
    }

def _get_mental_risk_radar(class_id):
    """全班心理风险分布"""
    assessments = MentalHealthAssessment.query.filter(
        MentalHealthAssessment.class_id == class_id
    ).all()

    risk_dist = {"high": 0, "medium": 0, "low": 0}
    for a in assessments:
        rl = (a.risk_level or "low").lower()
        if rl in risk_dist:
            risk_dist[rl] += 1

    high_risk = [a for a in assessments if (a.risk_level or "").lower() == "high"]
    high_risk_students = []
    for a in high_risk[:5]:
        stu = Student.query.get(a.student_id)
        if stu:
            high_risk_students.append({
                "name": stu.name,
                "risk_level": a.risk_level,
            })

    return {
        "total": len(assessments),
        "risk_dist": risk_dist,
        "high_risk_students": high_risk_students,
    }
