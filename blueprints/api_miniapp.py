"""小程序专用API — 家长/班主任/年级组长角色使用，JWT Token 认证"""
from functools import wraps
from datetime import date, datetime, timedelta

from flask import Blueprint, request, jsonify, g
from sqlalchemy import func

from models import (db, User, Student, Class, DisciplineRecord, Attendance,
                    Message, WingsScore, Announcement, LeaveRequest, Exam,
                    Score, Subject, Notice, NoticeReceipt, PsychSurvey,
                    EndTermComment)
from jwt_utils import create_token, verify_token, refresh_token as _refresh_token
from utils.db_utils import safe_commit
from blueprints.common import notify_parent

miniapp_bp = Blueprint("miniapp", __name__)


# ══════════════════════════════════════════════════════════════
#  JWT 认证装饰器
# ══════════════════════════════════════════════════════════════

def miniapp_login_required(f):
    """小程序API用 JWT token 认证，解码后存入 g.miniapp_user"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"code": 401, "msg": "缺少认证令牌"}), 401
        token = auth_header[7:]
        payload = verify_token(token)
        if not payload:
            return jsonify({"code": 401, "msg": "令牌无效或已过期"}), 401
        g.miniapp_user = {
            "user_id": payload["user_id"],
            "role": payload["role"],
            "display_name": payload["display_name"],
            "bound_student_id": payload.get("bound_student_id"),
            "grade_id": payload.get("grade_id"),
            "class_id": payload.get("class_id"),
        }
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════
#  认证端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/auth/login", methods=["POST"])
def auth_login():
    """小程序登录：用户名+密码换取 JWT"""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"code": 401, "msg": "用户名和密码不能为空"}), 401

    user = User.query.filter_by(username=username, is_active=True).first()
    if not user or not user.check_password(password):
        return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    safe_commit()

    token = create_token(
        user_id=user.id,
        role=user.role,
        display_name=user.display_name,
        bound_student_id=user.bound_student_id,
        grade_id=user.grade_id,
        class_id=user.class_id,
    )
    return jsonify({
        "code": 0,
        "data": {
            "token": token,
            "user": {
                "user_id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "bound_student_id": user.bound_student_id,
                "grade_id": user.grade_id,
                "class_id": user.class_id,
            },
        },
    })


@miniapp_bp.route("/auth/refresh", methods=["POST"])
def auth_refresh():
    """刷新 JWT token"""
    data = request.get_json(silent=True) or {}
    old_token = data.get("token", "")
    if not old_token:
        return jsonify({"code": 401, "msg": "缺少旧令牌"}), 401
    new_token = _refresh_token(old_token)
    if not new_token:
        return jsonify({"code": 401, "msg": "令牌无效或已过期"}), 401
    return jsonify({"code": 0, "data": {"token": new_token}})


# ══════════════════════════════════════════════════════════════
#  家长端 — 原有端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/parent/dashboard")
@miniapp_login_required
def parent_dashboard():
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    student = Student.query.get(sid) if sid else None
    if not student:
        return jsonify({"code": 404, "msg": "未绑定学生"})
    disciplines = DisciplineRecord.query.filter_by(
        student_id=sid, status="active").limit(5).all()
    attendances = Attendance.query.filter_by(student_id=sid).order_by(
        Attendance.record_date.desc()).limit(7).all()
    scores = WingsScore.query.filter_by(student_id=sid).all()
    return jsonify({
        "code": 0,
        "data": {
            "student": {"id": student.id, "name": student.name, "class": student.class_.name},
            "disciplines": [{"type": d.type, "desc": d.description, "date": str(d.created_at)}
                            for d in disciplines],
            "attendance": [{"date": str(a.record_date), "status": a.status}
                           for a in attendances],
            "wings_scores": [{"dimension": s.dimension, "score": s.score}
                             for s in scores],
        },
    })


@miniapp_bp.route("/parent/scores")
@miniapp_login_required
def parent_scores():
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    scores = WingsScore.query.filter_by(student_id=sid).all() if sid else []
    return jsonify({"code": 0, "data": [
        {"dimension": s.dimension, "score": s.score, "semester": s.semester}
        for s in scores
    ]})


@miniapp_bp.route("/parent/discipline")
@miniapp_login_required
def parent_discipline():
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    records = DisciplineRecord.query.filter_by(
        student_id=sid).order_by(DisciplineRecord.created_at.desc()).all() if sid else []
    return jsonify({"code": 0, "data": [
        {"type": r.type, "category": r.category, "description": r.description,
         "points": r.points, "date": str(r.created_at)}
        for r in records
    ]})


@miniapp_bp.route("/parent/leave/apply", methods=["POST"])
@miniapp_login_required
def apply_leave():
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    student = Student.query.get(sid) if sid else None
    if not student:
        return jsonify({"code": 404, "msg": "未绑定学生"})
    data = request.get_json(silent=True) or {}
    leave = LeaveRequest(
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        applicant_id=miniapp_user["user_id"],
        reason=data.get("reason", ""),
        start_date=date.fromisoformat(data["start_date"]),
        end_date=date.fromisoformat(data["end_date"]),
    )
    db.session.add(leave)
    safe_commit()
    return jsonify({"code": 0, "msg": "请假申请已提交"})


# ══════════════════════════════════════════════════════════════
#  班主任端 — 原有端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/teacher/dashboard")
@miniapp_login_required
def teacher_dashboard():
    miniapp_user = g.miniapp_user
    class_id = miniapp_user.get("class_id")
    if not class_id:
        return jsonify({"code": 403, "msg": "非班主任账号"})
    students = Student.query.filter_by(class_id=class_id, is_active=True).count()
    today_disciplines = DisciplineRecord.query.filter_by(class_id=class_id).count()
    return jsonify({
        "code": 0,
        "data": {
            "student_count": students,
            "discipline_today": today_disciplines,
        },
    })


@miniapp_bp.route("/teacher/students")
@miniapp_login_required
def teacher_students():
    miniapp_user = g.miniapp_user
    class_id = miniapp_user.get("class_id")
    students = Student.query.filter_by(
        class_id=class_id, is_active=True).order_by(Student.student_no).all()
    return jsonify({"code": 0, "data": [
        {"id": s.id, "name": s.name, "student_no": s.student_no, "gender": s.gender}
        for s in students
    ]})


@miniapp_bp.route("/teacher/discipline/add", methods=["POST"])
@miniapp_login_required
def teacher_add_discipline():
    miniapp_user = g.miniapp_user
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    if not student_id:
        return jsonify({"code": 400, "msg": "缺少 student_id"}), 400
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"code": 404, "msg": "学生不存在"}), 404
    if student.class_id != miniapp_user.get("class_id"):
        return jsonify({"code": 403, "msg": "无权操作"})
    record = DisciplineRecord(
        student_id=student.id,
        class_id=student.class_id,
        grade_id=student.grade_id,
        type=data.get("type", "minor"),
        category=data.get("category", ""),
        description=data.get("description", ""),
        points=data.get("points", 0),
        created_by=miniapp_user["user_id"],
    )
    db.session.add(record)
    safe_commit()
    return jsonify({"code": 0, "msg": "记录成功"})


# ══════════════════════════════════════════════════════════════
#  年级组长端 — 原有端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/grade-leader/dashboard")
@miniapp_login_required
def grade_leader_dashboard():
    miniapp_user = g.miniapp_user
    grade_id = miniapp_user.get("grade_id")
    if not grade_id:
        return jsonify({"code": 403, "msg": "非年级组长"})
    classes = Class.query.filter_by(grade_id=grade_id).all()
    return jsonify({
        "code": 0,
        "data": {
            "class_count": len(classes),
            "classes": [{"id": c.id, "name": c.name, "students": c.student_count}
                        for c in classes],
        },
    })


# ══════════════════════════════════════════════════════════════
#  公共端点 — 原有端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/announcements")
@miniapp_login_required
def announcements():
    today = date.today()
    anns = Announcement.query.filter(
        Announcement.is_active == True,
        db.or_(Announcement.expire_date == None, Announcement.expire_date >= today),
    ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(10).all()
    return jsonify({"code": 0, "data": [
        {"id": a.id, "title": a.title, "content": a.content, "created_at": str(a.created_at)}
        for a in anns
    ]})


@miniapp_bp.route("/messages")
@miniapp_login_required
def messages():
    miniapp_user = g.miniapp_user
    msgs = Message.query.filter_by(to_user_id=miniapp_user["user_id"]).order_by(
        Message.created_at.desc()).limit(20).all()
    return jsonify({"code": 0, "data": [
        {"id": m.id, "title": m.title, "content": m.content, "is_read": m.is_read,
         "from": m.from_user.display_name if m.from_user else "系统",
         "created_at": str(m.created_at)}
        for m in msgs
    ]})


# ══════════════════════════════════════════════════════════════
#  家长端 — 新增推送/通知端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/parent/discipline-push")
@miniapp_login_required
def parent_discipline_push():
    """获取绑定学生的未读违纪记录（自上次检查后新增）"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})
    since = request.args.get("since")
    query = DisciplineRecord.query.filter_by(student_id=sid)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.filter(DisciplineRecord.created_at >= since_dt)
        except ValueError:
            pass
    records = query.order_by(DisciplineRecord.created_at.desc()).limit(20).all()
    return jsonify({"code": 0, "data": {
        "total": len(records),
        "records": [
            {"id": r.id, "type": r.type, "category": r.category,
             "description": r.description, "points": r.points,
             "status": r.status, "date": str(r.created_at)}
            for r in records
        ],
    }})


