"""ML数学模型演示 — 成绩预测/心理风险/违纪预测/综合素质预测/成长预测"""
import os
import json as json_mod
from flask import Blueprint, render_template, jsonify, request, session, current_app
from decorators import login_required, require_role
from models import db, Student, Score, DisciplineRecord, Attendance, PsychSurvey, QualityScore, Exam, MentalHealthAssessment, RiskRecord, Class
from decorators import require_role
from utils import get_local_now
from datetime import date, datetime, timedelta
from sqlalchemy import text, func
import random

ml_models_bp = Blueprint("ml_models", __name__, url_prefix="/ml")

# ── 路由：成绩预测演示页 ──
@ml_models_bp.route("/grade-prediction")
@login_required
def grade_prediction():
    return render_template("ml_models/grade_prediction.html")

# ── 路由：心理风险演示页 ──
@ml_models_bp.route("/mental-risk")
@login_required
def mental_risk():
    return render_template("ml_models/mental_risk.html")

# ── 路由：违纪预测演示页 ──
@ml_models_bp.route("/discipline-prediction")
@login_required
def discipline_prediction():
    return render_template("ml_models/discipline_prediction.html")

# ── 路由：综合素质预测演示页 ──
@ml_models_bp.route("/quality-prediction")
@login_required
def quality_prediction():
    return render_template("ml_models/quality_prediction.html")

# ── 路由：成长预测演示页 ──
@ml_models_bp.route("/growth-prediction")
@login_required
def growth_prediction():
    return render_template("ml_models/growth_prediction.html")

# ── 路由：相似学生推荐演示页 ──
@ml_models_bp.route("/similar-students")
@login_required
def similar_students():
    return render_template("ml_models/similar_students.html")

# ── 路由：ML模型总览页 ──

# ── 辅助 API：班级列表（供成长预测/相似学生推荐下拉使用）──
@ml_models_bp.route("/api/classes")
@login_required
def api_classes():
    """返回当前用户可见的班级列表"""
    role = session.get("role", "")
    class_id = session.get("class_id")
    grade_id = session.get("grade_id")

    if role == "class_teacher" and class_id:
        classes = Class.query.filter_by(id=class_id, is_active=True).all()
    elif role in ("ms_admin", "grade_leader") and grade_id:
        classes = Class.query.filter_by(grade_id=grade_id, is_active=True).order_by(Class.name).all()
    else:
        classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()

    return jsonify({
        "classes": [{"id": c.id, "name": c.name, "grade_name": c.grade.name if c.grade else ""} for c in classes]
    })

# ── 辅助 API：学生列表（按班级）──
@ml_models_bp.route("/api/students")
@login_required
def api_students():
    """返回指定班级的学生列表"""
    class_id_param = request.args.get("class_id", type=int)
    role = session.get("role", "")
    my_class_id = session.get("class_id")

    # 班主任只能查自己班
    if role == "class_teacher" and my_class_id:
        class_id_param = my_class_id
    elif not class_id_param:
        return jsonify({"students": []})

    students = Student.query.filter_by(class_id=class_id_param, is_active=True).order_by(Student.name).all()
    return jsonify({
        "students": [
            {"id": s.id, "name": s.name, "student_no": s.student_no, "class_id": s.class_id}
            for s in students
        ]
    })

# ── 路由：ML模型总览页 ──
@ml_models_bp.route("/")
@login_required
def ml_index():
    return render_template("ml_models/index.html")


# ── API：成长预测（根据历史数据预测下学期趋势）──
@ml_models_bp.route("/api/growth-prediction/<int:sid>")
@login_required
def api_growth_prediction(sid):
    """预测学生下学期成长趋势"""
    student = Student.query.get_or_404(sid)
    
    # 1. 成绩趋势预测
    exams = Exam.query.order_by(Exam.exam_date.asc()).limit(5).all()
    score_trend = []
    for exam in exams:
        avg_score = db.session.query(func.avg(Score.score)).filter(
            Score.exam_id == exam.id,
            Score.student_id == sid
        ).scalar()
        if avg_score:
            score_trend.append(float(avg_score))
    
    # 简单线性回归预测下次考试成绩
    if len(score_trend) >= 2:
        # 计算趋势
        trend = score_trend[-1] - score_trend[-2]
        next_score_pred = min(100, max(0, score_trend[-1] + trend * 0.7))
        score_trend_desc = "上升" if trend > 0 else "下降"
    else:
        next_score_pred = 75.0
        score_trend_desc = "稳定"
    
    # 2. 违纪频率预测
    since_30 = get_local_now() - timedelta(days=30)
    since_60 = get_local_now() - timedelta(days=60)
    recent_disc = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= since_30
    ).count()
    prev_disc = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= since_60,
        DisciplineRecord.created_at < since_30
    ).count()
    
    if prev_disc > 0:
        disc_trend = "上升" if recent_disc > prev_disc else "下降"
        next_disc_pred = max(0, recent_disc + (recent_disc - prev_disc))
    else:
        disc_trend = "稳定" if recent_disc == 0 else "上升"
        next_disc_pred = recent_disc
    
    # 3. 心理风险预测
    mh = MentalHealthAssessment.query.filter_by(student_id=sid).order_by(
        MentalHealthAssessment.assessment_date.desc()
    ).first()
    mental_risk_pred = mh.risk_level if mh else "low"
    
    # 4. 考勤趋势预测
    recent_att = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= since_30
    ).all()
    att_rate = 0
    if recent_att:
        present_count = sum(1 for a in recent_att if a.status == 'present')
        att_rate = round(present_count / len(recent_att) * 100, 1)
    
    if att_rate >= 95:
        att_trend = "优秀"
    elif att_rate >= 85:
        att_trend = "良好"
    else:
        att_trend = "需改进"
    
    # 5. 综合素质预测
    quality_scores = QualityScore.query.filter_by(student_id=sid).order_by(
        QualityScore.assessment_date.asc()
    ).limit(3).all()
    if len(quality_scores) >= 2:
        q_trend = quality_scores[-1].score - quality_scores[-2].score
        next_quality_pred = min(100, max(0, quality_scores[-1].score + q_trend))
        quality_trend_desc = "上升" if q_trend > 0 else "下降"
    else:
        next_quality_pred = 75.0
        quality_trend_desc = "稳定"
    
    # 综合成长建议
    suggestions = []
    if next_score_pred < 60:
        suggestions.append("成绩预警：建议加强学业辅导")
    if next_disc_pred > 2:
        suggestions.append("行为预警：建议加强纪律教育")
    if mental_risk_pred == "high":
        suggestions.append("心理预警：建议心理老师介入")
    if att_rate < 85:
        suggestions.append("考勤预警：建议与家长沟通")
    if not suggestions:
        suggestions.append("整体状况良好，继续保持")
    
    return jsonify({
        "student_id": sid,
        "student_name": student.name,
        "next_score_prediction": round(next_score_pred, 1),
        "score_trend": score_trend_desc,
        "next_discipline_prediction": next_disc_pred,
        "discipline_trend": disc_trend,
        "mental_risk_prediction": mental_risk_pred,
        "attendance_rate": att_rate,
        "attendance_trend": att_trend,
        "next_quality_prediction": round(next_quality_pred, 1),
        "quality_trend": quality_trend_desc,
        "suggestions": suggestions,
        "historical_scores": score_trend
    })


