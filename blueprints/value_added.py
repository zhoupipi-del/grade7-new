"""增值评价AI评语 — 识别"隐形好学生"，生成温暖鼓励评语"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, session
from models import db, Student, Class, Grade, Exam, Score, WingsScore, DisciplineRecord, Attendance, ValueAddedComment
from decorators import login_required, require_role
from utils.db_utils import safe_commit
from utils import get_local_now
from blueprints.audit_log import audit_log
from sqlalchemy import func
import json as _json
import requests

value_added_bp = Blueprint("value_added", __name__)

# ══════════════════════════════════════════════════════════════
#  AI 增值评价 — System Prompt
# ══════════════════════════════════════════════════════════════
VALUE_ADDED_SYSTEM_PROMPT = """你是一位拥有25年经验的初中德育主任兼心理咨询师，专门关注那些"隐形好学生"——成绩不在前列但品行端正、正在默默进步的孩子。你的任务是根据学生的数据画像，生成一段温暖、有力、让人落泪的鼓励评语。

[核心约束]
1. 严禁出现"该生学习态度端正"等万能套话。每句话必须有数据或事实支撑。
2. 必须用"你"而非"该生"，语气像一位慈爱而睿智的长辈直接对话。
3. 必须点出至少1个具体进步（如"数学从X分提到了Y分"）和1个品行亮点。
4. 结尾必须有一句温暖展望，让学生感受到被看见、被认可。
5. comment_text 字数严格控制在 150-250 字之间。
6. 评语要让阅读的学生感到"原来老师一直在看着我"。

