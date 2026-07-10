-- homework_mgmt DDL — 结构化作业管理
-- 3表: hw_assignments / hw_submissions / hw_grading

-- 1. 作业布置表
CREATE TABLE IF NOT EXISTS hw_assignments (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id       BIGINT NOT NULL,
    teacher_id      BIGINT NOT NULL COMMENT '布置教师 user_id',
    subject_id      BIGINT NOT NULL COMMENT '科目 grades_subjects.id',
    class_id        BIGINT COMMENT '指定班级 NULL=全年级',
    grade_id        BIGINT COMMENT '指定年级',
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    homework_type   VARCHAR(20) NOT NULL DEFAULT 'daily' COMMENT 'daily/weekly/unit_review/exam_prep',
    assigned_date   DATETIME NOT NULL,
    due_date        DATETIME NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'published' COMMENT 'draft/published/closed',
    knowledge_point_ids JSON COMMENT '关联知识点ID数组',
    attachment_url  VARCHAR(500),
    total_score     DECIMAL(6,2) DEFAULT 100.00 COMMENT '作业总分',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_hw_assign_school_class (school_id, class_id),
    INDEX idx_hw_assign_school_teacher (school_id, teacher_id),
    INDEX idx_hw_assign_school_subject (school_id, subject_id),
    INDEX idx_hw_assign_status (school_id, status, due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 学生提交表
CREATE TABLE IF NOT EXISTS hw_submissions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id       BIGINT NOT NULL,
    assignment_id   BIGINT NOT NULL,
    student_id      BIGINT NOT NULL,
    content         TEXT COMMENT '文字作答',
    attachment_url  VARCHAR(500) COMMENT '拍照附件',
    submitted_at    DATETIME,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/submitted/late/graded/missing',
    late_minutes    INT DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_hw_sub_school_assign_student (school_id, assignment_id, student_id),
    INDEX idx_hw_sub_school_student (school_id, student_id),
    INDEX idx_hw_sub_assign (assignment_id, status),
    CONSTRAINT fk_hw_sub_assign FOREIGN KEY (assignment_id) REFERENCES hw_assignments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 教师批改表
CREATE TABLE IF NOT EXISTS hw_grading (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    school_id       BIGINT NOT NULL,
    submission_id   BIGINT NOT NULL,
    teacher_id      BIGINT NOT NULL,
    score           DECIMAL(6,2) COMMENT '得分',
    max_score       DECIMAL(6,2) DEFAULT 100.00,
    score_percentage DECIMAL(5,2) COMMENT '得分率',
    grade           VARCHAR(20) COMMENT 'excellent/good/fair/needs_improvement',
    feedback        TEXT COMMENT '文字反馈',
    error_items     JSON COMMENT '错题标记 [{question_no,question_content,student_answer,correct_answer,error_type,knowledge_point_ids,difficulty}]',
    error_count     INT DEFAULT 0 COMMENT '错题数量',
    graded_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_hw_grade_sub (school_id, submission_id),
    INDEX idx_hw_grade_teacher (school_id, teacher_id, graded_at),
    CONSTRAINT fk_hw_grade_sub FOREIGN KEY (submission_id) REFERENCES hw_submissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
