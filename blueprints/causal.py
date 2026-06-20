"""跨表因果链诊断引擎 — 成绩下滑时自动关联行为/心理/考勤数据，生成因果链诊断报告"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, session
from models import db, Student, Class, Grade, Exam, Score, Subject, WingsScore, \
    DisciplineRecord, Attendance, MentalHealthAssessment, \
    InterventionRecord, TeacherNote, CausalDiagnosis
from decorators import login_required, require_role
from utils.db_utils import safe_commit
from utils import get_local_now
from blueprints.audit_log import audit_log
from sqlalchemy import func
import json as _json
from utils.llm_client import call_llm_json, LLMAvailabilityError

causal_bp = Blueprint("causal", __name__)

# ══════════════════════════════════════════════════════════════
#  AI 因果链诊断 — System Prompt
# ══════════════════════════════════════════════════════════════
CAUSAL_SYSTEM_PROMPT = """你是一位拥有30年经验的初中教育数据分析师兼心理咨询师，精通"成绩-行为-心理"三元因果链诊断。你的任务是根据学生的跨表数据证据链，诊断成绩下滑的根本原因，并给出精准干预方案。

[核心约束]
1. 诊断必须基于提供的证据数据，严禁主观臆测。
2. 必须区分【主要原因】和【次要原因】，给出明确的因果推理。
3. 干预方案必须具体可执行（如"建议班主任周三下午单独谈话"而非"加强沟通"）。
4. risk_level 必须根据证据严重程度客观评定：critical(下滑>30分且有心理高危)/high(下滑>20分)/medium(下滑>10分)/low(下滑<=10分)。
5. diagnosis_report 200-400字，结构为：现象描述→证据分析→因果推理→建议。
6. evidence_chain 是JSON数组，每个元素包含 {"type": "类型", "detail": "具体内容", "severity": "high/medium/low"}