@miniapp_bp.route("/parent/score-push")
@miniapp_login_required
def parent_score_push():
    """获取最近考试成绩及排名"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})
    student = Student.query.get(sid)
    if not student:
        return jsonify({"code": 404, "msg": "学生不存在"})

    # 最近一场考试
    latest_exam = Exam.query.filter_by(grade_id=student.grade_id).order_by(
        Exam.exam_date.desc()).first()
    if not latest_exam:
        return jsonify({"code": 0, "data": {"exam": None, "scores": []}})

    scores = Score.query.filter_by(
        student_id=sid, exam_id=latest_exam.id).all()
    return jsonify({"code": 0, "data": {
        "exam": {
            "id": latest_exam.id, "name": latest_exam.name,
            "exam_type": latest_exam.exam_type,
            "exam_date": str(latest_exam.exam_date),
        },
        "scores": [
            {"subject": s.subject.name, "score": s.score,
             "rank_class": s.rank_class, "rank_grade": s.rank_grade,
             "full_score": s.subject.full_score}
            for s in scores
        ],
    }})


@miniapp_bp.route("/parent/attendance-push")
@miniapp_login_required
def parent_attendance_push():
    """获取近期考勤汇总"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})

    today = date.today()
    week_ago = today - timedelta(days=7)

    rows = Attendance.query.filter(
        Attendance.student_id == sid,
        Attendance.record_date >= week_ago,
        Attendance.record_date <= today,
    ).order_by(Attendance.record_date.desc()).all()

    # 汇总
    summary = {"present": 0, "late": 0, "absent": 0, "leave": 0, "early": 0}
    for r in rows:
        st = r.status
        if st in summary:
            summary[st] += 1

    return jsonify({"code": 0, "data": {
        "period": {"from": str(week_ago), "to": str(today)},
        "summary": summary,
        "records": [
            {"date": str(r.record_date), "status": r.status, "note": r.note}
            for r in rows
        ],
    }})


