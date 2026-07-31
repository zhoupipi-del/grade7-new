-- ═══════════════════════════════════════════════════════════════
-- Wings 3.1 教研板块升级 DDL — 阵地A+B (幂等版 V2)
-- 日期: 2026-07-28 (幂等守卫补丁)
-- 内容:
--   阵地B: 听评课时空弹道捕获器 — schedule_instance_id + timeline_comments
--   阵地A: AI全息备课仓 — content_markdown + ai_bias_prescription + ai_prescription_generated_at
--   research_plan_versions: content_markdown 快照列
--
-- 安全策略:
--   1. 所有 ALTER ADD COLUMN / ADD INDEX 带 information_schema 动态检查
--   2. 列/索引已存在时执行 SELECT 1 (noop)，可重复运行不报错
--   3. 与 003_multi_org_schema.sql 幂等模式一致
-- ═══════════════════════════════════════════════════════════════

-- ── 获取当前数据库名 ──────────────────────────────────────
SELECT DATABASE() INTO @dbname;

-- ────────────────────────────────────────────────────────────
-- 阵地B: 听评课时空弹道捕获器
-- ────────────────────────────────────────────────────────────

-- ── schedule_instance_id 列 ──
SET @tbl = 'research_class_observations';
SET @col = 'schedule_instance_id';

SET @pre = CONCAT(
    'SELECT COUNT(*) INTO @col_exists FROM information_schema.COLUMNS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl, ''' ',
    'AND COLUMN_NAME = ''', @col, '''');
PREPARE stmt FROM @pre;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(@col_exists = 0,
    CONCAT('ALTER TABLE `', @tbl, '` ADD COLUMN `', @col, '` BIGINT NULL COMMENT ''关联 timetable_schedule_instances.id (时空弹道锚定, 可空)'''),
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ── timeline_comments 列 ──
SET @col2 = 'timeline_comments';

SET @pre2 = CONCAT(
    'SELECT COUNT(*) INTO @col_exists2 FROM information_schema.COLUMNS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl, ''' ',
    'AND COLUMN_NAME = ''', @col2, '''');
PREPARE stmt2 FROM @pre2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

SET @sql2 = IF(@col_exists2 = 0,
    CONCAT('ALTER TABLE `', @tbl, '` ADD COLUMN `', @col2, '` JSON NULL COMMENT ''打点弹幕数组: [{seconds_in_lesson, type, text, author_id, author_name, created_at}]'''),
    'SELECT 1');
PREPARE stmt3 FROM @sql2;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;

-- ── idx_rco_schedule_instance 索引 ──
SET @idx = 'idx_rco_schedule_instance';

SET @pre3 = CONCAT(
    'SELECT COUNT(*) INTO @idx_exists FROM information_schema.STATISTICS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl, ''' ',
    'AND INDEX_NAME = ''', @idx, '''');
PREPARE stmt4 FROM @pre3;
EXECUTE stmt4;
DEALLOCATE PREPARE stmt4;

SET @sql3 = IF(@idx_exists = 0,
    CONCAT('ALTER TABLE `', @tbl, '` ADD INDEX `', @idx, '` (school_id, schedule_instance_id)'),
    'SELECT 1');
PREPARE stmt5 FROM @sql3;
EXECUTE stmt5;
DEALLOCATE PREPARE stmt5;

-- ────────────────────────────────────────────────────────────
-- 阵地A: AI全息备课仓
-- ────────────────────────────────────────────────────────────

SET @tbl2 = 'research_lesson_plans';

-- ── content_markdown 列 ──
SET @col3 = 'content_markdown';

SET @pre4 = CONCAT(
    'SELECT COUNT(*) INTO @col_exists3 FROM information_schema.COLUMNS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl2, ''' ',
    'AND COLUMN_NAME = ''', @col3, '''');
PREPARE stmt6 FROM @pre4;
EXECUTE stmt6;
DEALLOCATE PREPARE stmt6;

SET @sql4 = IF(@col_exists3 = 0,
    CONCAT('ALTER TABLE `', @tbl2, '` ADD COLUMN `', @col3, '` TEXT NULL COMMENT ''Markdown+LaTeX 教案正文 (协同编辑的完整文本内容)'''),
    'SELECT 1');
