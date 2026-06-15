#!/usr/bin/env python3
"""
补触发批量违纪记录的联动效果（升级检查 + 综合素质扣分 + 通知）

对 seed_discipline_batch.py 直接数据库写入的30条记录，
补执行 check_escalation、deduct_quality_score、send_discipline_notifications。

在服务器上运行，需要 Flask app context。
"""
import os
import sys

# ── 注入环境变量（与 systemd grade7-new.service 一致） ──
os.environ.setdefault("FLASK_ENV", "production")
os.environ.setdefault("SECRET_KEY", "2cf0e969e24c3e049b91f833b9a5571fe3e73dc004f874f1705752f18238c071")
os.environ.setdefault("JWT_SECRET_KEY", "9682e75d3d45e2e8ad04967d8689d0a882add1ad2c783edefd431fb54116ca05")
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new")
os.environ.setdefault("JWT_EXPIRATION_HOURS", "720")
os.environ.setdefault("LLM_API_KEY", "sk-7de6ea9e469a409f8f0691cee556211d")
os.environ.setdefault("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
os.environ.setdefault("LLM_MODEL", "deepseek-chat")

# ── 初始化 Flask app（触发 --preload 级别的完整初始化） ──
sys.path.insert(0, "/opt/grade7-new")
from app import create_app, db
from models import DisciplineRecord, Student, User, QualityIndicator, QualityScore, Message

app = create_app()

CREATED_BY = 2  # grade7_leader

with app.app_context():
    # 查找本次批量插入的30条记录
    # 识别方式：created_by=2 且 created_at >= 2026-04-01 且 verify_status='VERIFIED'
    records = DisciplineRecord.query.filter(
        DisciplineRecord.created_by == CREATED_BY,
        DisciplineRecord.verify_status == "VERIFIED",
        DisciplineRecord.created_at >= "2026-04-01 00:00:00",
    ).order_by(DisciplineRecord.created_at).all()

    print(f"[INFO] 找到 {len(records)} 条待补触发记录")
    print("=" * 60)

    # 按 student_id 分组，记录每个学生的累计扣分和已触发联动
    from collections import defaultdict
    student_records = defaultdict(list)
    for r in records:
        student_records[r.student_id].append(r)

    # ── 导入联动函数 ──
    from blueprints.discipline_utils import (
        check_escalation,
        deduct_quality_score,
        TYPE_MAP,
    )

    escalation_count = 0
    quality_count = 0
    error_count = 0

    for student_id, s_records in student_records.items():
        student = Student.query.get(student_id)
        if not student:
            print(f"[WARN] 学生 {student_id} 不存在，跳过")
            continue

        total_points = sum(r.points or 0 for r in s_records)
        print(f"\n[学生] {student.name}(id={student_id}, {student.class_.name}) | "
              f"本次 {len(s_records)} 条记录, 累计扣 {total_points} 分")

        for r in s_records:
            print(f"  #{r.id} | {r.created_at.strftime('%Y-%m-%d')} | "
                  f"{r.category} | {TYPE_MAP.get(r.type, r.type)} | "
                  f"{r.points}分 | {r.description[:30]}...")

        # 1) 检查升级
        try:
            check_escalation(student, CREATED_BY)
            print(f"  [OK] 升级检查完成")
        except Exception as e:
            print(f"  [ERR] 升级检查失败: {e}")
            error_count += 1

        # 2) 综合素质扣分（逐条）
        for r in s_records:
            try:
                deduct_quality_score(r, student, CREATED_BY)
                quality_count += 1
            except Exception as e:
                print(f"  [ERR] 扣分失败 #{r.id}: {e}")
                error_count += 1

    # 统一提交
    db.session.commit()
    print("\n" + "=" * 60)
    print(f"[DONE] 补触发完成")
    print(f"  综合素质扣分: {quality_count} 条")
    print(f"  错误: {error_count} 条")

    # 验证升级记录
    auto_escalations = DisciplineRecord.query.filter(
        DisciplineRecord.category == "系统自动",
        DisciplineRecord.created_by == CREATED_BY,
    ).all()
    if auto_escalations:
        print(f"\n[升级] 自动生成 {len(auto_escalations)} 条升级记录:")
        for ae in auto_escalations:
            s = Student.query.get(ae.student_id)
            print(f"  #{ae.id} | {s.name if s else '?'} | {ae.type} | {ae.description}")

    # 验证综合素质扣分记录
    quality_deductions = QualityScore.query.filter(
        QualityScore.scorer_type == "system",
        QualityScore.comment.like("[违纪自动扣减]%"),
    ).all()
    if quality_deductions:
        print(f"\n[素质扣分] 共 {len(quality_deductions)} 条:")
        for qd in quality_deductions:
            s = Student.query.get(qd.student_id)
            print(f"  学生: {s.name if s else '?'} | 分数: {qd.score} | {qd.comment[:50]}...")

    print(f"\n[INFO] 通知推送（SSE）需要服务运行时才能发送。")
    print(f"[INFO] 如需补发通知，请在德育处后台查看这些记录并手动操作。")