[输出格式]
必须输出严格的 JSON 格式，不要任何 Markdown 包裹（如 ```json），直接返回以下结构的字符串：
{
  "evidence_chain": [
    {"type": "成绩", "detail": "数学从85分降至62分(-23分)", "severity": "high"},
    {"type": "违纪", "detail": "近两周迟到3次、课堂讲话1次", "severity": "medium"}
  ],
  "primary_cause": "一句话主要诊断原因",
  "secondary_cause": "一句话次要原因",
  "diagnosis_report": "200-400字诊断报告正文",
  "intervention_plan": "100-200字具体干预方案",
  "risk_level": "low/medium/high/critical"
}"""


def _build_evidence_chain(student_id, class_id, grade_id, exam_id, subject_id, prev_score, curr_score, score_drop):
    """
    跨表收集证据链 — 查询违纪、考勤、心理评估、干预记录、班主任手记
    返回 (evidence_list, context_text)
    """
    evidence = []
    context_lines = []
    s = Student.query.get(student_id)
    subj = Subject.query.get(subject_id) if subject_id else None
    exam = Exam.query.get(exam_id)

    # 基本信息
    name = s.name if s else "未知"
    cls_name = s.class_.name if s and s.class_ else ""
    subj_name = subj.name if subj else "全科"
    exam_name = exam.name if exam else ""

    context_lines.append(f"学生: {name} | 班级: {cls_name} | 科目: {subj_name} | 考试: {exam_name}")
    context_lines.append(f"成绩变化: {prev_score:.1f} → {curr_score:.1f} (下滑 {score_drop:.1f} 分)")
    context_lines.append("")

    # 1. 成绩下滑证据
    evidence.append({
        "type": "成绩",
        "detail": f"{subj_name}从{prev_score:.1f}降至{curr_score:.1f}，下滑{score_drop:.1f}分",
        "severity": "critical" if score_drop > 30 else "high" if score_drop > 20 else "medium" if score_drop > 10 else "low"
    })

    # 2. 该科目其他学生是否有类似下滑（班级趋势）
    class_avg_prev = db.session.query(func.avg(Score.score)).filter(
        Score.exam_id == exam_id - 1 if exam else False,
        Score.subject_id == subject_id,
        Score.class_id == class_id,
        Score.verify_status == "VERIFIED"
    ).scalar()
    # 简化：只查当前考试班级均分
    class_avg_curr = db.session.query(func.avg(Score.score)).filter(
        Score.exam_id == exam_id,
        Score.subject_id == subject_id,
        Score.class_id == class_id,
        Score.verify_status == "VERIFIED"
    ).scalar()
    if class_avg_curr:
        context_lines.append(f"班级{subj_name}均分: {float(class_avg_curr):.1f}")

    # 3. 违纪记录（近30天）
    thirty_days_ago = get_local_now() - __import__("datetime").timedelta(days=30)
    disc_records = DisciplineRecord.query.filter(
        DisciplineRecord.student_id == student_id,
        DisciplineRecord.created_at >= thirty_days_ago,
        DisciplineRecord.status == "active"
    ).all()
    if disc_records:
        disc_summary = "; ".join([f"{r.category}({r.type})" for r in disc_records])
        evidence.append({
            "type": "违纪",
            "detail": f"近30天违纪{len(disc_records)}条: {disc_summary}",
            "severity": "high" if len(disc_records) >= 3 else "medium" if len(disc_records) >= 1 else "low"
        })
        context_lines.append(f"近30天违纪记录({len(disc_records)}条): {disc_summary}")
    else:
        context_lines.append("近30天无违纪记录")

    # 4. 考勤异常（近30天）
    att_abnormal = Attendance.query.filter(
        Attendance.student_id == student_id,
        Attendance.record_date >= thirty_days_ago.date() if hasattr(thirty_days_ago, "date") else thirty_days_ago,
        Attendance.status.in_(["late", "absent", "early", "leave"])
    ).count()
    if att_abnormal > 0:
        evidence.append({
            "type": "考勤",
            "detail": f"近30天考勤异常{att_abnormal}次",
            "severity": "high" if att_abnormal >= 5 else "medium" if att_abnormal >= 2 else "low"
        })
        context_lines.append(f"近30天考勤异常: {att_abnormal}次")
    else:
        context_lines.append("近30天考勤正常")

    # 5. 心理评估（最近一次）
    latest_psych = MentalHealthAssessment.query.filter_by(
        student_id=student_id
    ).order_by(MentalHealthAssessment.created_at.desc()).first()
    if latest_psych:
        total = 0
        count = 0
        # 尝试获取总分维度
        for dim in ["anxiety", "depression", "somatization", "fear", "paranoia", "obsession", "interpersonal", "hostility"]:
            val = getattr(latest_psych, dim, None)
            if val is not None:
                total += float(val)
                count += 1
        if count > 0:
            avg_psych = total / count
            psych_status = "高危" if avg_psych >= 3 else "关注" if avg_psych >= 2 else "正常"
            evidence.append({
                "type": "心理",
                "detail": f"心理筛查均分{avg_psych:.1f}({psych_status})",
                "severity": "high" if avg_psych >= 3 else "medium" if avg_psych >= 2 else "low"
            })
            context_lines.append(f"最近心理筛查均分: {avg_psych:.1f} ({psych_status})")
    else:
        context_lines.append("暂无心理筛查数据")

    # 6. 五翼行为分趋势
    wings_rows = WingsScore.query.filter_by(student_id=student_id).all()
    if wings_rows:
        wings_avg = sum(w.score for w in wings_rows) / len(wings_rows)
        context_lines.append(f"五翼行为均分: {wings_avg:.1f}")

    # 7. 班主任手记（最近3条）
    notes = TeacherNote.query.filter_by(student_id=student_id).order_by(
        TeacherNote.created_at.desc()).limit(3).all()
    if notes:
        note_texts = [n.content[:80] if n.content else "" for n in notes]
        context_lines.append(f"班主任手记(最近): {' | '.join(filter(None, note_texts))}")

    # 8. 历史干预记录
    interventions = InterventionRecord.query.filter_by(student_id=student_id).order_by(
        InterventionRecord.created_at.desc()).limit(3).all()
    if interventions:
        context_lines.append(f"历史干预({len(interventions)}条): " +
                           "; ".join([f"{i.type}:{i.result or '进行中'}" for i in interventions]))

    return evidence, "\n".join(context_lines)


@causal_bp.route("/")
@require_role("ms_admin")
def index():
    """因果链诊断列表"""
    grade_id = request.args.get("grade_id", type=int)
    exam_id = request.args.get("exam_id", type=int)
    risk_filter = request.args.get("risk_level", "")

    grades = Grade.query.all()
    exams = Exam.query.order_by(Exam.exam_date.desc()).all()

    q = CausalDiagnosis.query.order_by(CausalDiagnosis.created_at.desc())
    if grade_id:
        q = q.filter_by(grade_id=grade_id)
    if exam_id:
        q = q.filter_by(exam_id=exam_id)
    if risk_filter:
        q = q.filter_by(risk_level=risk_filter)

    diagnoses = q.limit(100).all()

    # 预解析 evidence_chain
    for d in diagnoses:
        try:
            d.evidence_list = _json.loads(d.evidence_chain) if d.evidence_chain else []
        except Exception:
            d.evidence_list = []

    return render_template("causal/index.html",
                           diagnoses=diagnoses, grades=grades, exams=exams,
                           grade_filter=grade_id, exam_filter=exam_id,
                           risk_filter=risk_filter)


@causal_bp.route("/scan", methods=["POST"])
@require_role("ms_admin")
def scan_drops():
    """扫描成绩下滑学生 — 选择两次考试对比，找出显著下滑学生"""
    prev_exam_id = request.form.get("prev_exam_id", type=int)
    curr_exam_id = request.form.get("curr_exam_id", type=int)
    grade_id = request.form.get("grade_id", type=int)

    if not prev_exam_id or not curr_exam_id:
        flash("请选择两次考试", "danger")
        return redirect(url_for("causal.index"))

    # 获取所有科目的成绩变化
    prev_scores = {}
    for row in db.session.query(Score.student_id, Score.subject_id, Score.score).filter(
        Score.exam_id == prev_exam_id, Score.verify_status == "VERIFIED"
    ).all():
        prev_scores[(row.student_id, row.subject_id)] = float(row.score)

    curr_scores = {}
    for row in db.session.query(Score.student_id, Score.subject_id, Score.score).filter(
        Score.exam_id == curr_exam_id, Score.verify_status == "VERIFIED"
    ).all():
        curr_scores[(row.student_id, row.subject_id)] = float(row.score)

    # 找出下滑超过5分的
    drops = []
    for (sid, subj_id), curr_s in curr_scores.items():
        prev_s = prev_scores.get((sid, subj_id))
        if prev_s is None or prev_s <= curr_s:
            continue
        drop = prev_s - curr_s
        if drop < 5:
            continue
        drops.append({
            "student_id": sid,
            "subject_id": subj_id,
            "prev_score": prev_s,
            "curr_score": curr_s,
            "score_drop": drop,
        })

    if not drops:
        flash("未发现显著下滑（下滑<5分的已过滤）", "info")
        return redirect(url_for("causal.index"))

    # 批量加载学生和科目信息
    student_ids = list(set(d["student_id"] for d in drops))
    subject_ids = list(set(d["subject_id"] for d in drops))
    students = {s.id: s for s in Student.query.filter(Student.id.in_(student_ids)).all()}
    subjects = {s.id: s for s in Subject.query.filter(Subject.id.in_(subject_ids)).all()}

    # 检查已存在的诊断
    existing = set()
    for d in CausalDiagnosis.query.filter_by(exam_id=curr_exam_id).all():
        existing.add((d.student_id, d.subject_id))

    for d in drops:
        d["student"] = students.get(d["student_id"])
        d["subject"] = subjects.get(d["subject_id"])
        d["has_diagnosis"] = (d["student_id"], d["subject_id"]) in existing

    # 按下滑幅度降序
    drops.sort(key=lambda x: x["score_drop"], reverse=True)

    exams = {e.id: e.name for e in Exam.query.all()}
    return render_template("causal/scan_results.html",
                           drops=drops[:50],  # 最多显示50条
                           prev_exam_id=prev_exam_id,
                           curr_exam_id=curr_exam_id,
                           grade_id=grade_id,
                           prev_exam_name=exams.get(prev_exam_id, ""),
                           curr_exam_name=exams.get(curr_exam_id, ""),
                           grades=Grade.query.all())


@causal_bp.route("/diagnose", methods=["POST"])
@require_role("ms_admin")
def diagnose():
    """生成因果链诊断 — 单个学生单科"""
    import time
    student_id = request.form.get("student_id", type=int)
    subject_id = request.form.get("subject_id", type=int)
    exam_id = request.form.get("exam_id", type=int)
    prev_score = float(request.form.get("prev_score", 0))
    curr_score = float(request.form.get("curr_score", 0))

    s = Student.query.get(student_id)
    if not s:
        flash("学生不存在", "danger")
        return redirect(url_for("causal.index"))

    score_drop = prev_score - curr_score

    # 检查已存在
    existing = CausalDiagnosis.query.filter_by(
        student_id=student_id, exam_id=exam_id, subject_id=subject_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.flush()

    # 收集证据链
    evidence_list, context = _build_evidence_chain(
        student_id, s.class_id, s.grade_id, exam_id, subject_id,
        prev_score, curr_score, score_drop
    )

    try:
        data = call_llm_json(CAUSAL_SYSTEM_PROMPT, context, temperature=0.5, max_tokens=2048, timeout=60)

        diagnosis = CausalDiagnosis(
            student_id=student_id,
            class_id=s.class_id,
            grade_id=s.grade_id,
            exam_id=exam_id,
            subject_id=subject_id,
            prev_score=prev_score,
            curr_score=curr_score,
            score_drop=score_drop,
            evidence_chain=_json.dumps(evidence_list + data.get("evidence_chain", []), ensure_ascii=False),
            primary_cause=data.get("primary_cause", ""),
            secondary_cause=data.get("secondary_cause", ""),
            diagnosis_report=data.get("diagnosis_report", ""),
            intervention_plan=data.get("intervention_plan", ""),
            risk_level=data.get("risk_level", "low"),
            created_at=get_local_now(),
        )
        db.session.add(diagnosis)
        safe_commit()
        audit_log("causal_diagnosis", f"生成因果链诊断: 学生{student_id}/科目{subject_id}/考试{exam_id}")

        flash("因果链诊断已生成", "success")
        return redirect(url_for("causal.detail", did=diagnosis.id))

    except Exception as e:
        flash(f"AI 诊断失败: {str(e)[:80]}", "danger")
        return redirect(url_for("causal.index"))


@causal_bp.route("/<int:did>")
@require_role("ms_admin")
def detail(did):
    """诊断详情"""
    d = CausalDiagnosis.query.get_or_404(did)
    try:
        d.evidence_list = _json.loads(d.evidence_chain) if d.evidence_chain else []
    except Exception:
        d.evidence_list = []

    risk_colors = {"critical": "danger", "high": "warning", "medium": "info", "low": "success"}
    d.risk_color = risk_colors.get(d.risk_level, "secondary")

    return render_template("causal/detail.html", d=d)


@causal_bp.route("/<int:did>/process", methods=["POST"])
@require_role("ms_admin")
def mark_processed(did):
    """标记为已处理"""
    d = CausalDiagnosis.query.get_or_404(did)
    d.is_processed = True
    d.processed_by = session.get("username", "")
    d.processed_at = get_local_now()
    safe_commit()
    flash("已标记为已处理", "success")
    return redirect(url_for("causal.detail", did=did))


@causal_bp.route("/<int:did>/delete", methods=["POST"])
@require_role("ms_admin")
def delete_diagnosis(did):
    """删除诊断"""
    d = CausalDiagnosis.query.get_or_404(did)
    db.session.delete(d)
    safe_commit()
    flash("诊断已删除", "success")
    return redirect(url_for("causal.index"))
