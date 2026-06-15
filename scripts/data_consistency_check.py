#!/usr/bin/env python3
"""
数据一致性巡检脚本
检查数据库中的数据一致性问题，输出详细报告
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

from app import create_app
from models import db, Student, Class, Grade, User, Score, Exam, DisciplineRecord, Attendance, MentalHealthAssessment, RiskRecord, WingsScore, Notice, NoticeReceipt, HomeVisit, Activity, ActivityRegistration
from sqlalchemy import func, text

app = create_app()
report = []
issues_count = 0

def add_issue(category, severity, description, table=None, record_id=None):
    """添加问题到报告"""
    global issues_count
    issues_count += 1
    report.append({
        'id': issues_count,
        'category': category,
        'severity': severity,  # 'HIGH', 'MEDIUM', 'LOW'
        'description': description,
        'table': table,
        'record_id': record_id,
        'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
    })

with app.app_context():
    print("=" * 70)
    print("  梨江中学德育管理平台 · 数据一致性巡检")
    print("=" * 70)
    print(f"  开始时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # ── 1. 孤儿记录检查 ──
    print("[1/6] 检查孤儿记录（引用不存在的ID）...")
    
    # Student.class_id 不存在于 Class
    orphans = db.session.query(Student).filter(
        Student.class_id.isnot(None),
        ~Student.class_id.in_(db.session.query(Class.id))
    ).all()
    for s in orphans:
        add_issue('孤儿记录', 'HIGH', 
                   f"Student.id={s.id} (name={s.name}) 引用不存在的 class_id={s.class_id}",
                   'Student', s.id)
    print(f"  - Student.class_id 孤儿: {len(orphans)} 条")
    
    # Student.grade_id 不存在于 Grade
    orphans = db.session.query(Student).filter(
        Student.grade_id.isnot(None),
        ~Student.grade_id.in_(db.session.query(Grade.id))
    ).all()
    for s in orphans:
        add_issue('孤儿记录', 'HIGH', 
                   f"Student.id={s.id} (name={s.name}) 引用不存在的 grade_id={s.grade_id}",
                   'Student', s.id)
    print(f"  - Student.grade_id 孤儿: {len(orphans)} 条")
    
    # Score.student_id 不存在于 Student
    orphans = db.session.query(Score).filter(
        ~Score.student_id.in_(db.session.query(Student.id))
    ).all()
    for sc in orphans:
        add_issue('孤儿记录', 'HIGH', 
                   f"Score.id={sc.id} 引用不存在的 student_id={sc.student_id}",
                   'Score', sc.id)
    print(f"  - Score.student_id 孤儿: {len(orphans)} 条")
    
    # Score.exam_id 不存在于 Exam
    orphans = db.session.query(Score).filter(
        ~Score.exam_id.in_(db.session.query(Exam.id))
    ).all()
    for sc in orphans:
        add_issue('孤儿记录', 'HIGH', 
                   f"Score.id={sc.id} 引用不存在的 exam_id={sc.exam_id}",
                   'Score', sc.id)
    print(f"  - Score.exam_id 孤儿: {len(orphans)} 条")
    
    # DisciplineRecord.student_id 不存在于 Student
    orphans = db.session.query(DisciplineRecord).filter(
        ~DisciplineRecord.student_id.in_(db.session.query(Student.id))
    ).all()
    for d in orphans:
        add_issue('孤儿记录', 'HIGH', 
                   f"DisciplineRecord.id={d.id} 引用不存在的 student_id={d.student_id}",
                   'DisciplineRecord', d.id)
    print(f"  - DisciplineRecord.student_id 孤儿: {len(orphans)} 条")
    
    # Attendance.student_id 不存在于 Student
    orphans = db.session.query(Attendance).filter(
        ~Attendance.student_id.in_(db.session.query(Student.id))
    ).all()
    for a in orphans:
        add_issue('孤儿记录', 'HIGH', 
                   f"Attendance.id={a.id} 引用不存在的 student_id={a.student_id}",
                   'Attendance', a.id)
    print(f"  - Attendance.student_id 孤儿: {len(orphans)} 条")
    
    # ── 2. 重复记录检查 ──
    print("\n[2/6] 检查重复记录...")
    
    # 同一学生在同一考试中多次成绩
    dup_scores = db.session.query(
        Score.student_id,
        Score.exam_id,
        func.count(Score.id).label('cnt')
    ).group_by(Score.student_id, Score.exam_id).having(func.count(Score.id) > 1).all()
    for sid, eid, cnt in dup_scores:
        student = Student.query.get(sid)
        exam = Exam.query.get(eid)
        sname = student.name if student else f"未知({sid})"
        ename = exam.name if exam else f"未知({eid})"
        add_issue('重复记录', 'MEDIUM', 
                   f"学生 {sname} 在考试 {ename} 中有 {cnt} 条成绩记录",
                   'Score', None)
    print(f"  - 重复成绩记录: {len(dup_scores)} 组")
    
    # 同一学生同一天多条考勤记录
    dup_att = db.session.query(
        Attendance.student_id,
        Attendance.record_date,
        func.count(Attendance.id).label('cnt')
    ).group_by(Attendance.student_id, Attendance.record_date).having(func.count(Attendance.id) > 1).all()
    for sid, date, cnt in dup_att:
        student = Student.query.get(sid)
        sname = student.name if student else f"未知({sid})"
        add_issue('重复记录', 'MEDIUM', 
                   f"学生 {sname} 在 {date} 有 {cnt} 条考勤记录",
                   'Attendance', None)
    print(f"  - 重复考勤记录: {len(dup_att)} 组")
    
    # ── 3. 字段值异常检查 ──
    print("\n[3/6] 检查字段值异常...")
    
    # 成绩超出范围
    invalid_scores = Score.query.filter((Score.score < 0) | (Score.score > 100)).all()
    for sc in invalid_scores:
        add_issue('字段值异常', 'HIGH', 
                   f"Score.id={sc.id} 成绩异常: {sc.score}（应在0-100之间）",
                   'Score', sc.id)
    print(f"  - 成绩超出0-100范围: {len(invalid_scores)} 条")
    
    # 考勤状态非法
    valid_status = ['present', 'absent', 'late', 'leave']
    invalid_att = Attendance.query.filter(~Attendance.status.in_(valid_status)).all()
    for a in invalid_att:
        add_issue('字段值异常', 'MEDIUM', 
                   f"Attendance.id={a.id} 考勤状态异常: {a.status}",
                   'Attendance', a.id)
    print(f"  - 考勤状态非法: {len(invalid_att)} 条")
    
    # 违纪类型非法
    valid_types = ['warning', 'minor', 'major', 'serious']
    invalid_disc = DisciplineRecord.query.filter(~DisciplineRecord.type.in_(valid_types)).all()
    for d in invalid_disc:
        add_issue('字段值异常', 'MEDIUM', 
                   f"DisciplineRecord.id={d.id} 违纪类型异常: {d.type}",
                   'DisciplineRecord', d.id)
    print(f"  - 违纪类型非法: {len(invalid_disc)} 条")
    
    # ── 4. 关联数据一致性检查 ──
    print("\n[4/6] 检查关联数据一致性...")
    
    # Student.is_active=False 但仍有活跃记录
    inactive_students = Student.query.filter_by(is_active=False).all()
    for s in inactive_students:
        # 检查是否还有未处理的违纪记录
        active_disc = DisciplineRecord.query.filter_by(
            student_id=s.id, 
            status='pending'
        ).first()
        if active_disc:
            add_issue('关联数据不一致', 'LOW', 
                       f"学生 {s.name} (id={s.id}) 已标记为不活跃，但仍有未处理的违纪记录",
                       'Student', s.id)
    print(f"  - 不活跃学生但有活跃记录: 检查完成")
    
    # ── 5. 数据完整性检查 ──
    print("\n[5/6] 检查数据完整性...")
    
    # 有学生但没有班级
    students_no_class = Student.query.filter(
        Student.class_id.is_(None),
        Student.is_active == True
    ).count()
    if students_no_class > 0:
        add_issue('数据完整性', 'MEDIUM', 
                   f"有 {students_no_class} 个活跃学生没有分配班级",
                   'Student', None)
    print(f"  - 无班级学生: {students_no_class} 人")
    
    # 有班级但没有学生
    classes_no_students = Class.query.filter_by(is_active=True).all()
    empty_classes = 0
    for c in classes_no_students:
        count = Student.query.filter_by(class_id=c.id, is_active=True).count()
        if count == 0:
            empty_classes += 1
    if empty_classes > 0:
        add_issue('数据完整性', 'LOW', 
                   f"有 {empty_classes} 个活跃班级没有学生",
                   'Class', None)
    print(f"  - 空班级: {empty_classes} 个")
    
    # ── 6. 统计摘要 ──
    print("\n[6/6] 生成报告摘要...")
    
    high_count = sum(1 for r in report if r['severity'] == 'HIGH')
    medium_count = sum(1 for r in report if r['severity'] == 'MEDIUM')
    low_count = sum(1 for r in report if r['severity'] == 'LOW')
    
    print()
    print("=" * 70)
    print("  巡检报告摘要")
    print("=" * 70)
    print(f"  总问题数: {issues_count}")
    print(f"  🔴 高优先级: {high_count}")
    print(f"  🟡 中优先级: {medium_count}")
    print(f"  🟢 低优先级: {low_count}")
    print()
    
    if issues_count > 0:
        print("  详细问题列表:")
        print("-" * 70)
        for r in report:
            severity_icon = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}[r['severity']]
            print(f"  [{r['id']}] {severity_icon} [{r['category']}] {r['description']}")
            if r['table']:
                print(f"      表: {r['table']}" + (f" | ID: {r['record_id']}" if r['record_id'] else ""))
        print("-" * 70)
    else:
        print("  ✅ 恭喜！未发现数据一致性问题。")
    
    print()
    print("=" * 70)
    print(f"  结束时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 保存报告到文件
    report_file = f"data_consistency_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("  梨江中学德育管理平台 · 数据一致性巡检报告\n")
        f.write("=" * 70 + "\n")
        f.write(f"  生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  总问题数: {issues_count}\n")
        f.write(f"  高优先级: {high_count}\n")
        f.write(f"  中优先级: {medium_count}\n")
        f.write(f"  低优先级: {low_count}\n")
        f.write("\n")
        
        if issues_count > 0:
            f.write("  详细问题列表:\n")
            f.write("-" * 70 + "\n")
            for r in report:
                severity_icon = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}[r['severity']]
                f.write(f"  [{r['id']}] {severity_icon} [{r['category']}] {r['description']}\n")
                if r['table']:
                    line = f"      表: {r['table']}"
                    if r['record_id']:
                        line += f" | ID: {r['record_id']}"
                    f.write(line + "\n")
            f.write("-" * 70 + "\n")
        else:
            f.write("  ✅ 恭喜！未发现数据一致性问题。\n")
        
        f.write("\n" + "=" * 70 + "\n")
    
    print(f"\n  报告已保存到: {report_file}")