@miniapp_bp.route("/parent/notices-unread")
@miniapp_login_required
def parent_notices_unread():
    """获取未读通知数量 + 列表"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})

    student = Student.query.get(sid)
    if not student:
        return jsonify({"code": 404, "msg": "学生不存在"})

    # 未读回执
    unread_receipts = NoticeReceipt.query.filter_by(
        student_id=sid, status="unread").all()
    notice_ids = [r.notice_id for r in unread_receipts]

    notices = Notice.query.filter(
        Notice.id.in_(notice_ids),
        db.or_(
            Notice.class_id == None,
            Notice.class_id == student.class_id,
        ),
    ).order_by(Notice.created_at.desc()).all() if notice_ids else []

    return jsonify({"code": 0, "data": {
        "unread_count": len(notices),
        "notices": [
            {"id": n.id, "title": n.title, "content": n.content,
             "require_receipt": n.require_receipt,
             "created_at": str(n.created_at)}
            for n in notices
        ],
    }})


@miniapp_bp.route("/parent/leaves")
@miniapp_login_required
def parent_leaves():
    """获取绑定学生的请假记录"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})

    leaves = LeaveRequest.query.filter_by(student_id=sid).order_by(
        LeaveRequest.created_at.desc()).all()
    return jsonify({"code": 0, "data": [
        {"id": l.id, "reason": l.reason,
         "start_date": str(l.start_date), "end_date": str(l.end_date),
         "status": l.status,
         "created_at": str(l.created_at)}
        for l in leaves
    ]})


