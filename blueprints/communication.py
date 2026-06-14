"""沟通记录追踪 — 统计/分析/提醒"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Message, MessageReply, MessageRead, User, Student
from decorators import login_required, require_role
from datetime import datetime, timedelta

communication_bp = Blueprint("communication", __name__, url_prefix="/communication")

@communication_bp.route("/")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher", "teacher")
def index():
    """沟通记录追踪看板"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    # 时间范围筛选
    days = request.args.get("days", 30, type=int)
    start_date = datetime.utcnow() - timedelta(days=days)

    # 基础查询
    q = Message.query.filter(Message.created_at >= start_date)
    if role == "grade_leader" and grade_id:
        # 年级组长：只看本年级的消息
        grade_users = [u.id for u in User.query.filter_by(grade_id=grade_id).all()]
        q = q.filter(Message.from_user_id.in_(grade_users) | Message.to_user_id.in_(grade_users))
    elif role in ("class_teacher", "teacher") and class_id:
        # 班主任：只看本班的消息
        class_users = [u.id for u in User.query.filter_by(class_id=class_id).all()]
        q = q.filter(Message.from_user_id.in_(class_users) | Message.to_user_id.in_(class_users))

    messages = q.order_by(Message.created_at.desc()).limit(500).all()

    # 统计卡片
    total_messages = len(messages)
    read_count = sum(1 for m in messages if m.is_read)
    replied_count = sum(1 for m in messages if m.replies.count() > 0)
    unread_count = total_messages - read_count

    read_rate = round(read_count / total_messages * 100, 1) if total_messages > 0 else 0
    reply_rate = round(replied_count / total_messages * 100, 1) if total_messages > 0 else 0

    # 按分类统计
    category_stats = {}
    for m in messages:
        cat = m.category or "通用"
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "read": 0, "replied": 0}
        category_stats[cat]["total"] += 1
        if m.is_read:
            category_stats[cat]["read"] += 1
        if m.replies.count() > 0:
            category_stats[cat]["replied"] += 1

    # 平均响应时间（仅计算有回复的消息）
    response_times = []
    for m in messages:
        if m.replies.count() > 0:
            first_reply = m.replies.order_by(MessageReply.created_at.asc()).first()
            if first_reply:
                delta = first_reply.created_at - m.created_at
                response_times.append(delta.total_seconds() / 3600)  # 转换为小时

    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0

    # 未读超过24小时的消息（需要提醒）
    overdue_messages = []
    for m in messages:
        if not m.is_read and (datetime.utcnow() - m.created_at).total_seconds() > 86400:
            overdue_messages.append(m)

    return render_template("communication/index.html",
                           total_messages=total_messages,
                           read_count=read_count,
                           replied_count=replied_count,
                           unread_count=unread_count,
                           read_rate=read_rate,
                           reply_rate=reply_rate,
                           category_stats=category_stats,
                           avg_response_time=avg_response_time,
                           overdue_messages=overdue_messages,
                           days=days)


@communication_bp.route("/api/remind/<int:msg_id>", methods=["POST"])
@login_required
def remind(msg_id):
    """发送提醒给未读消息的接收者"""
    from common import push_event

    msg = Message.query.get_or_404(msg_id)

    if msg.is_read:
        return jsonify({"error": "消息已读，无需提醒"}), 400

    # 推送提醒事件
    push_event(msg.to_user_id, {
        "type": "remind",
        "message_id": msg.id,
        "title": "提醒：请及时查看消息",
        "content": f"您有一条未读消息：「{msg.title}」"
    })

    return jsonify({"success": True, "message": "提醒已发送"})


@communication_bp.route("/api/stats")
@login_required
def api_stats():
    """API：获取沟通统计（JSON）"""
    role = session.get("role", "")
    grade_id = session.get("grade_id")
    class_id = session.get("class_id")

    days = request.args.get("days", 7, type=int)
    start_date = datetime.utcnow() - timedelta(days=days)

    q = Message.query.filter(Message.created_at >= start_date)
    if role == "grade_leader" and grade_id:
        grade_users = [u.id for u in User.query.filter_by(grade_id=grade_id).all()]
        q = q.filter(Message.from_user_id.in_(grade_users) | Message.to_user_id.in_(grade_users))
    elif role in ("class_teacher", "teacher") and class_id:
        class_users = [u.id for u in User.query.filter_by(class_id=class_id).all()]
        q = q.filter(Message.from_user_id.in_(class_users) | Message.to_user_id.in_(class_users))

    messages = q.all()

    # 按天统计
    date_labels = []
    msg_counts = []
    read_counts = []
    reply_counts = []

    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days-1-i)).date()
        date_labels.append(d.strftime("%m/%d"))
        day_msgs = [m for m in messages if m.created_at.date() == d]
        msg_counts.append(len(day_msgs))
        read_counts.append(sum(1 for m in day_msgs if m.is_read))
        reply_counts.append(sum(1 for m in day_msgs if m.replies.count() > 0))

    return jsonify({
        "date_labels": date_labels,
        "msg_counts": msg_counts,
        "read_counts": read_counts,
        "reply_counts": reply_counts,
    })
