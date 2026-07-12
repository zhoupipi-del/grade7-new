-- Task #1390: 新高考成绩血缘明细表
-- exam_grades_detail: 每行 = 一个学生 × 一个学科 × 一场考试

CREATE TABLE IF NOT EXISTS exam_grades_detail (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    exam_id BIGINT NOT NULL COMMENT '大考ID',
    student_id BIGINT NOT NULL COMMENT '学生ID',
    school_id BIGINT NOT NULL COMMENT '学校ID (多租户隔离)',
    admin_class_id BIGINT NOT NULL COMMENT '行政班ID',
    teaching_class_id BIGINT NULL COMMENT '教学班ID (选科班, 暂不用)',
    subject_code VARCHAR(20) NOT NULL COMMENT '学科代码: chinese/math/english/physics/history/chemistry/biology/politics/geography',
    raw_score FLOAT NOT NULL DEFAULT 0 COMMENT '原始分',
    scaled_score FLOAT NULL COMMENT '赋分 (仅再选科目: chemistry/biology/politics/geography)',
    is_absent TINYINT(1) DEFAULT 0 COMMENT '是否缺考',
    cohort_rank INT NULL COMMENT '集团/全校排名',
    cohort_total INT NULL COMMENT '集团/全校有效参考人数',
    percentile FLOAT NULL COMMENT '百分比排位 0~1',
    grade_level VARCHAR(2) NULL COMMENT '等级 A/B/C/D/E (仅再选科目)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_exam (exam_id),
    INDEX idx_student (student_id),
    INDEX idx_school (school_id),
    INDEX idx_class (admin_class_id),
    INDEX idx_subject (subject_code),
    UNIQUE KEY uk_exam_student_subject (exam_id, student_id, subject_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新高考成绩血缘明细表';
