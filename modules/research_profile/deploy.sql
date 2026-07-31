-- ========================================================
-- WINGS 3.1 L1 穿甲弹 数据库部署与技术债清扫 (V3 融合版, 幂等补丁)
-- ========================================================

-- ── 获取当前数据库名 ──
SELECT DATABASE() INTO @dbname;

-- 1. 清理 teach_math 重复注册（保留 id 最小的一条）
DELETE s1 FROM school_modules s1
INNER JOIN school_modules s2
WHERE s1.module_code = 'teach_math'
  AND s2.module_code = 'teach_math'
  AND s1.id > s2.id;

-- 2. 确保 research 模块注册
INSERT INTO school_modules (school_id, module_code, enabled)
VALUES (1, 'research', 1)
ON DUPLICATE KEY UPDATE enabled = 1;

-- 3. 补齐教研三剑客
INSERT INTO school_modules (school_id, module_code, enabled)
VALUES (1, 'research_lesson_prep', 1)
ON DUPLICATE KEY UPDATE enabled = 1;

INSERT INTO school_modules (school_id, module_code, enabled)
VALUES (1, 'research_observation', 1)
ON DUPLICATE KEY UPDATE enabled = 1;

INSERT INTO school_modules (school_id, module_code, enabled)
VALUES (1, 'research_activities', 1)
ON DUPLICATE KEY UPDATE enabled = 1;

-- 4. 性能索引 (幂等: information_schema.STATISTICS 检查)

-- ── idx_rlp_creator ──
SET @idx_tbl = 'research_lesson_plans';
SET @idx_name = 'idx_rlp_creator';

SET @pre_idx1 = CONCAT(
    'SELECT COUNT(*) INTO @idx_exists1 FROM information_schema.STATISTICS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @idx_tbl, ''' ',
    'AND INDEX_NAME = ''', @idx_name, '''');
PREPARE stmt FROM @pre_idx1;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql_idx1 = IF(@idx_exists1 = 0,
    CONCAT('ALTER TABLE `', @idx_tbl, '` ADD INDEX `', @idx_name, '` (creator_id)'),
    'SELECT 1');
PREPARE stmt2 FROM @sql_idx1;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- ── idx_rco_observer ──
SET @idx_tbl2 = 'research_class_observations';
SET @idx_name2 = 'idx_rco_observer';

SET @pre_idx2 = CONCAT(
    'SELECT COUNT(*) INTO @idx_exists2 FROM information_schema.STATISTICS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @idx_tbl2, ''' ',
    'AND INDEX_NAME = ''', @idx_name2, '''');
PREPARE stmt3 FROM @pre_idx2;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;

SET @sql_idx2 = IF(@idx_exists2 = 0,
    CONCAT('ALTER TABLE `', @idx_tbl2, '` ADD INDEX `', @idx_name2, '` (observer_id)'),
    'SELECT 1');
PREPARE stmt4 FROM @sql_idx2;
EXECUTE stmt4;
DEALLOCATE PREPARE stmt4;

-- ── idx_rap_user ──
SET @idx_tbl3 = 'research_activity_participants';
SET @idx_name3 = 'idx_rap_user';

SET @pre_idx3 = CONCAT(
    'SELECT COUNT(*) INTO @idx_exists3 FROM information_schema.STATISTICS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @idx_tbl3, ''' ',
    'AND INDEX_NAME = ''', @idx_name3, '''');
PREPARE stmt5 FROM @pre_idx3;
EXECUTE stmt5;
DEALLOCATE PREPARE stmt5;

SET @sql_idx3 = IF(@idx_exists3 = 0,
    CONCAT('ALTER TABLE `', @idx_tbl3, '` ADD INDEX `', @idx_name3, '` (user_id)'),
    'SELECT 1');
PREPARE stmt6 FROM @sql_idx3;
EXECUTE stmt6;
DEALLOCATE PREPARE stmt6;

-- 验证:
-- SELECT school_id, module_code, enabled FROM school_modules WHERE module_code IN ('research','research_lesson_prep','research_observation','research_activities','teach_math');
-- SELECT INDEX_NAME, TABLE_NAME FROM information_schema.STATISTICS
--   WHERE TABLE_SCHEMA = DATABASE()
--   AND INDEX_NAME IN ('idx_rlp_creator','idx_rco_observer','idx_rap_user');
