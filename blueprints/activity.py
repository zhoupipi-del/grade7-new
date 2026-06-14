"""活动管理模块"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Grade, Class, Student, Activity, ActivityRegistration, ActivitySignin, User
from models import QualityIndicator, QualityScore
from decorators import login_required, require_role
from datetime import datetime, date
import json
from utils.db_utils import safe_commit
from utils import get_local_now
from blueprints.common import notify_parent

activity_bp = Blueprint("activity", __name__, url_prefix="/activity")

ACTIVITY_TYPES = ["运动会", "艺术节", "社会实践", "社团活动", "志愿服务", "其他"]
STATUS_LABELS = {
    "draft": "草稿",
    "published": "已发布",
    "ongoing": "进行中",
    "completed": "已结束",
    "cancelled": "已取消",
}


@activity_bp.before_request
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def check_role():
    pass


def _get_class_groups(class_ids):
    """根据班级ID列表获取按年级分组的班级字典 {grade_name: [class_obj, ...]}"""
    from collections import OrderedDict
    classes = Class.query.filter(Class.id.in_(class_ids)).all() if class_ids else []
    groups = OrderedDict()
    for c in classes:
        grade_name = c.grade.name if c.grade else "未知年级"
        groups.setdefault(grade_name, []).append(c)
    return groups


def _parse_target_classes(raw):
    """安全解析 target_classes JSON 字段"""
    if not raw or raw in ("[]", ""):
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


# ══════════════════════════════════════════════════════════════
#  Activity Management (德育处)
# ══════════════════════════════════════════════════════════════

@activity_bp.route("/")
@login_required
def index():
    """活动列表（卡片视图），支持状态/类型筛选"""
    role = session.get("role", "")
    status = request.args.get("status", "")
    atype = request.args.get("type", "")
    search = request.args.get("search", "").strip()

    # 按角色限定数据范围
    if role == "ms_admin":
        q = Activity.query
    elif role == "grade_leader":
        gid = session.get("grade_id")
        q = Activity.query.filter(
            db.or_(Activity.grade_id == gid, Activity.grade_id.is_(None))
        )
    elif role in ("class_teacher", "teacher"):
        gid = session.get("grade_id")
        q = Activity.query.filter(
            db.or_(Activity.grade_id == gid, Activity.grade_id.is_(None))
        )
    elif role == "parent":
        q = Activity.query.filter(Activity.status.in_(["published", "ongoing", "completed"]))
    elif role == "student":
        q = Activity.query.filter(Activity.status.in_(["published", "ongoing", "completed"]))
    else:
        q = Activity.query

    if status:
        q = q.filter_by(status=status)
    if atype:
        q = q.filter_by(activity_type=atype)
    if search:
        q = q.filter(Activity.title.contains(search))

    activities = q.order_by(Activity.start_date.desc()).all()

    # 计算每个活动的报名人数
    activity_reg_counts = {}
    for a in activities:
        activity_reg_counts[a.id] = ActivityRegistration.query.filter_by(
            activity_id=a.id, status="confirmed"
        ).count()

    return render_template(
        "activity/index.html",
        activities=activities,
        activity_reg_counts=activity_reg_counts,
        status_filter=status,
        type_filter=atype,
        search=search,
        types=ACTIVITY_TYPES,
        STATUS_LABELS=STATUS_LABELS,
    )


@activity_bp.route("/create", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def create():
    """创建活动"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "")
        activity_type = request.form.get("activity_type", "其他")
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        location = request.form.get("location", "")
        grade_id = request.form.get("grade_id", type=int) or None
        target_classes = request.form.getlist("target_classes")
        max_participants = request.form.get("max_participants", 0, type=int)
        organizer = request.form.get("organizer", "")
        cover_image = request.form.get("cover_image", "")

        if not title or not start_date:
            flash("请填写活动标题和开始日期", "danger")
            return redirect(url_for("activity.create"))

        activity = Activity(
            title=title,
            description=description or "",
            activity_type=activity_type,
            start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
            end_date=datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None,
            location=location or "",
            grade_id=grade_id,
            target_classes=json.dumps([int(c) for c in target_classes]),
            max_participants=max_participants or 0,
            organizer=organizer or "",
            cover_image=cover_image or "",
            status="draft",
            created_by_id=session.get("user_id"),
        )
        db.session.add(activity)
        safe_commit()
        flash(f"活动「{title}」已创建（草稿状态）", "success")
        return redirect(url_for("activity.detail", aid=activity.id))

    grades = Grade.query.order_by(Grade.sort_order).all()
    classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
    return render_template(
        "activity/form.html",
        activity=None,
        grades=grades,
        classes=classes,
        types=ACTIVITY_TYPES,
        STATUS_LABELS=STATUS_LABELS,
    )


