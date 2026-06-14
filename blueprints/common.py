"""公共模块 — 消息中心/系统公告/SSE推送"""
import json, time, traceback, logging
from redis import Redis
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, Response, current_app
from models import db, Message, Announcement, User, Student, Class
from decorators import login_required
from datetime import date, datetime
from utils import get_local_now
from utils.db_utils import safe_commit

common_bp = Blueprint('common', __name__)

# ── SSE 实时推送（Redis Pub/Sub 跨 Worker 广播） ──────
# 物理直连本地 Redis，彻底废除内存字典 _event_queues
# 频道命名范式: sse:user:<user_id>
# 所有 Gunicorn Worker 共享同一 Redis Pub/Sub 通道
redis_client = Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)

def push_event(user_id: int, data: dict):
    """跨 Worker SSE 事件广播 — 任意 Worker 发，所有 Worker 收

    Redis Pub/Sub 确保无论老师连在哪个 Worker，通知百分百到达。
    如果 Redis 不可用，静默失败（DB 轮询兜底机制保障最终一致性）。
    同时向声呐大屏全局频道广播（Direction 4 流式可观测）。
    """
    try:
        payload = json.dumps({
            "event": data.get("type", "message"),
            "data": data,
            "timestamp": time.time()
        }, ensure_ascii=False)
        redis_client.publish(f"sse:user:{user_id}", payload)

        # 同步广播到声呐全局频道（零额外延迟）
        redis_client.publish("sse:sonar:global", payload)
    except Exception:
        pass


@common_bp.route("/api/events")
@login_required
def sse_events():
    """SSE 端点 — EventSource 连接"""
    user_id  = session.get("user_id")
    last_id = request.args.get("last_id", 0, type=int)
    # 在视图函数内捕获 app 对象（此时有 app context）
    app = current_app._get_current_object()

    def generate():
        nonlocal last_id, user_id, app
        start_time = time.time()
        MAX_SSE_DURATION = 55  # 秒，定期断开避免 Gunicorn timeout 触发

        # Redis Pub/Sub 订阅 — 跨 Worker 实时接收
        pubsub = redis_client.pubsub()
        channel = f"sse:user:{user_id}"
        try:
            pubsub.subscribe(channel)
        except Exception as e:
            app.logger.warning(f"SSE Redis订阅失败(user_id={user_id}): {e}，仅使用DB轮询兜底")

        last_db_poll = 0.0  # 上次 DB 轮询时间戳
        last_ping = time.time()  # 上次心跳时间戳

        # 1) 先把历史未读消息作为初始事件推送
        if last_id == 0:
            try:
                with app.app_context():
                    unread = Message.query.filter_by(
                        to_user_id=user_id, is_read=False
                    ).order_by(Message.id.asc()).all()
                    for msg in unread:
                        sender_name = msg.from_user.display_name if msg.from_user else "系统"
                        data = json.dumps({
                            "type": "new_message",
                            "msg": {"id": msg.id, "title": msg.title,
                                      "from": sender_name}
                        }, ensure_ascii=False)
                        yield f"data: {data}\n\n"
                        last_id = msg.id
            except Exception as e:
                app.logger.warning(f"SSE历史消息查询异常(user_id={user_id}): {e}")

        try:
            # 初始连接确认
            yield f"event: connect\ndata: {json.dumps({'status': 'ok', 'channel': channel})}\n\n"

            while time.time() - start_time < MAX_SSE_DURATION:
                # ── 主通道：Redis Pub/Sub 非阻塞探针（0.1s 超时） ──
                try:
                    message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                    if message and message.get('data'):
                        raw_data = json.loads(message['data'])
                        yield f"data: {json.dumps(raw_data['data'], ensure_ascii=False)}\n\n"
                        continue  # 收到事件，跳过 DB 轮询本轮
                except Exception as e:
                    app.logger.debug(f"SSE Redis读取异常(user_id={user_id}): {e}")

                # ── 安全网：DB 轮询新消息（每 3 秒，Redis 不可用时兜底） ──
                now = time.time()
                if now - last_db_poll > 3.0:
                    try:
                        with app.app_context():
                            new_msgs = Message.query.filter(
                                Message.to_user_id == user_id,
                                Message.id > last_id
                            ).order_by(Message.id.asc()).all()
                            for msg in new_msgs:
                                sender_name = msg.from_user.display_name if msg.from_user else "系统"
                                data = json.dumps({
                                    "type": "new_message",
                                    "msg": {"id": msg.id, "title": msg.title,
                                              "from": sender_name}
                                }, ensure_ascii=False)
                                yield f"data: {data}\n\n"
                                last_id = max(last_id, msg.id)
                    except Exception as e:
                        app.logger.warning(f"SSE数据库轮询异常(user_id={user_id}): {e}")
                    last_db_poll = now

                # ── 心跳保活（每 ~15s） ──
                if now - last_ping > 15.0:
                    yield f": ping {datetime.now().isoformat()}\n\n"
                    last_ping = now

                time.sleep(0.1)  # 高频轻量轮询，避免 CPU 空转

        except (GeneratorExit, SystemExit):
            pass  # 客户端断开连接，正常退出
        except Exception as e:
            app.logger.error(f"SSE生成器异常(user_id={user_id}): {e}\n{traceback.format_exc()}")
        finally:
            try:
                pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                pubsub.close()
            except Exception:
                pass

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


