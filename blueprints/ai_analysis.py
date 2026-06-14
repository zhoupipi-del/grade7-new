"""AI辅助分析 — 学生行为预测 + 风险预警 (性能优化版)"""
import os, json as json_mod, requests
from flask import Blueprint, render_template, jsonify, request, session, current_app, flash, redirect, url_for
from sqlalchemy.orm import joinedload
from models import db, Student, Attendance, DisciplineRecord, Score, LeaveRequest, Class, User, RiskRecord, PsychSurvey, MentalHealthAssessment, WingsScore, ProblemStudent
from decorators import login_required, require_role
from datetime import date, datetime, timedelta
from sqlalchemy import func, text
from collections import defaultdict
# send_notification 通过内联 import 调用以避免循环导入
from utils.sonar_bus import publish_risk, publish_briefing

ai_analysis_bp = Blueprint("ai_analysis", __name__, url_prefix="/ai-analysis")

# 定时扫描密钥（从环境变量或配置文件读取）
SCAN_SECRET = os.environ.get("AI_SCAN_SECRET", "lijiang-ai-scan-2026")

# ── 风险等级配置 ──
RISK_LEVELS = {
    "red": {"label": "高风险", "color": "danger", "icon": "bi-exclamation-triangle-fill"},
    "yellow": {"label": "中风险", "color": "warning", "icon": "bi-exclamation-circle-fill"},
    "green": {"label": "低风险", "color": "success", "icon": "bi-check-circle-fill"},
}

# ── 预警规则（含增强规则引擎新增） ──
WARNING_RULES = [
    ("连续缺勤>=3天", "red", "_check_consecutive_absent"),
    ("本月缺勤>=5次", "yellow", "_check_monthly_absent"),
    ("本周迟到>=3次", "yellow", "_check_weekly_late"),
    ("重大违纪>=1次", "red", "_check_major_discipline"),
    ("严重违纪>=2次", "red", "_check_serious_discipline"),
    ("成绩下滑>=10分", "yellow", "_check_score_drop"),
    ("频繁请假>=3次/月", "yellow", "_check_frequent_leave"),
    ("MSSMHS-55心理问卷高风险(>=160)", "red", "_check_psych_survey"),
    # ── 增强规则（Step1 学业预警规则引擎） ──
    ("教师心理评估高风险", "red", "_check_mental_assess_high"),
    ("五翼评价连续下滑>=20%", "yellow", "_check_wings_decline"),
    ("问题学生红色档案", "red", "_check_problem_student"),
    ("违纪扣分累积>=20分", "red", "_check_discipline_points"),
    ("违纪扣分累积>=10分", "yellow", "_check_discipline_points"),
    ("多类型违纪分散>=3类", "yellow", "_check_discipline_multi_type"),
]

# ── XGBoost 特征归因（将全局 feature_importances_ 映射为单生诱因解释） ──
# 预警类型 → 6 维特征映射（用于归因排名）
WARNING_TO_FEATURE = {
    "consecutive_absent": "attendance_rate",
    "monthly_absent": "attendance_rate",
    "weekly_late": "attendance_rate",
    "major_discipline": "discipline_factor",
    "serious_discipline": "discipline_factor",
    "score_drop": "math_slope",
    "frequent_leave": "attendance_rate",
    "psych_survey_high": "quality_score",
    "psych_survey_medium": "quality_score",
}

# 特征中文标签
FEATURE_LABELS = {
    "discipline_factor": "违纪记录",
    "math_avg": "数学均分",
    "attendance_rate": "出勤情况",
    "quality_score": "综合素质",
    "risk_density": "近期预警频次",
    "math_slope": "成绩趋势",
}

# 全局缓存 feature_importances_
_importances_cache = None
_importances_ts = 0
_IMPORTANCES_TTL = 300  # 5分钟

def _load_feature_importances():
    """加载训练时固化下的 feature_importances_.json（带 TTL 缓存）"""
    global _importances_cache, _importances_ts
    import time as _time
    now = _time.time()
    if _importances_cache is not None and now - _importances_ts < _IMPORTANCES_TTL:
        return _importances_cache
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "models", "feature_importances.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json_mod.load(f)
        _importances_cache = data.get("importances", {})
        _importances_ts = now
        return _importances_cache
    except Exception:
        # 模型文件不存在时使用经验默认值（基于论文训练结果）
        defaults = {
            "discipline_factor": 0.38, "math_slope": 0.22,
            "attendance_rate": 0.18, "quality_score": 0.12,
            "risk_density": 0.07, "math_avg": 0.03,
        }
        _importances_cache = defaults
        _importances_ts = now
        return defaults

def _build_feature_attribution(warnings):
    """根据预警列表 + XGBoost 全局重要性生成「核心诱因」归因摘要

    Args:
        warnings: list[dict] — 规则引擎输出的预警项列表

    Returns:
        dict: {"top_triggers": [...], "contributions": {...}, "summary": "..."}
    """
    if not warnings:
        return None
    importances = _load_feature_importances()

    # 统计各特征触发的预警次数，加权求和
    feature_scores = {}
    for w in warnings:
        fname = WARNING_TO_FEATURE.get(w.get("type", ""))
        if not fname:
            continue
        severity = 2 if w.get("level") == "red" else 1
        weight = importances.get(fname, 0.1)
        feature_scores[fname] = feature_scores.get(fname, 0) + weight * severity

    if not feature_scores:
        return None

    # 降序排列 top triggers（最多 3 个）
    sorted_features = sorted(feature_scores.items(), key=lambda x: x[1], reverse=True)
    top_triggers = []
    for fname, score in sorted_features[:3]:
        total = sum(v for _, v in sorted_features) or 1
        pct = round(score / total * 100, 1)
        top_triggers.append({
            "feature": fname,
            "label": FEATURE_LABELS.get(fname, fname),
            "score": round(score, 4),
            "pct": pct,
        })

    # 生成人类可读的总结
    trigger_texts = [f"{t['label']}({t['pct']}%)" for t in top_triggers]
    summary = f"🚨 核心诱因：{' + '.join(trigger_texts)}"

    return {
        "top_triggers": top_triggers,
        "contributions": {k: round(v, 4) for k, v in sorted_features},
        "summary": summary,
    }


@ai_analysis_bp.before_request
def check_login():
    # /api/scan 和 /api/regression 使用 Bearer token 鉴权，跳过 session 检查
    path = request.path
    if path.startswith("/ai-analysis/api/scan") or path.startswith("/ai-analysis/api/regression"):
        return None
    if not session.get("logged_in"):
        if request.path.startswith("/ai-analysis/api/"):
            return jsonify({"error": "未登录"}), 401
        flash("请先登录", "warning")
        return redirect(url_for("auth.login_page", next=request.path))


