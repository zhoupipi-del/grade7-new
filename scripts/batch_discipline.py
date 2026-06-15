"""清空现有违纪记录 + 批量录入6起事件14条违纪记录"""
import os
os.environ['DATABASE_URL'] = 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new'

from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])

CREATED_BY = 1  # admin (德育主任)
GRADE_ID = 1    # 初一

# 学生ID映射
STU = {
    '夏文彦': {'id': 39, 'class': 1},   # 2501班
    '夏文轩': {'id': 89, 'class': 2},   # 2502班
    '杨逸晨': {'id': 41, 'class': 1},   # 2501班
    '陈佳乐': {'id': 53, 'class': 2},   # 2502班
    '柳妍熙': {'id': 76, 'class': 2},   # 2502班
    '廖雨蒙': {'id': 16, 'class': 1},   # 2501班
    '肖湘轩': {'id': 137, 'class': 3},  # 2503班
    '戴诗颖': {'id': 56, 'class': 2},   # 2502班
    '曾逸瑾': {'id': 196, 'class': 5},  # 2505班
    '刘月彤': {'id': 119, 'class': 3},  # 2503班
}

# 14条违纪记录
records = [
    # ── 事件1: 5月28日 校园霸凌 ──
    {
        'student_id': STU['夏文彦']['id'], 'class_id': STU['夏文彦']['class'],
        'grade_id': GRADE_ID, 'type': 'serious', 'category': '霸凌',
        'description': '5月28日，夏文彦(2501班)伙同夏文轩(2502班)在学校女厕所对杨逸晨(2501班)实施校园霸凌，性质恶劣。',
        'action_taken': '德育处记严重处分，扣20分',
        'points': 20, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-05-28 10:00:00',
    },
    {
        'student_id': STU['夏文轩']['id'], 'class_id': STU['夏文轩']['class'],
        'grade_id': GRADE_ID, 'type': 'serious', 'category': '霸凌',
        'description': '5月28日，夏文轩(2502班)伙同夏文彦(2501班)在学校女厕所对杨逸晨(2501班)实施校园霸凌，性质恶劣。',
        'action_taken': '德育处记严重处分，扣20分',
        'points': 20, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-05-28 10:00:00',
    },
    {
        'student_id': STU['陈佳乐']['id'], 'class_id': STU['陈佳乐']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '霸凌',
        'description': '5月28日，陈佳乐(2502班)在校园霸凌事件中围观并参与，对杨逸晨(2501班)造成二次伤害。',
        'action_taken': '德育处记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-05-28 10:00:00',
    },
    {
        'student_id': STU['柳妍熙']['id'], 'class_id': STU['柳妍熙']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '霸凌',
        'description': '5月28日，柳妍熙(2502班)在校园霸凌事件中围观并参与，对杨逸晨(2501班)造成二次伤害。',
        'action_taken': '德育处记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-05-28 10:00:00',
    },
    {
        'student_id': STU['廖雨蒙']['id'], 'class_id': STU['廖雨蒙']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '霸凌',
        'description': '5月28日，廖雨蒙(2501班)在校园霸凌事件中围观并参与，对杨逸晨(2501班)造成二次伤害。',
        'action_taken': '德育处记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-05-28 10:00:00',
    },

    # ── 事件2: 6月3日 聚众抽烟 ──
    {
        'student_id': STU['杨逸晨']['id'], 'class_id': STU['杨逸晨']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '吸烟',
        'description': '6月3日，杨逸晨(2501班)在学校南栋教学楼一楼与多名同学聚众抽烟。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-03 14:00:00',
    },
    {
        'student_id': STU['廖雨蒙']['id'], 'class_id': STU['廖雨蒙']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '吸烟',
        'description': '6月3日，廖雨蒙(2501班)在学校南栋教学楼一楼与多名同学聚众抽烟。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-03 14:00:00',
    },
    {
        'student_id': STU['陈佳乐']['id'], 'class_id': STU['陈佳乐']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '吸烟',
        'description': '6月3日，陈佳乐(2502班)在学校南栋教学楼一楼与多名同学聚众抽烟。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-03 14:00:00',
    },
    {
        'student_id': STU['柳妍熙']['id'], 'class_id': STU['柳妍熙']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '吸烟',
        'description': '6月3日，柳妍熙(2502班)在学校南栋教学楼一楼与多名同学聚众抽烟。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-03 14:00:00',
    },

    # ── 事件3: 6月4日 教室后门骑马马 ──
    {
        'student_id': STU['肖湘轩']['id'], 'class_id': STU['肖湘轩']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '其他',
        'description': '6月4日，肖湘轩(2503班)与戴诗颖(2502班)在2502班教室后门有不雅行为（骑马马），被年级组当场抓获。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-04 09:30:00',
    },
    {
        'student_id': STU['戴诗颖']['id'], 'class_id': STU['戴诗颖']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '其他',
        'description': '6月4日，戴诗颖(2502班)与肖湘轩(2503班)在2502班教室后门有不雅行为（骑马马），被年级组当场抓获。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-04 09:30:00',
    },

    # ── 事件4: 6月9日 染发 ──
    {
        'student_id': STU['夏文轩']['id'], 'class_id': STU['夏文轩']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '仪容',
        'description': '6月9日，夏文轩(2502班)将头发染成黄色，违反学生仪容仪表规范，被年级组查获。',
        'action_taken': '口头警告处分，扣5分',
        'points': 5, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-09 08:00:00',
    },

    # ── 事件5: 6月10日 玩避孕套 ──
    {
        'student_id': STU['曾逸瑾']['id'], 'class_id': STU['曾逸瑾']['class'],
        'grade_id': GRADE_ID, 'type': 'serious', 'category': '其他',
        'description': '6月10日，曾逸瑾(2505班)在南栋教学楼二楼玩耍避孕套，被监控拍到，造成周围学生恐慌，影响极坏。',
        'action_taken': '德育处记严重处分，扣20分',
        'points': 20, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-10 10:00:00',
    },

    # ── 事件6: 6月10日 看黄色小说 ──
    {
        'student_id': STU['刘月彤']['id'], 'class_id': STU['刘月彤']['class'],
        'grade_id': GRADE_ID, 'type': 'warning', 'category': '其他',
        'description': '6月10日，刘月彤(2503班)在校园内看黄色小说并向他人传播，被年级组查获。',
        'action_taken': '记警告处分，扣10分',
        'points': 10, 'status': 'active', 'verify_status': 'VERIFIED',
        'created_by': CREATED_BY, 'created_at': '2026-06-10 11:00:00',
    },
]