# ── API：相似学生推荐 ──
@ml_models_bp.route("/api/similar-students/<int:sid>")
@login_required
def api_similar_students(sid):
    """找与指定学生相似的其他学生"""
    student = Student.query.get_or_404(sid)
    
    # 获取目标学生的特征向量
    def get_features(s):
        # 成绩均分
        avg_score_q = db.session.query(func.avg(Score.score)).filter(Score.student_id == s.id).scalar()
        avg_score = float(avg_score_q) if avg_score_q else 75.0
        
        # 违纪次数（近90天）
        since = get_local_now() - timedelta(days=90)
        disc_count = DisciplineRecord.query.filter(
            DisciplineRecord.student_id == s.id,
            DisciplineRecord.created_at >= since
        ).count()
        
        # 出勤率（近30天）
        since30 = get_local_now() - timedelta(days=30)
        att_records = Attendance.query.filter(
            Attendance.student_id == s.id,
            Attendance.record_date >= since30
        ).all()
        att_rate = 100.0
        if att_records:
            present = sum(1 for a in att_records if a.status == 'present')
            att_rate = round(present / len(att_records) * 100, 1)
        
        # 心理风险等级（数值化）
        mh = MentalHealthAssessment.query.filter_by(student_id=s.id).order_by(
            MentalHealthAssessment.assessment_date.desc()
        ).first()
        mh_risk = 0  # 0=low, 1=medium, 2=high
        if mh:
            mh_risk = {"low": 0, "medium": 1, "high": 2}.get(mh.risk_level, 0)
        
        # 综合素质均分
        avg_quality_q = db.session.query(func.avg(QualityScore.score)).filter(
            QualityScore.student_id == s.id
        ).scalar()
        avg_quality = float(avg_quality_q) if avg_quality_q else 75.0
        
        return [avg_score/100.0, disc_count/10.0, att_rate/100.0, mh_risk/2.0, avg_quality/100.0]
    
    target_features = get_features(student)
    
    # 计算所有其他学生的相似度
    other_students = Student.query.filter(
        Student.id != sid,
        Student.is_active == True
    ).limit(200).all()  # 限制数量避免性能问题
    
    similarities = []
    for other in other_students:
        other_features = get_features(other)
        # 余弦相似度
        dot_product = sum(a * b for a, b in zip(target_features, other_features))
        mag_a = sum(a * a for a in target_features) ** 0.5
        mag_b = sum(b * b for b in other_features) ** 0.5
        if mag_a > 0 and mag_b > 0:
            similarity = dot_product / (mag_a * mag_b)
        else:
            similarity = 0
        
        # 获取相似学生的关键信息
        other_avg_score = other_features[0] * 100
        other_risk = ["低风险", "中风险", "高风险"][int(other_features[3] * 2)]
        
        similarities.append({
            "student_id": other.id,
            "student_name": other.name,
            "class_name": other.class_.name if other.class_ else "未知",
            "similarity": round(similarity, 3),
            "avg_score": round(other_avg_score, 1),
            "discipline_count": int(other_features[1] * 10),
            "attendance_rate": round(other_features[2] * 100, 1),
            "mental_risk": other_risk,
            "quality_score": round(other_features[4] * 100, 1),
        })
    
    # 按相似度排序，取前10
    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    top_similar = similarities[:10]
    
    return jsonify({
        "target_student": {
            "id": student.id,
            "name": student.name,
            "class_name": student.class_.name if student.class_ else "未知",
        },
        "similar_students": top_similar,
        "feature_description": {
            "score_weight": "成绩均分 (归一化到0-1)",
            "discipline_weight": "违纪次数 (除以10归一化)",
            "attendance_weight": "出勤率 (归一化到0-1)",
            "mental_risk_weight": "心理风险 (0=低, 0.5=中, 1=高)",
            "quality_weight": "综合素质 (归一化到0-1)",
        }
    })
