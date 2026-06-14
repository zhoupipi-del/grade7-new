"""
迁移脚本 — 创建 intervention_records 表
直接配置数据库，绕过 create_app() 的环境变量依赖。
运行: cd /opt/grade7-new && python migrations/add_intervention_record.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from flask import Flask
from models import db, InterventionRecord

# ── 直接配置数据库（与 systemd service 中 DATABASE_URL 一致）──
DB_URI = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DB_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    print("[迁移] 开始创建 intervention_records 表...")
    db.create_all()  # 只创建缺失的表，安全幂等

    # 验证
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if "intervention_records" in tables:
        print("[迁移] ✅ intervention_records 表已创建")
    else:
        print("[迁移] ❌ 创建失败")
        sys.exit(1)

    columns = inspector.get_columns("intervention_records")
    print(f"[迁移] 字段数: {len(columns)}")
    for col in columns:
        print(f"    {col['name']:30s} {str(col['type']):25s}")

    # 字段完整性自检
    expected = {"id", "student_id", "teacher_id", "risk_before", "risk_after",
                "intervention_type", "notes", "effect_rating",
                "intervention_date", "follow_up_date", "follow_up_done",
                "follow_up_notes", "created_at", "updated_at"}
    actual = {c["name"] for c in columns}
    missing = expected - actual
    if missing:
        print(f"[迁移] ⚠️  缺失字段: {missing}")
    else:
        print("[迁移] ✅ 字段完整性检查通过")

    print("[迁移] 完成。")
