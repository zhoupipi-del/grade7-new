#!/usr/bin/env python3
"""服务器侧：重新导入第4次考试成绩（正确文件）
数据源: /opt/grade7-new/exam4_correct.csv
先删除旧的Exam #4数据，再从正确CSV导入
"""
import csv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"
CSV_PATH = "/opt/grade7-new/exam4_correct.csv"
EXAM_NAME = "2026年七年级下学期期中考试"
EXAM_DATE = "2026-04-28"
GRADE_ID = 1
SUBJECT_IDS = [1, 2, 3, 4, 5, 6, 7]  # 语数英政史地生

engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
session = Session()

try:
    # ========== 1. 删除旧数据 ==========
    # 查找旧Exam
    old = session.execute(
        text("SELECT id FROM exams WHERE name = :name"),
        {"name": EXAM_NAME}
    ).fetchone()

    if old:
        old_id = old[0]
        cnt = session.execute(
            text("SELECT COUNT(*) FROM scores WHERE exam_id = :eid"),
            {"eid": old_id}
        ).scalar()
        session.execute(text("DELETE FROM scores WHERE exam_id = :eid"), {"eid": old_id})
        session.execute(text("DELETE FROM exams WHERE id = :eid"), {"eid": old_id})
        session.commit()
        print(f"🗑  已删除旧Exam #{old_id} 及 {cnt} 条成绩")

    # ========== 2. 创建新Exam ==========
    session.execute(
        text("INSERT INTO exams (name, exam_date, exam_type, grade_id) VALUES (:n, :d, :t, :g)"),
        {"n": EXAM_NAME, "d": EXAM_DATE, "t": "期中", "g": GRADE_ID}
    )
    session.commit()

    new_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    print(f"✅ 创建考试: id={new_id} name={EXAM_NAME}")

    # ========== 3. 预加载学生映射 ==========
    students = session.execute(
        text("SELECT id, name, class_id FROM students WHERE is_active=1")
    ).fetchall()
    stu_map = {}
    for sid, sname, cid in students:
        stu_map.setdefault(cid, {})[sname.strip()] = sid
    print(f"已加载 {len(students)} 名学生")

    # ========== 4. 导入CSV ==========
    matched = 0
    unmatched = []
    batch = []
    batch_size = 500

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            class_id = int(row["class_id"])
            student_name = row["student_name"].strip()

            stu_id = stu_map.get(class_id, {}).get(student_name)
            if stu_id is None:
                unmatched.append(f"班级{class_id} {student_name}")
                continue

            matched += 1
            for sub_id in SUBJECT_IDS:
                score_str = row.get(f"subject_{sub_id}", "").strip()
                if not score_str:
                    continue
                batch.append({
                    "student_id": stu_id,
                    "exam_id": new_id,
                    "subject_id": sub_id,
                    "class_id": class_id,
                    "grade_id": GRADE_ID,
                    "score": float(score_str),
                })

            if len(batch) >= batch_size:
                session.execute(
                    text("""INSERT INTO scores (student_id, exam_id, subject_id, class_id, grade_id, score)
                            VALUES (:student_id, :exam_id, :subject_id, :class_id, :grade_id, :score)"""),
                    batch,
                )
                batch = []
                if matched % 100 == 0:
                    print(f"  处理进度: {matched}...")

    # 提交剩余批次
    if batch:
        session.execute(
            text("""INSERT INTO scores (student_id, exam_id, subject_id, class_id, grade_id, score)
                    VALUES (:student_id, :exam_id, :subject_id, :class_id, :grade_id, :score)"""),
            batch,
        )
    session.commit()

    total = session.execute(
        text("SELECT COUNT(*) FROM scores WHERE exam_id = :eid"),
        {"eid": new_id}
    ).scalar()

    print(f"\n✅ 成绩已提交: {total} 条记录")
    print(f"  匹配学生: {matched}/{matched + len(unmatched)}")
    if unmatched:
        print(f"  未匹配 ({len(unmatched)}): {unmatched[:5]}")

    # ========== 5. 计算排名 ==========
    print("\n计算排名...")
    for sub_id in SUBJECT_IDS:
        for cid in range(1, 9):
            scores = session.execute(
                text("""SELECT id FROM scores
                        WHERE exam_id=:eid AND subject_id=:sid AND class_id=:cid
                        AND score IS NOT NULL
                        ORDER BY score DESC"""),
                {"eid": new_id, "sid": sub_id, "cid": cid}
            ).fetchall()
            for rank, (s_id,) in enumerate(scores, 1):
                session.execute(
                    text("UPDATE scores SET rank_class=:r WHERE id=:i"),
                    {"r": rank, "i": s_id}
                )

        all_scores = session.execute(
            text("""SELECT id FROM scores
                    WHERE exam_id=:eid AND subject_id=:sid AND score IS NOT NULL
                    ORDER BY score DESC"""),
            {"eid": new_id, "sid": sub_id}
        ).fetchall()
        for rank, (s_id,) in enumerate(all_scores, 1):
            session.execute(
                text("UPDATE scores SET rank_grade=:r WHERE id=:i"),
                {"r": rank, "i": s_id}
            )
    session.commit()
    print("✅ 排名计算完成")

    # ========== 6. 验证 ==========
    print(f"\n=== 验证 Exam #{new_id} ===")
    print(f"{'科目':<6} {'人数':<6} {'平均分':<8} {'最低':<6} {'最高':<6}")
    print("-" * 40)

    subject_names = {1: "语文", 2: "数学", 3: "英语", 4: "政治", 5: "历史", 6: "地理", 7: "生物"}
    report = {
        "语文": 71.57, "数学": 65.64, "英语": 45.29,
        "政治": 62.90, "历史": 56.91, "地理": 46.34, "生物": 48.94,
    }

    for sub_id in SUBJECT_IDS:
        row = session.execute(
            text("""SELECT COUNT(*), AVG(score), MIN(score), MAX(score)
                    FROM scores WHERE exam_id=:eid AND subject_id=:sid AND score IS NOT NULL"""),
            {"eid": new_id, "sid": sub_id}
        ).fetchone()
        cnt, avg, mn, mx = row
        name = subject_names[sub_id]
        expected = report[name]
        diff = avg - expected
        flag = "✅" if abs(diff) < 0.01 else f"⚠️ 差{diff:+.2f}"
        print(f"{name:<6} {cnt:<6} {avg:<8.2f} {int(mn):<6} {int(mx):<6} {flag}")

    print(f"\n总成绩记录: {total}")

except Exception as e:
    session.rollback()
    print(f"\n❌ 错误: {e}")
    raise
finally:
    session.close()

print("\n" + "=" * 60)
print("✅ 导入完成！")
print("=" * 60)
