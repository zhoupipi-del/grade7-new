-- ============================================================
-- Wings 3.0 — 心理咨询预约与工作台 DDL
-- 模块: psych_counseling
-- 日期: 2026-07-10
-- Phase 2 心理关怀板块核心主干
--
-- 部署步骤:
--   1. mysql -h 127.0.0.1 -P 3307 -ugrade7 -p grade7_new < psych_counseling_ddl.sql
--   2. systemctl restart wings3
--   3. INSERT INTO school_modules (school_id, module_code, enabled) VALUES (1, 'psych_counseling', 1);
-- ============================================================

-- 1. 心理老师可预约时间槽位标尺
CREATE TABLE IF NOT EXISTS `psy_consultable_slots` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL,
    `teacher_id` BIGINT NOT NULL COMMENT '心理老师 user_id',
    `date` DATETIME NOT NULL COMMENT '开放日期',
    `start_time` VARCHAR(10) NOT NULL COMMENT '开始时间 HH:MM',
    `end_time` VARCHAR(10) NOT NULL COMMENT '结束时间 HH:MM',
    `location` VARCHAR(100) DEFAULT NULL COMMENT '咨询地点(咨询室/线上)',
    `max_capacity` INT DEFAULT 1 COMMENT '该时段最大容纳人数',
    `current_booked` INT DEFAULT 0 COMMENT '当前已预约人数',
    `status` VARCHAR(20) DEFAULT 'open' COMMENT 'open(开放)/booked(已约)/locked(锁定)',
    `week_pattern` VARCHAR(10) DEFAULT 'every' COMMENT 'every/odd/even — 单双周模式',
    `is_recurring` TINYINT(1) DEFAULT 0 COMMENT '是否每周重复',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_slot_school_date` (`school_id`, `date`),
    KEY `idx_slot_teacher` (`teacher_id`, `school_id`),
    KEY `idx_slot_status` (`status`, `school_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心理老师可预约时间槽位';

-- 2. 预约申请流水表
CREATE TABLE IF NOT EXISTS `psy_appointments` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL,
    `student_id` BIGINT NOT NULL COMMENT '被咨询学生 ID',
    `applicant_id` BIGINT NOT NULL COMMENT '发起人 user_id',
    `slot_id` BIGINT NOT NULL COMMENT '关联 psy_consultable_slots.id',
    `source` VARCHAR(20) NOT NULL COMMENT 'self(学生自荐)/teacher(班主任转介)/parent(家长申请)',
    `reason_summary` VARCHAR(200) DEFAULT NULL COMMENT '申请理由摘要(脱敏后可展示)',
    `status` VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/confirmed/cancelled/completed/no_show',
    `risk_flag` VARCHAR(10) DEFAULT 'green' COMMENT '当前风险色标: green/yellow/orange/red',
    `counselor_note` VARCHAR(300) DEFAULT NULL COMMENT '心理老师审核备注',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `confirmed_at` DATETIME DEFAULT NULL COMMENT '心理老师确认时间',
    `completed_at` DATETIME DEFAULT NULL COMMENT '咨询完成时间',
    PRIMARY KEY (`id`),
    KEY `idx_apt_school_student` (`school_id`, `student_id`),
    KEY `idx_apt_slot` (`slot_id`),
    KEY `idx_apt_status` (`status`, `school_id`),
    KEY `idx_apt_source` (`source`),
    UNIQUE KEY `uk_student_slot_active` (`student_id`, `slot_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心理咨询预约申请流水表';

-- 3. 硬核加密咨询记录表 (心理老师专属工作台写实)
CREATE TABLE IF NOT EXISTS `psy_consult_records` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL,
    `appointment_id` BIGINT NOT NULL COMMENT '关联 psy_appointments.id',
    `student_id` BIGINT NOT NULL COMMENT '冗余: 被咨询学生 ID',
    `counselor_id` BIGINT NOT NULL COMMENT '心理咨询师 user_id',
    -- 加密核心字段
    `encrypted_clog` TEXT COMMENT 'Fernet 加密的咨询日志正文 — 仅 counselor+MS_ADMIN 可解密',
    -- 明文元数据 (用于索引/统计)
    `risk_level` VARCHAR(10) DEFAULT 'green' COMMENT 'green/yellow/orange/red',
    `consult_category` VARCHAR(30) DEFAULT NULL COMMENT 'emotion/interpersonal/academic/family/self_harm/other',
    `is_crisis` TINYINT(1) DEFAULT 0 COMMENT '是否触发危机干预',
    `is_referred` TINYINT(1) DEFAULT 0 COMMENT '是否转介外部医院/机构',
    `referral_target` VARCHAR(200) DEFAULT NULL COMMENT '转介医院/机构名称',
    `followup_date` DATETIME DEFAULT NULL COMMENT '计划下次随访日期',
    `session_duration_min` INT DEFAULT NULL COMMENT '本次咨询时长(分钟)',
    -- 审计追踪
    `encryption_version` VARCHAR(10) DEFAULT 'v1' COMMENT '加密算法版本标识(支持密钥轮换)',
    `decryption_access_log` JSON DEFAULT NULL COMMENT '解密访问审计: [{user_id, role, ts}]',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_cr_school_student` (`school_id`, `student_id`),
    KEY `idx_cr_counselor` (`counselor_id`, `school_id`),
    KEY `idx_cr_risk` (`risk_level`, `school_id`),
    KEY `idx_cr_crisis` (`is_crisis`, `school_id`),
    KEY `idx_cr_followup` (`followup_date`),
    UNIQUE KEY `uk_appointment_record` (`appointment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心理咨询记录表(加密写实)';

-- 4. 注册模块到 school_modules (school_id=1 为梨江中学)
INSERT INTO school_modules (school_id, module_code, enabled)
VALUES (1, 'psych_counseling', 1)
ON DUPLICATE KEY UPDATE enabled = VALUES(enabled);

-- 5. 验证
SELECT
    'psy_consultable_slots' AS table_name, COUNT(*) AS row_count FROM psy_consultable_slots
UNION ALL
SELECT 'psy_appointments', COUNT(*) FROM psy_appointments
UNION ALL
SELECT 'psy_consult_records', COUNT(*) FROM psy_consult_records;
