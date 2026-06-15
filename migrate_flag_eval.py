"""迁移脚本：为流动红旗评价机制添加 scorer_type 列 + 创建 flag_evaluations 表"""
import os, sys

# 必须先设置环境变量才能 import app 的 models
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("SECRET_KEY", "migrate-only")
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new")

from app import create_app
from models import db, RoutineScore, FlagEvaluation

app = create_app()

with app.app_context():
    # 1. 给 routine_scores 加 scorer_type 列
    try:
        db.session.execute(db.text(
            "ALTER TABLE routine_scores ADD COLUMN scorer_type VARCHAR(20) NOT NULL DEFAULT 'class_teacher' AFTER inspector"
        ))
        db.session.execute(db.text(
            "ALTER TABLE routine_scores ADD INDEX ix_routine_scores_scorer_type (scorer_type)"
        ))
        print("[OK] routine_scores.scorer_type 列已添加")
    except Exception as e:
        if "Duplicate column" in str(e):
            print("[SKIP] routine_scores.scorer_type 列已存在")
        else:
            print(f"[ERR] 添加 scorer_type 失败: {e}")
            sys.exit(1)

    # 2. 创建 flag_evaluations 表
    FlagEvaluation.__table__.create(db.engine, checkfirst=True)
    print("[OK] flag_evaluations 表已创建（如不存在）")

    # 3. 回填存量 RoutineScore 的 scorer_type
    try:
        result = db.session.execute(db.text(
            "UPDATE routine_scores SET scorer_type = 'class_teacher' WHERE scorer_type IS NULL OR scorer_type = ''"
        ))
        db.session.commit()
        print(f"[OK] 回填了 {result.rowcount} 条记录的 scorer_type")
    except Exception as e:
        db.session.rollback()
        print(f"[ERR] 回填失败: {e}")

    # 4. 添加 class_ relationship（如果还没有）
    try:
        db.session.execute(db.text(
            "ALTER TABLE routine_scores ADD INDEX ix_routine_scores_class_id (class_id)"
        ))
        print("[OK] routine_scores.class_id 索引已确认")
    except Exception:
        print("[SKIP] class_id 索引已存在")

    print("\n迁移完成！")
