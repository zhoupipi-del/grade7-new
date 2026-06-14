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


# ============================================================
# 🌌 德育沙盘推演舱 (What-If Simulator)
# ============================================================

import numpy as np
import joblib
import json as json_mod
from datetime import datetime

# ── 干预类型 → 特征篡改映射表 ──
INTERVENTION_EFFECTS = {
    "class_mate_buddy": {
        "name": "班干部一对一结对子",
        "effects": {
            "quality_score": "+5",
            "risk_density": "max(0, x-1)",
            "discipline_factor": "x*0.9",
        },
        "description": "人际交往特征增强，同伴影响力提升",
    },
    "home_visit": {
        "name": "家校面谈",
        "effects": {
            "risk_density": "max(0, x-2)",
            "discipline_factor": "x*0.7",
            "attendance_rate": "min(1.0, x+0.05)",
        },
        "description": "家庭监督权重提升，家校合力形成",
    },
    "seat_adjust": {
        "name": "调整座位到第一排",
        "effects": {
            "discipline_factor": "x*0.5",
            "risk_density": "max(0, x-0.5)",
        },
        "description": "课堂违纪概率下降，注意力集中度提升",
    },
    "psych_icebreak": {
        "name": "专职心理老师破冰谈话",
        "effects": {
            "risk_density": "0",
            "quality_score": "+8",
        },
        "description": "心理高危因子熔断，情绪状态重置",
    },
    "award_incentive": {
        "name": "奖励激励（小红花/称号）",
        "effects": {
            "quality_score": "+10",
            "risk_density": "max(0, x-1)",
        },
        "description": "正向强化，自我效能感提升",
    },
    "sports_engagement": {
        "name": "体育破冰（安排体育活动）",
        "effects": {
            "quality_score": "+3",
            "risk_density": "max(0, x-1)",
            "discipline_factor": "x*0.8",
        },
        "description": "体能释放，团队协作能力培养",
    },
    "study_group": {
        "name": "学习小组捆绑",
        "effects": {
            "quality_score": "+4",
            "discipline_factor": "x*0.85",
        },
        "description": "学业互助，归属感增强",
    },
    "parent_contract": {
        "name": "家校契约（行为合约）",
        "effects": {
            "discipline_factor": "x*0.6",
            "attendance_rate": "min(1.0, x+0.08)",
            "risk_density": "max(0, x-1.5)",
        },
        "description": "契约约束，责任意识培养",
    },
}


def _load_xgb_pipeline():
    """懒加载 XGBoost pipeline"""
    pipeline_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "wings_xgb_pipeline.pkl")
    metadata_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "pipeline_metadata.pkl")
    
    if not os.path.exists(pipeline_path):
        return None, None
    
    pipeline = joblib.load(pipeline_path)
    
    if os.path.exists(metadata_path):
        metadata = joblib.load(metadata_path)
        feature_names = metadata["feature_names"]
        support_mask = metadata["support_mask"]
    else:
        feature_names = ["math_slope", "math_avg", "quality_score", "risk_density", "attendance_rate", "discipline_factor"]
        support_mask = [True] * 6
    
    return pipeline, (feature_names, support_mask)


def _get_student_feature_vector(student_id: int) -> dict:
    """
    获取学生特征向量（6维）
    返回: {"math_slope": float, "math_avg": float, ...}
    """
    from feature_extractor import FeatureExtractor
    
    fe = FeatureExtractor(grade_id=1)
    vector = fe.get_student_vector(student_id)
    
    if not vector or "features" not in vector:
        return None
    
    # features 是 [math_slope, math_avg, quality_score, risk_density, attendance_rate, discipline_factor]
    feature_names = ["math_slope", "math_avg", "quality_score", "risk_density", "attendance_rate", "discipline_factor"]
    return dict(zip(feature_names, vector["features"]))