@miniapp_bp.route("/parent/psych-result")
@miniapp_login_required
def parent_psych_result():
    """获取绑定学生的心理问卷结果"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})

    surveys = PsychSurvey.query.filter_by(
        student_id=sid, is_valid=True).order_by(
        PsychSurvey.completed_at.desc()).limit(5).all()
    return jsonify({"code": 0, "data": [
        {"id": s.id, "survey_type": s.survey_type,
         "total_score": s.total_score,
         "dimensions": s.dimensions_json,
         "completed_at": str(s.completed_at)}
        for s in surveys
    ]})


@miniapp_bp.route("/parent/endterm-comments")
@miniapp_login_required
def parent_endterm_comments():
    """获取绑定学生的期末评语"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    if not sid:
        return jsonify({"code": 404, "msg": "未绑定学生"})

    comments = EndTermComment.query.filter_by(
        student_id=sid, status="published").order_by(
        EndTermComment.created_at.desc()).limit(5).all()
    return jsonify({"code": 0, "data": [
        {"id": c.id, "semester": c.semester,
         "overall_comment": c.overall_comment,
         "strengths": c.strengths,
         "improvements": c.improvements,
         "teacher_suggestion": c.teacher_suggestion,
         "created_at": str(c.created_at)}
        for c in comments
    ]})


@miniapp_bp.route("/parent/feedback", methods=["POST"])
@miniapp_login_required
def parent_feedback():
    """家长提交反馈（纪律申诉/成绩疑问/一般留言）"""
    miniapp_user = g.miniapp_user
    sid = miniapp_user.get("bound_student_id")
    data = request.get_json(silent=True) or {}

    feedback_type = data.get("type", "comment")
    content = data.get("content", "").strip()
    related_id = data.get("related_id")

    if not content:
        return jsonify({"code": 401, "msg": "反馈内容不能为空"})

    type_labels = {
        "discipline": "纪律申诉",
        "appeal": "申诉",
        "comment": "家长留言",
    }
    title = f"[{type_labels.get(feedback_type, '反馈')}] {miniapp_user['display_name']}的反馈"
    if related_id:
        title += f" (关联ID:{related_id})"

    msg = Message(
        from_user_id=miniapp_user["user_id"],
        to_user_id=miniapp_user.get("class_id", 0) and _get_class_teacher_id(
            miniapp_user.get("class_id")) or 1,
        title=title,
        content=f"[类型:{feedback_type}]\n{content}",
    )
    db.session.add(msg)
    safe_commit()
    return jsonify({"code": 0, "msg": "反馈已提交"})