with engine.connect() as conn:
    # Step 1: 清空现有违纪记录
    old_count = conn.execute(text("SELECT COUNT(*) FROM discipline_records")).scalar()
    print("清空前记录数: %d" % old_count)
    conn.execute(text("DELETE FROM discipline_records"))
    conn.commit()
    print("已清空")

    # Step 2: 批量插入14条新记录
    for i, rec in enumerate(records):
        conn.execute(text(
            "INSERT INTO discipline_records "
            "(student_id, class_id, grade_id, type, category, description, action_taken, "
            "points, status, verify_status, created_by, created_at) "
            "VALUES (:student_id, :class_id, :grade_id, :type, :category, :description, "
            ":action_taken, :points, :status, :verify_status, :created_by, :created_at)"
        ), rec)
    conn.commit()

    # Step 3: 验证
    new_count = conn.execute(text("SELECT COUNT(*) FROM discipline_records")).scalar()
    print("插入后记录数: %d" % new_count)
    assert new_count == len(records), "数量不匹配!"

    # 打印汇总
    print("\n=== 违纪记录汇总 ===")
    summary = conn.execute(text(
        "SELECT dr.id, s.name as student, c.name as class_name, dr.type, dr.category, "
        "dr.points, dr.created_at, dr.description "
        "FROM discipline_records dr "
        "JOIN students s ON dr.student_id = s.id "
        "JOIN classes c ON dr.class_id = c.id "
        "ORDER BY dr.created_at, dr.id"
    )).fetchall()

    for row in summary:
        rid, name, cls, typ, cat, pts, dt, desc = row
        type_label = {'serious': '严重', 'warning': '警告'}.get(typ, typ)
        print("  [%d] %s(%s) %s|%s 扣%d分 %s" % (rid, name, cls, type_label, cat, pts, str(dt)[:10]))
        print("         %s" % desc[:50])

    total_pts = conn.execute(text(
        "SELECT SUM(points) FROM discipline_records"
    )).scalar()
    print("\n总扣分: %d 分" % (total_pts or 0))

print("\nDONE")
