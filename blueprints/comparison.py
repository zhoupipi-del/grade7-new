"""班级/年级对比分析"""
from flask import Blueprint, render_template, jsonify, request, session
from decorators import login_required, require_role
from models import db, Student, Class, Grade, Score, Exam, DisciplineRecord, Attendance, MentalHealthAssessment, WingsScore
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from utils import get_local_now
from datetime import datetime, timedelta

comparison_bp = Blueprint("comparison", __name__, url_prefix="/comparison")

# ── 路由：班级对比页 ──
@comparison_bp.route("/classes")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def classes_comparison():
    return render_template("comparison/classes.html")

# ── 路由：年级对比页 ──
@comparison_bp.route("/grades")
@login_required
@require_role("ms_admin", "grade_leader")
def grades_comparison():
    return render_template("comparison/grades.html")

# ── API：班级对比数据 ──
@comparison_bp.route("/api/classes")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def api_classes_comparison():
    role = session.get("role", "")
    my_class_id = session.get("class_id")

    class_ids = request.args.getlist("class_ids[]", type=int)

    # 班主任强制只能看自己班
    if role == "class_teacher" and my_class_id:
        class_ids = [my_class_id]
    elif not class_ids:
        # 默认返回所有活跃班级
        classes = Class.query.filter_by(is_active=True).limit(20).all()
        class_ids = [c.id for c in classes]

    result = []
    # 批量预加载班级（含年级），消除 N+1 的 Class.query.get
    classes_list = Class.query.options(joinedload(Class.grade)).filter(Class.id.in_(class_ids)).all()
    class_map = {c.id: c for c in classes_list}

    # 批量获取各班学生 ID 列表
    student_rows = db.session.query(
        Student.class_id, Student.id
    ).filter(
        Student.class_id.in_(class_ids),
        Student.is_active == True,
    ).all()
    class_student_ids = {}
    for s in student_rows:
        class_student_ids.setdefault(s.class_id, []).append(s.id)

    # 最近一次考试
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()

    # 批量查询各班平均成绩
    class_avg_scores = {}
    if latest_exam:
        avg_rows = db.session.query(
            Student.class_id, func.avg(Score.score).label("avg")
        ).join(Score, Score.student_id == Student.id).filter(
            Student.class_id.in_(class_ids),
            Student.is_active == True,
            Score.exam_id == latest_exam.id,
        ).group_by(Student.class_id).all()
        class_avg_scores = {r.class_id: round(float(r.avg), 1) if r.avg else 0 for r in avg_rows}

    # 批量查询各班违纪次数
    since = get_local_now() - timedelta(days=30)
    disc_rows = db.session.query(
        DisciplineRecord.class_id, func.count(DisciplineRecord.id)
    ).filter(
        DisciplineRecord.class_id.in_(class_ids),
        DisciplineRecord.created_at >= since
    ).group_by(DisciplineRecord.class_id).all()
    disc_counts = {r.class_id: r[1] for r in disc_rows}

    # 批量查询各班出勤率
    att_rows = db.session.query(
        Attendance.class_id,
        func.count(Attendance.id).label("total"),
        func.sum(func.IIF(Attendance.status == 'present', 1, 0)).label("present"),
    ).filter(
        Attendance.class_id.in_(class_ids),
        Attendance.record_date >= since
    ).group_by(Attendance.class_id).all()
    att_rates = {}
    for r in att_rows:
        att_rates[r.class_id] = round(float(r.present) / r.total * 100, 1) if r.total else 100.0

    # 批量查询心理高风险人数
    mh_rows = db.session.query(
        Student.class_id, func.count(MentalHealthAssessment.id)
    ).join(MentalHealthAssessment, MentalHealthAssessment.student_id == Student.id).filter(
        Student.class_id.in_(class_ids),
        Student.is_active == True,
        MentalHealthAssessment.risk_level == "high"
    ).group_by(Student.class_id).all()
    mh_counts = {r.class_id: r[1] for r in mh_rows}

    # 批量查询五翼均分
    wing_rows = db.session.query(
        WingsScore.class_id, func.avg(WingsScore.score).label("avg")
    ).filter(WingsScore.class_id.in_(class_ids)).group_by(WingsScore.class_id).all()
    wing_avgs = {r.class_id: round(float(r.avg), 1) if r.avg else 0 for r in wing_rows}

    # 组装结果
    for cid in class_ids:
        cls = class_map.get(cid)
        if not cls:
            continue

        sids = class_student_ids.get(cid, [])
        result.append({
            "class_id": cid,
            "class_name": cls.name,
            "grade_name": cls.grade.name if cls.grade else "未知",
            "student_count": len(sids),
            "avg_score": class_avg_scores.get(cid, 0),
            "discipline_count": disc_counts.get(cid, 0),
            "attendance_rate": att_rates.get(cid, 100.0),
            "mental_high_risk": mh_counts.get(cid, 0),
            "wing_avg": wing_avgs.get(cid, 0),
        })

    return jsonify({
        "classes": result,
        "latest_exam_name": latest_exam.name if latest_exam else "暂无考试",
    })