def _get_class_teacher_id(class_id):
    """根据班级ID获取班主任user_id"""
    if not class_id:
        return None
    cls = Class.query.get(class_id)
    return cls.head_teacher_id if cls else None


# ══════════════════════════════════════════════════════════════
#  班主任端 — 新增推送/通知端点
# ══════════════════════════════════════════════════════════════

@miniapp_bp.route("/teacher/pending-leaves")
@miniapp_login_required
def teacher_pending_leaves():
    """获取班主任待审批的请假请求"""
    miniapp_user = g.miniapp_user
    class_id = miniapp_user.get("class_id")
    if not class_id:
        return jsonify({"code": 403, "msg": "非班主任账号"})

    leaves = LeaveRequest.query.filter_by(
        class_id=class_id, status="pending"
    ).order_by(LeaveRequest.created_at.desc()).all()

    return jsonify({"code": 0, "data": {
        "total": len(leaves),
        "leaves": [
            {"id": l.id,
             "student": {"id": l.student.id, "name": l.student.name}
             if l.student else {"id": l.student_id, "name": "未知"},
             "reason": l.reason,
             "start_date": str(l.start_date), "end_date": str(l.end_date),
             "created_at": str(l.created_at)}
            for l in leaves
        ],
    }})


@miniapp_bp.route("/teacher/approve-leave", methods=["POST"])
@miniapp_login_required
def teacher_approve_leave():
    """班主任审批请假请求"""
    miniapp_user = g.miniapp_user
    class_id = miniapp_user.get("class_id")
    if not class_id:
        return jsonify({"code": 403, "msg": "非班主任账号"})

    data = request.get_json(silent=True) or {}
    leave_id = data.get("leave_id")
    action = data.get("action")  # approve / reject

    if not leave_id or action not in ("approve", "reject"):
        return jsonify({"code": 401, "msg": "参数错误"})

    leave = LeaveRequest.query.get(leave_id)
    if not leave or leave.class_id != class_id:
        return jsonify({"code": 404, "msg": "请假记录不存在或无权操作"})
    if leave.status != "pending":
        return jsonify({"code": 403, "msg": "该请求已处理"})

    if action == "approve":
        leave.status = "class_approved"
        leave.class_approved_by = miniapp_user["user_id"]
        leave.class_approved_at = datetime.utcnow()
    else:
        leave.status = "rejected"

    safe_commit()

    # 通知家长
    student = Student.query.get(leave.student_id)
    if student:
        from_user_id = miniapp_user.get("user_id")
        action_label = "已通过（班主任审批）" if leave.status == "class_approved" else "已被驳回"
        notify_parent(
            student,
            title=f"请假审批结果 — {student.name}",
            content=f"您孩子 {student.name} 的请假申请{action_label}。\n"
                    f"请假时间：{leave.start_date} ~ {leave.end_date}\n"
                    f"请假原因：{leave.reason}",
            from_user_id=from_user_id,
        )

    return jsonify({"code": 0, "msg": "已处理"})


@miniapp_bp.route("/teacher/attendance-stats")
@miniapp_login_required
def teacher_attendance_stats():
    """获取班主任班级本周考勤统计"""
    miniapp_user = g.miniapp_user
    class_id = miniapp_user.get("class_id")
    if not class_id:
        return jsonify({"code": 403, "msg": "非班主任账号"})

    today = date.today()
    # 本周一
    monday = today - timedelta(days=today.weekday())

    rows = db.session.query(
        Attendance.status,
        func.count(Attendance.id).label("cnt"),
    ).filter(
        Attendance.class_id == class_id,
        Attendance.record_date >= monday,
        Attendance.record_date <= today,
    ).group_by(Attendance.status).all()

    stats = {r.status: r.cnt for r in rows}
    return jsonify({"code": 0, "data": {
        "period": {"from": str(monday), "to": str(today)},
        "present": stats.get("present", 0),
        "late": stats.get("late", 0),
        "absent": stats.get("absent", 0),
        "leave": stats.get("leave", 0),
        "early": stats.get("early", 0),
    }})