[输出格式]
必须输出严格的 JSON 格式，不要任何 Markdown 包裹（如 ```json），直接返回以下结构的字符串：
{
  "comment_text": "150-250字的温暖鼓励评语",
  "highlight_tags": ["闪光点标签1", "闪光点标签2", "闪光点标签3"]
}"""


def _call_llm_api(system_prompt, user_content):
    """调用大模型API"""
    api_key = current_app.config.get("LLM_API_KEY", "")
    api_url = current_app.config.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = current_app.config.get("LLM_MODEL", "deepseek-chat")
    timeout = current_app.config.get("LLM_TIMEOUT", 45)

    if not api_key:
        raise RuntimeError("LLM_API_KEY 未配置")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _get_student_totals_by_exam(exam_id, grade_id=None):
    """获取某次考试每个学生的总分（按student_id聚合）"""
    q = db.session.query(
        Score.student_id,
        func.sum(Score.score).label("total"),
        func.count(Score.score).label("subject_count")
    ).filter(
        Score.exam_id == exam_id,
        Score.verify_status == "VERIFIED"
    )
    if grade_id:
        q = q.filter(Score.grade_id == grade_id)
    q = q.group_by(Score.student_id)
    results = q.all()
    return {r.student_id: {"total": float(r.total) if r.total else 0, "subjects": int(r.subject_count)} for r in results}


def _get_student_ranks_by_exam(exam_id, grade_id=None):
    """获取某次考试每个学生的年级排名"""
    totals = _get_student_totals_by_exam(exam_id, grade_id)
    if not totals:
        return {}
    sorted_students = sorted(totals.items(), key=lambda x: x[1]["total"], reverse=True)
    return {sid: rank + 1 for rank, (sid, _) in enumerate(sorted_students)}


def _identify_hidden_gems(prev_exam_id, curr_exam_id, grade_id=None):
    """
    识别"隐形好学生"——成绩中下游但品行好、进步大的学生。
    返回列表: [{"student": Student, "prev_total": float, "curr_total": float,
                "score_delta": float, "prev_rank": int, "curr_rank": int,
                "behavior_score": float, "discipline_count": int, "attendance_rate": float}]
    """
    # 获取两次考试总分
    prev_totals = _get_student_totals_by_exam(prev_exam_id, grade_id)
    curr_totals = _get_student_totals_by_exam(curr_exam_id, grade_id)

    # 共同学生
    common_ids = set(prev_totals.keys()) & set(curr_totals.keys())
    if not common_ids:
        return []

    # 批量加载学生信息
    students = {s.id: s for s in Student.query.filter(Student.id.in_(common_ids)).all()}

    # 获取排名
    prev_ranks = _get_student_ranks_by_exam(prev_exam_id, grade_id)
    curr_ranks = _get_student_ranks_by_exam(curr_exam_id, grade_id)
    total_students = len(curr_ranks)

    # 行为均分（WingsScore）
    wings_avg = {}
    ws_rows = db.session.query(
        WingsScore.student_id, func.avg(WingsScore.score).label("avg_score")
    ).filter(WingsScore.student_id.in_(common_ids)).group_by(WingsScore.student_id).all()
    for r in ws_rows:
        wings_avg[r.student_id] = float(r.avg_score) if r.avg_score else 0

    # 全体行为均分（用于比较）
    all_ws = db.session.query(func.avg(WingsScore.score)).scalar()
    avg_behavior = float(all_ws) if all_ws else 50.0

    # 违纪次数
    disc_count = {}
    disc_rows = db.session.query(
        DisciplineRecord.student_id, func.count(DisciplineRecord.id).label("cnt")
    ).filter(
        DisciplineRecord.student_id.in_(common_ids),
        DisciplineRecord.status == "active"
    ).group_by(DisciplineRecord.student_id).all()
    for r in disc_rows:
        disc_count[r.student_id] = int(r.cnt)

    # 出勤率
    att_rate = {}
    att_rows = db.session.query(
        Attendance.student_id,
        func.count(Attendance.id).label("total_days"),
        func.sum(func.IF(Attendance.status == "present", 1, 0)).label("present_days")
    ).filter(Attendance.student_id.in_(common_ids)).group_by(Attendance.student_id).all()
    for r in att_rows:
        if r.total_days and r.total_days > 0:
            att_rate[r.student_id] = round(float(r.present_days or 0) / float(r.total_days) * 100, 1)

    # 筛选"隐形好学生"
    gems = []
    for sid in common_ids:
        s = students.get(sid)
        if not s:
            continue

        prev_t = prev_totals[sid]["total"]
        curr_t = curr_totals[sid]["total"]
        delta = curr_t - prev_t
        curr_rank = curr_ranks.get(sid, total_students)

        # 条件1: 进步了（delta > 0）
        if delta <= 0:
            continue

        # 条件2: 当前排名在后50%
        if curr_rank > total_students * 0.5:
            continue

        # 条件3: 行为分高于平均 或 无违纪
        b_score = wings_avg.get(sid, 0)
        d_cnt = disc_count.get(sid, 0)
        if b_score < avg_behavior and d_cnt > 2:
            continue

        gems.append({
            "student": s,
            "prev_total": prev_t,
            "curr_total": curr_t,
            "score_delta": delta,
            "prev_rank": prev_ranks.get(sid, total_students),
            "curr_rank": curr_rank,
            "behavior_score": b_score,
            "discipline_count": d_cnt,
            "attendance_rate": att_rate.get(sid, 100.0),
        })

    # 按进步幅度降序排列
    gems.sort(key=lambda x: x["score_delta"], reverse=True)
    return gems


def _build_gem_context(gem):
    """为单个学生构建 LLM 上下文"""
    s = gem["student"]
    cls_name = s.class_.name if hasattr(s, "class_") and s.class_ else ""
    lines = [
        f"姓名: {s.name}",
        f"班级: {cls_name}",
        f"上次考试总分: {gem['prev_total']:.1f} (排名第{gem['prev_rank']}名)",
        f"本次考试总分: {gem['curr_total']:.1f} (排名第{gem['curr_rank']}名)",
        f"进步: +{gem['score_delta']:.1f}分",
        f"五翼行为均分: {gem['behavior_score']:.1f}",
        f"违纪记录: {gem['discipline_count']}条",
        f"出勤率: {gem['attendance_rate']:.1f}%",
    ]
    return "\n".join(lines)


@value_added_bp.route("/")
@require_role("ms_admin")
def index():
    """增值评价列表"""
    grade_id = request.args.get("grade_id", type=int)
    exam_id = request.args.get("exam_id", type=int)

    grades = Grade.query.all()
    exams = Exam.query.order_by(Exam.exam_date.desc()).all()

    q = ValueAddedComment.query.order_by(ValueAddedComment.created_at.desc())
    if grade_id:
        q = q.filter_by(grade_id=grade_id)
    if exam_id:
        q = q.filter_by(exam_id=exam_id)
    comments = q.limit(100).all()

    # 预解析 JSON tags
    for c in comments:
        try:
            c.tags = _json.loads(c.highlight_tags) if c.highlight_tags else []
        except Exception:
            c.tags = []

    return render_template("value_added/index.html",
                           comments=comments, grades=grades, exams=exams,
                           grade_filter=grade_id, exam_filter=exam_id)


@value_added_bp.route("/scan", methods=["POST"])
@require_role("ms_admin")
def scan_students():
    """扫描隐形好学生 — 选择两次考试进行比对"""
    prev_exam_id = request.form.get("prev_exam_id", type=int)
    curr_exam_id = request.form.get("curr_exam_id", type=int)
    grade_id = request.form.get("grade_id", type=int)

    if not prev_exam_id or not curr_exam_id:
        flash("请选择两次考试", "danger")
        return redirect(url_for("value_added.index"))

    gems = _identify_hidden_gems(prev_exam_id, curr_exam_id, grade_id)

    exams = {e.id: e.name for e in Exam.query.all()}
    return render_template("value_added/scan_results.html",
                           gems=gems,
                           prev_exam_id=prev_exam_id,
                           curr_exam_id=curr_exam_id,
                           grade_id=grade_id,
                           prev_exam_name=exams.get(prev_exam_id, ""),
                           curr_exam_name=exams.get(curr_exam_id, ""),
                           grades=Grade.query.all())


@value_added_bp.route("/generate", methods=["POST"])
@require_role("ms_admin")
def generate_comments():
    """批量生成 AI 温暖评语"""
    import time
    prev_exam_id = request.form.get("prev_exam_id", type=int)
    curr_exam_id = request.form.get("curr_exam_id", type=int)
    grade_id = request.form.get("grade_id", type=int)
    student_ids = request.form.getlist("student_ids")

    if not student_ids:
        flash("请至少选择一个学生", "warning")
        return redirect(url_for("value_added.scan_students",
                               prev_exam_id=prev_exam_id, curr_exam_id=curr_exam_id,
                               grade_id=grade_id))

    # 重新识别并过滤选中学生
    gems = _identify_hidden_gems(prev_exam_id, curr_exam_id, grade_id)
    gem_map = {g["student"].id: g for g in gems}

    generated = 0
    failed = 0
    for sid_str in student_ids:
        sid = int(sid_str)
        gem = gem_map.get(sid)
        if not gem:
            continue

        s = gem["student"]

        # 检查是否已存在
        existing = ValueAddedComment.query.filter_by(
            student_id=sid, exam_id=curr_exam_id
        ).first()
        if existing:
            # 删除旧的重新生成
            db.session.delete(existing)
            db.session.flush()

        try:
            context = _build_gem_context(gem)
            llm_output = _call_llm_api(VALUE_ADDED_SYSTEM_PROMPT, context)
            data = _json.loads(llm_output)

            vac = ValueAddedComment(
                student_id=sid,
                class_id=s.class_id,
                grade_id=s.grade_id,
                exam_id=curr_exam_id,
                prev_total=gem["prev_total"],
                curr_total=gem["curr_total"],
                score_delta=gem["score_delta"],
                rank_delta=gem["prev_rank"] - gem["curr_rank"],
                behavior_score=gem["behavior_score"],
                discipline_count=gem["discipline_count"],
                attendance_rate=gem["attendance_rate"],
                comment_text=data.get("comment_text", ""),
                highlight_tags=_json.dumps(data.get("highlight_tags", []), ensure_ascii=False),
                status="draft",
            )
            db.session.add(vac)
            generated += 1

            # LLM 限流：每次调用间隔 0.5 秒
            time.sleep(0.5)

        except Exception as e:
            failed += 1
            flash(f"{s.name}: AI 生成失败 - {str(e)[:50]}", "danger")

    safe_commit()

    if generated > 0:
        audit_log("generate_value_added", f"生成 {generated} 条增值评价（考试ID={curr_exam_id}）")
        flash(f"成功生成 {generated} 条温暖评语" + (f"，{failed} 条失败" if failed else ""), "success")
    else:
        flash("未能生成任何评语", "danger")

    return redirect(url_for("value_added.index", exam_id=curr_exam_id))


@value_added_bp.route("/<int:cid>/publish", methods=["POST"])
@require_role("ms_admin")
def publish_comment(cid):
    """发布单条评语"""
    vac = ValueAddedComment.query.get_or_404(cid)
    vac.status = "published"
    safe_commit()
    flash("评语已发布", "success")
    return redirect(url_for("value_added.index"))


@value_added_bp.route("/<int:cid>/delete", methods=["POST"])
@require_role("ms_admin")
def delete_comment(cid):
    """删除评语"""
    vac = ValueAddedComment.query.get_or_404(cid)
    db.session.delete(vac)
    safe_commit()
    flash("评语已删除", "success")
    return redirect(url_for("value_added.index"))