@ai_analysis_bp.route("/")
@require_role("ms_admin", "grade_leader", "class_teacher")
def index():
    """AI分析总览页 (优化版：批量查询)"""
    import time as time_module
    t_start = time_module.time()
    
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    today = date.today()

    # ── 1. 确定查询范围 ──
    t1 = time_module.time()
    students_q = Student.query.filter_by(is_active=True)
    if role == "grade_leader" and grade_id:
        students_q = students_q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        students_q = students_q.filter_by(class_id=class_id)

    all_students = students_q.all()
    student_ids = [s.id for s in all_students]
    print(f"[AI分析] 1. 查询学生: {len(student_ids)} 个, 耗时 {time_module.time()-t1:.3f}s")
    
    if not student_ids:
        return render_template("ai_analysis/index.html",
                               risk_list=[],
                               risk_summary={"red": 0, "yellow": 0, "green": 0},
                               trend_prediction={"total_students": 0, "risk_students": 0, "risk_rate": 0, "trend": "stable"},
                               today=today)

    # ── 2. 批量查询所有需要的数据 ──
    t2 = time_module.time()

    # 2.1 考勤记录（最近30天）
    attendance_records = {}
    if student_ids:
        att_records = Attendance.query.filter(
            Attendance.student_id.in_(student_ids),
            Attendance.record_date >= today - timedelta(days=30),
        ).all()
        # 按 student_id 分组
        for r in att_records:
            if r.student_id not in attendance_records:
                attendance_records[r.student_id] = []
            attendance_records[r.student_id].append(r)
    
    print(f"[AI分析] 2.1 考勤查询: {len(att_records) if student_ids else 0} 条, 耗时 {time_module.time()-t2:.3f}s")
    
    # 2.2 违纪记录（本学期）
    t3 = time_module.time()
    semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)
    discipline_records = {}
    if student_ids:
        disc_records = DisciplineRecord.query.filter(
            DisciplineRecord.student_id.in_(student_ids),
            DisciplineRecord.created_at >= semester_start,
        ).all()
        for r in disc_records:
            if r.student_id not in discipline_records:
                discipline_records[r.student_id] = []
            discipline_records[r.student_id].append(r)
    
    print(f"[AI分析] 2.2 违纪查询: {len(disc_records) if student_ids else 0} 条, 耗时 {time_module.time()-t3:.3f}s")
    
    # 2.3 成绩记录（最近2次考试，按考试ID聚合总分）
    t4 = time_module.time()
    score_data = {}
    if student_ids:
        # 用原始SQL批量查询，按 student_id + exam_id 聚合
        rows = db.session.execute(
            text("""
                SELECT student_id, exam_id, SUM(score) as total
                FROM scores WHERE student_id IN :sids
                GROUP BY student_id, exam_id
                ORDER BY student_id, exam_id DESC
            """),
            {"sids": tuple(student_ids) if len(student_ids) > 1 else f"({student_ids[0]})"}
        ).fetchall()

        # 只保留每个学生的前2次考试
        for row in rows:
            sid = row[0]
            if sid not in score_data:
                score_data[sid] = []
            if len(score_data[sid]) < 2:
                score_data[sid].append({"exam_id": row[1], "total": float(row[2] or 0)})

    # 2.4 请假记录（本月）
    month_start = today.replace(day=1)
    leave_records = {}
    if student_ids:
        leaves = LeaveRequest.query.filter(
            LeaveRequest.student_id.in_(student_ids),
            LeaveRequest.created_at >= month_start,
            LeaveRequest.status == "approved",
        ).all()
        for r in leaves:
            if r.student_id not in leave_records:
                leave_records[r.student_id] = []
            leave_records[r.student_id].append(r)

    # 2.5 心理问卷数据（MSSMHS-55，最近一次有效问卷）
    psych_surveys = {}
    if student_ids:
        psychs = PsychSurvey.query.filter(
            PsychSurvey.student_id.in_(student_ids),
            PsychSurvey.survey_type == "MSSMHS-55",
            PsychSurvey.is_valid == True,
        ).order_by(PsychSurvey.completed_at.desc()).all()
        for p in psychs:
            if p.student_id not in psych_surveys:
                psych_surveys[p.student_id] = p  # 取最新一条

    # ── 3. 分析每个学生 ──
    risk_list = []
    risk_summary = {"red": 0, "yellow": 0, "green": 0}

    scan_errors = []  # 收集扫描异常但不中断全局
    for stu in all_students:
        try:
            sid = stu.id
            warnings = []

            # 3.1 连续缺勤检测
            att_list = attendance_records.get(sid, [])
            if _check_consecutive_absent_batch(att_list, today):
                warnings.append({
                    "type": "consecutive_absent",
                    "level": "red",
                    "text": "连续缺勤≥3天",
                    "suggestion": "建议立即联系家长，了解缺勤原因",
                })

            # 3.2 本月缺勤次数
            month_absent = sum(1 for r in att_list if r.record_date >= month_start and r.status == "absent")
            if month_absent >= 5:
                warnings.append({
                    "type": "monthly_absent",
                    "level": "yellow",
                    "text": f"本月已缺勤{month_absent}次",
                    "suggestion": "建议关注学生出勤情况，必要时约谈家长",
                })

            # 3.3 本周迟到次数
            week_start = today - timedelta(days=today.weekday())
            week_late = sum(1 for r in att_list if r.record_date >= week_start and r.status == "late")
            if week_late >= 3:
                warnings.append({
                    "type": "weekly_late",
                    "level": "yellow",
                    "text": f"本周已迟到{week_late}次",
                    "suggestion": "建议加强时间观念教育",
                })

            # 3.4 重大违纪
            major_count = sum(1 for r in discipline_records.get(sid, []) if r.type == "major")
            if major_count >= 1:
                warnings.append({
                    "type": "major_discipline",
                    "level": "red",
                    "text": f"有重大违纪{major_count}次",
                    "suggestion": "建议德育处介入，制定个别教育方案",
                })

            # 3.5 严重违纪
            serious_count = sum(1 for r in discipline_records.get(sid, []) if r.type == "serious")
            if serious_count >= 2:
                warnings.append({
                    "type": "serious_discipline",
                    "level": "red",
                    "text": f"严重违纪{serious_count}次",
                    "suggestion": "建议启动危机干预机制",
                })

            # 3.6 成绩下滑
            scores = score_data.get(sid, [])
            if len(scores) >= 2:
                score_drop = max(0, scores[1]["total"] - scores[0]["total"])
                if score_drop >= 10:
                    warnings.append({
                        "type": "score_drop",
                        "level": "yellow",
                        "text": f"成绩下滑{score_drop:.1f}分",
                        "suggestion": "建议与任课教师沟通，查找学习困难原因",
                    })

            # 3.7 频繁请假
            leave_count = len(leave_records.get(sid, []))
            if leave_count >= 3:
                warnings.append({
                    "type": "frequent_leave",
                    "level": "yellow",
                    "text": f"本月请假{leave_count}次",
                    "suggestion": "建议关注学生身心健康，了解请假原因",
                })

            # 3.8 MSSMHS-55心理问卷高风险
            psych = psych_surveys.get(sid)
            if psych and psych.total_score and psych.total_score >= 160:
                warnings.append({
                    "type": "psych_survey_high",
                    "level": "red",
                    "text": f"MSSMHS-55心理问卷高风险（{int(psych.total_score)}分）",
                    "suggestion": "心理健康筛查提示高风险，建议安排心理老师个别访谈",
                })
            elif psych and psych.total_score and psych.total_score >= 120:
                warnings.append({
                    "type": "psych_survey_medium",
                    "level": "yellow",
                    "text": f"MSSMHS-55心理问卷中风险（{int(psych.total_score)}分）",
                    "suggestion": "建议班主任关注学生情绪状态，适时沟通",
                })

            # 确定最高风险等级
            if warnings:
                max_level = "green"
                for w in warnings:
                    if w["level"] == "red":
                        max_level = "red"
                        break
                    elif w["level"] == "yellow" and max_level == "green":
                        max_level = "yellow"

                risk_summary[max_level] += 1
                risk_list.append({
                    "student": stu,
                    "warnings": warnings,
                    "max_level": max_level,
                })
        except Exception as e:
            scan_errors.append({"student_id": stu.id, "student_name": stu.name, "error": str(e)})
            continue

    # 按风险等级排序（红>黄>绿）
    risk_list.sort(key=lambda x: {"red": 0, "yellow": 1, "green": 2}[x["max_level"]])

    # ── 4. 行为趋势预测（简化版） ──
    total = len(all_students)
    risk_count = len(risk_list)
    risk_rate = round(risk_count / total * 100, 1) if total > 0 else 0

    if risk_rate > 30:
        trend = "rising"
    elif risk_rate > 15:
        trend = "stable"
    else:
        trend = "declining"

    trend_prediction = {
        "total_students": total,
        "risk_students": risk_count,
        "risk_rate": risk_rate,
        "trend": trend,
    }

    # 记录扫描异常到日志
    if scan_errors:
        import logging
        logging.getLogger("grade7").warning(f"AI扫描异常: {len(scan_errors)}名学生分析失败: {scan_errors[:5]}")

    return render_template("ai_analysis/index.html",
                           risk_list=risk_list,
                           risk_summary=risk_summary,
                           trend_prediction=trend_prediction,
                           scan_errors=scan_errors,
                           today=today)


@ai_analysis_bp.route("/api/student/<int:sid>")
@login_required
def student_detail(sid):
    """单个学生的AI分析报告（JSON）"""
    student = Student.query.get_or_404(sid)
    today = date.today()

    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        return jsonify({"error": "无权查看"}), 403
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        return jsonify({"error": "无权查看"}), 403

    # 为单个学生做分析（使用批量函数）
    warnings = _analyze_student_detail(student, today)
    prediction = _predict_student_behavior(student, today)

    return jsonify({
        "student": {
            "id": student.id,
            "name": student.name,
            "class_name": student.class_.name if student.class_ else "",
        },
        "warnings": warnings,
        "prediction": prediction,
    })


# ── 批量分析函数 ──

def _check_consecutive_absent_batch(att_records, today):
    """检查连续缺勤≥3天（批量版）"""
    if not att_records:
        return False

    # 按日期排序
    att_records.sort(key=lambda r: r.record_date)

    max_consecutive = 0
    consecutive = 0
    last_date = None

    for r in att_records:
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

    return max_consecutive >= 3