@activity_bp.route("/<int:aid>/edit", methods=["GET", "POST"])
@login_required
@require_role("ms_admin")
def edit(aid):
    """编辑活动"""
    activity = Activity.query.get_or_404(aid)

    if request.method == "POST":
        activity.title = request.form.get("title", "").strip()
        activity.description = request.form.get("description", "")
        activity.activity_type = request.form.get("activity_type", "其他")
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        activity.location = request.form.get("location", "")
        activity.grade_id = request.form.get("grade_id", type=int) or None
        target_classes = request.form.getlist("target_classes")
        activity.max_participants = request.form.get("max_participants", 0, type=int)
        activity.organizer = request.form.get("organizer", "")
        activity.cover_image = request.form.get("cover_image", "")

        if not activity.title or not start_date:
            flash("请填写活动标题和开始日期", "danger")
            return redirect(url_for("activity.edit", aid=aid))

        activity.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        activity.end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        activity.target_classes = json.dumps([int(c) for c in target_classes])
        activity.updated_at = get_local_now()

        safe_commit()
        flash(f"活动「{activity.title}」已更新", "success")
        return redirect(url_for("activity.detail", aid=aid))

    grades = Grade.query.order_by(Grade.sort_order).all()
    classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
    tc = _parse_target_classes(activity.target_classes)
    return render_template(
        "activity/form.html",
        activity=activity,
        grades=grades,
        classes=classes,
        types=ACTIVITY_TYPES,
        STATUS_LABELS=STATUS_LABELS,
        target_class_ids=tc,
    )


@activity_bp.route("/<int:aid>")
@login_required
def detail(aid):
    """活动详情（报名数/签到数/参与率）"""
    activity = Activity.query.get_or_404(aid)

    # 注册统计
    total_reg = ActivityRegistration.query.filter_by(activity_id=aid).count()
    confirmed_reg = ActivityRegistration.query.filter_by(
        activity_id=aid, status="confirmed"
    ).count()
    cancelled_reg = ActivityRegistration.query.filter_by(
        activity_id=aid, status="cancelled"
    ).count()

    # 签到统计
    total_signins = ActivitySignin.query.filter_by(activity_id=aid).count()
    on_time_signins = ActivitySignin.query.filter_by(
        activity_id=aid, status="on_time"
    ).count()
    late_signins = ActivitySignin.query.filter_by(
        activity_id=aid, status="late"
    ).count()
    absent_signins = ActivitySignin.query.filter_by(
        activity_id=aid, status="absent"
    ).count()

    # 按班级分组报名
    reg_records = (
        ActivityRegistration.query.filter_by(activity_id=aid)
        .order_by(ActivityRegistration.class_id, ActivityRegistration.registered_at)
        .all()
    )
    reg_by_class = {}
    for r in reg_records:
        cid = r.class_id
        reg_by_class.setdefault(cid, []).append(r)

    # 按班级分组签到
    signin_records = (
        ActivitySignin.query.filter_by(activity_id=aid)
        .order_by(ActivitySignin.student_id)
        .all()
    )
    signin_by_class = {}
    for s in signin_records:
        st = Student.query.get(s.student_id)
        cid = st.class_id if st else 0
        signin_by_class.setdefault(cid, []).append(s)

    # 班级列表
    class_map = {}
    tc = _parse_target_classes(activity.target_classes)
    if tc:
        clist = Class.query.filter(Class.id.in_(tc)).all()
    elif activity.grade_id:
        clist = Class.query.filter_by(grade_id=activity.grade_id, is_active=True).all()
    else:
        clist = Class.query.filter_by(is_active=True).all()

    for c in clist:
        class_map[c.id] = c

    # 签到统计（按班级用于图表）
    signin_stats = []
    for c in clist:
        cid = c.id
        students = Student.query.filter_by(class_id=cid, is_active=True).filter(
            Student.id.in_(
                db.session.query(ActivityRegistration.student_id).filter_by(
                    activity_id=aid, status="confirmed"
                )
            )
        ).all() if confirmed_reg > 0 else Student.query.filter_by(
            class_id=cid, is_active=True
        ).all()
        total = len(students)
        signed = sum(
            1 for s in signin_records
            if Student.query.get(s.student_id) and Student.query.get(s.student_id).class_id == cid
        )
        signin_stats.append({
            "class_name": c.name,
            "total": total,
            "signed": signed,
            "unsigned": total - signed if total > signed else 0,
        })

    return render_template(
        "activity/detail.html",
        activity=activity,
        total_reg=total_reg,
        confirmed_reg=confirmed_reg,
        cancelled_reg=cancelled_reg,
        total_signins=total_signins,
        on_time_signins=on_time_signins,
        late_signins=late_signins,
        absent_signins=absent_signins,
        reg_by_class=reg_by_class,
        signin_by_class=signin_by_class,
        class_map=class_map,
        signin_stats=signin_stats,
        STATUS_LABELS=STATUS_LABELS,
        max_p=activity.max_participants,
    )


