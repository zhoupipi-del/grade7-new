"""
迁移脚本：为 flag_evaluations 表添加违纪+考勤扣分字段
"""
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("开始迁移 flag_evaluations 表...")

    # 检查字段是否已存在
    result = db.session.execute(text("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'flag_evaluations'
          AND COLUMN_NAME IN ('base_score', 'discipline_points', 'discipline_deduction',
                            'attendance_exceptions', 'attendance_deduction')
    """))

    existing_cols = [row[0] for row in result.fetchall()]
    print(f"  已存在字段: {existing_cols}")

    # 添加新字段
    migrations = [
        ("base_score", "ADD COLUMN base_score FLOAT NULL AFTER ms_weight"),
        ("discipline_points", "ADD COLUMN discipline_points FLOAT NULL AFTER base_score"),
        ("discipline_deduction", "ADD COLUMN discipline_deduction FLOAT NULL AFTER discipline_points"),
        ("attendance_exceptions", "ADD COLUMN attendance_exceptions INT NULL AFTER discipline_deduction"),
        ("attendance_deduction", "ADD COLUMN attendance_deduction FLOAT NULL AFTER attendance_exceptions"),
    ]

    for col_name, sql in migrations:
        if col_name in existing_cols:
            print(f"  ⏭ {col_name} 已存在，跳过")
            continue
        try:
            db.session.execute(text(f"ALTER TABLE flag_evaluations {sql}"))
            db.session.commit()
            print(f"  ✓ 已添加字段: {col_name}")
        except Exception as e:
            print(f"  ✗ 添加字段失败 {col_name}: {e}")
            db.session.rollback()

    print("\n迁移完成！")
