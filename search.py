"""全局搜索 — 跨表搜索学生/违纪/通知/消息/活动"""
from flask import Blueprint, render_template, request, jsonify, session
from models import Student, DisciplineRecord, Notice, Message, Activity
from decorators import login_required
from datetime import datetime, timedelta

search_bp = Blueprint("search", __name__, template_folder="../templates")


@search_bp.route("/")
@login_required
def search_page():
    """搜索页面（支持分页和高级筛选）"""
    query = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    filter_type = request.args.get("filter", "all")  # all/student/discipline/notice/message/activity
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    results = {}
    total_count = 0

    if query and len(query) >= 2:
        results, total_count = _perform_search(query, filter_type, date_from, date_to, page)
        # 保存搜索历史
        _save_search_history(query)

    # 获取搜索历史
    search_history = session.get("search_history", [])[:10]

    return render_template(
        "search/results.html",
        query=query,
        results=results,
        total_count=total_count,
        filter_type=filter_type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        search_history=search_history
    )


@search_bp.route("/api/search")
@login_required
def api_search():
    """API：搜索建议（用于搜索框自动补全）"""
    query = request.args.get("q", "").strip()

    if not query or len(query) < 2:
        return jsonify({"results": []})

    suggestions = []
    seen = set()

    # 学生姓名建议
    students = Student.query.filter(Student.name.contains(query)).limit(5).all()
    for s in students:
        if s.name not in seen:
            seen.add(s.name)
            suggestions.append({
                "type": "student",
                "title": s.name,
                "subtitle": f"学号: {s.national_id or s.id_card or s.id}, 班级: {s.class_}",
                "url": f"/class/student/{s.id}",
                "icon": "bi-person"
            })

    # 班级建议
    classes = db.session.query(Student.class_).filter(Student.class_.contains(query)).distinct().limit(3).all()
    for c in classes:
        class_name = c[0]
        if class_name and class_name not in seen:
            seen.add(class_name)
            count = Student.query.filter_by(class_=class_name).count()
            suggestions.append({
                "type": "class",
                "title": class_name,
                "subtitle": f"共 {count} 名学生",
                "url": f"/class/?class={class_name}",
                "icon": "bi-people"
            })

    return jsonify({"results": suggestions})


@search_bp.route("/api/history")
@login_required
def api_history():
    """API：获取搜索历史"""
    history = session.get("search_history", [])
    return jsonify({"history": history})


@search_bp.route("/api/history/clear", methods=["POST"])
@login_required
def api_clear_history():
    """API：清除搜索历史"""
    session["search_history"] = []
    return jsonify({"success": True})


def _perform_search(query, filter_type="all", date_from="", date_to="", page=1, per_page=20):
    """执行全局搜索（支持筛选和分页）"""
    results = {
        "students": [],
        "disciplines": [],
        "notices": [],
        "messages": [],
        "activities": []
    }
    total_count = 0

    # 搜索学生
    if filter_type in ["all", "student"]:
        student_query = Student.query.filter(
            (Student.name.contains(query)) |
            (Student.national_id.contains(query)) |
            (Student.id_card.contains(query)) |
            (Student.class_.contains(query))
        )
        students = student_query.limit(per_page).offset((page-1)*per_page).all()
        total_count += student_query.count()

        for s in students:
            results["students"].append({
                "id": s.id,
                "name": s.name,
                "student_id": s.national_id or s.id_card or str(s.id),
                "class": s.class_,
                "gender": s.gender,
                "url": f"/class/student/{s.id}",
                "icon": "bi-person"
            })

    # 搜索违纪记录
    if filter_type in ["all", "discipline"]:
        disc_query = DisciplineRecord.query.filter(
            DisciplineRecord.description.contains(query)
        )
        if date_from:
            disc_query = disc_query.filter(DisciplineRecord.date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        if date_to:
            disc_query = disc_query.filter(DisciplineRecord.date <= datetime.strptime(date_to, "%Y-%m-%d").date())

        disciplines = disc_query.limit(per_page).offset((page-1)*per_page).all()
        total_count += disc_query.count()

        for d in disciplines:
            student = Student.query.get(d.student_id)
            results["disciplines"].append({
                "id": d.id,
                "student_name": student.name if student else "未知",
                "student_class": student.class_ if student else "未知",
                "type": d.type,
                "description": d.description,
                "date": d.date.strftime("%Y-%m-%d"),
                "url": f"/class/discipline/{d.id}",
                "icon": "bi-exclamation-triangle"
            })

    # 搜索通知
    if filter_type in ["all", "notice"]:
        notice_query = Notice.query.filter(
            (Notice.title.contains(query)) |
            (Notice.content.contains(query))
        )
        if date_from:
            notice_query = notice_query.filter(Notice.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            notice_query = notice_query.filter(Notice.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

        notices = notice_query.limit(per_page).offset((page-1)*per_page).all()
        total_count += notice_query.count()

        for n in notices:
            results["notices"].append({
                "id": n.id,
                "title": n.title,
                "type": n.type,
                "created_at": n.created_at.strftime("%Y-%m-%d"),
                "url": f"/notices/{n.id}",
                "icon": "bi-megaphone"
            })

    # 搜索消息
    if filter_type in ["all", "message"]:
        msg_query = Message.query.filter(
            (Message.title.contains(query)) |
            (Message.content.contains(query))
        )
        if date_from:
            msg_query = msg_query.filter(Message.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            msg_query = msg_query.filter(Message.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

        messages = msg_query.limit(per_page).offset((page-1)*per_page).all()
        total_count += msg_query.count()

        for m in messages:
            results["messages"].append({
                "id": m.id,
                "title": m.title,
                "sender": m.sender.display_name if m.sender else "未知",
                "created_at": m.created_at.strftime("%Y-%m-%d"),
                "is_read": m.is_read,
                "url": f"/common/messages/{m.id}",
                "icon": "bi-envelope"
            })

    # 搜索活动
    if filter_type in ["all", "activity"]:
        act_query = Activity.query.filter(
            (Activity.title.contains(query)) |
            (Activity.description.contains(query))
        )
        if date_from:
            act_query = act_query.filter(Activity.start_time >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            act_query = act_query.filter(Activity.start_time <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

        activities = act_query.limit(per_page).offset((page-1)*per_page).all()
        total_count += act_query.count()

        for a in activities:
            results["activities"].append({
                "id": a.id,
                "title": a.title,
                "type": a.type,
                "start_time": a.start_time.strftime("%Y-%m-%d"),
                "status": a.status,
                "url": f"/activity/{a.id}",
                "icon": "bi-calendar-event"
            })

    return results, total_count


def _save_search_history(query):
    """保存搜索历史到session"""
    history = session.get("search_history", [])

    # 如果已存在，移到最前面
    if query in history:
        history.remove(query)
    history.insert(0, query)

    # 只保留最近10条
    session["search_history"] = history[:10]