@activity_bp.route("/<int:aid>/publish", methods=["POST"])
@login_required
@require_role("ms_admin")
def publish(aid):
    """发布活动（draft→published），并通知家长"""
    activity = Activity.query.get_or_404(aid)
    if activity.status != "draft":
        flash("只有草稿状态的活动可以发布", "warning")
        return redirect(url_for("activity.detail", aid=aid))

    old_status = activity.status
    activity.status = "published"
    activity.updated_at = get_local_now()
    safe_commit()

    # 发布时通知目标学生家长
    if old_status != activity.status:
        from_user_id = session.get("user_id")
        try:
            class_ids = json.loads(activity.target_classes or "[]")
            if class_ids:
                target_students = Student.query.filter(
                    Student.class_id.in_(class_ids),
                    Student.is_active == True
                ).all()
                for stu in target_students:
                    notify_parent(
                        stu,
                        title=f"活动通知 — {activity.title}",
                        content=f"【{activity.title}】已发布，请提醒孩子关注。\n"
                                f"活动类型：{activity.activity_type}\n"
                                f"开始时间：{activity.start_date}\n"
                                f"地点：{activity.location or '待定'}",
                        from_user_id=from_user_id,
                    )
        except Exception:
            pass

    flash(f"活动「{activity.title}」已发布", "success")
    return redirect(url_for("activity.detail", aid=aid))


@activity_bp.route("/<int:aid>/complete", methods=["POST"])
@login_required
@require_role("ms_admin")
def complete(aid):
    """结束活动（ongoing→completed），并自动计入综合素质评价"""
    activity = Activity.query.get_or_404(aid)
    if activity.status != "ongoing":
        flash("只有进行中的活动可以结束", "warning")
        return redirect(url_for("activity.detail", aid=aid))
    activity.status = "completed"
    activity.updated_at = get_local_now()
    safe_commit()

    # ── 活动完成后，自动计入综合素质评价 ──
    _auto_score_activity(activity)

    flash(f"活动「{activity.title}」已结束", "success")
    return redirect(url_for("activity.detail", aid=aid))


@activity_bp.route("/<int:aid>/cancel", methods=["POST"])
@login_required
@require_role("ms_admin")
def cancel_activity(aid):
    """取消活动"""
    activity = Activity.query.get_or_404(aid)
    if activity.status in ("completed", "cancelled"):
        flash("已完成或已取消的活动无法再次取消", "warning")
        return redirect(url_for("activity.detail", aid=aid))
    activity.status = "cancelled"
    activity.updated_at = get_local_now()
    safe_commit()
    flash(f"活动「{activity.title}」已取消", "success")
    return redirect(url_for("activity.detail", aid=aid))


@activity_bp.route("/<int:aid>/delete", methods=["POST"])
@login_required
@require_role("ms_admin")
def delete(aid):
    """删除活动（仅draft可删）"""
    activity = Activity.query.get_or_404(aid)
    if activity.status != "draft":
        flash("只有草稿状态的活动可以删除", "warning")
        return redirect(url_for("activity.detail", aid=aid))
    title = activity.title
    # 删除关联数据
    ActivityRegistration.query.filter_by(activity_id=aid).delete()
    ActivitySignin.query.filter_by(activity_id=aid).delete()
    db.session.delete(activity)
    safe_commit()
    flash(f"活动「{title}」已删除", "success")
    return redirect(url_for("activity.index"))