def _analyze_student_detail(stu, today):
    """分析单个学生的风险预警（用于API详情页）"""
    sid = stu.id
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())
    semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)

    warnings = []

    # 1. 连续缺勤
    att_records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= today - timedelta(days=30),
    ).order_by(Attendance.record_date.asc()).all()

    if _check_consecutive_absent_batch(att_records, today):
        warnings.append({
            "type": "consecutive_absent",
            "level": "red",
            "text": "连续缺勤≥3天",
            "suggestion": "建议立即联系家长，了解缺勤原因",
        })

    # 2. 本月缺勤
    month_absent = sum(1 for r in att_records if r.record_date >= month_start and r.status == "absent")
    if month_absent >= 5:
        warnings.append({
            "type": "monthly_absent",
            "level": "yellow",
            "text": f"本月已缺勤{month_absent}次",
            "suggestion": "建议关注学生出勤情况，必要时约谈家长",
        })

    # 3. 本周迟到
    week_late = sum(1 for r in att_records if r.record_date >= week_start and r.status == "late")
    if week_late >= 3:
        warnings.append({
            "type": "weekly_late",
            "level": "yellow",
            "text": f"本周已迟到{week_late}次",
            "suggestion": "建议加强时间观念教育",
        })

    # 4. 重大违纪
    major_count = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.type == "major",
        DisciplineRecord.created_at >= semester_start,
    ).count()

    if major_count >= 1:
        warnings.append({
            "type": "major_discipline",
            "level": "red",
            "text": f"有重大违纪{major_count}次",
            "suggestion": "建议德育处介入，制定个别教育方案",
        })

    # 5. 严重违纪
    serious_count = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.type == "serious",
        DisciplineRecord.created_at >= semester_start,
    ).count()

    if serious_count >= 2:
        warnings.append({
            "type": "serious_discipline",
            "level": "red",
            "text": f"严重违纪{serious_count}次",
            "suggestion": "建议启动危机干预机制",
        })

    # 6. 成绩下滑
    rows = db.session.execute(
        text("""
            SELECT exam_id, SUM(score) as total
            FROM scores WHERE student_id = :sid
            GROUP BY exam_id ORDER BY exam_id DESC LIMIT 2
        """),
        {"sid": sid}
    ).fetchall()

    if len(rows) >= 2:
        prev_total = float(rows[1].total or 0)
        curr_total = float(rows[0].total or 0)
        score_drop = max(0, prev_total - curr_total)
        if score_drop >= 10:
            warnings.append({
                "type": "score_drop",
                "level": "yellow",
                "text": f"成绩下滑{score_drop:.1f}分",
                "suggestion": "建议与任课教师沟通，查找学习困难原因",
            })

    # 7. 频繁请假
    leave_count = LeaveRequest.query.filter(
        LeaveRequest.student_id == sid,
        LeaveRequest.created_at >= month_start,
        LeaveRequest.status == "approved",
    ).count()

    if leave_count >= 3:
        warnings.append({
            "type": "frequent_leave",
            "level": "yellow",
            "text": f"本月请假{leave_count}次",
            "suggestion": "建议关注学生身心健康，了解请假原因",
        })

    # 8. MSSMHS-55心理问卷风险
    psych = PsychSurvey.query.filter_by(
        student_id=sid,
        survey_type="MSSMHS-55",
        is_valid=True
    ).order_by(PsychSurvey.completed_at.desc()).first()
    if psych and psych.total_score:
        if psych.total_score >= 160:
            warnings.append({
                "type": "psych_survey_high",
                "level": "red",
                "text": f"MSSMHS-55心理问卷高风险（{int(psych.total_score)}分）",
                "suggestion": "心理健康筛查提示高风险，建议安排心理老师个别访谈",
            })
    elif psych.total_score >= 120:
        warnings.append({
            "type": "psych_survey_medium",
            "level": "yellow",
            "text": f"MSSMHS-55心理问卷中风险（{int(psych.total_score)}分）",
            "suggestion": "建议班主任关注学生情绪状态，适时沟通",
        })

    # ══ 增强规则引擎：接入额外数据源 ══
    try:
        from utils.rule_engine import evaluate_rules

        # 教师心理评估
        mental_assessments = MentalHealthAssessment.query.filter_by(
            student_id=sid
        ).order_by(MentalHealthAssessment.created_at.desc()).limit(5).all()

        # 五翼评价
        wings_scores = WingsScore.query.filter_by(student_id=sid).all()

        # 问题学生档案
        problem_student = ProblemStudent.query.filter_by(
            student_id=sid, is_active=True
        ).first()

        # 执行增强规则（原有规则已通过上面的代码检查，此处只补充新规则）
        # 注意：evaluate_rules 会检查 requires 字段，缺失的数据源自动跳过
        # 为避免重复触发原有8条规则，仅传入新规则所需的数据源
        enhanced_warnings = evaluate_rules(
            sid, today,
            mental_assessments=mental_assessments,
            wings_scores=wings_scores,
            problem_student=problem_student,
            discipline_records=DisciplineRecord.query.filter(
                DisciplineRecord.student_id == sid,
                DisciplineRecord.created_at >= semester_start,
            ).all(),
        )
        # 过滤：只保留新类型（不与已有 warnings 重复）
        existing_types = {w["type"] for w in warnings}
        for w in enhanced_warnings:
            if w["type"] not in existing_types:
                warnings.append(w)
    except Exception:
        pass  # 增强规则失败不影响原有预警

    return warnings


def _predict_student_behavior(stu, today):
    """预测单个学生未来行为"""
    sid = stu.id

    # 最近30天考勤
    recent_attendance = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= today - timedelta(days=30),
    ).all()

    # 最近90天违纪
    recent_discipline = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= today - timedelta(days=90),
    ).all()

    # 预测未来7天的出勤风险
    absent_rate = sum(1 for r in recent_attendance if r.status == "absent") / max(len(recent_attendance), 1)
    late_rate = sum(1 for r in recent_attendance if r.status == "late") / max(len(recent_attendance), 1)

    # 预测违纪风险
    discipline_count = len(recent_discipline)
    discipline_risk = "high" if discipline_count >= 2 else "medium" if discipline_count == 1 else "low"

    return {
        "absent_risk": round(absent_rate * 100, 1),
        "late_risk": round(late_rate * 100, 1),
        "discipline_risk": discipline_risk,
        "prediction_text": _generate_prediction_text(absent_rate, late_rate, discipline_risk),
    }


def _generate_prediction_text(absent_rate, late_rate, discipline_risk):
    """生成预测建议文本"""
    texts = []
    if absent_rate > 0.2:
        texts.append("未来一周缺勤风险较高，建议重点关注")
    if late_rate > 0.3:
        texts.append("迟到现象较频繁，建议加强时间管理教育")
    if discipline_risk == "high":
        texts.append("违纪风险高，建议加强行为规范和心理辅导")
    elif discipline_risk == "medium":
        texts.append("有一定违纪风险，建议持续关注")

    return texts if texts else ["学生表现良好，建议继续保持"]


# ══════════════════════════════════════════════════════════════
#  定时自动预警扫描 (Cron 调用)
# ══════════════════════════════════════════════════════════════

