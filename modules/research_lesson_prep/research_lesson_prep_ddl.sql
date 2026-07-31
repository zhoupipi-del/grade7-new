-- ============================================================
-- research_lesson_prep DDL — 集体备课协同编辑引擎
-- ============================================================
-- 3张表:
--   1. research_lesson_plans    — 备课主案表 (状态机+版本指针)
--   2. research_plan_versions   — 版本快照表 (不可变, 每次保存创建)
--   3. research_plan_reviews    — 协同批注表 (按教案组件定位)
-- ============================================================

-- ── 1. research_lesson_plans — 备课主案表 ──
CREATE TABLE IF NOT EXISTS `research_lesson_plans` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离 (外键 schools.id)',

    -- 教案元信息
    `title` VARCHAR(200) NOT NULL COMMENT '教案标题',
    `description` TEXT COMMENT '教案简介/教学说明',
    `subject_code` VARCHAR(20) NOT NULL COMMENT '学科代码: chinese/math/english/physics/...',
    `grade_level` VARCHAR(20) NOT NULL COMMENT '年级: grade_7/grade_8/grade_9/...',
    `lesson_type` VARCHAR(20) NOT NULL DEFAULT 'new' COMMENT '课型: new/review/exam/test/activity',
    `duration` INT NOT NULL DEFAULT 1 COMMENT '课时数',
    `tags` JSON DEFAULT NULL COMMENT '标签: ["函数","大单元","跨学科"]',

    -- 状态机
    `status` VARCHAR(20) NOT NULL DEFAULT 'draft' COMMENT '状态: draft/review/approved/published',
    `status_updated_at` DATETIME DEFAULT NULL COMMENT '状态最后变更时间',
    `status_updated_by` BIGINT DEFAULT NULL COMMENT '状态变更操作人 user_id',
    `reject_reason` TEXT COMMENT '打回原因 (回退至draft时填写)',

    -- 版本控制
    `current_version` INT NOT NULL DEFAULT 1 COMMENT '当前版本号(递增)',
    `published_version` INT DEFAULT NULL COMMENT '已发布版本号(NULL=未发布)',

    -- 引用统计
    `reference_count` INT NOT NULL DEFAULT 0 COMMENT '被其他教师引用次数',
    `fork_count` INT NOT NULL DEFAULT 0 COMMENT '被Fork派生次数',

    -- 人员
    `creator_id` BIGINT NOT NULL COMMENT '主备人 user_id',
    `grade_leader_id` BIGINT DEFAULT NULL COMMENT '教研组长 user_id (审核人)',

    -- 关联
    `forked_from_id` BIGINT DEFAULT NULL COMMENT 'Fork来源 plan_id (NULL=原创)',
    `chapter_id` BIGINT DEFAULT NULL COMMENT '关联章节ID (如有教材管理模块)',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    KEY `idx_rlp_school_status` (`school_id`, `status`),
    KEY `idx_rlp_school_subject` (`school_id`, `subject_code`, `grade_level`),
    KEY `idx_rlp_creator` (`school_id`, `creator_id`),
    KEY `idx_rlp_published` (`school_id`, `published_version`),
    CONSTRAINT `fk_rlp_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='集体备课主案表';


-- ── 2. research_plan_versions — 版本快照表 ──
CREATE TABLE IF NOT EXISTS `research_plan_versions` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',
    `plan_id` BIGINT NOT NULL COMMENT '关联 research_lesson_plans.id',
    `version_number` INT NOT NULL COMMENT '版本号(从1递增)',
    `editor_id` BIGINT NOT NULL COMMENT '编辑人 user_id',

    -- 结构化教案内容
    `content_json` JSON NOT NULL COMMENT '结构化教案: {teaching_objectives, key_points, difficulties, teaching_methods, teaching_process[], homework, blackboard_design, reflection}',

    -- 变更说明
    `change_log` TEXT COMMENT '本版本变更说明',
    `is_major` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否重大修订',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_rpv_plan_ver_school` (`plan_id`, `version_number`, `school_id`),
    KEY `idx_rpv_plan` (`school_id`, `plan_id`, `version_number`),
    CONSTRAINT `fk_rpv_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='备课版本快照表(不可变)';


-- ── 3. research_plan_reviews — 协同批注表 ──
CREATE TABLE IF NOT EXISTS `research_plan_reviews` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',
    `plan_id` BIGINT NOT NULL COMMENT '关联 research_lesson_plans.id',
    `version_number` INT NOT NULL COMMENT '批注针对的版本号',
    `reviewer_id` BIGINT NOT NULL COMMENT '批注人 user_id',

    -- 批注定位
    `target_section` VARCHAR(100) NOT NULL COMMENT '教案组件路径: teaching_objectives / teaching_process[0] / homework / ...',
    `target_anchor` VARCHAR(200) DEFAULT NULL COMMENT '锚点文本 (批注引用的原文片段)',

    -- 批注内容
    `comment` TEXT NOT NULL COMMENT '批注正文',
    `severity` VARCHAR(20) NOT NULL DEFAULT 'suggestion' COMMENT '严重度: suggestion/issue/critical',

    -- 解决状态
    `is_resolved` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已解决',
    `resolved_by` BIGINT DEFAULT NULL COMMENT '解决人 user_id',
    `resolved_at` DATETIME DEFAULT NULL COMMENT '解决时间',
    `resolution_note` TEXT COMMENT '解决说明',

    -- 回复链
    `parent_review_id` BIGINT DEFAULT NULL COMMENT '父批注ID (回复链, NULL=顶级批注)',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    KEY `idx_rpr_plan_ver` (`school_id`, `plan_id`, `version_number`),
    KEY `idx_rpr_resolved` (`school_id`, `plan_id`, `is_resolved`),
    KEY `idx_rpr_reviewer` (`school_id`, `reviewer_id`),
    CONSTRAINT `fk_rpr_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协同评审批注表';


-- ── 4. 注册模块到 school_modules ──
INSERT INTO `school_modules` (`school_id`, `module_code`, `enabled`)
VALUES (1, 'research_lesson_prep', 1)
ON DUPLICATE KEY UPDATE `enabled` = 1;


-- ── 5. 验证 ──
SELECT 'research_lesson_plans' AS table_name, COUNT(*) AS row_count FROM `research_lesson_plans`
UNION ALL
SELECT 'research_plan_versions', COUNT(*) FROM `research_plan_versions`
UNION ALL
SELECT 'research_plan_reviews', COUNT(*) FROM `research_plan_reviews`;

SELECT id, school_id, module_code, enabled
FROM `school_modules`
WHERE module_code = 'research_lesson_prep';