# ══════════════════════════════════════════════════════════════
#  Registration Management (报名管理)
# ══════════════════════════════════════════════════════════════

@activity_bp.route("/<int:aid>/registrations")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def registrations(aid):
    """报名列表（按班级分组）"""
    activity = Activity.query.get_or_404(aid)

    role = session.get("role", "")
    my_class_id = session.get("class_id")

    regs = ActivityRegistration.query.filter_by(activity_id=aid).order_by(
        ActivityRegistration.class_id, ActivityRegistration.registered_at
    ).all()

    # 按班级分组
    reg_by_class = {}
    for r in regs:
        cid = r.class_id
        reg_by_class.setdefault(cid, []).append(r)

    # 班主任只能看自己班
    if role == "class_teacher" and my_class_id:
        reg_by_class = {my_class_id: reg_by_class.get(my_class_id, [])}

    # 获取班级信息
    class_ids = set(reg_by_class.keys())
    class_map = {c.id: c for c in Class.query.filter(Class.id.in_(class_ids)).all()} if class_ids else {}

    # 所有可用班级（用于筛选）— 班主任只能看自己的班
    if role == "class_teacher" and my_class_id:
        all_classes = [Class.query.get(my_class_id)] if my_class_id else []
    else:
        all_classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()

    class_filter = request.args.get("class_id", type=int)
    if class_filter:
        reg_by_class = {class_filter: reg_by_class.get(class_filter, [])}

    return render_template(
        "activity/registrations.html",
        activity=activity,
        reg_by_class=reg_by_class,
        class_map=class_map,
        all_classes=all_classes,
        class_filter=class_filter,
        STATUS_LABELS=STATUS_LABELS,
    )