@ai_analysis_bp.route("/api/scan", methods=["POST"])
def api_scan():
    """定时自动扫描全年级学生风险 — 由 Cron/systemd timer 调用
    请求头: Authorization: Bearer <SCAN_SECRET>
    """
    # 验证密钥
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {SCAN_SECRET}":
        return jsonify({"code": 1, "msg": "Unauthorized"}), 401

    today = date.today()
    app = current_app._get_current_object()
    scan_summary = {"scanned": 0, "new_risks": 0, "red": 0, "yellow": 0, "notifications_sent": 0}

    try:
        with app.app_context():
            # 1. 获取昨天的扫描记录（用于对比新增风险）
            yesterday = today - timedelta(days=1)
            yesterday_records = {
                r.student_id: r.risk_level
                for r in RiskRecord.query.filter(RiskRecord.scan_date == yesterday).all()
            }

            # 2. 查询所有在校学生（含班级预加载）
            all_students = Student.query.filter_by(is_active=True).options(
                joinedload(Student.class_)
            ).all()
            if not all_students:
                return jsonify({"code": 0, "msg": "无学生数据", "summary": scan_summary})

            student_ids = [s.id for s in all_students]
            scan_summary["scanned"] = len(all_students)

            # 3. 批量查询数据（与 index 页面逻辑一致）
            # 3a. 考勤记录（最近30天）
            attendance_map = defaultdict(list)
            att_records = Attendance.query.filter(
                Attendance.student_id.in_(student_ids),
                Attendance.record_date >= today - timedelta(days=30),
            ).all()
            for r in att_records:
                attendance_map[r.student_id].append(r)

            # 3b. 违纪记录（本学期）
            semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)
            discipline_map = defaultdict(list)
            disc_records = DisciplineRecord.query.filter(
                DisciplineRecord.student_id.in_(student_ids),
                DisciplineRecord.created_at >= semester_start,
            ).all()
            for r in disc_records:
                discipline_map[r.student_id].append(r)

            # 3c. 成绩记录（最近2次考试）
            score_map = defaultdict(list)
            rows = db.session.execute(
                text("""
                    SELECT student_id, exam_id, SUM(score) as total
                    FROM scores WHERE student_id IN :sids
                    GROUP BY student_id, exam_id
                    ORDER BY student_id, exam_id DESC
                """),
                {"sids": tuple(student_ids)}
            ).fetchall()
            for row in rows:
                sid = row[0]
                if len(score_map[sid]) < 2:
                    score_map[sid].append({"exam_id": row[1], "total": float(row[2] or 0)})

            # 3d. 请假记录（本月）
            month_start = today.replace(day=1)
            leave_map = defaultdict(list)
            leaves = LeaveRequest.query.filter(
                LeaveRequest.student_id.in_(student_ids),
                LeaveRequest.created_at >= month_start,
                LeaveRequest.status == "approved",
            ).all()
            for r in leaves:
                leave_map[r.student_id].append(r)

            # 3e. 心理问卷数据（MSSMHS-55，取最新一条有效问卷）
            psych_map = {}
            psychs = PsychSurvey.query.filter(
                PsychSurvey.student_id.in_(student_ids),
                PsychSurvey.survey_type == "MSSMHS-55",
                PsychSurvey.is_valid == True,
            ).order_by(PsychSurvey.completed_at.desc()).all()
            for p in psychs:
                if p.student_id not in psych_map:
                    psych_map[p.student_id] = p

            # 3f. 查询班级-教师映射
            class_teacher_map = {}
            teachers = User.query.filter(User.role.in_(["class_teacher", "teacher"])).all()
            for t in teachers:
                if t.class_id:
                    if t.class_id not in class_teacher_map:
                        class_teacher_map[t.class_id] = []
                    class_teacher_map[t.class_id].append(t.id)

            # ══ 增强数据源：批量预加载 ══
            # 3g. 心理健康教师评估
            mental_map = defaultdict(list)
            mental_records = MentalHealthAssessment.query.filter(
                MentalHealthAssessment.student_id.in_(student_ids)
            ).order_by(MentalHealthAssessment.created_at.desc()).all()
            for m in mental_records:
                if len(mental_map[m.student_id]) < 5:
                    mental_map[m.student_id].append(m)

            # 3h. 五翼评价
            wings_map = defaultdict(list)
            wings_records = WingsScore.query.filter(
                WingsScore.student_id.in_(student_ids)
            ).all()
            for w in wings_records:
                wings_map[w.student_id].append(w)

            # 3i. 问题学生档案
            prob_map = {}
            prob_records = ProblemStudent.query.filter(
                ProblemStudent.student_id.in_(student_ids),
                ProblemStudent.is_active == True,
            ).all()
            for p in prob_records:
                prob_map[p.student_id] = p

            # 4. 对每个学生执行预警规则
            week_start = today - timedelta(days=today.weekday())
            new_risks_data = []

            for stu in all_students:
                sid = stu.id
                warnings = []
                att_list = attendance_map.get(sid, [])

                # 4.1 连续缺勤≥3天
                if _check_consecutive_absent_batch(att_list, today):
                    warnings.append({
                        "type": "consecutive_absent", "level": "red",
                        "text": "连续缺勤≥3天",
                        "suggestion": "建议立即联系家长，了解缺勤原因",
                    })

                # 4.2 本月缺勤≥5次
                month_absent = sum(1 for r in att_list if r.record_date >= month_start and r.status == "absent")
                if month_absent >= 5:
                    warnings.append({
                        "type": "monthly_absent", "level": "yellow",
                        "text": f"本月已缺勤{month_absent}次",
                        "suggestion": "建议关注学生出勤情况，必要时约谈家长",
                    })

                # 4.3 本周迟到≥3次
                week_late = sum(1 for r in att_list if r.record_date >= week_start and r.status == "late")
                if week_late >= 3:
                    warnings.append({
                        "type": "weekly_late", "level": "yellow",
                        "text": f"本周已迟到{week_late}次",
                        "suggestion": "建议加强时间观念教育",
                    })

                # 4.4 重大违纪≥1次
                major_count = sum(1 for r in discipline_map.get(sid, []) if r.type == "major")
                if major_count >= 1:
                    warnings.append({
                        "type": "major_discipline", "level": "red",
                        "text": f"有重大违纪{major_count}次",
                        "suggestion": "建议德育处介入，制定个别教育方案",
                    })

                # 4.5 严重违纪≥2次
                serious_count = sum(1 for r in discipline_map.get(sid, []) if r.type == "serious")
                if serious_count >= 2:
                    warnings.append({
                        "type": "serious_discipline", "level": "red",
                        "text": f"严重违纪{serious_count}次",
                        "suggestion": "建议启动危机干预机制",
                    })

                # 4.6 成绩下滑≥10分
                scores = score_map.get(sid, [])
                if len(scores) >= 2:
                    score_drop = max(0, scores[1]["total"] - scores[0]["total"])
                    if score_drop >= 10:
                        warnings.append({
                            "type": "score_drop", "level": "yellow",
                            "text": f"成绩下滑{score_drop:.1f}分",
                            "suggestion": "建议与任课教师沟通，查找学习困难原因",
                        })

                # 4.7 频繁请假≥3次/月
                leave_count = len(leave_map.get(sid, []))
                if leave_count >= 3:
                    warnings.append({
                        "type": "frequent_leave", "level": "yellow",
                        "text": f"本月请假{leave_count}次",
                        "suggestion": "建议关注学生身心健康，了解请假原因",
                    })

                # 4.8 MSSMHS-55心理问卷风险
                psych = psych_map.get(sid)
                if psych and psych.total_score:
                    if psych.total_score >= 160:
                        warnings.append({
                            "type": "psych_survey_high", "level": "red",
                            "text": f"MSSMHS-55心理问卷高风险（{int(psych.total_score)}分）",
                            "suggestion": "心理健康筛查提示高风险，建议安排心理老师个别访谈",
                        })
                    elif psych.total_score >= 120:
                        warnings.append({
                            "type": "psych_survey_medium", "level": "yellow",
                            "text": f"MSSMHS-55心理问卷中风险（{int(psych.total_score)}分）",
                            "suggestion": "建议班主任关注学生情绪状态，适时沟通",
                        })

                # ══ 增强规则：接入额外数据源 ══
                try:
                    from utils.rule_engine import evaluate_rules
                    existing_types = {w["type"] for w in warnings}
                    enhanced = evaluate_rules(
                        sid, today,
                        mental_assessments=mental_map.get(sid, []),
                        wings_scores=wings_map.get(sid, []),
                        problem_student=prob_map.get(sid),
                        discipline_records=discipline_map.get(sid, []),
                    )
                    for w in enhanced:
                        if w["type"] not in existing_types:
                            warnings.append(w)
                except Exception:
                    pass

                # 确定最高风险等级
                max_level = "green"
                for w in warnings:
                    if w["level"] == "red":
                        max_level = "red"
                        break
                    elif w["level"] == "yellow" and max_level == "green":
                        max_level = "yellow"

                # 5. 存入 RiskRecord（含 XGBoost 特征归因）
                attr_result = _build_feature_attribution(warnings) if warnings else None
                attr_json = json_mod.dumps(attr_result, ensure_ascii=False) if attr_result else None
                record = RiskRecord(
                    student_id=sid,
                    grade_id=stu.grade_id,
                    class_id=stu.class_id,
                    scan_date=today,
                    risk_level=max_level,
                    warning_details=json_mod.dumps(warnings, ensure_ascii=False) if warnings else None,
                    warning_count=len(warnings),
                    feature_attribution=attr_json,
                    notification_sent=False,
                )
                db.session.add(record)
                db.session.flush()  # 确保 record.id 可用
                # ── 声呐广播：AI 风险预警实时推送 ──
                if max_level != "green":
                    try:
                        publish_risk(record, "AI扫描")
                    except Exception:
                        pass

                if max_level != "green":
                    scan_summary[max_level] += 1
                    new_risks_data.append({
                        "student_id": sid,
                        "student_name": stu.name or f"学生{sid}",
                        "class_id": stu.class_id,
                        "class_name": stu.class_.name if stu.class_ else "",
                        "risk_level": max_level,
                        "warnings": warnings,
                    })

            db.session.commit()

            # 6. 发送通知（仅对新增或升级的风险）
            from blueprints.common import send_notification
            for risk in new_risks_data:
                yesterday_level = yesterday_records.get(risk["student_id"], "green")
                # 判断是否新增/升级
                level_rank = {"green": 0, "yellow": 1, "red": 2}
                if level_rank.get(risk["risk_level"], 0) > level_rank.get(yesterday_level, 0):
                    # 发送给班主任
                    teacher_ids = class_teacher_map.get(risk["class_id"], [])
                    warning_texts = "；".join(w["text"] for w in risk["warnings"])
                    for tid in teacher_ids:
                        send_notification(
                            to_user_id=tid,
                            title=f"⚠️ AI风险预警 — {risk['student_name']}",
                            content=f"{risk['student_name']}（{risk['class_name']}）触发{risk['risk_level']}预警：{warning_texts}",
                        )
                        scan_summary["notifications_sent"] += 1

                    # 标记已通知
                    RiskRecord.query.filter_by(
                        student_id=risk["student_id"], scan_date=today
                    ).update({"notification_sent": True})
                    db.session.commit()
                    scan_summary["new_risks"] += 1

            print(f"[AI扫描] 扫描{scan_summary['scanned']}人, "
                  f"红{scan_summary['red']} 黄{scan_summary['yellow']}, "
                  f"新增{scan_summary['new_risks']}, 通知{scan_summary['notifications_sent']}条")

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"code": 2, "msg": f"扫描异常: {str(e)}"}), 500

    return jsonify({
        "code": 0,
        "msg": "扫描完成",
        "summary": scan_summary,
        "timestamp": today.isoformat(),
    })


