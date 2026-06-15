"""数据一致性巡检脚本

检查项目：
1. 孤儿记录 — 外键指向不存在的记录
2. class_id/grade_id 不一致 — 记录与关联学生不匹配
3. 重复记录
4. 无效角色/状态值

用法：
    cd /opt/grade7-new
    python scripts/consistency_check.py          # 仅输出异常
    python scripts/consistency_check.py -v       # 详细输出
    python scripts/consistency_check.py --fix    # 尝试自动修复（谨慎使用）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Student, Class, Grade, User, DisciplineRecord
from models import Score, Exam, RoutineScore, Attendance, LeaveRequest
from models import HomeVisit, EndTermComment, Task, TaskFeedback
from models import Message, ParentMeeting, ParentMeetingSignin
from models import ProblemStudent, ProblemTrack, RiskRecord
from sqlalchemy import func, text
from collections import Counter, defaultdict

app = create_app()

FIX_MODE = "--fix" in sys.argv
VERBOSE = "-v" in sys.argv

issues = []
fixed = []


def report(category, severity, detail):
    """记录问题"""
    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "INFO": "🔵"}.get(severity, "⚪")
    issues.append((category, severity, detail))
    if VERBOSE or severity in ("CRITICAL", "HIGH"):
        print(f"  {icon} [{severity}] {category}: {detail}")


def auto_fix(model_class, pk, field, expected, actual):
    """自动修复字段不一致（仅 --fix 模式）"""
    if not FIX_MODE:
        return
    try:
        obj = model_class.query.get(pk)
        if obj:
            setattr(obj, field, expected)
            db.session.commit()
            fixed.append(f"{model_class.__name__}#{pk}.{field}: {actual} → {expected}")
    except Exception as e:
        print(f"  ❌ 修复失败: {e}")


def count_section(name, count):
    if count == 0 and not VERBOSE:
        return
    status = "✅" if count == 0 else "❌"
    print(f"\n{'='*50}")
    print(f"  {status} {name} — 发现问题 {count} 个")
    print(f"{'='*50}")


def check_section(name, items, pre_count):
    """输出检查结果小节"""
    new_count = len(issues) - pre_count
    count_section(name, new_count)


with app.app_context():
    print("=" * 60)
    print("  梨江中学德育管理系统 — 数据一致性巡检")
    print("=" * 60)
    print(f"  模式: {'自动修复' if FIX_MODE else '只读检查'}")
    print()

    # ═══════════════════════════════════════════
    # 1. 孤儿记录检查
    # ═══════════════════════════════════════════
    pre = len(issues)

    # 1a — 有 student_id 的模型
    models_with_student = [
        ("DisciplineRecord", DisciplineRecord),
        ("Score", Score),
        ("RoutineScore", RoutineScore),
        ("Attendance", Attendance),
        ("LeaveRequest", LeaveRequest),
        ("RiskRecord", RiskRecord),
        ("HomeVisit", HomeVisit),
        ("EndTermComment", EndTermComment),
        ("ParentMeetingSignin", ParentMeetingSignin),
        ("ProblemStudent", ProblemStudent),
        ("ProblemTrack", ProblemTrack),
    ]
    for name, model in models_with_student:
        if not hasattr(model, "student_id"):
            continue
        orphans = (
            model.query.outerjoin(Student, model.student_id == Student.id)
            .filter(Student.id == None)
            .with_entities(model.id, model.student_id)
            .all()
        )
        for rid, sid in orphans:
            report("孤儿记录", "CRITICAL", f"{name}#{rid} → student_id={sid} (学生不存在)")

    # 1b — 有 class_id 的模型
    models_with_class = [
        ("DisciplineRecord", DisciplineRecord),
        ("RoutineScore", RoutineScore),
        ("Attendance", Attendance),
        ("HomeVisit", HomeVisit),
        ("EndTermComment", EndTermComment),
        ("Score", Score),
    ]
    for name, model in models_with_class:
        if not hasattr(model, "class_id"):
            continue
        orphans = (
            model.query.outerjoin(Class, model.class_id == Class.id)
            .filter(Class.id == None)
            .where(model.class_id != None)
            .with_entities(model.id, model.class_id)
            .all()
        )
        for rid, cid in orphans:
            report("孤儿记录", "CRITICAL", f"{name}#{rid} → class_id={cid} (班级不存在)")

    # 1c — 没有对应班级的 Student
    orphan_students = (
        Student.query.outerjoin(Class, Student.class_id == Class.id)
        .filter(Class.id == None)
        .where(Student.class_id != None)
        .with_entities(Student.id, Student.name, Student.class_id)
        .all()
    )
    for sid, name, cid in orphan_students:
        report("孤儿记录", "CRITICAL", f"Student#{sid} {name} → class_id={cid} (班级不存在)")

    # 1d — 没有对应年级的 Class
    orphan_classes = (
        Class.query.outerjoin(Grade, Class.grade_id == Grade.id)
        .filter(Grade.id == None)
        .with_entities(Class.id, Class.name, Class.grade_id)
        .all()
    )
    for cid, name, gid in orphan_classes:
        report("孤儿记录", "CRITICAL", f"Class#{cid} {name} → grade_id={gid} (年级不存在)")

    check_section("1. 孤儿记录", issues, pre)

    # ═══════════════════════════════════════════
    # 2. class_id / grade_id 不一致
    # ═══════════════════════════════════════════
    pre = len(issues)

    for name, model in models_with_student:
        if not hasattr(model, "class_id") or not hasattr(model, "student_id"):
            continue
        mismatches = (
            model.query.join(Student, model.student_id == Student.id)
            .filter(model.class_id != Student.class_id)
            .with_entities(model.id, model.class_id, Student.class_id, model.student_id)
            .all()
        )
        for rid, record_cid, student_cid, sid in mismatches:
            report("class_id不一致", "HIGH",
                   f"{name}#{rid} class_id={record_cid} ≠ Student#{sid}.class_id={student_cid}")
            auto_fix(model, rid, "class_id", student_cid, record_cid)

    for name, model in models_with_student:
        if not hasattr(model, "grade_id") or not hasattr(model, "student_id"):
            continue
        mismatches = (
            model.query.join(Student, model.student_id == Student.id)
            .filter(model.grade_id != Student.grade_id)
            .with_entities(model.id, model.grade_id, Student.grade_id, model.student_id)
            .all()
        )
        for rid, record_gid, student_gid, sid in mismatches:
            report("grade_id不一致", "HIGH",
                   f"{name}#{rid} grade_id={record_gid} ≠ Student#{sid}.grade_id={student_gid}")
            auto_fix(model, rid, "grade_id", student_gid, record_gid)

    check_section("2. class_id/grade_id 不一致", issues, pre)

    # ═══════════════════════════════════════════
    # 3. 逻辑一致性
    # ═══════════════════════════════════════════
    pre = len(issues)

    # 3a — DisciplineRecord: verify_status 不合法
    weird_disc = (
        DisciplineRecord.query
        .filter(~DisciplineRecord.verify_status.in_(['DRAFT', 'VERIFIED']))
        .count()
    )
    if weird_disc > 0:
        report("状态不一致", "MEDIUM",
               f"DisciplineRecord: {weird_disc} 条 verify_status 不在 [DRAFT, VERIFIED]")

    # 3b — Student.is_active=False 但有未完成的记录
    inactive_students = set(
        sid for sid, in Student.query.filter_by(is_active=False)
        .with_entities(Student.id).all()
    )
    if inactive_students:
        for name, model in [
            ("DisciplineRecord", DisciplineRecord),
            ("LeaveRequest", LeaveRequest),
            ("Score", Score),
            ("ProblemStudent", ProblemStudent),
        ]:
            if hasattr(model, "student_id"):
                orphaned = model.query.filter(
                    model.student_id.in_(list(inactive_students))
                ).count()
                if orphaned > 0:
                    report("非活跃学生残留", "MEDIUM",
                           f"{name}: {orphaned} 条记录关联已停用的学生")

    # 3c — LeaveRequest: status=approved 但没有对应的 Attendance
    approved_leaves = LeaveRequest.query.filter_by(status="approved").count()
    if approved_leaves > 0:
        leave_dates = set(
            (lid, ld)
            for lid, ld in LeaveRequest.query.filter_by(status="approved")
            .with_entities(LeaveRequest.student_id, LeaveRequest.start_date).all()
        )
        matched = (
            Attendance.query.filter(
                Attendance.attendance_type == "leave",
                db.and_(
                    Attendance.student_id.in_([x[0] for x in leave_dates]),
                )
            ).count()
        )
        if matched < approved_leaves:
            report("请假-考勤不一致", "MEDIUM",
                   f"已审批请假 {approved_leaves} 条，仅 {matched} 条有对应考勤记录")

    # 3d — ProblemStudent: level 不合法
    weird_ps = ProblemStudent.query.filter(
        ~ProblemStudent.level.in_(['red', 'yellow'])
    ).count()
    if weird_ps > 0:
        report("状态不一致", "MEDIUM",
               f"ProblemStudent: {weird_ps} 条 level 不在 [red, yellow]")

    check_section("3. 逻辑一致性", issues, pre)

    # ═══════════════════════════════════════════
    # 4. 重复记录
    # ═══════════════════════════════════════════
    pre = len(issues)

    # 4a — RoutineScore 同班同日重复
    dup_routine = (
        db.session.query(
            RoutineScore.class_id, RoutineScore.record_date, RoutineScore.category,
            func.count(RoutineScore.id).label("cnt")
        )
        .group_by(RoutineScore.class_id, RoutineScore.record_date, RoutineScore.category)
        .having(func.count(RoutineScore.id) > 1)
        .all()
    )
    for cid, rdate, cat, cnt in dup_routine:
        report("重复记录", "MEDIUM",
               f"RoutineScore: class_id={cid} date={rdate} category={cat} 有 {cnt} 条记录")

    # 4b — Score 同一考试+学生+科目
    dup_scores = (
        db.session.query(
            Score.exam_id, Score.student_id, Score.subject_id,
            func.count(Score.id).label("cnt")
        )
        .group_by(Score.exam_id, Score.student_id, Score.subject_id)
        .having(func.count(Score.id) > 1)
        .all()
    )
    for eid, sid, subj_id, cnt in dup_scores:
        report("重复记录", "HIGH",
               f"Score: exam_id={eid} student_id={sid} subject_id={subj_id} 有 {cnt} 条记录")

    check_section("4. 重复记录", issues, pre)

    # ═══════════════════════════════════════════
    # 5. 引用完整性（软删除/外键有效性）
    # ═══════════════════════════════════════════
    pre = len(issues)

    # 5a — created_by / processed_by 指向不存在的 User
    models_with_user = [
        ("DisciplineRecord", "created_by", DisciplineRecord),
        ("RiskRecord", "processed_by", RiskRecord),
    ]
    for name, field, model in models_with_user:
        if not hasattr(model, field):
            continue
        orphans = (
            model.query.outerjoin(User, getattr(model, field) == User.id)
            .filter(User.id == None)
            .where(getattr(model, field) != None)
            .with_entities(model.id, getattr(model, field))
            .all()
        )
        for rid, uid in orphans:
            report("引用无效User", "MEDIUM",
                   f"{name}#{rid} → {field}={uid} (用户不存在或被删除)")

    check_section("5. 引用完整性", issues, pre)

    # ═══════════════════════════════════════════
    # 汇总
    # ═══════════════════════════════════════════
    print("\n" + "=" * 60)
    print("  巡检汇总")
    print("=" * 60)

    severity_counts = Counter(s for _, s, _ in issues)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "INFO"]:
        c = severity_counts.get(sev, 0)
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "INFO": "🔵"}.get(sev, "⚪")
        if c > 0:
            print(f"  {icon} {sev}: {c} 个")

    if fixed:
        print(f"\n  ✅ 自动修复: {len(fixed)} 项")
        for f in fixed:
            print(f"     - {f}")

    if not issues:
        print(f"\n  ✅ 数据一致性检查全部通过")
    else:
        print(f"\n  总计: {len(issues)} 个问题")
        print(f"  提示: 使用 --fix 可自动修复 class_id/grade_id 不一致问题")
