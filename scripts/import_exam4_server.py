#!/usr/bin/env python3
"""
服务器侧：导入第4次考试成绩（纯 SQLAlchemy 版本，不依赖 Flask）
数据源: /opt/grade7-new/exam4_scores.csv
用法: source /opt/grade7-new/venv/bin/activate && python /opt/grade7-new/scripts/import_exam4_server.py
"""

import sys, os, csv
from datetime import date
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base, scoped_session
from sqlalchemy.sql import func

# ── 直接连接数据库 ──
DB_URI = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new?charset=utf8mb4"

engine = create_engine(
    DB_URI,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
)
SessionLocal = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()

# ── 模型定义（仅导入所需字段）──
class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    exam_date = Column(Date, default=date.today)
    exam_type = Column(String(20), default="月考")
    grade_id = Column(Integer, default=1)
    created_at = Column(DateTime)

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_no = Column(String(30), unique=True)
    name = Column(String(30), nullable=False)
    class_id = Column(Integer)
    grade_id = Column(Integer)
    is_active = Column(Integer, default=1)

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, index=True)
    exam_id = Column(Integer, index=True)
    subject_id = Column(Integer, index=True)
    class_id = Column(Integer)
    grade_id = Column(Integer)
    score = Column(Float, default=0.0)
    rank_class = Column(Integer, default=0)
    rank_grade = Column(Integer, default=0)

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String(30))
    sort_order = Column(Integer, default=0)


EXAM_NAME = "2026年七年级下学期期中考试"
EXAM_DATE = date(2026, 4, 28)
GRADE_ID = 1
CSV_PATH = "/opt/grade7-new/exam4_scores.csv"

# Excel列名 → Subject.id
SUBJECT_IDS = [1, 2, 3, 4, 5, 6, 7]  # 语文,数学,英语,政治,历史,地理,生物


def parse_score(val):
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "缺考", "未扫", "缺", "—", "-", "NaN", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    Session = SessionLocal
    session = Session()

    print("=" * 60)
    print("导入第4次考试成绩（纯 SQLAlchemy 直连）")
    print("=" * 60)

    try:
        # 1. 创建/清理考试
        print("\n[1/5] 检查考试记录...")
        exam = session.query(Exam).filter(Exam.name == EXAM_NAME).first()
        if exam:
            old_cnt = session.query(Score).filter(Score.exam_id == exam.id).count()
            session.query(Score).filter(Score.exam_id == exam.id).delete()
            session.delete(exam)
            session.commit()
            print("  🗑  已删除旧考试及 {} 条成绩".format(old_cnt))

        exam = Exam(
            name=EXAM_NAME,
            exam_date=EXAM_DATE,
            exam_type="期中",
            grade_id=GRADE_ID,
        )
        session.add(exam)
        session.commit()
        exam_id = exam.id
        print("  ✅ 创建考试: id={} name={}".format(exam_id, EXAM_NAME))

        # 2. 预加载学生映射 (name + class_id → student_id)
        print("\n[2/5] 加载学生映射...")
        students = session.query(Student).filter(Student.is_active == 1).all()
        stu_map = {}
        for s in students:
            key = (s.name, s.class_id)
            stu_map[key] = s.id
        print("  ✅ 加载 {} 名在校生".format(len(stu_map)))

        # 3. 读取CSV并导入
        print("\n[3/5] 读取CSV并导入成绩...")
        matched = 0
        unmatched = []
        inserted = 0

        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                class_id = int(row["class_id"])
                student_name = row["student_name"].strip()
                key = (student_name, class_id)

                student_id = stu_map.get(key)
                if not student_id:
                    unmatched.append("{}班 {}".format(row.get("class_name", class_id), student_name))
                    continue

                matched += 1

                for sub_id in SUBJECT_IDS:
                    score_str = row.get("subject_{}".format(sub_id), "").strip()
                    score_val = parse_score(score_str)
                    if score_val is None:
                        continue

                    # 查找是否已存在
                    old = session.query(Score).filter(
                        Score.student_id == student_id,
                        Score.exam_id == exam_id,
                        Score.subject_id == sub_id,
                    ).first()

                    if old:
                        old.score = score_val
                    else:
                        s = Score(
                            student_id=student_id,
                            exam_id=exam_id,
                            subject_id=sub_id,
                            class_id=class_id,
                            grade_id=GRADE_ID,
                            score=score_val,
                        )
                        session.add(s)

                    inserted += 1

                if matched % 50 == 0:
                    print("  处理进度: {}...".format(matched))
                    session.commit()  # 分批提交

        session.commit()
        print("  ✅ 成绩已提交: {} 条记录".format(inserted))
        print("  匹配学生: {}/{}".format(matched, matched + len(unmatched)))
        if unmatched:
            print("  ⚠ 未匹配 ({}): {}".format(len(unmatched), unmatched[:5]))

        # 4. 计算排名
        print("\n[4/5] 计算排名...")
        for sub_id in SUBJECT_IDS:
            # 班级排名
            for cid in range(1, 9):
                scores = session.query(Score).filter(
                    Score.exam_id == exam_id,
                    Score.subject_id == sub_id,
                    Score.class_id == cid,
                    Score.score.isnot(None),
                ).order_by(Score.score.desc()).all()
                for rank, s in enumerate(scores, 1):
                    s.rank_class = rank

            # 年级排名
            all_scores = session.query(Score).filter(
                Score.exam_id == exam_id,
                Score.subject_id == sub_id,
                Score.score.isnot(None),
            ).order_by(Score.score.desc()).all()
            for rank, s in enumerate(all_scores, 1):
                s.rank_grade = rank

            session.commit()
            print("  科目 {} 排名完成".format(sub_id))

        print("  ✅ 排名计算完成")

        # 5. 验证
        print("\n[5/5] 验证导入结果...")
        total = session.query(Score).filter(Score.exam_id == exam_id).count()
        print("  考试ID: {}, 总成绩记录数: {}".format(exam_id, total))

        for sub_id in SUBJECT_IDS:
            sub_name = session.query(Subject).filter(Subject.id == sub_id).first().name
            cnt = session.query(Score).filter(
                Score.exam_id == exam_id,
                Score.subject_id == sub_id,
            ).count()
            avg = session.query(func.avg(Score.score)).filter(
                Score.exam_id == exam_id,
                Score.subject_id == sub_id,
                Score.score.isnot(None),
            ).scalar() or 0
            print("    {}: {}条, 平均分={:.1f}".format(sub_name, cnt, avg))

        print("\n" + "=" * 60)
        print("✅ 导入完成！")
        print("=" * 60)

    finally:
        Session.remove()


if __name__ == "__main__":
    main()
