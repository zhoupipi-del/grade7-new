"""创建家长会 + 登记出勤/缺席"""
import os
os.environ['DATABASE_URL'] = 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new'

from sqlalchemy import create_engine, text
from datetime import date, datetime

engine = create_engine(os.environ['DATABASE_URL'])

# ── 缺席学生名单 ──
ABSENT_STUDENTS = {
    2501: ['夏文彦', '廖雨蒙', '成雅彤', '毛佳睿', '陶宇凡'],
    2502: ['陈慧慧', '常竣杰', '李秉航', '郭嘉奕', '贺嘉翔', '罗炎旺', '刘煜泽', '夏文轩', '程涛林', '柳妍熙'],
    2503: ['王成龙', '王语思', '罗雨果', '许倩倩', '陈茜', '陈阳依', '刘锦程', '张浩宇', '彭梓坤'],
    2504: ['罗利学', '袁杰隆', '阳鑫'],
    2505: ['刘天羽', '刘畅', '曾逸瑾', '李湘阳', '杨作宇', '瞿英豪', '罗欣雅', '蒲道国', '金娜娜', '陈紫云'],
    2506: ['刘嘉欣', '向宇航', '姜子轩', '孙博', '彭思航', '方玟婷', '李紫月', '钟溪谣'],
    2507: ['吴烨杰', '夏天', '杨其运', '柳权铭'],
    2508: ['伍子涵', '周齐欢', '曹文轩', '曾雨萱', '李浩东', '李雅晗', '瞿天雪', '谢瑾'],
}

with engine.connect() as conn:
    # Step 1: 查找缺席学生的ID集合
    all_absent_names = []
    for cls, names in ABSENT_STUDENTS.items():
        all_absent_names.extend(names)

    placeholders = ','.join([':n%d' % i for i in range(len(all_absent_names))])
    params = {'n%d' % i: name for i, name in enumerate(all_absent_names)}

    absent_rows = conn.execute(text(
        "SELECT id, name FROM students WHERE name IN (%s)" % placeholders
    ), params).fetchall()

    absent_ids = set(r[0] for r in absent_rows)
    absent_name_map = {r[0]: r[1] for r in absent_rows}
    print("缺席学生数: %d" % len(absent_ids))

    # Step 2: 创建家长会
    conn.execute(text(
        "INSERT INTO parent_meetings "
        "(title, meeting_date, start_time, location, grade_id, target_classes, "
        "description, organizer, created_by, created_by_id, created_at) "
        "VALUES (:title, :date, :time, :loc, :gid, :cls, :desc, :org, :cb, :cbid, :ca)"
    ), {
        'title': '初一第二次家长会',
        'date': date(2026, 5, 29),
        'time': '15:50',
        'loc': '南栋各班教室',
        'gid': 1,
        'cls': '[1,2,3,4,5,6,7,8]',
        'desc': '年级大会（网络直播）+ 分班会议 + "给彼此一封信"温情书信活动。请提前10分钟到场签到。',
        'org': '初一年级组',
        'cb': '系统管理员',
        'cbid': 1,
        'ca': datetime(2026, 5, 29, 8, 0, 0),
    })
    conn.commit()

    meeting_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    print("家长会ID: %d" % meeting_id)

    # Step 3: 获取所有目标班级的活跃学生（出勤家长）
    all_students = conn.execute(text(
        "SELECT s.id, s.parent1_name, s.parent1_phone "
        "FROM students s "
        "WHERE s.is_active=1 AND s.class_id IN (1,2,3,4,5,6,7,8) "
        "ORDER BY s.class_id, s.id"
    )).fetchall()

    # Step 4: 批量插入出勤签到（排除缺席学生）
    now_str = datetime(2026, 5, 29, 16, 0, 0).strftime('%Y-%m-%d %H:%M:%S')
    signin_count = 0
    absent_count = 0
    batch = []

    for sid, p_name, p_phone in all_students:
        if sid in absent_ids:
            absent_count += 1
            continue
        batch.append({
            'mid': meeting_id,
            'sid': sid,
            'pn': p_name or '家长',
            'ph': p_phone or '',
            'il': 0,
            'nt': '',
            'st': now_str,
        })
        signin_count += 1
        if len(batch) >= 2000:
            conn.execute(text(
                "INSERT INTO parent_meeting_signins "
                "(meeting_id, student_id, parent_name, phone, is_late, notes, signin_time) "
                "VALUES (:mid, :sid, :pn, :ph, :il, :nt, :st)"
            ), batch)
            conn.commit()
            print("  已签到 %d 人..." % signin_count)
            batch = []

    if batch:
        conn.execute(text(
            "INSERT INTO parent_meeting_signins "
            "(meeting_id, student_id, parent_name, phone, is_late, notes, signin_time) "
            "VALUES (:mid, :sid, :pn, :ph, :il, :nt, :st)"
        ), batch)
        conn.commit()

    # Step 5: 验证
    total = conn.execute(text(
        "SELECT COUNT(*) FROM parent_meeting_signins WHERE meeting_id=:mid"
    ), {'mid': meeting_id}).scalar()
    print("\n=== 家长会登记完成 ===")
    print("家长会: 初一第二次家长会 (2026-05-29 15:50)")
    print("应到: %d 人" % (signin_count + absent_count))
    print("实到签到: %d 人" % total)
    print("缺席: %d 人" % absent_count)

    # 按班统计
    print("\n各班出勤情况:")
    summary = conn.execute(text(
        "SELECT c.name, "
        "COUNT(DISTINCT s.id) as total, "
        "COUNT(DISTINCT CASE WHEN si.id IS NOT NULL THEN s.id END) as signed, "
        "COUNT(DISTINCT CASE WHEN si.id IS NULL THEN s.id END) as absent_cnt "
        "FROM students s "
        "JOIN classes c ON s.class_id = c.id "
        "LEFT JOIN parent_meeting_signins si ON si.student_id = s.id AND si.meeting_id = :mid "
        "WHERE s.is_active=1 AND s.class_id IN (1,2,3,4,5,6,7,8) "
        "GROUP BY s.class_id ORDER BY c.name"
    ), {'mid': meeting_id}).fetchall()

    for cls_name, total, signed, absent_cnt in summary:
        rate = signed / total * 100 if total > 0 else 0
        print("  %s: 应到%d 实到%d 缺席%d 出勤率%.1f%%" % (cls_name, total, signed, absent_cnt, rate))

print("\nDONE")
