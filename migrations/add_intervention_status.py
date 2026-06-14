"""Migration: 给 intervention_records 表加 status 列 (Phase 5.3 方案A 后验追踪补丁)"""
import sys
sys.path.insert(0, "/opt/grade7-new")

from sqlalchemy import create_engine, text, inspect

DB_URI = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"
engine = create_engine(DB_URI)

with engine.connect() as conn:
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("intervention_records")}
    print(f"现有列: {cols}")

    if "status" not in cols:
        conn.execute(text(
            "ALTER TABLE intervention_records ADD COLUMN status VARCHAR(20) "
            "NOT NULL DEFAULT 'tracking'"
        ))
        conn.commit()
        print("✅ status 列已添加 (default='tracking')")

        # 已有 follow_up_done=1 的记录标为 completed
        conn.execute(text(
            "UPDATE intervention_records SET status='completed' WHERE follow_up_done=1"
        ))
        conn.commit()
        print("✅ 已完成的随访记录已标为 completed")
    else:
        print("⏭️  status 列已存在，跳过")

    # 验证
    result = conn.execute(text("SELECT id, status, follow_up_done FROM intervention_records"))
    for row in result:
        print(f"  id={row[0]} status={row[1]} follow_up_done={row[2]}")

    print("✅ 迁移完成")