# ── 工具函数：供其他蓝图调用 ──
def send_notification(to_user_id, title, content, from_user_id=None):
    """发送系统消息（同时推 SSE 事件）

    注意：SSE 推送失败不会中断通知流程，失败仅写日志。
    """
    msg = Message(
        to_user_id=to_user_id,
        from_user_id=from_user_id,
        title=title,
        content=content,
        is_read=False,
        created_at=get_local_now()
    )
    db.session.add(msg)
    safe_commit()
    # SSE 实时推送（非关键路径，失败不影响消息持久化）
    try:
        push_event(to_user_id, {
            "type": "new_message",
            "msg": {"id": msg.id, "title": title}
        })
    except Exception as e:
        logging.getLogger("grade7").warning(
            f"SSE push_event 失败 (user: {to_user_id}, msg: {msg.id}): {e}"
        )


def notify_parent(student, title, content, from_user_id=None, template_name=None, template_vars=None):
    """向学生家长发送通知（通过 bound_student_id 查找家长用户）

    支持消息模板：如果提供 template_name，先尝试从模板获取内容，
    模板变量自动补全 student_name, class_name 等。
    """
    # 尝试使用消息模板
    if template_name and template_vars is not None:
        t_title, t_content = get_template_text(template_name, template_vars)
        if t_title and t_content:
            title, content = t_title, t_content

    parent = User.query.filter_by(
        bound_student_id=student.id, role="parent", is_active=True
    ).first()
    if parent:
        send_notification(parent.id, title, content, from_user_id=from_user_id)
    return parent


def notify_class_teacher(student, title, content, from_user_id=None, template_name=None, template_vars=None):
    """向班主任发送通知

    支持消息模板：如果提供 template_name，先尝试从模板获取内容。
    """
    # 尝试使用消息模板
    if template_name and template_vars is not None:
        t_title, t_content = get_template_text(template_name, template_vars)
        if t_title and t_content:
            title, content = t_title, t_content

    class_teachers = User.query.filter_by(
        class_id=student.class_id, role="class_teacher", is_active=True
    ).all()
    for ct in class_teachers:
        if ct.id != from_user_id:  # 避免自己通知自己
            send_notification(ct.id, title, content, from_user_id=from_user_id)
    return class_teachers


def get_template_text(template_name, variables):
    """获取消息模板渲染后的文本（自动触发时使用）

    如果模板存在则返回 (title, content) 元组，否则返回 (None, None)。
    """
    from models import MessageTemplate
    tmpl = MessageTemplate.query.filter_by(name=template_name).first()
    if not tmpl:
        return None, None
    try:
        title = tmpl.title_template.format(**variables)
        content = tmpl.content_template.format(**variables)
        return title, content
    except (KeyError, ValueError):
        return None, None


@common_bp.route("/api/unread_count")
@login_required
def api_unread_count():
    """返回未读消息数量（用于导航角标）"""
    count = Message.query.filter_by(
        to_user_id=session.get("user_id"), is_read=False
    ).count()
    return jsonify({"count": count})


@common_bp.route("/messages")
@login_required
def messages():
    page = request.args.get("page", 1, type=int)
    unread_only = request.args.get("unread_only", 0, type=int)
    q = Message.query.filter_by(to_user_id=session.get("user_id"))
    if unread_only:
        q = q.filter_by(is_read=False)
    msgs = q.order_by(Message.id.desc()).paginate(page=page, per_page=20)
    unread_count = Message.query.filter_by(
        to_user_id=session.get("user_id"), is_read=False
    ).count()
    return render_template("common/messages.html", messages=msgs, unread_only=unread_only, unread_count=unread_count)


@common_bp.route("/messages/<int:mid>")
@login_required
def message_detail(mid):
    """消息详情"""
    msg = Message.query.get_or_404(mid)
    if msg.to_user_id != session.get("user_id"):
        flash("无权查看", "danger")
        return redirect(url_for("common.messages"))

    # 标记为已读
    if not msg.is_read:
        msg.is_read = True
        safe_commit()

    sender_name = msg.from_user.display_name if msg.from_user else "系统"
    sent_at = msg.created_at.strftime("%Y-%m-%d %H:%M") if msg.created_at else "未知时间"

    return render_template("common/message_detail.html",
                           msg=msg, sender_name=sender_name, sent_at=sent_at)