PREPARE stmt7 FROM @sql4;
EXECUTE stmt7;
DEALLOCATE PREPARE stmt7;

-- ── ai_bias_prescription 列 ──
SET @col4 = 'ai_bias_prescription';

SET @pre5 = CONCAT(
    'SELECT COUNT(*) INTO @col_exists4 FROM information_schema.COLUMNS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl2, ''' ',
    'AND COLUMN_NAME = ''', @col4, '''');
PREPARE stmt8 FROM @pre5;
EXECUTE stmt8;
DEALLOCATE PREPARE stmt8;

SET @sql5 = IF(@col_exists4 = 0,
    CONCAT('ALTER TABLE `', @tbl2, '` ADD COLUMN `', @col4, '` TEXT NULL COMMENT ''AI学情逆向处方 (DeepSeek从错题断层逆向生成的教学偏方)'''),
    'SELECT 1');
PREPARE stmt9 FROM @sql5;
EXECUTE stmt9;
DEALLOCATE PREPARE stmt9;

-- ── ai_prescription_generated_at 列 ──
SET @col5 = 'ai_prescription_generated_at';

SET @pre6 = CONCAT(
    'SELECT COUNT(*) INTO @col_exists5 FROM information_schema.COLUMNS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl2, ''' ',
    'AND COLUMN_NAME = ''', @col5, '''');
PREPARE stmt10 FROM @pre6;
EXECUTE stmt10;
DEALLOCATE PREPARE stmt10;

SET @sql6 = IF(@col_exists5 = 0,
    CONCAT('ALTER TABLE `', @tbl2, '` ADD COLUMN `', @col5, '` DATETIME NULL COMMENT ''AI处方最后生成时间'''),
    'SELECT 1');
PREPARE stmt11 FROM @sql6;
EXECUTE stmt11;
DEALLOCATE PREPARE stmt11;

-- ────────────────────────────────────────────────────────────
-- research_plan_versions: content_markdown 快照列
-- ────────────────────────────────────────────────────────────

SET @tbl3 = 'research_plan_versions';
SET @col6 = 'content_markdown';

SET @pre7 = CONCAT(
    'SELECT COUNT(*) INTO @col_exists6 FROM information_schema.COLUMNS ',
    'WHERE TABLE_SCHEMA = ''', @dbname, ''' ',
    'AND TABLE_NAME = ''', @tbl3, ''' ',
    'AND COLUMN_NAME = ''', @col6, '''');
PREPARE stmt12 FROM @pre7;
EXECUTE stmt12;
DEALLOCATE PREPARE stmt12;

SET @sql7 = IF(@col_exists6 = 0,
    CONCAT('ALTER TABLE `', @tbl3, '` ADD COLUMN `', @col6, '` TEXT NULL COMMENT ''Markdown+LaTeX 正文快照 (每次保存时锁定一份不可变副本)'''),
    'SELECT 1');
PREPARE stmt13 FROM @sql7;
EXECUTE stmt13;
DEALLOCATE PREPARE stmt13;

-- ═══════════════════════════════════════════════════════════════
-- 验证: 检查所有新增列和索引是否到位
-- ═══════════════════════════════════════════════════════════════
-- SELECT COLUMN_NAME, TABLE_NAME FROM information_schema.COLUMNS
--   WHERE TABLE_SCHEMA = DATABASE()
--   AND COLUMN_NAME IN (
--     'schedule_instance_id', 'timeline_comments',
--     'content_markdown', 'ai_bias_prescription', 'ai_prescription_generated_at'
--   );
-- SELECT INDEX_NAME, TABLE_NAME FROM information_schema.STATISTICS
--   WHERE TABLE_SCHEMA = DATABASE()
--   AND INDEX_NAME = 'idx_rco_schedule_instance';