def _apply_interventions(features: dict, interventions: list) -> dict:
    """
    根据干预类型篡改特征向量
    
    Args:
        features: 原始特征向量
        interventions: 干预类型列表，如 ["home_visit", "seat_adjust"]
    
    Returns:
        篡改后的特征向量
    """
    simulated = features.copy()
    
    for intervention in interventions:
        if intervention not in INTERVENTION_EFFECTS:
            continue
        
        effects = INTERVENTION_EFFECTS[intervention]["effects"]
        
        for feature_name, effect_expr in effects.items():
            if feature_name not in simulated:
                continue
            
            x = simulated[feature_name]
            
            # 解析效果表达式
            if effect_expr.startswith("+"):
                # 加法：如 "+5"
                delta = float(effect_expr[1:])
                simulated[feature_name] = x + delta
            elif effect_expr.startswith("x*"):
                # 乘法：如 "x*0.7"
                factor = float(effect_expr[2:])
                simulated[feature_name] = x * factor
            elif "max(0, x-" in effect_expr:
                # 减法但有下限：如 "max(0, x-2)"
                delta = float(effect_expr.split("x-")[1].rstrip(")"))
                simulated[feature_name] = max(0, x - delta)
            elif effect_expr == "0":
                # 强行置零
                simulated[feature_name] = 0.0
            elif "min(1.0, x+" in effect_expr:
                # 加法但有上限：如 "min(1.0, x+0.05)"
                delta = float(effect_expr.split("x+")[1].rstrip(")"))
                simulated[feature_name] = min(1.0, x + delta)
    
    return simulated


def _predict_risk(features: dict, pipeline, feature_names: list, support_mask: list) -> dict:
    """
    用 XGBoost pipeline 预测风险
    
    Returns:
        {"risk_prob": float, "risk_level": str, "feature_contrib": dict}
    """
    if pipeline is None:
        # 如果模型没加载，用规则引擎兜底
        risk_score = 0.0
        if features.get("risk_density", 0) > 2:
            risk_score += 0.3
        if features.get("discipline_factor", 0) > 10:
            risk_score += 0.3
        if features.get("attendance_rate", 1.0) < 0.9:
            risk_score += 0.2
        if features.get("math_slope", 0) < -5:
            risk_score += 0.2
        
        risk_prob = min(1.0, risk_score)
        risk_level = "high" if risk_prob > 0.7 else ("medium" if risk_prob > 0.4 else "low")
        return {"risk_prob": risk_prob, "risk_level": risk_level, "feature_contrib": {}}
    
    # 组装特征向量（按全量特征顺序）
    X_raw = [[features.get(f, 0.0) for f in feature_names]]
    X = np.array(X_raw, dtype=np.float64)
    
    # 预测概率
    proba = pipeline.predict_proba(X)[0]  # [neg_prob, pos_prob]
    risk_prob = float(proba[1])  # 正例概率（需关注）
    
    risk_level = "high" if risk_prob > 0.7 else ("medium" if risk_prob > 0.4 else "low")
    
    # 特征贡献度（用 feature_importances_ 近似）
    classifier_step = pipeline.named_steps['classifier']
    importances = classifier_step.feature_importances_
    passed_features = [feature_names[i] for i, passed in enumerate(support_mask) if passed]
    
    feature_contrib = {}
    for i, f_name in enumerate(passed_features):
        # 简化：用特征值 * 重要性作为贡献度
        feature_contrib[f_name] = round(float(features.get(f_name, 0)) * float(importances[i]), 4)
    
    return {"risk_prob": risk_prob, "risk_level": risk_level, "feature_contrib": feature_contrib}


def _generate_risk_curve(student_id: int, base_risk: float, simulated_risk: float) -> dict:
    """
    生成风险曲线（未来30天，每天一个数据点）
    用指数衰减模拟干预效果的随时间变化
    """
    import math
    
    days = 30
    curve = []
    
    # 原始曲线：假设风险随时间缓慢上升（若无干预）
    for day in range(days + 1):
        # 缓慢上升：base_risk * (1 + 0.01 * day)
        orig = min(1.0, base_risk * (1 + 0.01 * day))
        curve.append(round(orig, 3))
    
    # 模拟曲线：干预后风险断崖式下跌，然后缓慢回升（但有残留效果）
    sim_curve = []
    for day in range(days + 1):
        if day == 0:
            sim = base_risk
        elif day <= 3:
            # 前3天：断崖式下跌
            sim = base_risk - (base_risk - simulated_risk) * (day / 3)
        else:
            # 3天后：指数衰减回升（干预效果逐渐减弱）
            decay = (simulated_risk - base_risk * 0.3) * math.exp(-0.05 * (day - 3))
            sim = simulated_risk + decay
            sim = max(simulated_risk, sim)  # 不低于模拟风险
        
        sim_curve.append(round(min(1.0, max(0.0, sim)), 3))
    
    return {"original_curve": curve, "simulated_curve": sim_curve}


