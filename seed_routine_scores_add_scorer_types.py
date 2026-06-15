#!/usr/bin/env python3
"""
补充常规评分数据 — 为已生成的 class_teacher 数据补充 grade_leader 和 ms_admin 评分

执行方式: /opt/grade7-new/venv/bin/python /opt/grade7-new/seed_routine_scores_add_scorer_types.py

逻辑:
  - class_teacher 数据已存在（约 5万条），本次只补充缺失的两种评分人
  - grade_leader: 比班主任自评严格 2-4 分（年级组会更客观）
  - ms_admin:    比年级组再严格 1-3 分（德育处检查最严格）
  - 同一天同一班级同一类别，三种评分人各有一条记录
"""
import os, sys, random
from datetime import date, datetime, timedelta

os.environ.setdefault('DATABASE_URL', 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new')
os.environ.setdefault('SECRET_KEY', 'seed-script-secret-key-must-be-32chars-ok!')
os.environ.setdefault('JWT_SECRET_KEY', 'seed-script-jwt-secret-key-32chars-ok!')
sys.path.insert(0, '/opt/grade7-new')

from app import create_app
from models import db, RoutineScore, Class

app = create_app()

CATEGORIES = ['卫生', '纪律', '两操', '礼仪', '自习']
SCORER_TYPES = ['grade_leader', 'ms_admin']

with app.app_context():
    # 1. 获取所有已有 class_teacher 数据的日期和班级
    existing = RoutineScore.query.filter_by(scorer_type='class_teacher').all()
    if not existing:
        print("[ERROR] 未找到 class_teacher 数据，请先运行 seed_routine_scores.py")
        sys.exit(1)

    # 收集所有 (class_id, grade_id, record_date, category) 组合
    keys = {}
    for r in existing:
        keys[(r.class_id, r.grade_id, r.record_date, r.category)] = r.score

    print(f"已有 class_teacher 记录: {len(existing)} 条")
    print(f"涉及唯一键值对: {len(keys)} 个")

    # 2. 为每种评分人类型生成数据
    total_inserted = 0
    batch = []
    batch_size = 500

    for (class_id, grade_id, record_date, category), class_score in keys.items():
        for scorer_type in SCORER_TYPES:
            # 检查是否已存在
            exists = RoutineScore.query.filter_by(
                class_id=class_id,
                category=category,
                scorer_type=scorer_type,
                record_date=record_date
            ).first()
            if exists:
                continue

            # 根据评分人类型调整分数
            if scorer_type == 'grade_leader':
                # 年级组: 比班主任严格 2-4 分
                offset = random.randint(-4, -2)
            else:
                # ms_admin: 比年级组再严格 1-3 分
                offset = random.randint(-6, -3)

            score = max(70, min(100, class_score + offset))

            # created_at 设在当天 9:00~10:00（模拟稍晚的评分）
            minute_offset = random.randint(0, 60)
            created_at = datetime.combine(record_date, datetime.min.time().replace(hour=9, minute=minute_offset))

            batch.append(RoutineScore(
                class_id=class_id,
                grade_id=grade_id,
                category=category,
                score=score,
                note=f"{scorer_type}评分",
                inspector=scorer_type,
                scorer_type=scorer_type,
                record_date=record_date,
                created_at=created_at,
            ))

            if len(batch) >= batch_size:
                db.session.add_all(batch)
                db.session.commit()
                total_inserted += len(batch)
                print(f"  已插入 {total_inserted} 条 {scorer_type} 数据...")
                batch = []

    # 提交剩余
    if batch:
        db.session.add_all(batch)
        db.session.commit()
        total_inserted += len(batch)

    print(f"\n完成！共补充 {total_inserted} 条评分记录")
    print(f"  - grade_leader: {RoutineScore.query.filter_by(scorer_type='grade_leader').count()} 条")
    print(f"  - ms_admin:     {RoutineScore.query.filter_by(scorer_type='ms_admin').count()} 条")

    # 验证：抽查某天某班的三维度数据
    print("\n" + "=" * 60)
    print("抽样验证（2026-03-05，2501班）:")
    print("=" * 60)
    sample = RoutineScore.query.filter(
        RoutineScore.class_id == 1,  # 假设2501班是class_id=1
        RoutineScore.record_date == date(2026, 3, 5)
    ).all()
    for r in sample:
        print(f"  {r.scorer_type:15s} | {r.category:4s} | 分数: {r.score}")
