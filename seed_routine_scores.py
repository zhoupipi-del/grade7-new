#!/usr/bin/env python3
"""
批量生成常规评分数据（卫生/纪律/两操/礼仪/自习）
日期范围: 2026-03-05 ~ 2026-06-14（排除周六周日）

评分逻辑 — 模拟班主任真实自评：
  - 每班每项有一个"基准线"(92~98)，代表该班该项目的日常水平
  - 每天在基准线上下波动(±3~5分)，班主任自评总体偏高
  - 约 70% 天在 92-100，约 20% 天在 85-91，约 10% 天在 78-84
  - 周一(假期后)和周五(放假前)波动稍大
  - created_at 回写到对应 record_date 当天 8:00~8:30，保证趋势图正确

在服务器执行: /opt/grade7-new/venv/bin/python /opt/grade7-new/seed_routine_scores.py
"""
import os, sys, random, hashlib
from datetime import date, datetime, timedelta

os.environ.setdefault('DATABASE_URL', 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new')
os.environ.setdefault('SECRET_KEY', 'seed-script-secret-key-must-be-32chars-ok!')
os.environ.setdefault('JWT_SECRET_KEY', 'seed-script-jwt-secret-key-32chars-ok!')
sys.path.insert(0, '/opt/grade7-new')

from app import create_app
from models import db, RoutineScore, Class, User

app = create_app()

CATEGORIES = ['卫生', '纪律', '两操', '礼仪', '自习']
START = date(2026, 3, 5)
END = date(2026, 6, 14)

# ── 随机种子：基于班级ID，保证同一班级每次生成数据一致 ──

def class_seed(class_id):
    """用 class_id 派生稳定种子，同一班级重跑结果一致"""
    h = hashlib.md5(f"routine-{class_id}".encode()).hexdigest()
    return int(h[:8], 16)


def generate_score(rng, base, day_idx):
    """
    生成一个自然分数。
    base: 该班该项基准线 (92~98)
    day_idx: 该日期在工作日列表中的序号(0-based)，用于制造周几效应
    """
    weekday_effect = 0
    # 周一(idx%5==0)和周五(idx%5==4)波动稍大
    if day_idx % 5 == 0:
        weekday_effect = -1  # 假期后第一天，偶尔松懈
    elif day_idx % 5 == 4:
        weekday_effect = -1  # 放假前夕，心散

    roll = rng.random()
    if roll < 0.70:
        # 70% 概率：基准线附近 ±3
        delta = rng.randint(-3, 3) + weekday_effect
    elif roll < 0.90:
        # 20% 概率：明显偏差 ±5~8
        delta = rng.randint(-8, -4) + weekday_effect
    else:
        # 10% 概率：偶尔较差 ±10~18
        delta = rng.randint(-18, -10) + weekday_effect

    score = base + delta
    # 班主任自评下限不低于75，上限不超过100
    return max(75, min(100, score))


def generate_note(rng, cat, score):
    """根据分数生成不同的备注文案"""
    if score >= 96:
        notes = [f"{cat}良好", f"{cat}表现优秀", f"{cat}检查正常", f"{cat}整体较好"]
    elif score >= 90:
        notes = [f"{cat}基本达标", f"{cat}有小问题已提醒", f"{cat}正常检查", f"{cat}整体合格"]
    elif score >= 85:
        notes = [f"{cat}个别地方需改进", f"{cat}扣分已通知整改", f"{cat}部分区域不达标", f"{cat}提醒后改善"]
    else:
        notes = [f"{cat}问题较多已通报", f"{cat}需重点整改", f"{cat}表现不佳已约谈", f"{cat}限期整改"]
    return rng.choice(notes)


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

    # 4. 为每个班级生成基准线配置（稳定种子保证可复现）
    class_baselines = {}
    for cls in classes:
        rng = random.Random(class_seed(cls.id))
        # 每个类别一个基准线，代表该班该项目的"日常水平"
        baselines = {}
        for cat in CATEGORIES:
            baselines[cat] = rng.randint(92, 98)
        class_baselines[cls.id] = baselines
        base_str = ", ".join(f"{cat}:{v}" for cat, v in baselines.items())
        print(f"  班级 {cls.name} 基准线: {base_str}")

    print(f"\n开始生成数据...\n")

    # 5. 批量生成
    batch_size = 500
    total_inserted = 0
    batch = []

    for day_idx, wd in enumerate(workdays):
        # 检查该日期是否已有数据（补填模式）
        day_existing = RoutineScore.query.filter_by(record_date=wd).count()
        if day_existing > 0:
            weekday_name = ['周一','周二','周三','周四','周五','周六','周日'][wd.weekday()]
            print(f"  [SKIP] {wd.strftime('%Y-%m-%d')} ({weekday_name}) — 已有{day_existing}条")
            continue

        for cls in classes:
            # 每个班级用稳定种子，保证每天的数据模式一致
            rng = random.Random(class_seed(cls.id) + day_idx * 137)
            inspector = class_teacher_map[cls.id]
            baselines = class_baselines[cls.id]

            for cat in CATEGORIES:
                score = generate_score(rng, baselines[cat], day_idx)
                note = generate_note(rng, cat, score)

                # created_at 回写到对应 record_date 当天 8:00~8:30
                minute_offset = rng.randint(0, 30)
                created_at = datetime.combine(wd, datetime.min.time().replace(hour=8, minute=minute_offset))

                batch.append(RoutineScore(
                    class_id=cls.id,
                    grade_id=cls.grade_id,
                    category=cat,
                    score=score,
                    note=note,
                    inspector=inspector,
                    record_date=wd,
                    created_at=created_at,
                ))

        # 批量提交
        if len(batch) >= batch_size:
            db.session.add_all(batch)
            db.session.commit()
            total_inserted += len(batch)
            weekday_name = ['周一','周二','周三','周四','周五','周六','周日'][wd.weekday()]
            print(f"  [OK] {wd.strftime('%Y-%m-%d')} ({weekday_name}) — 已插入 {total_inserted} 条")
            batch = []

    # 提交剩余
    if batch:
        db.session.add_all(batch)
        db.session.commit()
        total_inserted += len(batch)
        print(f"  [OK] 最后一批 — 已插入 {total_inserted} 条")

    print(f"\n完成！共生成 {total_inserted} 条常规评分记录")

    # 6. 验证统计
    print("\n" + "=" * 60)
    print("数据验证:")
    print("=" * 60)
    from sqlalchemy import func
    stats = db.session.query(
        RoutineScore.record_date,
        func.count(RoutineScore.id),
        func.min(RoutineScore.score),
        func.max(RoutineScore.score),
        func.avg(RoutineScore.score),
    ).filter(
        RoutineScore.record_date >= START,
        RoutineScore.record_date <= END,
    ).group_by(RoutineScore.record_date).order_by(RoutineScore.record_date).all()

    print(f"{'日期':<14} {'记录数':>8} {'最低分':>8} {'最高分':>8} {'均分':>8}")
    print("-" * 50)
    for d, cnt, mn, mx, avg in stats:
        print(f"{d.strftime('%Y-%m-%d')} {cnt:>8} {mn:>8} {mx:>8} {float(avg):>8.1f}")
    print(f"\n共 {len(stats)} 天有数据")

    # 分数分布
    print("\n" + "-" * 50)
    print("分数分布:")
    score_dist = db.session.query(
        func.count(RoutineScore.id),
        func.avg(RoutineScore.score),
    ).filter(
        RoutineScore.record_date >= START,
        RoutineScore.record_date <= END,
    ).first()
    print(f"  总记录数: {score_dist[0]}")
    print(f"  全局均分: {float(score_dist[1]):.1f}")

    for label, lo, hi in [("100分(满分)", 100, 100), ("95-99分", 95, 99), ("90-94分", 90, 94), ("85-89分", 85, 89), ("80-84分", 80, 84), ("75-79分", 75, 79)]:
        cnt = RoutineScore.query.filter(
            RoutineScore.record_date >= START,
            RoutineScore.record_date <= END,
            RoutineScore.score >= lo,
            RoutineScore.score <= hi,
        ).count()
        print(f"  {label}: {cnt}")
