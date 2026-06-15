"""迁移脚本：为流动红旗评价机制添加 scorer_type 列 + 创建 flag_evaluations 表
直接使用 SQLAlchemy 引擎，不触发 create_app() 的配置校验"""
import os, sys

DB_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"
)

from sqlalchemy import create_engine, text, inspect

engine = create_engine(DB_URL, pool_pre_ping=True)

with engine.connect() as conn:
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("routine_scores")]
    tbls = insp.get_table_names()

    # 1. 给 routine_scores 加 scorer_type 列
    if "scorer_type" in cols:
        print("[SKIP] routine_scores.scorer_type 已存在")
    else:
        conn.execute(text(
            "ALTER TABLE routine_scores ADD COLUMN scorer_type VARCHAR(20) NOT NULL DEFAULT 'class_teacher' AFTER inspector"
        ))
        conn.execute(text(
            "ALTER TABLE routine_scores ADD INDEX ix_routine_scores_scorer_type (scorer_type)"
        ))
        conn.commit()
        print("[OK] routine_scores.scorer_type 列已添加")

    # 2. 创建 flag_evaluations 表
    if "flag_evaluations" in tbls:
        print("[SKIP] flag_evaluations 表已存在")
    else:
        conn.execute(text("""
            CREATE TABLE flag_evaluations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                period_type VARCHAR(10) NOT NULL,
                period_label VARCHAR(60) NOT NULL,
                grade_id INT NOT NULL,
                class_id INT NOT NULL,
                self_score FLOAT NULL,
                grade_score FLOAT NULL,
                ms_score FLOAT NULL,
                self_weight FLOAT NOT NULL DEFAULT 0.2,
                grade_weight FLOAT NOT NULL DEFAULT 0.3,
                ms_weight FLOAT NOT NULL DEFAULT 0.5,
                final_score FLOAT NOT NULL,
                rank INT NULL,
                status VARCHAR(10) NOT NULL DEFAULT 'draft',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                published_at DATETIME NULL,
                INDEX ix_flag_evaluations_period_type (period_type),
                INDEX ix_flag_evaluations_grade_id (grade_id),
                INDEX ix_flag_evaluations_class_id (class_id),
                INDEX ix_flag_evaluations_status (status),
                UNIQUE KEY uq_flag_eval_period_grade_class (period_type, period_label, grade_id, class_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.commit()
        print("[OK] flag_evaluations 表已创建")

    # 3. 回填存量 RoutineScore 的 scorer_type
    result = conn.execute(text(
        "UPDATE routine_scores SET scorer_type = 'class_teacher' WHERE scorer_type IS NULL OR scorer_type = ''"
    ))
    conn.commit()
    print(f"[OK] 回填了 {result.rowcount} 条记录的 scorer_type")

    # 4. class_id 索引（如果缺失）
    indexes = [idx["name"] for idx in insp.get_indexes("routine_scores")]
    if "ix_routine_scores_class_id" not in indexes:
        conn.execute(text(
            "ALTER TABLE routine_scores ADD INDEX ix_routine_scores_class_id (class_id)"
        ))
        conn.commit()
        print("[OK] routine_scores.class_id 索引已添加")
    else:
        print("[SKIP] class_id 索引已存在")

print("\n迁移完成！")