# ══════════════════════════════════════════════════════════════
#  多元回归预测模型
# ══════════════════════════════════════════════════════════════

def _matrix_multiply(A, B):
    """矩阵乘法 A(m×n) × B(n×p) → C(m×p)"""
    m, n = len(A), len(A[0])
    p = len(B[0]) if isinstance(B[0], list) else 1
    if p == 1:
        # B 可能是列向量 [[b0],[b1],...] 或平铺列表 [b0,b1,...]
        return [[sum(A[i][k] * (B[k][0] if isinstance(B[k], list) else B[k]) for k in range(n))] for i in range(m)]
    return [[sum(A[i][k] * B[k][j] for k in range(n)) for j in range(p)] for i in range(m)]


def _matrix_transpose(A):
    """矩阵转置"""
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]


def _matrix_inverse(A):
    """矩阵求逆（高斯消元法，仅用于小型矩阵）"""
    n = len(A)
    # 增广矩阵 [A|I]
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for col in range(n):
        # 寻找主元
        pivot = aug[col][col]
        if abs(pivot) < 1e-10:
            # 尝试换行
            for r in range(col + 1, n):
                if abs(aug[r][col]) > 1e-10:
                    aug[col], aug[r] = aug[r], aug[col]
                    pivot = aug[col][col]
                    break
            else:
                return None  # 奇异矩阵
        # 归一化
        for j in range(2 * n):
            aug[col][j] /= pivot
        # 消元
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            for j in range(2 * n):
                aug[r][j] -= factor * aug[col][j]
    # 提取逆矩阵
    return [[aug[i][j] for j in range(n, 2 * n)] for i in range(n)]


def _multiple_regression(X_list, y_list, feature_names=None):
    """多元线性回归 — 最小二乘法
    Args:
        X_list: [[x1_1, x2_1, ...], [x1_2, x2_2, ...], ...]  自变量矩阵 (n×m)
        y_list: [y1, y2, ...]  因变量
        feature_names: ["缺勤率", "违纪次数", ...]  特征名称
    Returns:
        {
            "intercept": float,
            "coefficients": [(name, beta), ...],
            "r_squared": float,
            "sample_count": int,
            "equation": str,
        }
    """
    n = len(X_list)
    if n < 3:
        return {"error": "样本不足，需要至少3个数据点", "sample_count": n}

    m = len(X_list[0])  # 特征数

    # 构建设计矩阵 X（加截距列全1）
    X = [[1.0] + list(row) for row in X_list]

    # y 转为列向量
    y_vec = [[yi] for yi in y_list]

    # β = (XᵀX)⁻¹Xᵀy
    Xt = _matrix_transpose(X)
    XtX = _matrix_multiply(Xt, X)
    XtX_inv = _matrix_inverse(XtX)
    if XtX_inv is None:
        return {"error": "矩阵奇异，无法求解（特征间可能存在共线性）", "sample_count": n}

    XtY = _matrix_multiply(Xt, y_vec)
    betas = _matrix_multiply(XtX_inv, XtY)  # 列向量 [β0, β1, ..., βm]

    # 提取系数
    intercept = round(betas[0][0], 4)
    coefficients = []
    for i in range(m):
        name = feature_names[i] if feature_names and i < len(feature_names) else f"X{i+1}"
        coefficients.append((name, round(betas[i + 1][0], 4)))

    # 计算 R²
    y_mean = sum(y_list) / n
    ss_total = sum((yi - y_mean) ** 2 for yi in y_list)
    y_pred = [sum(b[0] * X[i][j] for j, b in enumerate(betas)) for i in range(n)]
    ss_residual = sum((y_list[i] - y_pred[i]) ** 2 for i in range(n))
    r_squared = round(1 - ss_residual / max(ss_total, 1e-10), 4)

    # 构造方程字符串
    parts = [f"ŷ = {intercept:.2f}"]
    for name, beta in coefficients:
        sign = "+" if beta >= 0 else ""
        parts.append(f" {sign} {beta:.4f}·{name}")
    equation = "".join(parts)

    return {
        "intercept": intercept,
        "coefficients": coefficients,
        "r_squared": r_squared,
        "sample_count": n,
        "equation": equation,
    }


@ai_analysis_bp.route("/api/regression")
def api_regression():
    """多元回归分析 — 预测期末成绩
    自变量: 缺勤率、迟到率、违纪次数、请假次数
    因变量: 最近一次考试总分
    支持: Bearer token 鉴权（定时任务）或 session 登录（网页端）
    """
    # 验证：要么有 Bearer token，要么有 session 登录
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == SCAN_SECRET:
        pass  # Bearer token 验证通过
    elif session.get("logged_in"):
        # 检查角色权限
        role = session.get("role", "")
        if role not in ("ms_admin", "grade_leader"):
            return jsonify({"code": 1, "msg": "权限不足"}), 403
    else:
        return jsonify({"code": 1, "msg": "未登录"}), 401
    
    today = date.today()
    semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)
    month_start = today.replace(day=1)

    # 权限范围
    role = session.get("role", "")
    grade_id = session.get("grade_id")

    students_q = Student.query.filter_by(is_active=True)
    if grade_id:
        students_q = students_q.filter_by(grade_id=grade_id)

    students = students_q.all()
    if len(students) < 5:
        return jsonify({"code": 1, "msg": "样本不足，需要至少5名学生"})

    student_ids = [s.id for s in students]

    # 批量查询
    att_records = Attendance.query.filter(
        Attendance.student_id.in_(student_ids),
        Attendance.record_date >= semester_start,
    ).all()
    att_map = defaultdict(list)
    for r in att_records:
        att_map[r.student_id].append(r)

    disc_records = DisciplineRecord.query.filter(
        DisciplineRecord.student_id.in_(student_ids),
        DisciplineRecord.created_at >= semester_start,
    ).all()
    disc_map = defaultdict(list)
    for r in disc_records:
        disc_map[r.student_id].append(r)

    leaves = LeaveRequest.query.filter(
        LeaveRequest.student_id.in_(student_ids),
        LeaveRequest.created_at >= semester_start,
        LeaveRequest.status == "approved",
    ).all()
    leave_map = defaultdict(list)
    for r in leaves:
        leave_map[r.student_id].append(r)

    # 最近一次考试 ID
    last_exam = db.session.execute(
        text("SELECT exam_id FROM scores WHERE student_id IN :sids GROUP BY exam_id ORDER BY exam_id DESC LIMIT 1"),
        {"sids": tuple(student_ids)}
    ).fetchone()
    if not last_exam:
        return jsonify({"code": 1, "msg": "无考试成绩数据"})

    last_exam_id = last_exam[0]

    # 构建回归数据
    X_list = []
    y_list = []
    student_names = []

    # 批量查询最后一场考试的所有学生总分（优化: 1次替代N次）
    student_scores = {}
    if last_exam_id:
        score_rows = db.session.query(
            Score.student_id,
            func.sum(Score.score)
        ).filter(
            Score.exam_id == last_exam_id
        ).group_by(Score.student_id).all()
        student_scores = {sid: float(total) for sid, total in score_rows}

    for s in students:
        atts = att_map.get(s.id, [])
        total_att = len(atts)
        absent_rate = sum(1 for r in atts if r.status == "absent") / max(total_att, 1)
        late_rate = sum(1 for r in atts if r.status == "late") / max(total_att, 1)
        disc_count = len(disc_map.get(s.id, []))
        leave_count = len(leave_map.get(s.id, []))

        # 从预加载的字典中获取总分（已批量查询，避免N+1）
        total_score = student_scores.get(s.id)

        if total_score is None:
            continue

        X_list.append([absent_rate * 100, disc_count, leave_count])
        y_list.append(float(total_score))
        student_names.append(s.name or f"学生{s.id}")

    if len(X_list) < 5:
        return jsonify({"code": 1, "msg": f"有效样本仅{len(X_list)}个，需要≥5"})

    # 逐列检查特征方差，移除零方差列（会导致矩阵奇异）
    feature_names = ["缺勤率(%)", "违纪次数", "请假次数"]
    n_features = len(X_list[0])
    valid_cols = []
    for j in range(n_features):
        vals = [X_list[i][j] for i in range(len(X_list))]
        mean_val = sum(vals) / len(vals)
        var_val = sum((v - mean_val) ** 2 for v in vals) / len(vals)
        if var_val > 0.0001:  # 方差>0的列保留
            valid_cols.append(j)

    if not valid_cols:
        return jsonify({
            "code": 1,
            "msg": "当前无有效特征数据（考勤/违纪/请假均为0），无法建立回归模型。请先导入相关业务数据。",
            "hint": "需要: attendance(考勤), discipline_records(违纪), leave_requests(请假)"
        })

    # 仅保留有效列
    X_filtered = [[X_list[i][j] for j in valid_cols] for i in range(len(X_list))]
    names_filtered = [feature_names[j] for j in valid_cols]

    result = _multiple_regression(
        X_filtered, y_list,
        feature_names=names_filtered
    )

    if "error" in result:
        return jsonify({"code": 1, "msg": result["error"]})

    # 为每个学生生成预测值
    predictions = []
    betas = [result["intercept"]] + [c[1] for c in result["coefficients"]]
    for i in range(len(X_filtered)):
        y_pred = betas[0] + sum(betas[j + 1] * X_filtered[i][j] for j in range(len(X_filtered[i])))
        residual = y_list[i] - y_pred
        predictions.append({
            "name": student_names[i],
            "actual": round(y_list[i], 1),
            "predicted": round(y_pred, 1),
            "residual": round(residual, 1),
        })

    return jsonify({
        "code": 0,
        "model": {
            "equation": result["equation"],
            "r_squared": result["r_squared"],
            "sample_count": result["sample_count"],
            "coefficients": [{"name": n, "beta": b} for n, b in result["coefficients"]],
            "intercept": result["intercept"],
        },
        "predictions": predictions,
    })


