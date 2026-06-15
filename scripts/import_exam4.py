#!/usr/bin/env python3
"""
导入第4次考试成绩（2026年七年级下学期期中考试）
数据源: 桌面【七年级期中】全部考生成绩汇总.xls
用法: python import_exam4.py
"""

import sys
import os
import pandas as pd
from datetime import date

# 添加项目路径
sys.path.insert(0, r"C:\Users\Administrator\WorkBuddy\2026-05-26-20-55-49\grade7-new")

from app import create_app
from models import db, Student, Exam, Score, Subject, Class

EXCEL_PATH = r"C:\Users\Administrator\Desktop\【七年级期中】全部考生成绩汇总.xls"

# Excel列名 → Subject.id 映射
SUBJECT_MAP = {
    "语文": 1,
    "数学": 2,
    "英语": 3,
    "生物": 7,   # 注意：生物在Excel里排在政治前面
    "政治": 4,
    "历史": 5,
    "地理": 6,
}

# 班级名 → class.id 映射
CLASS_MAP = {
    "2501班": 1,
    "2502班": 2,
    "2503班": 3,
    "2504班": 4,
    "2505班": 5,
    "2506班": 6,
    "2507班": 7,
    "2508班": 8,
}


def parse_score(val):
    """将Excel中的分数转为float，缺考/未扫/空 → None"""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "缺考", "未扫", "缺", "—", "-", "NaN", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        print(f"  ⚠ 无法解析分数: '{val}'，视为缺考")
        return None


def main():
    app = create_app()

    print("=" * 60)
    print("导入第4次考试成绩（2026年七年级下学期期中考试）")
    print("=" * 60)

    with app.app_context():
        # 1. 读取Excel
        print(f"\n[1/6] 读取Excel: {EXCEL_PATH}")
        df = pd.read_excel(EXCEL_PATH)
        print(f"  读取到 {len(df)} 行，列: {list(df.columns)[:12]}")

        # 2. 创建/获取Exam记录
        print("\n[2/6] 创建考试记录...")
        existing = Exam.query.filter_by(name="2026年七年级下学期期中考试").first()
        if existing:
            print(f"  ⚠ 考试已存在: id={existing.id} name={existing.name}")
            resp = input("  是否删除旧数据并重新导入？(y/N): ")
            if resp.strip().lower() == "y":
                # 删除旧成绩
                old_count = Score.query.filter_by(exam_id=existing.id).count()
                Score.query.filter_by(exam_id=existing.id).delete()
                db.session.delete(existing)
                db.session.commit()
                print(f"  ✅ 已删除旧考试及 {old_count} 条成绩")
                existing = None
            else:
                print("  ℹ 取消导入")
                return

        if not existing:
            exam = Exam(
                name="2026年七年级下学期期中考试",
                exam_date=date(2026, 4, 28),
                exam_type="期中",
                grade_id=1,
            )
            db.session.add(exam)
            db.session.commit()
            print(f"  ✅ 创建考试记录: id={exam.id} name={exam.name}")
        else:
            exam = existing

        exam_id = exam.id

        # 3. 匹配学生并导入成绩
        print(f"\n[3/6] 匹配学生并导入成绩...")
        results = {"matched": 0, "unmatched": [], "inserted": 0, "errors": []}

        for idx, row in df.iterrows():
            class_name = str(row["班级"]).strip()
            student_name = str(row["姓名"]).strip()

            class_id = CLASS_MAP.get(class_name)
            if not class_id:
                results["errors"].append(f"行{idx+2}: 未知班级 {class_name}")
                continue

            # 按姓名+班级查找学生
            student = Student.query.filter_by(
                name=student_name,
                class_id=class_id,
                is_active=True,
            ).first()

            if not student:
                results["unmatched"].append(f"{class_name} {student_name}")
                continue

            results["matched"] += 1

            # 逐科插入/更新成绩
            for col_name, subject_id in SUBJECT_MAP.items():
                score_val = parse_score(row[col_name])
                if score_val is None:
                    continue  # 缺考，跳过

                # 查找是否已存在
                existing_score = Score.query.filter_by(
                    student_id=student.id,
                    exam_id=exam_id,
                    subject_id=subject_id,
                ).first()

                if existing_score:
                    if existing_score.score != score_val:
                        existing_score.score = score_val
                        results["inserted"] += 1
                else:
                    s = Score(
                        student_id=student.id,
                        exam_id=exam_id,
                        subject_id=subject_id,
                        class_id=class_id,
                        grade_id=1,
                        score=score_val,
                    )
                    db.session.add(s)
                    results["inserted"] += 1

            if (idx + 1) % 50 == 0:
                print(f"  处理进度: {idx+1}/{len(df)}")

        db.session.commit()
        print(f"  ✅ 数据库提交完成，共处理 {results['inserted']} 条成绩记录")

        # 4. 计算排名
        print(f"\n[4/6] 计算班级排名和年级排名...")
        from sqlalchemy import func

        # 获取该考试所有科目
        subjects_in_exam = db.session.query(
            Score.subject_id
        ).filter_by(exam_id=exam_id).distinct().all()
        subjects_in_exam = [s[0] for s in subjects_in_exam]
        print(f"  考试科目IDs: {subjects_in_exam}")

        for subject_id in subjects_in_exam:
            # 班级排名
            for class_id in range(1, 9):
                scores_list = Score.query.filter(
                    Score.exam_id == exam_id,
                    Score.subject_id == subject_id,
                    Score.class_id == class_id,
                    Score.score.isnot(None),
                ).order_by(Score.score.desc()).all()

                for rank, s in enumerate(scores_list, 1):
                    s.rank_class = rank

            # 年级排名
            all_scores = Score.query.filter(
                Score.exam_id == exam_id,
                Score.subject_id == subject_id,
                Score.score.isnot(None),
            ).order_by(Score.score.desc()).all()

            for rank, s in enumerate(all_scores, 1):
                s.rank_grade = rank

        db.session.commit()
        print(f"  ✅ 排名计算完成")

        # 5. 汇总报告
        print(f"\n[5/6] 导入汇总:")
        print(f"  匹配学生: {results['matched']}/{len(df)}")
        print(f"  插入/更新成绩: {results['inserted']}")
        if results["unmatched"]:
            print(f"  ⚠ 未匹配学生 ({len(results['unmatched'])}):")
            for name in results["unmatched"][:10]:
                print(f"    - {name}")
            if len(results["unmatched"]) > 10:
                print(f"    ... 还有 {len(results['unmatched'])-10} 条")

        # 6. 验证
        print(f"\n[6/6] 验证导入结果...")
        total = Score.query.filter_by(exam_id=exam_id).count()
        by_subject = db.session.query(
            Subject.name, func.count(Score.id), func.avg(Score.score)
        ).join(Subject, Score.subject_id == Subject.id).filter(
            Score.exam_id == exam_id
        ).group_by(Score.subject_id).all()

        print(f"  考试ID: {exam_id}")
        print(f"  总成绩记录数: {total}")
        print(f"  各科统计:")
        for sub_name, cnt, avg in by_subject:
            print(f"    {sub_name}: {cnt}条, 平均分={avg:.1f}")

    print(f"\n{'='*60}")
    print("✅ 导入完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
