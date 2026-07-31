-- ═══════════════════════════════════════════════════════════════
-- parent_meeting_letters — 见字如面 · 家长会书信表
-- 创建时间: 2026-07-16
-- 业务场景: 2026年5月29日"见字如面·成长有你"初一年级家长会
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS `parent_meeting_letters` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '租户隔离: 学校ID',
    `student_id` BIGINT NOT NULL COMMENT '学生ID',
    `parent_user_id` BIGINT NOT NULL COMMENT '家长用户ID',
    `meeting_id` VARCHAR(60) DEFAULT NULL COMMENT '家长会批次标识, 如 2026_05_29_grade7',
    `letter_content` TEXT DEFAULT NULL COMMENT '孩子写给家长的信内容',
    `reply_content` TEXT DEFAULT NULL COMMENT '家长回信内容',
    `letter_status` VARCHAR(20) NOT NULL DEFAULT 'sent' COMMENT 'sent(孩子已写) / read(家长已读) / replied(已回信)',
    `sent_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '孩子写信时间',
    `read_at` DATETIME DEFAULT NULL COMMENT '家长阅读时间',
    `replied_at` DATETIME DEFAULT NULL COMMENT '家长回信时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_pml_student` (`student_id`),
    INDEX `idx_pml_parent` (`parent_user_id`),
    INDEX `idx_pml_status` (`letter_status`),
    INDEX `idx_pml_school` (`school_id`),
    CONSTRAINT `fk_pml_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='见字如面·家长会书信表';