# ══════════════════════════════════════════════════════════════
#  统一仪表盘 — 问卷 + 评估 + 行为预警 三合一视图
# ══════════════════════════════════════════════════════════════

@ai_analysis_bp.route("/dashboard")
@require_role("ms_admin", "grade_leader", "class_teacher")
def dashboard():
    """统一仪表盘：每个学生展示问卷分数 + 心理健康评估 + AI行为预警"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")
    today = date.today()

    # 1. 确定学生范围
    students_q = Student.query.filter_by(is_active=True)
    if role == "grade_leader" and grade_id:
        students_q = students_q.filter_by(grade_id=grade_id)
    elif role in ("class_teacher", "teacher") and class_id:
        students_q = students_q.filter_by(class_id=class_id)

    all_students = students_q.options(
        joinedload(Student.class_)
    ).order_by(Student.class_id, Student.name).all()
    student_ids = [s.id for s in all_students]

    if not student_ids:
        return render_template("ai_analysis/dashboard.html", students=[], stats={})

    # 2. 批量查询三种数据源
    # 2a. 心理问卷（MSSMHS-55，每人最新一条）
    psych_map = {}
    psychs = PsychSurvey.query.filter(
        PsychSurvey.student_id.in_(student_ids),
        PsychSurvey.survey_type == "MSSMHS-55",
        PsychSurvey.is_valid == True,
    ).order_by(PsychSurvey.completed_at.desc()).all()
    for p in psychs:
        if p.student_id not in psych_map:
            psych_map[p.student_id] = p

    # 2b. 心理健康评估（每人最新一条）
    assessment_map = {}
    assessments = MentalHealthAssessment.query.filter(
        MentalHealthAssessment.student_id.in_(student_ids),
    ).order_by(MentalHealthAssessment.created_at.desc()).all()
    for a in assessments:
        if a.student_id not in assessment_map:
            assessment_map[a.student_id] = a

    # 2c. 最新的AI扫描记录
    latest_scan = db.session.execute(
        text("SELECT student_id, MAX(scan_date) FROM risk_records WHERE student_id IN :sids GROUP BY student_id"),
        {"sids": tuple(student_ids) if len(student_ids) > 1 else f"({student_ids[0]})"}
    ).fetchall()
    latest_scan_dates = {row[0]: row[1] for row in latest_scan}

    risk_map = {}
    if latest_scan_dates:
        risk_records = RiskRecord.query.filter(
            RiskRecord.student_id.in_(student_ids),
        ).all()
        for r in risk_records:
            if r.student_id in latest_scan_dates and r.scan_date == latest_scan_dates[r.student_id]:
                risk_map[r.student_id] = r

    # 3. 组装学生数据
    student_data = []
    for stu in all_students:
        sid = stu.id
        psych = psych_map.get(sid)
        assessment = assessment_map.get(sid)
        risk = risk_map.get(sid)

        # 计算综合风险等级（取三种数据源中最严重的）
        levels = {"green": 0, "yellow": 1, "red": 2}
        combined = "green"
        if psych and psych.total_score:
            if psych.total_score >= 160:
                combined = "red"
            elif psych.total_score >= 120 and combined == "green":
                combined = "yellow"

        if assessment and assessment.risk_level:
            lvl = assessment.risk_level
            if levels.get(lvl, 0) > levels.get(combined, 0):
                combined = lvl

        if risk and risk.risk_level:
            lvl = risk.risk_level
            if levels.get(lvl, 0) > levels.get(combined, 0):
                combined = lvl

        student_data.append({
            "student": stu,
            "class_name": stu.class_.name if stu.class_ else "",
            "psych_score": int(psych.total_score) if psych and psych.total_score else None,
            "psych_risk": "high" if psych and psych.total_score and psych.total_score >= 160 else (
                "medium" if psych and psych.total_score and psych.total_score >= 120 else (
                    "low" if psych else None
                )
            ),
            "assessment": assessment,
            "risk_record": risk,
            "combined_risk": combined,
        })

    # 4. 统计（含处置率）
    total_risks = sum(1 for d in student_data if d["risk_record"])
    processed_risks = sum(1 for d in student_data if d["risk_record"] and d["risk_record"].is_processed)
    stats = {
        "total": len(student_data),
        "has_psych": sum(1 for d in student_data if d["psych_score"] is not None),
        "has_assessment": sum(1 for d in student_data if d["assessment"]),
        "has_risk": total_risks,
        "processed_risks": processed_risks,
        "disposal_rate": round(processed_risks / total_risks * 100, 1) if total_risks > 0 else 0,
        "red": sum(1 for d in student_data if d["combined_risk"] == "red"),
        "yellow": sum(1 for d in student_data if d["combined_risk"] == "yellow"),
        "green": sum(1 for d in student_data if d["combined_risk"] == "green"),
    }

    return render_template("ai_analysis/dashboard.html",
                           students=student_data,
                           stats=stats,
                           today=today)


@ai_analysis_bp.route("/dashboard/<int:sid>")
@require_role("ms_admin", "grade_leader", "class_teacher")
def dashboard_detail(sid):
    """统一仪表盘 — 单个学生详细视图"""
    student = Student.query.get_or_404(sid)
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        flash("无权查看", "danger")
        return redirect(url_for("ai_analysis.dashboard"))
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        flash("无权查看", "danger")
        return redirect(url_for("ai_analysis.dashboard"))

    today = date.today()

    # 心理问卷
    psych = PsychSurvey.query.filter_by(
        student_id=sid,
        survey_type="MSSMHS-55",
        is_valid=True
    ).order_by(PsychSurvey.completed_at.desc()).first()

    # 心理健康评估列表
    assessments = MentalHealthAssessment.query.filter_by(
        student_id=sid
    ).order_by(MentalHealthAssessment.created_at.desc()).all()

    # 最新AI扫描
    risk = RiskRecord.query.filter_by(
        student_id=sid
    ).order_by(RiskRecord.scan_date.desc()).first()

    # AI行为预警（调用已有的分析函数）
    warnings = _analyze_student_detail(student, today)

    # 问卷答案解析（如果有）
    psych_answers = None
    if psych and psych.answers_json:
        try:
            psych_answers = json_mod.loads(psych.answers_json)
        except Exception:
            pass

    # 解析心理问卷维度JSON（供模板使用）
    psych_dimensions = {}
    if psych and psych.dimensions_json:
        try:
            psych_dimensions = json_mod.loads(psych.dimensions_json)
        except Exception:
            psych_dimensions = {}

    # 解析 XGBoost 特征归因
    feature_attr = None
    if risk and risk.feature_attribution:
        try:
            feature_attr = json_mod.loads(risk.feature_attribution)
        except Exception:
            pass

    return render_template("ai_analysis/dashboard_detail.html",
                           student=student,
                           psych=psych, psych_answers=psych_answers,
                           psych_dimensions=psych_dimensions,
                           assessments=assessments,
                           risk=risk, warnings=warnings, feature_attr=feature_attr,
                           today=today)


# ════════════════════════════════════════════════════════════
#  综合风险评分模型（规则引擎增强版）
# ════════════════════════════════════════════════════════════

def _calculate_comprehensive_risk_score(stu, today, attendance_records=None,
                                        discipline_records=None, score_data=None,
                                        leave_records=None, psych_survey=None):
    """
    综合风险评分（0-100分）
    公式: 总分 = 心理×0.4 + 成绩×0.3 + 违纪×0.2 + 考勤×0.1
    返回: {"total_score": float, "risk_level": str, "factors": {...}}
    """
    sid = stu.id
    factors = {}

    # 1. 心理健康风险 (权重 0.4)
    psych_score = 0
    psych_details = ""
    if psych_survey and psych_survey.total_score:
        psych_total = psych_survey.total_score
        if psych_total >= 160:
            psych_score = 100
            psych_details = f"MSSMHS-55高风险({int(psych_total)}分)"
        elif psych_total >= 120:
            psych_score = 60
            psych_details = f"MSSMHS-55中风险({int(psych_total)}分)"
        else:
            psych_score = 20
            psych_details = f"MSSMHS-55低风险({int(psych_total)}分)"
    else:
        psych_score = 10
        psych_details = "无心理问卷数据"

    factors["psych"] = {"score": psych_score, "weight": 0.4, "details": psych_details}

    # 2. 成绩下滑风险 (权重 0.3)
    grade_score = 0
    grade_details = ""
    if score_data and len(score_data) >= 2:
        score_drop = max(0, score_data[1]["total"] - score_data[0]["total"])
        if score_drop >= 20:
            grade_score = 80
            grade_details = f"成绩大幅下滑{score_drop:.1f}分"
        elif score_drop >= 10:
            grade_score = 60
            grade_details = f"成绩下滑{score_drop:.1f}分"
        elif score_drop >= 5:
            grade_score = 40
            grade_details = f"成绩轻微下滑{score_drop:.1f}分"
        else:
            grade_score = 10
            grade_details = f"成绩稳定（变化{score_drop:.1f}分）"
    else:
        grade_score = 30
        grade_details = "成绩数据不足"

    factors["grade"] = {"score": grade_score, "weight": 0.3, "details": grade_details}

    # 3. 违纪风险 (权重 0.2)
    discipline_score = 0
    discipline_details = ""
    if discipline_records:
        major_count = sum(1 for r in discipline_records if r.type == "major")
        serious_count = sum(1 for r in discipline_records if r.type == "serious")
        minor_count = sum(1 for r in discipline_records if r.type == "minor")

        if major_count >= 1 or serious_count >= 2:
            discipline_score = 100
            discipline_details = f"重大违纪{major_count}次/严重违纪{serious_count}次"
        elif serious_count >= 1 or minor_count >= 3:
            discipline_score = 60
            discipline_details = f"严重违纪{serious_count}次/轻微违纪{minor_count}次"
        elif minor_count >= 1:
            discipline_score = 30
            discipline_details = f"轻微违纪{minor_count}次"
        else:
            discipline_score = 0
            discipline_details = "本学期无违纪"
    else:
        discipline_score = 0
        discipline_details = "本学期无违纪记录"

    factors["discipline"] = {"score": discipline_score, "weight": 0.2, "details": discipline_details}

    # 4. 考勤风险 (权重 0.1)
    attendance_score = 0
    attendance_details = ""
    if attendance_records:
        month_start = today.replace(day=1)
        month_absent = sum(1 for r in attendance_records if r.record_date >= month_start and r.status == "absent")
        week_start = today - timedelta(days=today.weekday())
        week_late = sum(1 for r in attendance_records if r.record_date >= week_start and r.status == "late")

        if month_absent >= 5:
            attendance_score = 100
            attendance_details = f"本月缺勤{month_absent}次"
        elif month_absent >= 3 or week_late >= 3:
            attendance_score = 60
            attendance_details = f"本月缺勤{month_absent}次/本周迟到{week_late}次"
        elif month_absent >= 1 or week_late >= 1:
            attendance_score = 30
            attendance_details = f"本月缺勤{month_absent}次/本周迟到{week_late}次"
        else:
            attendance_score = 0
            attendance_details = "出勤正常"
    else:
        attendance_score = 20
        attendance_details = "考勤数据不足"

    factors["attendance"] = {"score": attendance_score, "weight": 0.1, "details": attendance_details}

    # 计算总分
    total_score = sum(factors[f]["score"] * factors[f]["weight"] for f in factors)
    total_score = round(total_score, 1)

    return {
        "total_score": total_score,
        "risk_level": "red" if total_score >= 70 else ("yellow" if total_score >= 40 else "green"),
        "factors": factors,
    }


@ai_analysis_bp.route("/api/comprehensive-risk/<int:sid>")
@login_required
def api_comprehensive_risk(sid):
    """综合风险评分 API — 返回0-100分风险评分 + 因子分解"""
    student = Student.query.get_or_404(sid)
    today = date.today()

    # 权限检查
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        return jsonify({"error": "无权查看"}), 403
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        return jsonify({"error": "无权查看"}), 403

    semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    # 查询各类数据
    att_records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= today - timedelta(days=30),
    ).all()

    disc_records = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= semester_start,
    ).all()

    score_rows = db.session.execute(
        text("""
            SELECT exam_id, SUM(score) as total
            FROM scores WHERE student_id = :sid
            GROUP BY exam_id ORDER BY exam_id DESC LIMIT 2
        """),
        {"sid": sid}
    ).fetchall()
    score_data = [{"exam_id": r[0], "total": float(r[1] or 0)} for r in score_rows]

    leave_count = LeaveRequest.query.filter(
        LeaveRequest.student_id == sid,
        LeaveRequest.created_at >= month_start,
        LeaveRequest.status == "approved",
    ).count()

    psych = PsychSurvey.query.filter_by(
        student_id=sid,
        survey_type="MSSMHS-55",
        is_valid=True
    ).order_by(PsychSurvey.completed_at.desc()).first()

    # 计算综合风险评分
    result = _calculate_comprehensive_risk_score(
        student, today,
        attendance_records=att_records,
        discipline_records=disc_records,
        score_data=score_data,
        leave_records=list(range(leave_count)),  # 仅用数量
        psych_survey=psych,
    )

    return jsonify({
        "student_id": sid,
        "student_name": student.name,
        "total_score": result["total_score"],
        "risk_level": result["risk_level"],
        "factors": result["factors"],
        "suggested_actions": _generate_action_suggestions(result),
    })


@ai_analysis_bp.route("/api/briefing/<int:sid>")
@login_required
def api_briefing(sid):
    """
    AI 面谈简报生成 — 6维特征 → DeepSeek → 面谈脚本
    返回: {"code": 0, "briefing": {...}}
    """
    from models import WingsScore
    from sqlalchemy import func
    student = Student.query.get_or_404(sid)
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        return jsonify({"error": "无权查看"}), 403
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        return jsonify({"error": "无权查看"}), 403

    today = date.today()
    semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    # ── 1. 提取6维特征 ──
    # 维度1: WingsScore 各维度均分 + 趋势
    wings_avg = {}
    wings_trend = {}
    for dim in ("德", "智", "体", "美", "劳"):
        avg = db.session.query(func.avg(WingsScore.score)).filter(
            WingsScore.student_id == sid,
            WingsScore.dimension == dim
        ).scalar()
        wings_avg[dim] = round(float(avg), 1) if avg else 0
        scores = WingsScore.query.filter_by(
            student_id=sid, dimension=dim
        ).order_by(WingsScore.created_at.desc()).limit(3).all()
        wings_trend[dim] = [round(float(s.score), 1) for s in scores]

    # 维度2: 违纪次数（本学期）
    disc_count = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= semester_start,
    ).count()
    major_count = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= semester_start,
        DisciplineRecord.type == "major",
    ).count()
    serious_count = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= semester_start,
        DisciplineRecord.type == "serious",
    ).count()

    # 维度3: 最新 RiskRecord
    risk = RiskRecord.query.filter_by(student_id=sid).order_by(RiskRecord.scan_date.desc()).first()
    risk_level = risk.risk_level if risk else "green"
    risk_warning_count = risk.warning_count if risk else 0

    # 维度4: 近期违纪类型
    recent_discs = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= today - timedelta(days=30),
    ).all()
    disc_types = {}
    for d in recent_discs:
        cat = d.category or "未分类"
        disc_types[cat] = disc_types.get(cat, 0) + 1

    # 维度5: 出勤率（最近30天）
    att_records = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= today - timedelta(days=30),
    ).all()
    att_total = len(att_records)
    att_present = sum(1 for r in att_records if r.status == "present")
    attendance_rate = round(att_present / att_total * 100, 1) if att_total > 0 else 100

    # 维度6: 请假频率（本月）
    leave_count = LeaveRequest.query.filter(
        LeaveRequest.student_id == sid,
        LeaveRequest.created_at >= month_start,
        LeaveRequest.status == "approved",
    ).count()

    feature_summary = {
        "student_name": student.name,
        "class_name": student.class_.name if student.class_ else "",
        "wings_avg": wings_avg,
        "wings_trend": wings_trend,
        "disc_count": disc_count,
        "major_count": major_count,
        "serious_count": serious_count,
        "risk_level": risk_level,
        "risk_warning_count": risk_warning_count,
        "recent_disc_types": disc_types,
        "attendance_rate": attendance_rate,
        "leave_count": leave_count,
    }

    # ── 2. 调用 DeepSeek LLM ──
    try:
        briefing = _call_deepseek_briefing(feature_summary)
    except Exception as e:
        return jsonify({"code": 1, "msg": f"LLM 调用失败: {str(e)}"}), 500

    # ── 3. 声呐广播 ──
    try:
        publish_briefing(student.name, session.get("display_name", ""), briefing.get("highlights", []))
    except Exception:
        pass

    return jsonify({
        "code": 0,
        "student_id": sid,
        "student_name": student.name,
        "briefing": briefing,
    })


def _call_deepseek_briefing(feature_summary):
    """
    调用 DeepSeek 生成结构化面谈简报
    要求输出严格 JSON（response_format: json_object）
    """
    api_key = current_app.config.get("LLM_API_KEY", "")
    api_url = current_app.config.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = current_app.config.get("LLM_MODEL", "deepseek-chat")
    timeout = current_app.config.get("LLM_TIMEOUT", 30)

    if not api_key:
        raise RuntimeError("LLM_API_KEY 未配置，请在环境变量中设置")

    system_prompt = """你是梨江中学资深德育主任，擅长与学生进行高效、共情的面谈。
