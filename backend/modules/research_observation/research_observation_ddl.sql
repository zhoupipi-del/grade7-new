-- ============================================================
-- research_observation DDL — 听课评课量化追踪引擎
-- ============================================================
-- 3张表:
--   1. research_class_observations    — 听课记录主表 (血缘咬合lesson_plan_id)
--   2. research_observation_rubrics   — 多维量化打分快照 (JSON动态评分矩阵)
--   3. research_observation_appeals   — 教师确认/申诉状态机记录
-- ============================================================

-- ── 1. research_class_observations — 听课记录主表 ──
CREATE TABLE IF NOT EXISTS `research_class_observations` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',

    -- 人员
    `observer_id` BIGINT NOT NULL COMMENT '听课人 user_id',
    `teacher_id` BIGINT NOT NULL COMMENT '授课人 user_id',
    `class_id` BIGINT NOT NULL COMMENT '班级ID',

    -- 教学信息
    `subject_code` VARCHAR(20) NOT NULL COMMENT '学科代码',
    `lesson_title` VARCHAR(200) DEFAULT NULL COMMENT '课题名称',
    `observation_type` VARCHAR(20) NOT NULL DEFAULT 'routine' COMMENT '听课类型: routine/scheduled/public/demo/competition',

    -- 血缘咬合集体备课
    `lesson_plan_id` BIGINT DEFAULT NULL COMMENT '关联 research_lesson_plans.id',
    `plan_version_number` INT DEFAULT NULL COMMENT '听课时教案版本号 (锁定快照)',

    -- 量化评分
    `score_total` FLOAT DEFAULT NULL COMMENT '量化总分 (从rubric自动计算)',
    `score_max` FLOAT NOT NULL DEFAULT 100.0 COMMENT '满分分值',
    `score_percentage` FLOAT DEFAULT NULL COMMENT '得分率%',

    -- 评级
    `grade` VARCHAR(20) DEFAULT NULL COMMENT '等级: excellent/good/fair/needs_improvement',

    -- 文本反馈
    `text_feedback` JSON DEFAULT NULL COMMENT '结构化文本: {highlights:[], suggestions:[], overall_comment}',

    -- 教案执行度
    `plan_adherence` VARCHAR(20) DEFAULT NULL COMMENT '教案执行度: full/partial/deviated',
    `plan_deviation_note` TEXT COMMENT '偏离说明',

    -- 反馈状态机
    `feedback_status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '反馈状态: pending/confirmed/appealed/resolved',
    `feedback_status_updated_at` DATETIME DEFAULT NULL,
    `teacher_viewed_at` DATETIME DEFAULT NULL COMMENT '教师首次查看时间',

    -- 时间
    `observed_at` DATETIME NOT NULL COMMENT '听课日期时间',
    `duration_minutes` INT NOT NULL DEFAULT 45 COMMENT '听课时长(分钟)',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    KEY `idx_rco_school_observer` (`school_id`, `observer_id`, `observed_at`),
    KEY `idx_rco_school_teacher` (`school_id`, `teacher_id`, `observed_at`),
    KEY `idx_rco_school_status` (`school_id`, `feedback_status`),
    KEY `idx_rco_plan` (`school_id`, `lesson_plan_id`),
    CONSTRAINT `fk_rco_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='听课记录主表';


-- ── 2. research_observation_rubrics — 多维量化打分快照 ──
CREATE TABLE IF NOT EXISTS `research_observation_rubrics` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',
    `observation_id` BIGINT NOT NULL COMMENT '关联 research_class_observations.id',

    -- 评分模板
    `template_name` VARCHAR(100) DEFAULT NULL COMMENT '评分模板名称',
    `template_version` VARCHAR(20) DEFAULT NULL,

    -- 多维评分矩阵
    `rubric_metrics` JSON NOT NULL COMMENT '多维动态评分: [{name, score, max, weight, comment}]',

    -- 汇总
    `total_score` FLOAT NOT NULL COMMENT '总分',
    `max_score` FLOAT NOT NULL DEFAULT 100.0 COMMENT '满分',
    `percentage` FLOAT DEFAULT NULL COMMENT '得分率%',

    -- 评分人
    `scorer_id` BIGINT NOT NULL COMMENT '评分人 user_id',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ror_obs_school` (`observation_id`, `school_id`),
    KEY `idx_ror_observation` (`school_id`, `observation_id`),
    CONSTRAINT `fk_ror_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='多维量化打分快照表';


-- ── 3. research_observation_appeals — 教师确认/申诉记录 ──
CREATE TABLE IF NOT EXISTS `research_observation_appeals` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',
    `observation_id` BIGINT NOT NULL COMMENT '关联 research_class_observations.id',
    `teacher_id` BIGINT NOT NULL COMMENT '教师 user_id',

    -- 动作类型
    `action_type` VARCHAR(20) NOT NULL COMMENT '动作: confirm/appeal/resolve',

    -- 申诉内容
    `appeal_reason` TEXT COMMENT '申诉理由 (appeal时填写)',
    `appealed_dimensions` JSON DEFAULT NULL COMMENT '申诉维度列表',

    -- 处理结果
    `resolution` TEXT COMMENT '处理结论 (resolve时填写)',
    `resolved_by` BIGINT DEFAULT NULL COMMENT '处理人 user_id',
    `score_adjusted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否调整了评分',
    `adjusted_total_score` FLOAT DEFAULT NULL COMMENT '调整后总分',

    -- 时间
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `resolved_at` DATETIME DEFAULT NULL,

    PRIMARY KEY (`id`),
    KEY `idx_rap_observation` (`school_id`, `observation_id`),
    KEY `idx_rap_teacher` (`school_id`, `teacher_id`),
    CONSTRAINT `fk_roa_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教师确认/申诉记录表';


-- ── 4. 注册模块到 school_modules ──
INSERT INTO `school_modules` (`school_id`, `module_code`, `enabled`)
VALUES (1, 'research_observation', 1)
ON DUPLICATE KEY UPDATE `enabled` = 1;


-- ── 5. 验证 ──
SELECT 'research_class_observations' AS table_name, COUNT(*) AS row_count FROM `research_class_observations`
UNION ALL
SELECT 'research_observation_rubrics', COUNT(*) FROM `research_observation_rubrics`
UNION ALL
SELECT 'research_observation_appeals', COUNT(*) FROM `research_observation_appeals`;

SELECT id, school_id, module_code, enabled
FROM `school_modules`
WHERE module_code = 'research_observation';
