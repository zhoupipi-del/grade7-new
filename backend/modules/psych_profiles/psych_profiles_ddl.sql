-- ============================================================
-- psych_profiles DDL — 心理档案 + 筛查流水 + 双轨预警
-- ============================================================
-- 执行顺序:
--   1. 创建 psy_profiles 表
--   2. 创建 psy_screening_records 表
--   3. 注册 school_modules
--   4. 验证
-- ============================================================

-- ── 1. psy_profiles — 学生心理综合档案主表 ──
CREATE TABLE IF NOT EXISTS `psy_profiles` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `student_id` BIGINT NOT NULL COMMENT '学生ID (逻辑外键 students.id)',
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离 (外键 schools.id)',

    -- 动态风险等级
    `risk_level` VARCHAR(10) NOT NULL DEFAULT 'green' COMMENT '综合风险等级: green/yellow/orange/red',
    `risk_level_source` VARCHAR(20) NOT NULL DEFAULT 'manual' COMMENT '来源: manual/auto/screening/nexus',
    `risk_level_updated_at` DATETIME DEFAULT NULL COMMENT '风险等级最后更新时间',
    `risk_level_updated_by` BIGINT DEFAULT NULL COMMENT '风险等级最后更新人 user_id',

    -- 标签云
    `tags` JSON DEFAULT NULL COMMENT '标签云: ["单亲家庭", "考前焦虑", "人际敏感"]',

    -- 家校沟通
    `guardian_contact_status` VARCHAR(20) NOT NULL DEFAULT 'normal' COMMENT '家校沟通状态: normal/sensitive/restricted/blocked',
    `guardian_contact_note` VARCHAR(200) DEFAULT NULL COMMENT '家校沟通备注(明文)',

    -- 聚合统计
    `total_counseling_count` INT NOT NULL DEFAULT 0 COMMENT '累计咨询次数',
    `total_screening_count` INT NOT NULL DEFAULT 0 COMMENT '累计筛查次数',
    `total_intervention_count` INT NOT NULL DEFAULT 0 COMMENT '累计干预次数',
    `highest_risk_level` VARCHAR(10) NOT NULL DEFAULT 'green' COMMENT '历史最高风险等级',

    -- 转介追踪
    `is_referred` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否曾转介外部机构',
    `referral_status` VARCHAR(20) DEFAULT NULL COMMENT '转介状态: pending/in_progress/completed/returned',
    `referral_target` VARCHAR(200) DEFAULT NULL COMMENT '转介医院/机构名称',

    -- 最近活动
    `last_counseling_date` DATETIME DEFAULT NULL COMMENT '最近咨询日期',
    `last_screening_date` DATETIME DEFAULT NULL COMMENT '最近筛查日期',
    `last_intervention_date` DATETIME DEFAULT NULL COMMENT '最近干预日期',

    -- 明文备注
    `notes` TEXT COMMENT '档案备注(明文, 非敏感信息)',

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_psy_profile_student_school` (`student_id`, `school_id`),
    KEY `idx_psy_profile_risk` (`school_id`, `risk_level`),
    KEY `idx_psy_profile_school` (`school_id`),
    CONSTRAINT `fk_psy_profile_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生心理综合档案';


-- ── 2. psy_screening_records — 量表筛查流水快照 ──
CREATE TABLE IF NOT EXISTS `psy_screening_records` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `student_id` BIGINT NOT NULL COMMENT '学生ID (逻辑外键 students.id)',
    `school_id` BIGINT NOT NULL COMMENT '多租户隔离',

    -- 量表信息
    `scale_name` VARCHAR(100) NOT NULL COMMENT '量表名称: MSSMHS-55 / SCL-90 / MHT / SDS / SAS / PCE-55',
    `scale_version` VARCHAR(20) DEFAULT NULL COMMENT '量表版本',

    -- 原始分
    `raw_scores` JSON DEFAULT NULL COMMENT '各因子原始分: {dimension: score}',
    `total_score` FLOAT DEFAULT NULL COMMENT '量表总分',

    -- 风险因子
    `risk_factors` JSON DEFAULT NULL COMMENT '高风险因子列表: ["depression:4.2", "anxiety:3.8"]',
    `risk_level` VARCHAR(10) NOT NULL DEFAULT 'green' COMMENT '本次筛查风险等级: green/yellow/orange/red',

    -- 结论
    `conclusion` TEXT COMMENT 'AI/专家综合判定结论',
    `ai_generated` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '结论是否AI生成',

    -- 来源
    `source` VARCHAR(20) NOT NULL DEFAULT 'self_report' COMMENT '来源: self_report/teacher_referral/routine/external/synced',
    `operator_id` BIGINT DEFAULT NULL COMMENT '操作人 user_id',

    -- 关联
    `assessment_id` BIGINT DEFAULT NULL COMMENT '关联 mental_health_assessments.id',

    `test_date` DATETIME NOT NULL COMMENT '测试日期',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    KEY `idx_psy_screening_student` (`school_id`, `student_id`, `test_date`),
    KEY `idx_psy_screening_scale` (`school_id`, `scale_name`),
    KEY `idx_psy_screening_risk` (`school_id`, `risk_level`),
    CONSTRAINT `fk_psy_screening_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='量表筛查流水快照';


-- ── 3. 注册模块到 school_modules ──
INSERT INTO `school_modules` (`school_id`, `module_code`, `enabled`)
VALUES (1, 'psych_profiles', 1)
ON DUPLICATE KEY UPDATE `enabled` = 1;


-- ── 4. 验证 ──
SELECT 'psy_profiles' AS table_name, COUNT(*) AS row_count FROM `psy_profiles`
UNION ALL
SELECT 'psy_screening_records', COUNT(*) FROM `psy_screening_records`;

SELECT id, school_id, module_code, enabled
FROM `school_modules`
WHERE module_code = 'psych_profiles';