你根据6维特征向量，生成结构化的面谈简报。

输出必须是合法 JSON（response_format: json_object），严格遵循以下 Schema：
{
  "summary": "一句话画像（≤30字，简练有力）",
  "highlights": ["亮点1（≤15字）", "亮点2（≤15字）"],
  "concerns": ["需关注点1（≤15字）", "需关注点2（≤15字）"],
  "conversation_script": [
    {"role": "teacher", "text": "开场白（共情、不对抗，≤40字）"},
    {"role": "student", "text": "（预设学生可能反应，真实）"},
    {"role": "teacher", "text": "跟进话术（具体、可操作，≤50字）"},
    {"role": "student", "text": "（预设反应）"},
    {"role": "teacher", "text": "收尾（约定下次检查，≤30字）"}
  ],
  "suggestions": ["后续跟进建议1（≤20字）", "后续跟进建议2（≤20字）"]
}

注意：
1. conversation_script 不少于5轮，真实还原面谈场景；
2. 话术必须符合初中生心理，避免说教；
3. 如果 risk_level 为 red，话术须包含危机干预内容；
4. 所有文本使用中文，语气平和、共情。
"""

    user_content = f"请为以下学生生成面谈简报：\n{json_mod.dumps(feature_summary, ensure_ascii=False, indent=2)}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    return json_mod.loads(content)


def _generate_action_suggestions(risk_result):
    """根据风险评分生成干预建议"""
    suggestions = []
    factors = risk_result["factors"]

    if factors["psych"]["score"] >= 60:
        suggestions.append("建议安排心理老师个别访谈，评估心理健康状况")
    if factors["grade"]["score"] >= 60:
        suggestions.append("建议与任课教师沟通，制定学习辅导计划")
    if factors["discipline"]["score"] >= 60:
        suggestions.append("建议德育处介入，制定行为干预方案")
    if factors["attendance"]["score"] >= 60:
        suggestions.append("建议联系家长，了解缺勤/迟到原因")

    if not suggestions:
        suggestions.append("学生表现良好，建议继续保持并定期关注")

    return suggestions

# ════════════════════════════════════════════════════════════
#  Step 2：成绩预测模型（线性回归） + Step 3-5
# ════════════════════════════════════════════════════════════

@ai_analysis_bp.route("/api/predict/grades/<int:sid>")
@login_required
def api_predict_grades(sid):
    """成绩预测 API — 线性回归预测下次考试成绩"""
    from sklearn.linear_model import LinearRegression
    import numpy as np

    student = Student.query.get_or_404(sid)
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        return jsonify({"error": "无权查看"}), 403
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        return jsonify({"error": "无权查看"}), 403

    rows = db.session.execute(
        text("SELECT s.exam_id, sub.name AS subject, s.score FROM scores s JOIN subjects sub ON s.subject_id = sub.id WHERE s.student_id=:sid ORDER BY s.exam_id ASC"),
        {"sid": sid}
    ).fetchall()

    if not rows:
        return jsonify({"code": 1, "msg": "无成绩数据，无法预测"})

    from collections import defaultdict
    subject_scores = defaultdict(list)
    for r in rows:
        subject_scores[r[1]].append(float(r[2]))

    predictions = []
    for subject, scores in subject_scores.items():
        if len(scores) < 2:
            continue
        X = np.array([[i+1] for i in range(len(scores))])
        y = np.array(scores)
        model = LinearRegression()
        model.fit(X, y)
        next_no = len(scores) + 1
        pred = float(model.predict([[next_no]])[0])
        predictions.append({
            "subject": subject,
            "historical": scores,
            "predicted": round(pred, 1),
            "trend": "rising" if model.coef_[0] > 0 else ("declining" if model.coef_[0] < 0 else "stable"),
            "confidence": round(float(model.score(X, y)), 2)
        })

    return jsonify({"code": 0, "student_name": student.name, "predictions": predictions})


@ai_analysis_bp.route("/api/predict/mental-health/<int:sid>")
@login_required
def api_predict_mental_health(sid):
    """心理健康风险预测 API — 逻辑回归"""
    from sklearn.linear_model import LogisticRegression
    import numpy as np

    student = Student.query.get_or_404(sid)
    role = session.get("role", "")
    if role == "grade_leader" and student.grade_id != session.get("grade_id"):
        return jsonify({"error": "无权查看"}), 403
    elif role in ("class_teacher", "teacher") and student.class_id != session.get("class_id"):
        return jsonify({"error": "无权查看"}), 403

    # 获取该生MSSMHS-55维度分
    psych = PsychSurvey.query.filter_by(student_id=sid, survey_type="MSSMHS-55", is_valid=True).order_by(PsychSurvey.completed_at.desc()).first()
    if not psych or not psych.dimensions_json:
        return jsonify({"code": 1, "msg": "无心理问卷数据"})

    try:
        dims = json_mod.loads(psych.dimensions_json)
        X = np.array([[v for v in dims.values()]])
    except Exception:
        return jsonify({"code": 1, "msg": "问卷数据格式错误"})

    # 简化：用规则引擎代替训练模型（需要标注数据才能训练）
    # 这里用阈值规则给出风险概率
    total = psych.total_score or 0
    if total >= 160:
        prob = 0.85
        level = "high"
    elif total >= 120:
        prob = 0.55
        level = "medium"
    else:
        prob = 0.15
        level = "low"

    return jsonify({
        "code": 0,
        "student_name": student.name,
        "total_score": int(total),
        "risk_probability": prob,
        "risk_level": level,
        "dimensions": dims,
    })


@ai_analysis_bp.route("/api/predict/discipline/<int:sid>")
@login_required
def api_predict_discipline(sid):
    """违纪趋势预测 API — 基于历史频率的简单预测"""
    student = Student.query.get_or_404(sid)
    today = date.today()
    semester_start = today.replace(month=9, day=1) if today.month >= 9 else today.replace(month=2, day=1)

    records = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == sid,
        DisciplineRecord.created_at >= semester_start,
    ).order_by(DisciplineRecord.created_at.asc()).all()

    if len(records) < 2:
        return jsonify({"code": 0, "student_name": student.name, "predicted_count_30d": 0, "risk": "low"})

    # 计算日均违纪率
    days = max(1, (records[-1].created_at.date() - records[0].created_at.date()).days)
    rate = len(records) / days  # 平均每天违纪次数
    predicted_30d = round(rate * 30, 1)

    risk = "high" if predicted_30d >= 3 else ("medium" if predicted_30d >= 1 else "low")

    return jsonify({
        "code": 0,
        "student_name": student.name,
        "historical_count": len(records),
        "daily_rate": round(rate, 3),
        "predicted_count_30d": predicted_30d,
        "risk": risk,
    })


@ai_analysis_bp.route("/api/predict/quality/<int:sid>")
@login_required
def api_predict_quality(sid):
    """综合素质评价预测 API — 基于历史评分趋势"""
    student = Student.query.get_or_404(sid)

    # 获取该生所有综合素质评分记录
    from models import QualityScore
    scores = QualityScore.query.filter_by(student_id=sid).order_by(QualityScore.created_at.asc()).all()

    if not scores:
        return jsonify({"code": 1, "msg": "无综合素质评价数据"})

    # 按维度分组，计算每个维度的趋势
    from collections import defaultdict
    dim_trends = defaultdict(list)
    for s in scores:
        dim_trends[s.dimension].append(s.score)

    predictions = {}
    for dim, hist in dim_trends.items():
        if len(hist) >= 2:
            # 简单线性回归
            import numpy as np
            X = np.array([[i+1] for i in range(len(hist))])
            y = np.array(hist)
            from sklearn.linear_model import LinearRegression
            model = LinearRegression()
            model.fit(X, y)
            next_no = len(hist) + 1
            pred = float(model.predict([[next_no]])[0])
            predictions[dim] = {
                "historical": hist,
                "predicted": round(max(0, min(100, pred)), 1),
                "trend": "rising" if model.coef_[0] > 0 else ("declining" if model.coef_[0] < 0 else "stable")
            }

    return jsonify({
        "code": 0,
        "student_name": student.name,
        "dimension_predictions": predictions,
    })
