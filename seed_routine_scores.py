#!/usr/bin/env python3
"""
批量生成常规评分数据（卫生/纪律/两操/礼仪/自习）
日期范围: 2026-03-05 ~ 2026-06-14（排除周六周日）
评分: 满分100，检查人=各班班主任display_name
在服务器执行: /opt/grade7-new/venv/bin/python /opt/grade7-new/seed_routine_scores.py
"""
import os, sys
from datetime import date, timedelta

os.environ.setdefault('DATABASE_URL', 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new')
sys.path.insert(0, '/opt/grade7-new')

from app import create_app
from models import db, RoutineScore, Class, User

app = create_app()

CATEGORIES = ['卫生', '纪律', '两操', '礼仪', '自习']
START = date(2026, 3, 5)
END = date(2026, 6, 14)

with app.app_context():
    # 1. 获取所有活跃班级及其班主任
    classes = Class.query.filter_by(is_active=True).all()
    if not classes:
        print("[ERROR] 未找到活跃班级")
        sys.exit(1)

    # 预加载班主任信息
    class_teacher_map = {}
    for cls in classes:
        teacher = None
        if cls.head_teacher_id:
            teacher = User.query.get(cls.head_teacher_id)
        if teacher:
            class_teacher_map[cls.id] = teacher.display_name or teacher.username
        else:
            class_teacher_map[cls.id] = "班主任"

    print(f"共 {len(classes)} 个班级")
    for cls in classes:
        t = class_teacher_map[cls.id]
        print(f"  班级ID={cls.id} | {cls.name} (grade_id={cls.grade_id}) | 检查人: {t}")
    print()

    # 2. 生成工作日日期列表
    workdays = []
    d = START
    while d <= END:
        if d.weekday() < 5:  # 0=周一 ... 4=周五
            workdays.append(d)
        d += timedelta(days=1)

    print(f"日期范围: {START} ~ {END}")
    print(f"工作日数量: {len(workdays)} 天")
    print(f"五项类别: {', '.join(CATEGORIES)}")
    print(f"预计生成: {len(workdays)} x {len(classes)} x {len(CATEGORIES)} = {len(workdays) * len(classes) * len(CATEGORIES)} 条记录")
    print()

    # 3. 检查已有数据，避免重复
    existing_count = RoutineScore.query.filter(
        RoutineScore.record_date >= START,
        RoutineScore.record_date <= END,
    ).count()

    if existing_count > 0:
        # 显示已有数据的概况
        existing_dates = db.session.query(
            RoutineScore.record_date
        ).filter(
            RoutineScore.record_date >= START,
            RoutineScore.record_date <= END,
        ).distinct().order_by(RoutineScore.record_date).all()
        print(f"[WARN] 已有 {existing_count} 条记录在 {len(existing_dates)} 个日期中")
        print(f"已有数据日期: ", end="")
        for (d,) in existing_dates[:10]:
            print(f"{d.strftime('%m-%d')} ", end="")
        if len(existing_dates) > 10:
            print(f"... 共{len(existing_dates)}天")
        else:
            print()

        print()
        choice = input("输入 y 清空已有数据后重新生成，输入 n 仅补填缺失日期: ").strip().lower()
        if choice == 'y':
            deleted = RoutineScore.query.filter(
                RoutineScore.record_date >= START,
                RoutineScore.record_date <= END,
            ).delete()
            db.session.commit()
            print(f"已清空 {deleted} 条旧记录")
        # else: 跳过已有日期

    # 4. 批量生成
    print("\n开始生成数据...")

    batch_size = 500
    total_inserted = 0
    batch = []

    for wd in workdays:
        # 检查该日期是否已有数据（补填模式）
        day_existing = RoutineScore.query.filter_by(record_date=wd).count()
        if day_existing > 0:
            print(f"  [SKIP] {wd.strftime('%Y-%m-%d')} ({['周一','周二','周三','周四','周五','周六','周日'][wd.weekday()]}) — 已有{day_existing}条")
            continue

        for cls in classes:
            inspector = class_teacher_map[cls.id]
            for cat in CATEGORIES:
                batch.append(RoutineScore(
                    class_id=cls.id,
                    grade_id=cls.grade_id,
                    category=cat,
                    score=100,
                    note=f"{cat}日常检查",
                    inspector=inspector,
                    record_date=wd,
                ))

        # 批量提交
        if len(batch) >= batch_size:
            db.session.add_all(batch)
            db.session.commit()
            total_inserted += len(batch)
            print(f"  [OK] {wd.strftime('%Y-%m-%d')} — 已插入 {total_inserted} 条")
            batch = []

    # 提交剩余
    if batch:
        db.session.add_all(batch)
        db.session.commit()
        total_inserted += len(batch)
        print(f"  [OK] 最后一批 — 已插入 {total_inserted} 条")

    print(f"\n完成！共生成 {total_inserted} 条常规评分记录")

    # 5. 验证统计
    print("\n" + "=" * 60)
    print("数据验证:")
    print("=" * 60)
    from sqlalchemy import func
    stats = db.session.query(
        RoutineScore.record_date,
        func.count(RoutineScore.id),
        func.min(RoutineScore.score),
        func.max(RoutineScore.score),
    ).filter(
        RoutineScore.record_date >= START,
        RoutineScore.record_date <= END,
    ).group_by(RoutineScore.record_date).order_by(RoutineScore.record_date).all()

    print(f"{'日期':<14} {'记录数':>8} {'最低分':>8} {'最高分':>8}")
    print("-" * 42)
    for d, cnt, mn, mx in stats:
        print(f"{d.strftime('%Y-%m-%d')} {cnt:>8} {mn:>8} {mx:>8}")
    print(f"\n共 {len(stats)} 天有数据")
