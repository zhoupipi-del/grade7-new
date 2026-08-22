#!/usr/bin/env python3
"""Grades Module: DDL + ETL Migration Script
Creates 4 new tables (grades_subjects/exams/records/audit_logs) and migrates data from old tables.
"""
import sys
sys.path.insert(0, "/root/backend")

from sqlalchemy import create_engine, text

DB_URL = (os.getenv("DATABASE_URL") or "").replace("aiomysql", "pymysql")
engine = create_engine(DB_URL, echo=False)

DDL_STATEMENTS = [
    # 1. grades_subjects
    """
    CREATE TABLE IF NOT EXISTS grades_subjects (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        school_id BIGINT NOT NULL DEFAULT 1,
        name VARCHAR(50) NOT NULL,
        code VARCHAR(30) NOT NULL,
        full_score DECIMAL(6,2) DEFAULT 100.00,
        sort_order INT DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_grades_subject_code (school_id, code),
        INDEX idx_gsubject_school (school_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # 2. grades_exams
    """
    CREATE TABLE IF NOT EXISTS grades_exams (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        school_id BIGINT NOT NULL DEFAULT 1,
        name VARCHAR(200) NOT NULL,
        exam_type VARCHAR(20) DEFAULT 'midterm',
        grade_id BIGINT NOT NULL,
        semester VARCHAR(20) DEFAULT '2025-1',
        exam_date DATETIME NULL,
        status VARCHAR(20) DEFAULT 'draft',
        created_by BIGINT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_gexam_school_grade (school_id, grade_id),
        INDEX idx_gexam_semester (semester),
        INDEX idx_gexam_status (status),
        INDEX idx_gexam_grade (grade_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # 3. grades_records
    """
    CREATE TABLE IF NOT EXISTS grades_records (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        school_id BIGINT NOT NULL DEFAULT 1,
        exam_id BIGINT NOT NULL,
        student_id BIGINT NOT NULL,
        subject_id BIGINT NOT NULL,
        score DECIMAL(6,2) NULL,
        class_rank INT NULL,
        grade_rank INT NULL,
        is_absent BOOLEAN DEFAULT FALSE,
        remark VARCHAR(200) NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_grades_record (school_id, exam_id, student_id, subject_id),
        INDEX idx_grecord_exam_student (exam_id, student_id),
        INDEX idx_grecord_student (student_id),
        INDEX idx_grecord_subject (subject_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # 4. grades_audit_logs
    """
    CREATE TABLE IF NOT EXISTS grades_audit_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        school_id BIGINT NOT NULL DEFAULT 1,
        exam_id BIGINT NOT NULL,
        student_id BIGINT NOT NULL,
        subject_id BIGINT NOT NULL,
        old_score DECIMAL(6,2) NULL,
        new_score DECIMAL(6,2) NULL,
        action VARCHAR(20) DEFAULT 'upsert',
        operator_id BIGINT NULL,
        operator_name VARCHAR(50) NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_gaudit_exam (exam_id),
        INDEX idx_gaudit_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

ETL_SUBJECTS = """
    INSERT INTO grades_subjects (id, school_id, name, code, full_score, sort_order, is_active, created_at)
    SELECT
        id, 1, name,
        CASE name
            WHEN '语文' THEN 'chinese'
            WHEN '数学' THEN 'math'
            WHEN '英语' THEN 'english'
            WHEN '政治' THEN 'politics'
            WHEN '历史' THEN 'history'
            WHEN '地理' THEN 'geography'
            WHEN '生物' THEN 'biology'
            WHEN '物理' THEN 'physics'
            WHEN '化学' THEN 'chemistry'
            ELSE CONCAT('subj_', id)
        END as code,
        COALESCE(full_score, 100),
        COALESCE(sort_order, 0),
        TRUE,
        NOW()
    FROM subjects
    ON DUPLICATE KEY UPDATE name=VALUES(name)
"""

ETL_EXAMS = """
    INSERT INTO grades_exams (id, school_id, name, exam_type, grade_id, semester, exam_date, status, created_by, created_at, updated_at)
    SELECT
        id, 1, name,
        CASE exam_type
            WHEN '月考' THEN 'monthly'
            WHEN '期中' THEN 'midterm'
            WHEN '期末' THEN 'final'
            WHEN 'quiz' THEN 'quiz'
            ELSE 'midterm'
        END as exam_type,
        grade_id,
        '2025-1',
        CAST(exam_date AS DATETIME),
        'published',
        NULL, created_at, NOW()
    FROM exams
    ON DUPLICATE KEY UPDATE name=VALUES(name)
"""

ETL_SCORES = """
    INSERT INTO grades_records (school_id, exam_id, student_id, subject_id, score, class_rank, grade_rank, is_absent, remark, created_at, updated_at)
    SELECT
        1,
        exam_id,
        student_id,
        subject_id,
        score,
        rank_class,
        rank_grade,
        CASE WHEN score IS NULL THEN TRUE ELSE FALSE END,
        verify_status,
        NOW(), NOW()
    FROM scores
"""

ETL_AUDIT = """
    INSERT INTO grades_audit_logs (school_id, exam_id, student_id, subject_id, old_score, new_score, action, operator_name, created_at)
    SELECT 1, exam_id, student_id, subject_id, NULL, score, 'upsert', 'system_migration', NOW()
    FROM grades_records
"""


def main():
    print("=" * 60)
    print("Grades Module Migration: DDL + ETL")
    print("=" * 60)

    with engine.begin() as conn:
        # Step 1: DDL
        print("\n[Step 1] Creating 4 new tables...")
        table_names = ["grades_subjects", "grades_exams", "grades_records", "grades_audit_logs"]
        for i, ddl in enumerate(DDL_STATEMENTS, 1):
            conn.execute(text(ddl))
            print(f"  [{i}/4] {table_names[i-1]} ... CREATED")

        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='grade7_new' AND table_name LIKE 'grades_%' "
            "ORDER BY table_name"
        ))
        tables = [r[0] for r in result]
        print(f"\n  Verification: {len(tables)} grades_ tables found: {tables}")

        # Step 2: ETL
        print("\n[Step 2] Migrating data from old tables...")

        result = conn.execute(text(ETL_SUBJECTS))
        print(f"  [1/3] subjects -> grades_subjects ... {result.rowcount} rows")

        result = conn.execute(text(ETL_EXAMS))
        print(f"  [2/3] exams -> grades_exams ... {result.rowcount} rows")

        result = conn.execute(text(ETL_SCORES))
        print(f"  [3/3] scores -> grades_records ... {result.rowcount} rows")

        result = conn.execute(text(ETL_AUDIT))
        print(f"  [extra] grades_audit_logs ... {result.rowcount} rows (migration audit trail)")

        # Final counts
        print("\n[Verification] Row counts in new tables:")
        for table in table_names:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table}: {count} rows")

        print("\n[Cross-check] Old table counts:")
        for table in ["subjects", "exams", "scores"]:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table}: {count} rows")

    print("\n" + "=" * 60)
    print("Migration COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
