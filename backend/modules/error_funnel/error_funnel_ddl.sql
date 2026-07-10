-- error_funnel DDL — 错题断层漏斗引擎
-- 3表: knowledge_points / error_book_items / knowledge_gaps

-- 1. 知识点表 (新系统首创)
CREATE TABLE IF NOT EXISTS knowledge_points (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id       BIGINT NOT NULL,
    subject_id      BIGINT NOT NULL COMMENT '科目 grades_subjects.id',
    name            VARCHAR(100) NOT NULL,
    code            VARCHAR(50) COMMENT '知识点代码',
    description     TEXT,
    parent_id       BIGINT COMMENT '父知识点 (树形结构)',
    sort_order      INT DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_kp_school_subject_code (school_id, subject_id, code),
    INDEX idx_kp_school_subject (school_id, subject_id, is_active),
    INDEX idx_kp_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 错题本条目表
CREATE TABLE IF NOT EXISTS error_book_items (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id       BIGINT NOT NULL,
    student_id      BIGINT NOT NULL,
    subject_id      BIGINT NOT NULL,
    source_type     VARCHAR(20) NOT NULL COMMENT 'homework/exam/manual',
    source_id       BIGINT COMMENT 'assignment_id or exam_id',
    source_desc     VARCHAR(200) COMMENT '来源描述',
    question_content TEXT NOT NULL,
    question_type   VARCHAR(20) COMMENT 'choice/fill/short_answer/essay/calculation',
    student_answer  TEXT,
    correct_answer  TEXT,
    error_type      VARCHAR(20) NOT NULL COMMENT 'conceptual/procedural/careless/omission/unknown',
    knowledge_point_ids JSON COMMENT '关联知识点ID数组',
    difficulty      VARCHAR(10) COMMENT 'easy/medium/hard',
    ai_analysis     TEXT COMMENT 'AI分析结果',
    ai_status       VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/completed/failed',
    is_resolved     BOOLEAN DEFAULT FALSE COMMENT '学生是否已纠错掌握',
    resolved_at     DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ebi_school_student (school_id, student_id),
    INDEX idx_ebi_school_subject (school_id, subject_id),
    INDEX idx_ebi_source (school_id, source_type, source_id),
    INDEX idx_ebi_error_type (school_id, error_type),
    INDEX idx_ebi_resolved (school_id, is_resolved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 知识点断层记录表 (聚合表)
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id       BIGINT NOT NULL,
    student_id      BIGINT NOT NULL,
    subject_id      BIGINT NOT NULL,
    knowledge_point_id BIGINT NOT NULL,
    knowledge_point_name VARCHAR(100) COMMENT '冗余存储方便查询',
    error_count     INT DEFAULT 0 COMMENT '累计错误次数',
    consecutive_errors INT DEFAULT 0 COMMENT '连续错误次数',
    last_error_date DATETIME,
    last_error_source VARCHAR(200),
    gap_level       VARCHAR(20) DEFAULT 'watch' COMMENT 'none/watch/warning/critical',
    gap_status      VARCHAR(20) DEFAULT 'active' COMMENT 'active/resolved',
    resolved_at     DATETIME,
    ai_prescription TEXT COMMENT 'AI处方',
    ai_prescription_generated_at DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_kg_school_student_kp (school_id, student_id, knowledge_point_id),
    INDEX idx_kg_school_student (school_id, student_id),
    INDEX idx_kg_school_subject (school_id, subject_id),
    INDEX idx_kg_gap_level (school_id, gap_level, gap_status),
    INDEX idx_kg_status (school_id, gap_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