def _call_deepseek_for_tactical_report(student_name: str, orig_risk: float, sim_risk: float, 
                                        interventions: list, feature_changes: dict) -> str:
    """
    调用 DeepSeek 生成战术推演报告
    """
    try:
        from llm_client import LLMClient
        llm = LLMClient()
        
        intervention_names = [INTERVENTION_EFFECTS.get(i, {}).get("name", i) for i in interventions]
        
        # 构建干预措施详情（用于Prompt上下文）
        intervention_context = []
        for i in interventions:
            info = INTERVENTION_EFFECTS.get(i, {})
            effects_desc = "、".join(
                "{}→{}".format(
                    {"math_slope": "数学学力斜率", "math_avg": "数学均分", "quality_score": "综合素质分",
                     "risk_density": "风险密度", "attendance_rate": "出勤率", "discipline_factor": "违纪因子"}.get(k, k),
                    v
                ) for k, v in info.get("effects", {}).items()
            )
            intervention_context.append(
                "  - {}：{}".format(info.get("name", i), info.get("description", ""))
                + ("（特征调整：{}）".format(effects_desc) if effects_desc else "")
            )

        # 特征变化中文化
        FEATURE_LABELS = {
            "math_slope": "数学学力斜率", "math_avg": "数学均分", "quality_score": "综合素质分",
            "risk_density": "风险密度", "attendance_rate": "出勤率", "discipline_factor": "违纪因子"
        }
        changes_desc = "\n".join(
            "  - {}：{:.3f} → {:.3f}（Δ {:.3f}）".format(
                FEATURE_LABELS.get(k, k), v["original"], v["simulated"], v["delta"]
            ) for k, v in feature_changes.items()
        ) if feature_changes else "  - 无显著变化"

        risk_drop = orig_risk - sim_risk
        risk_pct = risk_drop / orig_risk * 100 if orig_risk > 0 else 0

        prompt = """你是一位拥有15年初中德育工作经验的资深心理咨询师兼班主任导师，熟悉教育心理学、行为干预理论（如认知行为疗法CBT、正念干预、社会学习理论）。

我正在使用「德育沙盘推演舱」进行干预前预演。系统通过篡改XGBoost模型的6维特征向量来模拟干预效果。请根据以下推演数据，生成一份实用的战术推演报告。

## 一、学生概况
- 姓名：{}
- 原始风险概率：{:.1%}（基于XGBoost分类器）
- 干预后模拟风险：{:.1%}
- 风险降幅：{:.1%}（相对降幅 {:.1f}%）

## 二、干预方案
{}
## 三、模型特征变化
{}
## 四、输出要求
请直接输出以下四部分（不要加额外标题，用粗体标注每部分小标题）：

**干预成效评估**（200字以内）
- 从教育心理学角度评估这组干预组合的协同效应
- 指出哪些干预之间存在互补或冗余
- 结合风险降幅判断该方案是否值得执行

**实操执行手册**（3-5条，每条50字以内）
- 每条必须是班主任明天就能执行的具体动作
- 包含执行时机、话术要点、预期反馈
- 按执行优先级排序

**残余风险预警**
- 干预后仍存在的2-3个潜在风险点
- 每个风险点给出一个早期识别信号

**谈话破冰脚本**（100字以内）
- 如果需要安排心理老师或班主任谈话，给出一段破冰开场白
- 语气温暖、自然，适合初中生

注意：你是在辅助一位负责任的班主任做干预决策。语气要专业务实，避免空话套话。数据中的"风险密度""违纪因子"等是模型内部特征名，请在报告中用教育工作者能理解的语言转述。""".format(
            student_name, orig_risk, sim_risk, risk_drop, risk_pct,
            "\n".join(intervention_context),
            changes_desc
        )
        
        report = llm.generate(prompt, max_tokens=1200)
        return report if report else "AI报告生成失败，请稍后重试。"
    
    except Exception as e:
        print("DeepSeek 调用失败: {}".format(e))
        return "AI战术报告生成失败（{}）。但风险推演数据已计算完成，请参考曲线数据。".format(str(e))


# ── 路由：沙盘推演页面 ──
@ml_models_bp.route("/sandbox")
@login_required
def sandbox():
    """德育沙盘推演舱页面"""
    return render_template("ml_models/sandbox.html")