@common_bp.route("/messages/<int:msg_id>", methods=["DELETE"])
@login_required
def delete_message(msg_id):
    """删除消息"""
    msg = Message.query.get_or_404(msg_id)
    if msg.to_user_id != session.get("user_id"):
        return jsonify(ok=False, msg="无权操作"), 403
    db.session.delete(msg)
    safe_commit()
    return jsonify(ok=True)


@common_bp.route("/messages/read/<int:msg_id>", methods=["POST"])
@login_required
def mark_read(msg_id):
    msg = Message.query.get_or_404(msg_id)
    if msg.to_user_id != session.get("user_id"):
        flash("无权操作", "danger")
        return redirect(url_for("common.messages"))
    msg.is_read = True
    safe_commit()
    return jsonify(ok=True)


@common_bp.route("/messages/read_all", methods=["POST"])
@login_required
def mark_all_read():
    Message.query.filter_by(to_user_id=session.get("user_id"), is_read=False).update({"is_read": True})
    safe_commit()
    return jsonify(ok=True)


@common_bp.route("/messages/compose", methods=["GET", "POST"])
@login_required
def compose_message():
    """写新消息 / 发送（支持关联学生→快速定位家长/班主任）"""
    role = session.get("role")

    if request.method == "POST":
        to_user_id = request.form.get("to_user_id", type=int)
        student_id = request.form.get("student_id", type=int)
        title      = request.form.get("title", "").strip()
        content    = request.form.get("content", "").strip()

        if not title:
            flash("请填写消息标题", "warning")
            return redirect(url_for("common.compose_message"))

        # 关联学生快捷发送：自动查找对应家长
        if student_id and not to_user_id:
            stu = Student.query.get(student_id)
            if stu:
                parent = User.query.filter_by(
                    bound_student_id=stu.id, role="parent", is_active=True
                ).first()
                if parent:
                    to_user_id = parent.id
                else:
                    # 无家长绑定时退而找班主任
                    cts = User.query.filter_by(
                        class_id=stu.class_id, role="class_teacher", is_active=True
                    ).first()
                    if cts:
                        to_user_id = cts.id
            if not to_user_id:
                flash("该学生未绑定家长或班主任，请手动选择收件人", "warning")
                return redirect(url_for("common.compose_message"))

        if not to_user_id:
            flash("请选择收件人或关联学生", "warning")
            return redirect(url_for("common.compose_message"))

        send_notification(to_user_id, title, content,
                          from_user_id=session.get("user_id"))
        flash("消息已发送", "success")
        return redirect(url_for("common.messages"))

    # GET：列出可发送的用户 + 班级/学生选择器
    users = User.query.filter(User.id != session.get("user_id")).all()

    # 按角色范围过滤学生列表
    students = []
    classes = []
    if role == "ms_admin":
        classes = Class.query.order_by(Class.name).all()
        students = Student.query.filter_by(is_active=True).order_by(Student.class_id, Student.name).all()
    elif role == "grade_leader":
        grade_id = session.get("grade_id")
        classes = Class.query.filter_by(grade_id=grade_id).order_by(Class.name).all()
        students = Student.query.filter_by(grade_id=grade_id, is_active=True).order_by(Student.class_id, Student.name).all()
    elif role in ("class_teacher", "teacher"):
        class_id = session.get("class_id")
        classes = Class.query.filter_by(id=class_id).all()
        students = Student.query.filter_by(class_id=class_id, is_active=True).order_by(Student.name).all()
    else:
        # parent → 只能看到自己孩子，student → 不需要
        if role == "parent":
            sid = session.get("bound_student_id")
            if sid:
                students = Student.query.filter_by(id=sid, is_active=True).all()

    reply_to = request.args.get("reply_to", type=int)
    return render_template("common/compose.html",
                           users=users, students=students, classes=classes, reply_to=reply_to)


# ── 系统公告 ─────────────────────────────────────────
@common_bp.route("/announcements")
@login_required
def announcements():
    """查看系统公告"""
    page = request.args.get("page", 1, type=int)
    now = date.today()
    q = Announcement.query.filter_by(is_active=True)
    role = session.get("role")
    if role:
        q = q.filter(
            (Announcement.target_roles == None) |
            (Announcement.target_roles.contains(role))
        )
    q = q.filter(
        (Announcement.expire_date == None) |
        (Announcement.expire_date >= now)
    )
    items = q.order_by(Announcement.created_at.desc()).paginate(page=page, per_page=10)
    return render_template("common/announcements.html", items=items)