@activity_bp.route("/<int:aid>/register", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def register_student(aid):
    """学生报名（班主任替学生报名）"""
    activity = Activity.query.get_or_404(aid)

    if activity.status not in ("published", "ongoing"):
        return jsonify({"code": 1, "msg": "该活动不接受报名"}), 400

    student_id = request.form.get("student_id", type=int)
    note = request.form.get("note", "")

    if not student_id:
        return jsonify({"code": 1, "msg": "请选择学生"}), 400

    student = Student.query.get(student_id)
    if not student:
        return jsonify({"code": 1, "msg": "学生不存在"}), 404

    # 检查是否已报名
    existing = ActivityRegistration.query.filter_by(
        activity_id=aid, student_id=student_id
    ).first()
    if existing:
        if existing.status == "cancelled":
            existing.status = "registered"
            existing.note = note
            existing.registered_at = get_local_now()
            safe_commit()
            return jsonify({"code": 0, "msg": "重新报名成功"})
        return jsonify({"code": 1, "msg": "该学生已报名"}), 400

    # 检查人数上限
    if activity.max_participants > 0:
        count = ActivityRegistration.query.filter_by(
            activity_id=aid, status="confirmed"
        ).count()
        if count >= activity.max_participants:
            return jsonify({"code": 1, "msg": "报名人数已达上限"}), 400

    reg = ActivityRegistration(
        activity_id=aid,
        student_id=student_id,
        class_id=student.class_id,
        status="registered",
        note=note or "",
    )
    db.session.add(reg)
    safe_commit()

    return jsonify({"code": 0, "msg": f"{student.name} 报名成功"})


@activity_bp.route("/<int:aid>/cancel-reg/<int:rid>", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def cancel_registration(aid, rid):
    """取消报名"""
    reg = ActivityRegistration.query.get_or_404(rid)
    if reg.status == "cancelled":
        return jsonify({"code": 1, "msg": "该报名已取消"}), 400

    reg.status = "cancelled"
    safe_commit()
    return jsonify({"code": 0, "msg": "报名已取消"})


@activity_bp.route("/<int:aid>/confirm-reg/<int:rid>", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def confirm_registration(aid, rid):
    """确认报名"""
    reg = ActivityRegistration.query.get_or_404(rid)
    if reg.status == "cancelled":
        return jsonify({"code": 1, "msg": "已取消的报名无法确认"}), 400

    # 检查人数上限
    activity = Activity.query.get(aid)
    if activity and activity.max_participants > 0 and reg.status != "confirmed":
        count = ActivityRegistration.query.filter_by(
            activity_id=aid, status="confirmed"
        ).count()
        if count >= activity.max_participants:
            return jsonify({"code": 1, "msg": "确认人数已达上限"}), 400

    reg.status = "confirmed"
    safe_commit()
    return jsonify({"code": 0, "msg": "报名已确认"})


@activity_bp.route("/<int:aid>/batch-register", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def batch_register(aid):
    """批量报名"""
    activity = Activity.query.get_or_404(aid)
    role = session.get("role", "")
    my_class_id = session.get("class_id")

    if request.method == "POST":
        class_id = request.form.get("class_id", type=int)
        student_ids = request.form.getlist("student_ids")

        # 班主任只能给自己班报名
        if role == "class_teacher" and my_class_id and class_id != my_class_id:
            flash("只能为本班学生报名", "danger")
            return redirect(url_for("activity.batch_register", aid=aid))

        if not class_id or not student_ids:
            flash("请选择班级和学生", "danger")
            return redirect(url_for("activity.batch_register", aid=aid))

        count = 0
        for sid in student_ids:
            sid = int(sid)
            existing = ActivityRegistration.query.filter_by(
                activity_id=aid, student_id=sid
            ).first()
            if not existing:
                # 检查人数上限
                if activity.max_participants > 0:
                    cur = ActivityRegistration.query.filter_by(
                        activity_id=aid, status="confirmed"
                    ).count()
                    if cur >= activity.max_participants:
                        break

                student = Student.query.get(sid)
                if student:
                    reg = ActivityRegistration(
                        activity_id=aid,
                        student_id=sid,
                        class_id=student.class_id,
                        status="registered",
                    )
                    db.session.add(reg)
                    count += 1
            elif existing.status == "cancelled":
                existing.status = "registered"
                existing.registered_at = get_local_now()
                count += 1

        safe_commit()
        flash(f"批量报名完成，共 {count} 名学生", "success")
        return redirect(url_for("activity.registrations", aid=aid))

    # GET: 显示班级选择 — 班主任只能看自己的班
    if role == "class_teacher" and my_class_id:
        classes = [Class.query.get(my_class_id)] if my_class_id else []
        selected_class = my_class_id
    else:
        classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
        selected_class = request.args.get("class_id", type=int)
    students = []
    if selected_class:
        students = Student.query.filter_by(
            class_id=selected_class, is_active=True
        ).order_by(Student.student_no).all()
        # 标记已报名的
        existing_ids = {
            r.student_id
            for r in ActivityRegistration.query.filter(
                ActivityRegistration.activity_id == aid,
                ActivityRegistration.status != "cancelled",
            ).all()
        }

    return render_template(
        "activity/batch_register.html",
        activity=activity,
        classes=classes,
        students=students,
        selected_class=selected_class,
        existing_ids=existing_ids if selected_class else set(),
    )


# ══════════════════════════════════════════════════════════════
#  Signin Management (签到管理)
# ══════════════════════════════════════════════════════════════

@activity_bp.route("/<int:aid>/signin", methods=["GET", "POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def signin(aid):
    """签到页面"""
    activity = Activity.query.get_or_404(aid)
    role = session.get("role", "")
    my_class_id = session.get("class_id")

    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        status_val = request.form.get("status", "on_time")
        note = request.form.get("note", "")

        if not student_id:
            return jsonify({"code": 1, "msg": "请选择学生"}), 400

        # 班主任只能给本班学生签到
        if role == "class_teacher" and my_class_id:
            stu = Student.query.get(student_id)
            if not stu or stu.class_id != my_class_id:
                return jsonify({"code": 1, "msg": "只能为本班学生签到"}), 403

        existing = ActivitySignin.query.filter_by(
            activity_id=aid, student_id=student_id
        ).first()
        if existing:
            existing.status = status_val
            existing.signin_time = get_local_now()
            existing.note = note
        else:
            signin = ActivitySignin(
                activity_id=aid,
                student_id=student_id,
                status=status_val,
                note=note,
            )
            db.session.add(signin)
        safe_commit()
        return jsonify({"code": 0, "msg": "签到成功"})

    # GET: 显示签到列表
    # 获取已报名的学生列表
    regs = ActivityRegistration.query.filter_by(
        activity_id=aid, status="confirmed"
    ).all()
    registered_student_ids = [r.student_id for r in regs]
    registered_map = {r.student_id: r for r in regs}

    # 获取签到记录
    signins = ActivitySignin.query.filter_by(activity_id=aid).all()
    signin_map = {s.student_id: s for s in signins}

    # 构建学生列表 — 班主任只能看本班
    students = []
    if registered_student_ids:
        student_q = Student.query.filter(
            Student.id.in_(registered_student_ids)
        )
        if role == "class_teacher" and my_class_id:
            student_q = student_q.filter_by(class_id=my_class_id)
        students = student_q.order_by(Student.class_id, Student.student_no).all()

    # 签到计数
    signed_count = sum(1 for s in signins if s.status in ("on_time", "late"))
    absent_count = sum(1 for s in signins if s.status == "absent")
    total_count = len(students)

    # 班主任只能看自己的班
    if role == "class_teacher" and my_class_id:
        classes = [Class.query.get(my_class_id)] if my_class_id else []
    else:
        classes = Class.query.filter_by(is_active=True).order_by(Class.name).all()
    class_map = {c.id: c.name for c in classes}

    return render_template(
        "activity/signin.html",
        activity=activity,
        students=students,
        signin_map=signin_map,
        registered_map=registered_map,
        signed_count=signed_count,
        absent_count=absent_count,
        total_count=total_count,
        class_map=class_map,
        STATUS_LABELS=STATUS_LABELS,
    )


@activity_bp.route("/<int:aid>/signin/batch", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def signin_batch(aid):
    """批量签到"""
    student_ids = request.form.getlist("student_ids")
    status_val = request.form.get("status", "on_time")

    if not student_ids:
        return jsonify({"code": 1, "msg": "请选择学生"}), 400

    count = 0
    for sid in student_ids:
        sid = int(sid)
        existing = ActivitySignin.query.filter_by(
            activity_id=aid, student_id=sid
        ).first()
        if existing:
            existing.status = status_val
            existing.signin_time = get_local_now()
        else:
            signin = ActivitySignin(
                activity_id=aid,
                student_id=sid,
                status=status_val,
            )
            db.session.add(signin)
        count += 1

    safe_commit()
    return jsonify({"code": 0, "msg": f"批量签到完成，共 {count} 人"})


@activity_bp.route("/<int:aid>/signin/<int:sid>/absent", methods=["POST"])
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def mark_absent(aid, sid):
    """标记缺席"""
    note = request.form.get("note", "")
    existing = ActivitySignin.query.filter_by(
        activity_id=aid, student_id=sid
    ).first()
    if existing:
        existing.status = "absent"
        existing.note = note
    else:
        signin = ActivitySignin(
            activity_id=aid,
            student_id=sid,
            status="absent",
            note=note or "",
        )
        db.session.add(signin)
    safe_commit()
    return jsonify({"code": 0, "msg": "已标记为缺席"})


@activity_bp.route("/<int:aid>/signin-stats")
@login_required
@require_role("ms_admin", "grade_leader", "class_teacher")
def signin_stats(aid):
    """签到统计"""
    activity = Activity.query.get_or_404(aid)

    signins = ActivitySignin.query.filter_by(activity_id=aid).all()
    on_time = sum(1 for s in signins if s.status == "on_time")
    late = sum(1 for s in signins if s.status == "late")
    absent = sum(1 for s in signins if s.status == "absent")

    # 按班级统计
    regs = ActivityRegistration.query.filter_by(
        activity_id=aid, status="confirmed"
    ).all()
    registered_ids = [r.student_id for r in regs]
    signin_map = {s.student_id: s for s in signins}

    by_class = {}
    if registered_ids:
        students = Student.query.filter(Student.id.in_(registered_ids)).all()
        for s in students:
            cid = s.class_id
            if cid not in by_class:
                by_class[cid] = {"class_name": "", "total": 0, "signed": 0, "absent": 0, "not_checked": 0}
            by_class[cid]["total"] += 1
            si = signin_map.get(s.id)
            if si:
                if si.status in ("on_time", "late"):
                    by_class[cid]["signed"] += 1
                elif si.status == "absent":
                    by_class[cid]["absent"] += 1
            else:
                by_class[cid]["not_checked"] += 1

    # 获取班级名称
    class_ids = list(by_class.keys())
    if class_ids:
        for c in Class.query.filter(Class.id.in_(class_ids)).all():
            if c.id in by_class:
                by_class[c.id]["class_name"] = c.name

    class_stats = list(by_class.values())
    not_checked = len(registered_ids) - on_time - late - absent
    total_registered = len(registered_ids)

    return render_template(
        "activity/signin_stats.html",
        activity=activity,
        on_time=on_time,
        late=late,
        absent=absent,
        not_checked=not_checked,
        total_registered=total_registered,
        class_stats=class_stats,
        STATUS_LABELS=STATUS_LABELS,
    )


# ══════════════════════════════════════════════════════════════
#  Student / Parent Views (学生/家长端)
# ══════════════════════════════════════════════════════════════

@activity_bp.route("/student")
@login_required
@require_role("student", "parent")
def student_list():
    """学生活动列表（已发布的活动）"""
    atype = request.args.get("type", "")
    q = Activity.query.filter(Activity.status.in_(["published", "ongoing", "completed"]))
    if atype:
        q = q.filter_by(activity_type=atype)
    activities = q.order_by(Activity.start_date.desc()).all()

    # 获取当前学生的报名记录
    student_id = None
    if session.get("role") == "student":
        student_id = session.get("student_id")
    elif session.get("role") == "parent":
        student_id = session.get("bound_student_id") or session.get("student_id")

    my_regs = {}
    if student_id:
        regs = ActivityRegistration.query.filter_by(student_id=student_id).all()
        my_regs = {r.activity_id: r for r in regs}

    return render_template(
        "activity/student_list.html",
        activities=activities,
        my_regs=my_regs,
        type_filter=atype,
        types=ACTIVITY_TYPES,
        STATUS_LABELS=STATUS_LABELS,
    )


@activity_bp.route("/student/<int:aid>")
@login_required
@require_role("student", "parent")
def student_detail(aid):
    """活动详情+报名入口"""
    activity = Activity.query.get_or_404(aid)

    if activity.status not in ("published", "ongoing", "completed"):
        flash("该活动暂未开放", "warning")
        return redirect(url_for("activity.student_list"))

    student_id = None
    if session.get("role") == "student":
        student_id = session.get("student_id")
    elif session.get("role") == "parent":
        student_id = session.get("bound_student_id") or session.get("student_id")

    my_reg = None
    if student_id:
        my_reg = ActivityRegistration.query.filter_by(
            activity_id=aid, student_id=student_id
        ).first()

    confirmed_count = ActivityRegistration.query.filter_by(
        activity_id=aid, status="confirmed"
    ).count()

    return render_template(
        "activity/student_detail.html",
        activity=activity,
        my_reg=my_reg,
        confirmed_count=confirmed_count,
        STATUS_LABELS=STATUS_LABELS,
        max_p=activity.max_participants,
    )


@activity_bp.route("/student/<int:aid>/register", methods=["POST"])
@login_required
@require_role("student", "parent")
def student_register(aid):
    """学生自主报名"""
    activity = Activity.query.get_or_404(aid)

    if activity.status not in ("published", "ongoing"):
        flash("该活动不接受报名", "warning")
        return redirect(url_for("activity.student_detail", aid=aid))

    student_id = None
    if session.get("role") == "student":
        student_id = session.get("student_id")
    elif session.get("role") == "parent":
        student_id = session.get("bound_student_id") or session.get("student_id")

    if not student_id:
        flash("无法确认学生身份", "danger")
        return redirect(url_for("activity.student_list"))

    existing = ActivityRegistration.query.filter_by(
        activity_id=aid, student_id=student_id
    ).first()
    if existing and existing.status != "cancelled":
        flash("您已报名该活动", "info")
        return redirect(url_for("activity.student_detail", aid=aid))

    if activity.max_participants > 0:
        count = ActivityRegistration.query.filter_by(
            activity_id=aid, status="confirmed"
        ).count()
        if count >= activity.max_participants:
            flash("报名人数已满", "warning")
            return redirect(url_for("activity.student_detail", aid=aid))

    student = Student.query.get(student_id)
    if existing and existing.status == "cancelled":
        existing.status = "registered"
        existing.registered_at = get_local_now()
    else:
        reg = ActivityRegistration(
            activity_id=aid,
            student_id=student_id,
            class_id=student.class_id if student else 0,
            status="registered",
        )
        db.session.add(reg)

    safe_commit()
    flash("报名成功", "success")
    return redirect(url_for("activity.student_detail", aid=aid))


@activity_bp.route("/student/my")
@login_required
@require_role("student", "parent")
def my_activities():
    """我的活动（已报名的）"""
    student_id = None
    if session.get("role") == "student":
        student_id = session.get("student_id")
    elif session.get("role") == "parent":
        student_id = session.get("bound_student_id") or session.get("student_id")

    regs = []
    if student_id:
        regs = (
            ActivityRegistration.query.filter_by(student_id=student_id)
            .order_by(ActivityRegistration.registered_at.desc())
            .all()
        )

    return render_template(
        "activity/my_activities.html",
        regs=regs,
        STATUS_LABELS=STATUS_LABELS,
    )


# ── 活动→综合素质评价自动计入 ─────────────────────────────
ACTIVITY_DIMENSION_MAP = {
    "社会实践": "social",
    "志愿服务": "social",
    "艺术节": "art",
    "运动会": "health",
    "社团活动": "art",
}


def _current_semester():
    """获取当前学期"""
    now = get_local_now()
    y = now.year
    m = now.month
    if m >= 9:
        return f"{y}-{y+1}-1"
    elif m >= 2:
        return f"{y-1}-{y}-2"
    else:
        return f"{y-1}-{y}-2"


def _auto_score_activity(activity):
    """活动完成后，自动为参与学生在综合素质评价中记录分数

    映射规则：
    - 社会实践/志愿服务 → social（社会实践）维度
    - 艺术节/社团活动 → art（艺术素养）维度
    - 运动会 → health（身心健康）维度

    评分规则：
    - 基础参与分：85
    - 签到准时 +10，迟到 +5，缺席 -20，未签到保持 85
    """
    dim_key = ACTIVITY_DIMENSION_MAP.get(activity.activity_type)
    if not dim_key:
        return  # 不属于可计分的活动类型

    # 查找对应维度的二级指标
    indicators = QualityIndicator.query.filter(
        QualityIndicator.parent_id > 0,
        QualityIndicator.dimension == dim_key,
        QualityIndicator.is_active == True,
    ).all()
    if not indicators:
        return

    semester = _current_semester()

    # 获取已确认报名的学生
    regs = ActivityRegistration.query.filter_by(
        activity_id=activity.id, status="confirmed"
    ).all()

    # 获取签到记录
    signins = ActivitySignin.query.filter_by(activity_id=activity.id).all()
    signin_map = {s.student_id: s.status for s in signins}

    count = 0
    for reg in regs:
        student = Student.query.get(reg.student_id)
        if not student or not student.is_active:
            continue

        # 计算得分
        signin_status = signin_map.get(reg.student_id)
        if signin_status == "on_time":
            score = 95
        elif signin_status == "late":
            score = 90
        elif signin_status == "absent":
            score = 65
        else:
            score = 85  # 报名但未签到，给基础分

        # 为每个相关的二级指标记录分数
        for ind in indicators:
            existing = QualityScore.query.filter_by(
                student_id=student.id,
                indicator_id=ind.id,
                scorer_type="system",
                semester=semester,
            ).first()

            if existing:
                # 已有系统评分，取较高值
                if score > existing.score:
                    existing.score = score
                    existing.comment = f"活动「{activity.title}」参与分（更新）"
            else:
                qs = QualityScore(
                    student_id=student.id,
                    class_id=student.class_id,
                    grade_id=student.grade_id,
                    indicator_id=ind.id,
                    score=score,
                    scorer_type="system",
                    scorer_id=1,  # 系统账号
                    semester=semester,
                    comment=f"活动「{activity.title}」参与分",
                )
                db.session.add(qs)
            count += 1

    if count > 0:
        safe_commit()
        print(f"[activity] 活动「{activity.title}」完成，已自动计入 {count} 条综合素质评价记录")