# ── API：沙盘推演核心端点 ──
@ml_models_bp.route("/api/sandbox-deduce", methods=["POST"])
@login_required
def api_sandbox_deduce():
    """
    德育沙盘推演核心 API
    
    请求体:
    {
        "student_id": 123,
        "interventions": ["home_visit", "seat_adjust"]
    }
    
    响应:
    {
        "code": 0,
        "student_name": "陈佳乐",
        "original_risk": 0.85,
        "simulated_risk": 0.32,
        "risk_drop": 0.53,
        "original_curve": [0.85, 0.86, 0.87, ...],
        "simulated_curve": [0.85, 0.45, 0.18, ...],
        "feature_changes": {...},
        "ai_report": "...",
        "intervention_details": [...]
    }
    """
    req_data = request.json
    student_id = req_data.get("student_id", 0)
    interventions = req_data.get("interventions", [])
    
    if not student_id:
        return jsonify({"code": 400, "msg": "缺少 student_id"})
    
    if not interventions:
        return jsonify({"code": 400, "msg": "请至少选择一种干预措施"})
    
    # 1. 权限检查
    from models import Student
    student = Student.query.get_or_404(student_id)
    role = session.get("role", "")
    my_class_id = session.get("class_id")
    
    if role == "class_teacher" and my_class_id and student.class_id != my_class_id:
        return jsonify({"code": 403, "msg": "无权访问该学生数据"})
    
    # 2. 加载 XGBoost pipeline
    pipeline, metadata = _load_xgb_pipeline()
    feature_names = metadata[0] if metadata else ["math_slope", "math_avg", "quality_score", "risk_density", "attendance_rate", "discipline_factor"]
    support_mask = metadata[1] if metadata else [True] * 6
    
    # 3. 提取原始特征向量
    orig_features = _get_student_feature_vector(student_id)
    if not orig_features:
        return jsonify({"code": 404, "msg": "无法提取该生特征向量，可能数据不足"})
    
    # 4. 应用干预措施，生成模拟特征向量
    sim_features = _apply_interventions(orig_features, interventions)
    
    # 5. 分别计算原始风险和模拟风险
    orig_result = _predict_risk(orig_features, pipeline, feature_names, support_mask)
    sim_result = _predict_risk(sim_features, pipeline, feature_names, support_mask)
    
    orig_risk = orig_result["risk_prob"]
    sim_risk = sim_result["risk_prob"]
    
    # 6. 生成风险曲线（未来30天）
    curves = _generate_risk_curve(student_id, orig_risk, sim_risk)
    
    # 7. 计算特征变化（供前端展示）
    feature_changes = {}
    for key in orig_features:
        if key in sim_features and orig_features[key] != sim_features[key]:
            feature_changes[key] = {
                "original": round(orig_features[key], 3),
                "simulated": round(sim_features[key], 3),
                "delta": round(sim_features[key] - orig_features[key], 3),
            }
    
    # 8. 调用 DeepSeek 生成战术推演报告
    ai_report = _call_deepseek_for_tactical_report(
        student.name, orig_risk, sim_risk, interventions, feature_changes
    )
    
    # 9. 干预措施详情（供前端展示）
    intervention_details = []
    for intervention in interventions:
        if intervention in INTERVENTION_EFFECTS:
            intervention_details.append({
                "id": intervention,
                "name": INTERVENTION_EFFECTS[intervention]["name"],
                "description": INTERVENTION_EFFECTS[intervention]["description"],
                "effects": INTERVENTION_EFFECTS[intervention]["effects"],
            })
    
    return jsonify({
        "code": 0,
        "student_id": student_id,
        "student_name": student.name,
        "original_risk": round(orig_risk, 3),
        "simulated_risk": round(sim_risk, 3),
        "risk_drop": round(orig_risk - sim_risk, 3),
        "risk_drop_pct": round((orig_risk - sim_risk) / orig_risk * 100, 1) if orig_risk > 0 else 0,
        "original_curve": curves["original_curve"],
        "simulated_curve": curves["simulated_curve"],
        "feature_changes": feature_changes,
        "ai_report": ai_report,
        "intervention_details": intervention_details,
        "orig_risk_level": orig_result["risk_level"],
        "sim_risk_level": sim_result["risk_level"],
    })