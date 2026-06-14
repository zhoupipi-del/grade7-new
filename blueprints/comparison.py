"""班级/年级对比分析"""
from flask import Blueprint, render_template, jsonify, request, session
from decorators import login_required, require_role
from models import db, Student, Class, Grade, Score, Exam, DisciplineRecord, Attendance, MentalHealthAssessment, WingsScore
from sqlalchemy import func
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
    for cid in class_ids:
        cls = Class.query.get(cid)
        if not cls:
            continue

        # 学生人数
        student_count = Student.query.filter_by(class_id=cid, is_active=True).count()

        # 平均成绩（最近一次考试）
        latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
        avg_score = 0
        if latest_exam:
            avg = db.session.query(func.avg(Score.score)).filter(
                Score.exam_id == latest_exam.id,
                Score.student_id.in_([s.id for s in cls.students if s.is_active])
            ).scalar()
            avg_score = round(float(avg), 1) if avg else 0

        # 违纪次数（近30天）
        since = datetime.utcnow() - timedelta(days=30)
        disc_count = DisciplineRecord.query.filter(
            DisciplineRecord.class_id == cid,
            DisciplineRecord.created_at >= since
        ).count()

        # 出勤率（近30天）
        att_records = Attendance.query.filter(
            Attendance.class_id == cid,
            Attendance.record_date >= since
        ).all()
        att_rate = 100.0
        if att_records:
            present = sum(1 for a in att_records if a.status == 'present')
            att_rate = round(present / len(att_records) * 100, 1)

        # 心理高风险人数
        mh_high = MentalHealthAssessment.query.filter(
            MentalHealthAssessment.student_id.in_([s.id for s in cls.students if s.is_active]),
            MentalHealthAssessment.risk_level == "high"
        ).count()

        # 五翼均分
        wing_avg = db.session.query(func.avg(WingsScore.score)).filter(
            WingsScore.class_id == cid
        ).scalar() or 0

        result.append({
            "class_id": cid,
            "class_name": cls.name,
            "grade_name": cls.grade.name if cls.grade else "未知",
            "student_count": student_count,
            "avg_score": avg_score,
            "discipline_count": disc_count,
            "attendance_rate": att_rate,
            "mental_high_risk": mh_high,
            "wing_avg": round(float(wing_avg), 1),
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
    since = datetime.utcnow() - timedelta(days=30)

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
