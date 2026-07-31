-- ============================================================
-- Wings 3.0 三级组织架构迁移脚本
-- Group(Branch) → Branch → School
--
-- 安全策略:
--   1. 所有 ALTER/CREATE 带 IF EXISTS / IF NOT EXISTS 守卫
--   2. 新增列均为 nullable，允许渐进式迁移
--   3. 种子数据不破坏现有 schools/users 记录
--   4. 幂等执行 — 可重复运行不报错
--
-- 执行顺序: organizations → branches → schools 补列 →
--           users 补列 → cascading_configs → 种子数据 → 绑定
-- ============================================================

-- ─── Step 1: 创建 organizations 表 ────────────────────────
CREATE TABLE IF NOT EXISTS `organizations` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT,
    `name`        VARCHAR(100) NOT NULL             COMMENT '集团名称',
    `code`        VARCHAR(50)  NOT NULL             COMMENT '集团代码',
    `is_active`   BOOLEAN      DEFAULT TRUE         COMMENT '集团是否启用',
    `created_at`  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_org_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='三级组织架构顶层 — 教育集团';

-- ─── Step 2: 创建 branches 表 ────────────────────────────
CREATE TABLE IF NOT EXISTS `branches` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT,
    `org_id`      BIGINT       NOT NULL             COMMENT '所属集团 ID',
    `name`        VARCHAR(100) NOT NULL             COMMENT '片区名称',
    `code`        VARCHAR(50)  NOT NULL             COMMENT '片区代码',
    `is_active`   BOOLEAN      DEFAULT TRUE         COMMENT '片区是否启用',
    `created_at`  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_branch_org_code` (`org_id`, `code`),
    INDEX `idx_branch_org_id` (`org_id`),
    CONSTRAINT `fk_branch_org` FOREIGN KEY (`org_id`) REFERENCES `organizations`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='三级组织架构中间层 — 片区/校区';

-- ─── Step 3: schools 表新增 branch_id + org_id 列 ────────
-- nullable=True 允许迁移过渡，旧数据先不填
SET @dbname = DATABASE();
SET @tablename = 'schools';
SET @columnname1 = 'branch_id';
SET @columnname2 = 'org_id';

-- 添加 branch_id 列（如果不存在）
SET @pre1 = CONCAT('SELECT COUNT(*) INTO @col_exists1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = ''', @dbname, ''' AND TABLE_NAME = ''', @tablename, ''' AND COLUMN_NAME = ''', @columnname1, '''');
PREPARE stmt1 FROM @pre1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

SET @sql1 = IF(@col_exists1 = 0,
    CONCAT('ALTER TABLE `', @tablename, '` ADD COLUMN `', @columnname1, '` BIGINT NULL COMMENT ''所属片区'' AFTER `name`, ADD INDEX `idx_school_branch_id` (`', @columnname1, '`), ADD CONSTRAINT `fk_school_branch` FOREIGN KEY (`', @columnname1, '`) REFERENCES `branches`(`id`)'),
    'SELECT 1');
PREPARE stmt2 FROM @sql1;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- 添加 org_id 列（如果不存在）
SET @pre2 = CONCAT('SELECT COUNT(*) INTO @col_exists2 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = ''', @dbname, ''' AND TABLE_NAME = ''', @tablename, ''' AND COLUMN_NAME = ''', @columnname2, '''');
PREPARE stmt3 FROM @pre2;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;

SET @sql2 = IF(@col_exists2 = 0,
    CONCAT('ALTER TABLE `', @tablename, '` ADD COLUMN `', @columnname2, '` BIGINT NULL COMMENT ''所属集团'' AFTER `branch_id`, ADD INDEX `idx_school_org_id` (`', @columnname2, '`), ADD CONSTRAINT `fk_school_org` FOREIGN KEY (`', @columnname2, '`) REFERENCES `organizations`(`id`)'),
    'SELECT 1');
PREPARE stmt4 FROM @sql2;
EXECUTE stmt4;
DEALLOCATE PREPARE stmt4;

-- ─── Step 4: users 表新增 org_id + branch_id 列 ─────────
SET @tablename2 = 'users';
SET @columnname3 = 'org_id';
SET @columnname4 = 'branch_id';

-- 添加 org_id（如果不存在）
SET @pre3 = CONCAT('SELECT COUNT(*) INTO @col_exists3 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = ''', @dbname, ''' AND TABLE_NAME = ''', @tablename2, ''' AND COLUMN_NAME = ''', @columnname3, '''');
PREPARE stmt5 FROM @pre3;
EXECUTE stmt5;
DEALLOCATE PREPARE stmt5;

SET @sql3 = IF(@col_exists3 = 0,
    CONCAT('ALTER TABLE `', @tablename2, '` ADD COLUMN `', @columnname3, '` BIGINT NULL COMMENT ''集团管理员所属集团'' AFTER `school_id`, ADD INDEX `idx_user_org_id` (`', @columnname3, '`), ADD CONSTRAINT `fk_user_org` FOREIGN KEY (`', @columnname3, '`) REFERENCES `organizations`(`id`)'),
    'SELECT 1');
PREPARE stmt6 FROM @sql3;
EXECUTE stmt6;
DEALLOCATE PREPARE stmt6;

-- 添加 branch_id（如果不存在）
SET @pre4 = CONCAT('SELECT COUNT(*) INTO @col_exists4 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = ''', @dbname, ''' AND TABLE_NAME = ''', @tablename2, ''' AND COLUMN_NAME = ''', @columnname4, '''');
PREPARE stmt7 FROM @pre4;
EXECUTE stmt7;
DEALLOCATE PREPARE stmt7;

SET @sql4 = IF(@col_exists4 = 0,
    CONCAT('ALTER TABLE `', @tablename2, '` ADD COLUMN `', @columnname4, '` BIGINT NULL COMMENT ''片区管理员所属片区'' AFTER `org_id`, ADD INDEX `idx_user_branch_id` (`', @columnname4, '`), ADD CONSTRAINT `fk_user_branch` FOREIGN KEY (`', @columnname4, '`) REFERENCES `branches`(`id`)'),
    'SELECT 1');
PREPARE stmt8 FROM @sql4;
EXECUTE stmt8;
DEALLOCATE PREPARE stmt8;

-- ─── Step 5: 创建 cascading_configs 表 ───────────────────
CREATE TABLE IF NOT EXISTS `cascading_configs` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT,
    `scope_type`  ENUM('org','branch','school') NOT NULL COMMENT '作用域类型',
    `scope_id`    BIGINT       NOT NULL             COMMENT '作用域ID(org_id/branch_id/school_id)',
    `module_key`  VARCHAR(50)  NOT NULL             COMMENT '模块代码或配置分组键',
    `config_data` JSON         NOT NULL             COMMENT '配置内容JSON',
    `is_enabled`  BOOLEAN      DEFAULT TRUE         COMMENT '此配置是否生效',
    `created_at`  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    `updated_at`  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_cascading_config_scope` (`module_key`, `scope_type`, `scope_id`),
    INDEX `idx_cascading_scope` (`scope_type`, `scope_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='级联配置表 — 支持 Organization→Branch→School 三级继承';

-- ─── Step 6: 扩展 UserRole ENUM ──────────────────────────
-- MySQL ENUM 扩展需要 ALTER TABLE 修改列定义
-- 注意: 这只影响 wings3 数据库中的 users 表
-- 检查当前 ENUM 是否包含新值，如果不含则 ALTER
SET @pre5 = CONCAT('SELECT COUNT(*) INTO @enum_has_group FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = ''', @dbname, ''' AND TABLE_NAME = ''users'' AND COLUMN_NAME = ''role'' AND COLUMN_TYPE LIKE ''%group_admin%''');
PREPARE stmt9 FROM @pre5;
EXECUTE stmt9;
DEALLOCATE PREPARE stmt9;

SET @sql5 = IF(@enum_has_group = 0,
    'ALTER TABLE `users` MODIFY COLUMN `role` ENUM(\'ms_admin\',\'group_admin\',\'branch_admin\',\'grade_leader\',\'class_teacher\',\'teacher\',\'parent\',\'student\') NOT NULL DEFAULT \'teacher\' COMMENT \'用户角色(三级RBAC)\'',
    'SELECT 1');
PREPARE stmt10 FROM @sql5;
EXECUTE stmt10;
DEALLOCATE PREPARE stmt10;

-- ─── Step 7: 种子数据 — 默认集团 + 片区 ──────────────────
-- 幂等：使用 INSERT IGNORE 避免重复插入

-- 默认集团: 梨江教育集团
INSERT IGNORE INTO `organizations` (`id`, `name`, `code`, `is_active`)
VALUES (1, '梨江教育集团', 'lijiang-edu', TRUE);

-- 默认片区: 长沙县片区
INSERT IGNORE INTO `branches` (`id`, `org_id`, `name`, `code`, `is_active`)
VALUES (1, 1, '长沙县片区', 'changsha-county', TRUE);

-- ─── Step 8: 绑定现有学校到片区+集团 ────────────────────
-- 将已有的梨江中学(id=1)和测试二中(id=2)绑定到默认组织
UPDATE `schools` SET `org_id` = 1, `branch_id` = 1 WHERE `id` = 1 AND `org_id` IS NULL;
UPDATE `schools` SET `org_id` = 1, `branch_id` = 1 WHERE `id` = 2 AND `org_id` IS NULL;

-- ─── Step 9: 绑定现有用户到集团 ──────────────────────────
-- MS_ADMIN 角色用户补 org_id（保持向下兼容，MS_ADMIN 等同 SCHOOL_ADMIN）
UPDATE `users` SET `org_id` = 1 WHERE `school_id` IN (1, 2) AND `org_id` IS NULL;

-- ─── Step 10: 插入默认级联配置示例 ───────────────────────
-- 集团级默认配置（作为所有学校的兜底）
INSERT IGNORE INTO `cascading_configs` (`scope_type`, `scope_id`, `module_key`, `config_data`, `is_enabled`)
VALUES
    ('org', 1, 'attendance', '{"enabled": true, "auto_notify": true, "threshold_days": 5}', TRUE),
    ('org', 1, 'evaluation', '{"enabled": true, "base_score": 100, "fallback_strategy": "base_score"}', TRUE),
    ('org', 1, 'discipline', '{"enabled": true, "auto_escalation": true, "window_days": 30}', TRUE),
    ('org', 1, 'risk_models', '{"enabled": true, "scan_frequency": "daily", "sensitivity": "normal"}', TRUE);

-- ─── 验证查询 ────────────────────────────────────────────
SELECT 'organizations' AS tbl, COUNT(*) AS cnt FROM organizations;
SELECT 'branches' AS tbl, COUNT(*) AS cnt FROM branches;
SELECT 'cascading_configs' AS tbl, COUNT(*) AS cnt FROM cascading_configs;
SELECT 'schools_with_org' AS chk, COUNT(*) AS cnt FROM schools WHERE org_id IS NOT NULL;
SELECT 'users_with_org' AS chk, COUNT(*) AS cnt FROM users WHERE org_id IS NOT NULL;

-- ─── 完成 ────────────────────────────────────────────────
SELECT '✅ 三级组织架构迁移完成' AS status;