# ── API：年级对比数据 ──
@comparison_bp.route("/api/grades")
@login_required
@require_role("ms_admin", "grade_leader")
def api_grades_comparison():
    grade_ids = request.args.getlist("grade_ids[]", type=int)
    if not grade_ids:
        grades = Grade.query.all()
        grade_ids = [g.id for g in grades]

    # ── 批量预加载（1 次查询替代 N×6 次循环查询） ──
    since = get_local_now() - timedelta(days=30)

    # 最近一次考试（所有年级共用，只查一次）
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()

    # 学生人数 / 班级数 — 单次 GROUP BY
    stu_cnt_map = dict(db.session.query(
        Student.grade_id, func.count(Student.id)
    ).filter(Student.grade_id.in_(grade_ids), Student.is_active == True).group_by(Student.grade_id).all())
    class_cnt_map = dict(db.session.query(
        Class.grade_id, func.count(Class.id)
    ).filter(Class.grade_id.in_(grade_ids), Class.is_active == True).group_by(Class.grade_id).all())

    # 平均成绩（批量聚合）
    avg_score_map = {}
    if latest_exam:
        avg_rows = db.session.query(
            Student.grade_id, func.avg(Score.score).label("avg")
        ).join(Score, Score.student_id == Student.id).filter(
            Student.grade_id.in_(grade_ids),
            Student.is_active == True,
            Score.exam_id == latest_exam.id
        ).group_by(Student.grade_id).all()
        avg_score_map = {row[0]: round(float(row[1]), 1) for row in avg_rows if row[1]}

    # 违纪次数（近30天） — 单次 GROUP BY
    disc_map = dict(db.session.query(
        DisciplineRecord.grade_id, func.count(DisciplineRecord.id)
    ).filter(
        DisciplineRecord.grade_id.in_(grade_ids),
        DisciplineRecord.created_at >= since
    ).group_by(DisciplineRecord.grade_id).all())

    # 出勤率（近30天） — 单次 GROUP BY
    att_rows = db.session.query(
        Attendance.grade_id,
        func.count().label("total"),
        func.sum(func.if_(Attendance.status == "present", 1, 0)).label("present")
    ).filter(
        Attendance.grade_id.in_(grade_ids),
        Attendance.record_date >= since
    ).group_by(Attendance.grade_id).all()
    att_map = {}
    for row in att_rows:
        total, present = int(row[1]), int(row[2] or 0)
        att_map[row[0]] = round(present / total * 100, 1) if total > 0 else 100.0

    # 心理高风险人数 — 单次 GROUP BY
    mh_map = dict(db.session.query(
        Student.grade_id, func.count(MentalHealthAssessment.id)
    ).join(MentalHealthAssessment, MentalHealthAssessment.student_id == Student.id).filter(
        Student.grade_id.in_(grade_ids),
        Student.is_active == True,
        MentalHealthAssessment.risk_level == "high"
    ).group_by(Student.grade_id).all())

    # 年级名称 — 批量加载
    grade_obj_map = {g.id: g for g in Grade.query.filter(Grade.id.in_(grade_ids)).all()}

    result = []
    for gid in grade_ids:
        grade = grade_obj_map.get(gid)
        if not grade:
            continue
        result.append({
            "grade_id": gid,
            "grade_name": grade.name,
            "student_count": stu_cnt_map.get(gid, 0),
            "class_count": class_cnt_map.get(gid, 0),
            "avg_score": avg_score_map.get(gid, 0),
            "discipline_count": int(disc_map.get(gid, 0)),
            "attendance_rate": att_map.get(gid, 100.0),
            "mental_high_risk": int(mh_map.get(gid, 0)),
        })

    return jsonify({
        "grades": result,
        "latest_exam_name": latest_exam.name if latest_exam else "暂无考试",
    })
