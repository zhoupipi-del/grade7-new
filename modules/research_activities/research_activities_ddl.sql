-- ============================================================
-- research_activities DDL — 教研活动管理引擎
-- ============================================================
-- 3张表:
--   1. research_activities            — 活动主表 (计划/记录/总结)
--   2. research_activity_participants — 参与人员表 (签到/角色/贡献度)
--   3. research_activity_agendas      — 议题/议程表 (讨论记录/决议)
-- ============================================================

-- ── 1. research_activities — 活动主表 ──
CREATE TABLE IF NOT EXISTS `research_activities` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',

    -- 基本信息
    `title` VARCHAR(200) NOT NULL COMMENT '活动标题',
    `description` TEXT COMMENT '活动简介',
    `activity_type` VARCHAR(30) NOT NULL DEFAULT 'regular_meeting' COMMENT '类型: regular_meeting/special_topic/lesson_study/training/exchange',

    -- 学科/年级
    `subject_code` VARCHAR(20) NOT NULL COMMENT '学科代码',
    `grade_level` VARCHAR(20) DEFAULT NULL COMMENT '年级 (NULL=跨年级)',

    -- 时间地点
    `planned_at` DATETIME NOT NULL COMMENT '计划开始时间',
    `planned_end_at` DATETIME DEFAULT NULL COMMENT '计划结束时间',
    `actual_start_at` DATETIME DEFAULT NULL COMMENT '实际开始时间',
    `actual_end_at` DATETIME DEFAULT NULL COMMENT '实际结束时间',
    `location` VARCHAR(200) DEFAULT NULL COMMENT '活动地点',

    -- 状态机
    `status` VARCHAR(20) NOT NULL DEFAULT 'planned' COMMENT '状态: planned/in_progress/completed/cancelled',
    `status_updated_at` DATETIME DEFAULT NULL,
    `status_updated_by` BIGINT DEFAULT NULL,
    `cancel_reason` TEXT COMMENT '取消原因',

    -- 组织人
    `organizer_id` BIGINT NOT NULL COMMENT '组织人 user_id',

    -- 活动总结
    `summary` TEXT COMMENT '活动总结',
    `decisions` JSON DEFAULT NULL COMMENT '决议事项: ["统一函数章节进度"]',
    `attachments` JSON DEFAULT NULL COMMENT '附件列表: [{name, url, type}]',

    -- 血缘咬合备课+听课
    `linked_plan_ids` JSON DEFAULT NULL COMMENT '关联备课教案ID列表',
    `linked_observation_ids` JSON DEFAULT NULL COMMENT '关联听课记录ID列表',

    -- 统计缓存
    `participant_count` INT NOT NULL DEFAULT 0 COMMENT '参与人数(缓存)',
    `agenda_count` INT NOT NULL DEFAULT 0 COMMENT '议题数(缓存)',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    KEY `idx_ra_school_status` (`school_id`, `status`),
    KEY `idx_ra_school_subject` (`school_id`, `subject_code`, `planned_at`),
    KEY `idx_ra_organizer` (`school_id`, `organizer_id`),
    KEY `idx_ra_planned` (`school_id`, `planned_at`),
    CONSTRAINT `fk_ra_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教研活动主表';


-- ── 2. research_activity_participants — 参与人员表 ──
CREATE TABLE IF NOT EXISTS `research_activity_participants` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',
    `activity_id` BIGINT NOT NULL COMMENT '关联 research_activities.id',
    `user_id` BIGINT NOT NULL COMMENT '参与者 user_id',

    -- 角色
    `role` VARCHAR(20) NOT NULL DEFAULT 'participant' COMMENT '角色: organizer/presenter/recorder/participant',

    -- 考勤
    `attendance_status` VARCHAR(20) NOT NULL DEFAULT 'registered' COMMENT '考勤: registered/present/late/absent/leave',
    `check_in_at` DATETIME DEFAULT NULL COMMENT '签到时间',
    `check_out_at` DATETIME DEFAULT NULL COMMENT '签退时间',

    -- 贡献度
    `contribution_score` INT DEFAULT NULL COMMENT '参与贡献度 1-5',
    `contribution_note` VARCHAR(200) DEFAULT NULL COMMENT '贡献度备注',

    -- 备注
    `note` VARCHAR(200) DEFAULT NULL,

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_rap_act_user_school` (`activity_id`, `user_id`, `school_id`),
    KEY `idx_rap_activity` (`school_id`, `activity_id`),
    KEY `idx_rap_user` (`school_id`, `user_id`),
    CONSTRAINT `fk_rap_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教研活动参与人员表';


-- ── 3. research_activity_agendas — 议题/议程表 ──
CREATE TABLE IF NOT EXISTS `research_activity_agendas` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',
    `activity_id` BIGINT NOT NULL COMMENT '关联 research_activities.id',
    `seq` INT NOT NULL DEFAULT 1 COMMENT '议程排序(从1递增)',

    -- 议题内容
    `title` VARCHAR(200) NOT NULL COMMENT '议题标题',
    `presenter_id` BIGINT DEFAULT NULL COMMENT '议题主讲人 user_id',
    `content` TEXT COMMENT '议题内容/讨论记录',

    -- 时间
    `planned_duration` INT DEFAULT NULL COMMENT '预计时长(分钟)',
    `actual_duration` INT DEFAULT NULL COMMENT '实际时长(分钟)',

    -- 决议
    `decision` TEXT COMMENT '决议结果',
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '议题状态: pending/discussing/resolved/deferred',

    -- 血缘咬合
    `linked_plan_id` BIGINT DEFAULT NULL COMMENT '关联备课教案ID',
    `linked_observation_id` BIGINT DEFAULT NULL COMMENT '关联听课记录ID',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    KEY `idx_rag_activity` (`school_id`, `activity_id`, `seq`),
    KEY `idx_rag_status` (`school_id`, `activity_id`, `status`),
    CONSTRAINT `fk_rag_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教研活动议题/议程表';


-- ── 4. 注册模块 ──
INSERT INTO `school_modules` (`school_id`, `module_code`, `enabled`)
VALUES (1, 'research_activities', 1)
ON DUPLICATE KEY UPDATE `enabled` = 1;


-- ── 5. 验证 ──
SELECT 'research_activities' AS table_name, COUNT(*) AS row_count FROM `research_activities`
UNION ALL
SELECT 'research_activity_participants', COUNT(*) FROM `research_activity_participants`
UNION ALL
SELECT 'research_activity_agendas', COUNT(*) FROM `research_activity_agendas`;

SELECT id, school_id, module_code, enabled
FROM `school_modules`
WHERE module_code = 'research_activities';
