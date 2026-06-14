"""消息模板系统 — CRUD / 使用模板发消息"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, User, Student, Class, MessageTemplate, Message
from decorators import login_required, require_role
import json
from utils.db_utils import safe_commit

message_templates_bp = Blueprint("message_templates", __name__)


# ── 系统种子模板 ──
SYSTEM_TEMPLATES = [
    {
        "name": "违纪通知",
        "category": "违纪通知",
        "title_template": "违纪通知 - {student_name}",
        "content_template": "{student_name}同学于{date}因{discipline_desc}被记录{discipline_type}违纪，扣{points}分。请家长关注并配合教育。",
        "target_role": "parent",
    },
    {
        "name": "成绩发布",
        "category": "成绩通知",
        "title_template": "成绩通知 - {student_name}",
        "content_template": "{student_name}同学{semester}考试成绩已发布，请登录平台查看详情。如有疑问请及时与班主任联系。",
        "target_role": "parent",
    },
    {
        "name": "家长会通知",
        "category": "家长会",
        "title_template": "家长会通知",
        "content_template": "定于{meeting_date}在{meeting_location}召开家长会，主题：{meeting_title}。请家长准时参加，谢谢配合！",
        "target_role": "parent",
    },
    {
        "name": "表扬信",
        "category": "表扬",
        "title_template": "表扬信 - {student_name}",
        "content_template": "{student_name}同学表现优异，特此表扬！{reason}\n\n希望继续保持，再接再厉！",
        "target_role": "parent",
    },
    {
        "name": "请假审批通知",
        "category": "请假通知",
        "title_template": "请假审批结果 - {student_name}",
        "content_template": "{student_name}同学{date}的请假申请已审批通过，原因：{reason}。\n\n请按时返校销假。",
        "target_role": "parent",
    },
    {
        "name": "活动通知",
        "category": "活动通知",
        "title_template": "活动通知",
        "content_template": "学校将于{date}举办活动，请关注后续安排。\n\n具体事项另行通知。",
        "target_role": "parent",
    },
]

TEMPLATE_VARIABLES = [
    ("{student_name}", "学生姓名"),
    ("{class_name}", "班级名称"),
    ("{score}", "分数"),
    ("{reason}", "原因/事由"),
    ("{date}", "日期"),
    ("{teacher_name}", "教师姓名"),
    ("{meeting_title}", "会议主题"),
    ("{meeting_date}", "会议日期"),
    ("{meeting_location}", "会议地点"),
    ("{points}", "扣分/积分"),
    ("{discipline_type}", "违纪类型"),
    ("{discipline_desc}", "违纪描述"),
    ("{semester}", "学期"),
]


def seed_system_templates():
    """首次加载时创建系统预设模板"""
    for tmpl in SYSTEM_TEMPLATES:
        existing = MessageTemplate.query.filter_by(name=tmpl["name"]).first()
        if not existing:
            db.session.add(MessageTemplate(
                name=tmpl["name"],
                category=tmpl["category"],
                title_template=tmpl["title_template"],
                content_template=tmpl["content_template"],
                target_role=tmpl.get("target_role", ""),
                is_system=True,
                created_by_id=None,
            ))
    safe_commit()


# ── 模板列表（按分类分组） ──
@message_templates_bp.route("/")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def index():
    seed_system_templates()
    templates = (MessageTemplate.query
                 .order_by(MessageTemplate.category, MessageTemplate.is_system.desc(),
                           MessageTemplate.created_at.desc())
                 .all())

    # 按分类分组
    grouped = {}
    for t in templates:
        grouped.setdefault(t.category, []).append(t)

    return render_template("message_templates/index.html", grouped=grouped)


# ── 创建模板 ──
@message_templates_bp.route("/create", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        title_template = request.form.get("title_template", "").strip()
        content_template = request.form.get("content_template", "").strip()
        target_role = request.form.get("target_role", "")

        if not name or not content_template:
            flash("模板名称和内容不能为空", "danger")
            return redirect(url_for("message_templates.create"))

        if MessageTemplate.query.filter_by(name=name).first():
            flash("模板名称已存在", "danger")
            return redirect(url_for("message_templates.create"))

        tmpl = MessageTemplate(
            name=name,
            category=category or "通用",
            title_template=title_template,
            content_template=content_template,
            target_role=target_role,
            is_system=False,
            created_by_id=session.get("user_id"),
        )
        db.session.add(tmpl)
        safe_commit()
        flash(f"模板「{name}」已创建", "success")
        return redirect(url_for("message_templates.index"))

    return render_template("message_templates/form.html", template=None)


# ── 编辑模板 ──
@message_templates_bp.route("/<int:tid>/edit", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def edit(tid):
    template = MessageTemplate.query.get_or_404(tid)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        title_template = request.form.get("title_template", "").strip()
        content_template = request.form.get("content_template", "").strip()
        target_role = request.form.get("target_role", "")

        if not name or not content_template:
            flash("模板名称和内容不能为空", "danger")
            return redirect(url_for("message_templates.edit", tid=tid))

        # 名称唯一性检查（排除自身）
        dup = MessageTemplate.query.filter_by(name=name).first()
        if dup and dup.id != tid:
            flash("模板名称已被其他模板使用", "danger")
            return redirect(url_for("message_templates.edit", tid=tid))

        template.name = name
        template.category = category or "通用"
        template.title_template = title_template
        template.content_template = content_template
        template.target_role = target_role
        safe_commit()
        flash(f"模板「{name}」已更新", "success")
        return redirect(url_for("message_templates.index"))

    return render_template("message_templates/form.html", template=template)


# ── 删除模板 ──
@message_templates_bp.route("/<int:tid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin")
def delete(tid):
    template = MessageTemplate.query.get_or_404(tid)
    if template.is_system:
        flash("系统预设模板不能删除", "warning")
        return redirect(url_for("message_templates.index"))
    name = template.name
    db.session.delete(template)
    safe_commit()
    flash(f"模板「{name}」已删除", "success")
    return redirect(url_for("message_templates.index"))


# ── 使用模板发消息 ──
@message_templates_bp.route("/<int:tid>/use", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def use_template(tid):
    seed_system_templates()
    template = MessageTemplate.query.get_or_404(tid)

    role = session.get("role", "")
    class_id = session.get("class_id")
    grade_id = session.get("grade_id")

    # 获取可选择的班级和学生列表
    classes_list = []
    students_list = []
    if role == "ms_admin":
        classes_list = Class.query.filter_by(is_active=True).order_by(Class.name).all()
    elif role == "grade_leader" and grade_id:
        classes_list = Class.query.filter_by(grade_id=grade_id, is_active=True).order_by(Class.name).all()
    elif role == "class_teacher" and class_id:
        cls = Class.query.get(class_id)
        if cls:
            classes_list = [cls]

    selected_class_id = request.args.get("class_id", type=int) or (
        class_id if role == "class_teacher" else None
    )
    if selected_class_id:
        students_list = (Student.query.filter_by(class_id=selected_class_id, is_active=True)
                         .order_by(Student.student_no).all())

    error_msg = ""
    preview_title = ""
    preview_content = ""

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "preview":
            # 预览：用表单变量值渲染
            variables = {v[0].strip("{}"): request.form.get(v[0].strip("{}"), "") for v in TEMPLATE_VARIABLES}
            preview_title = template.title_template.format(**variables)
            preview_content = template.content_template.format(**variables)
            return render_template(
                "message_templates/use.html",
                template=template,
                classes_list=classes_list,
                students_list=students_list,
                selected_class_id=selected_class_id,
                preview_title=preview_title,
                preview_content=preview_content,
                form_values=request.form,
                TEMPLATE_VARIABLES=TEMPLATE_VARIABLES,
            )

        elif action == "send":
            # 发送消息
            target_type = request.form.get("target_type")
            send_count = 0

            try:
                variables = {v[0].strip("{}"): request.form.get(v[0].strip("{}"), "") for v in TEMPLATE_VARIABLES}
            except Exception as e:
                flash("预览失败：" + str(e), "danger")

            recipients = []
            if target_type == "individual":
                student_ids = request.form.getlist("student_ids")
                for sid in student_ids:
                    student = Student.query.get(int(sid))
                    if student:
                        recipients.append(student)
            elif target_type == "class_all":
                cid = request.form.get("send_class_id", type=int)
                recipients = Student.query.filter_by(class_id=cid, is_active=True).all()

            if not recipients:
                flash("未选择收件人", "warning")
                return redirect(url_for("message_templates.use_template", tid=tid))

            for stu in recipients:
                # 为每个学生填充变量
                stu_vars = {
                    "student_name": stu.name,
                    "class_name": stu.class_.name if stu.class_ else "",
                    **variables,
                }
                # 清除空变量避免格式化错误
                final_vars = {}
                for k, v in stu_vars.items():
                    final_vars[k] = v if v else f"[待填{{{k}}}]"

                msg_title = template.title_template.format(**final_vars)
                msg_content = template.content_template.format(**final_vars)

                # 找绑定家长发送
                parents = User.query.filter_by(bound_student_id=stu.id, role="parent").all()
                for p in parents:
                    msg = Message(
                        from_user_id=session.get("user_id"),
                        to_user_id=p.id,
                        title=msg_title,
                        content=msg_content,
                    )
                    db.session.add(msg)
                    send_count += 1

            # 更新使用计数
            template.use_count = (template.use_count or 0) + send_count
            safe_commit()

            flash(f"已使用模板「{template.name}」发送 {send_count} 条消息", "success")
            return redirect(url_for("message_templates.index"))

    return render_template(
        "message_templates/use.html",
        template=template,
        classes_list=classes_list,
        students_list=students_list,
        selected_class_id=selected_class_id,
        preview_title="",
        preview_content="",
        form_values={},
        TEMPLATE_VARIABLES=TEMPLATE_VARIABLES,
    )
