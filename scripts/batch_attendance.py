"""批量插入考勤全勤记录 — 3月2日到6月14日，75个工作日"""
import os
os.environ['DATABASE_URL'] = 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new'

from datetime import date, timedelta, datetime
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])

# 参数
START = date(2026, 3, 2)
END = date(2026, 6, 14)  # today is Sunday, last weekday is June 12 (Fri)
STATUS = 'present'

# 生成工作日列表（周一到周五）
workdays = []
d = START
while d <= END:
    if d.weekday() < 5:
        workdays.append(d)
    d += timedelta(days=1)

print("工作日天数: %d" % len(workdays))

# 用原生SQL批量INSERT
with engine.connect() as conn:
    # 1. 获取所有活跃学生
    students = conn.execute(text(
        "SELECT id, class_id, grade_id FROM students WHERE is_active=1 ORDER BY class_id, id"
    )).fetchall()
    print("活跃学生数: %d" % len(students))

    # 2. 批量构建INSERT
    total = 0
    batch_size = 5000
    batch = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for stu_id, class_id, grade_id in students:
        for wd in workdays:
            batch.append({
                'sid': stu_id, 'cid': class_id, 'gid': grade_id,
                'st': STATUS, 'rd': wd, 'ca': now_str
            })
            total += 1
            if len(batch) >= batch_size:
                conn.execute(text(
                    "INSERT INTO attendance (student_id, class_id, grade_id, status, record_date, created_at) "
                    "VALUES (:sid, :cid, :gid, :st, :rd, :ca)"
                ), batch)
                conn.commit()
                print("  已插入 %d 条..." % total)
                batch = []

    # 插入剩余
    if batch:
        conn.execute(text(
            "INSERT INTO attendance (student_id, class_id, grade_id, status, record_date, created_at) "
            "VALUES (:sid, :cid, :gid, :st, :rd, :ca)"
        ), batch)
        conn.commit()

    print("\n完成! 共插入 %d 条考勤记录" % total)

    # 4. 验证
    cnt = conn.execute(text("SELECT COUNT(*) FROM attendance")).scalar()
    print("数据库总记录: %d" % cnt)

    # 验证各班数据
    summary = conn.execute(text(
        "SELECT c.name, COUNT(a.id) as cnt "
        "FROM attendance a JOIN classes c ON a.class_id = c.id "
        "GROUP BY a.class_id ORDER BY c.name"
    )).fetchall()
    print("\n各班记录数:")
    for name, cnt in summary:
        print("  %s: %d" % (name, cnt))

    # 验证日期范围
    rng = conn.execute(text(
        "SELECT MIN(record_date), MAX(record_date), COUNT(DISTINCT record_date) FROM attendance"
    )).fetchone()
    print("\n日期范围: %s ~ %s, 共 %d 个工作日" % (rng[0], rng[1], rng[2]))

print("\nDONE")
