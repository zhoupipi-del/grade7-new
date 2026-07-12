-- ═══════════════════════════════════════════════════════════════════════════════
-- teacher_mgmt DDL v2.0 — DB/ORM 对齐 + 双重角色解耦 overlay
-- 执行日期: 2026-07-11
-- 执行人: AI+BOSS
-- ═════════════════════════════════════════════════════════════════════════════════

-- STEP 1: ALTER teacher_extensions — 补齐 ORM 定义但 DB 缺失的列
-- 背景: ORM 有 teacher_id/qualifications/graduate_school/is_head_teacher/homeroom_grade/is_active
--       但生产 DB 这些列不存在。DB 有 max_weekly_hours/contact_phone/hire_date/notes/employee_no
--       但 ORM 不映射。本步补齐缺失列 + ORM 后续映射 DB 已有列。

ALTER TABLE teacher_extensions
  ADD COLUMN teacher_id BIGINT NULL COMMENT '关联 teachers.id FK' AFTER user_id,
  ADD COLUMN qualifications JSON NULL COMMENT '资质证书列表 ["教师资格证","心理咨询师",...]' AFTER office_location,
  ADD COLUMN graduate_school VARCHAR(100) NULL COMMENT '毕业院校' AFTER major,
  ADD COLUMN is_head_teacher TINYINT(1) DEFAULT 0 COMMENT '是否班主任' AFTER graduate_school,
  ADD COLUMN homeroom_grade VARCHAR(20) NULL COMMENT '带班组年级' AFTER is_head_teacher,
  ADD COLUMN is_active TINYINT(1) DEFAULT 1 COMMENT '是否在职' AFTER homeroom_grade;

-- STEP 2: ALTER teacher_extensions — 补 UK (ORM 定义了 uk_teacher_ext_user 但 DB 可能缺)
-- 安全做法: 先查再建, 如已存在则跳过

-- uk_teacher_ext_user (school_id + user_id) — 与 user_id unique 冗余但 ORM 要求存在
SET @uk_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_extensions'
  AND CONSTRAINT_NAME='uk_teacher_ext_user');
SET @sql = IF(@uk_exists = 0,
  'ALTER TABLE teacher_extensions ADD UNIQUE KEY uk_teacher_ext_user (school_id, user_id)',
  'SELECT "uk_teacher_ext_user already exists, skipping" AS msg');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- STEP 3: ALTER teacher_subjects — 补齐 ORM 定义但 DB 缺失的列
-- ORM 有 subject_code/is_primary/grade_level 但 DB 缺

ALTER TABLE teacher_subjects
  ADD COLUMN subject_code VARCHAR(30) NOT NULL DEFAULT '' COMMENT '学科代码: chinese/math/english/...' AFTER teacher_user_id,
  ADD COLUMN is_primary TINYINT(1) DEFAULT 1 COMMENT '是否主教科任' AFTER subject_name,
  ADD COLUMN grade_level VARCHAR(20) NULL COMMENT '执教年级: 初一/初二/初三/高一/高二/高三' AFTER is_primary;

-- uk_teacher_subject (school_id + teacher_user_id + subject_code) — ORM 要求
SET @uk2_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_subjects'
  AND CONSTRAINT_NAME='uk_teacher_subject');
SET @sql2 = IF(@uk2_exists = 0,
  'ALTER TABLE teacher_subjects ADD UNIQUE KEY uk_teacher_subject (school_id, teacher_user_id, subject_code)',
  'SELECT "uk_teacher_subject already exists, skipping" AS msg');
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- idx_ts_subject / idx_ts_teacher — ORM 要求的索引
SET @idx1_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_subjects' AND INDEX_NAME='idx_ts_subject');
SET @sql3 = IF(@idx1_exists = 0,
  'ALTER TABLE teacher_subjects ADD INDEX idx_ts_subject (subject_code)',
  'SELECT "idx_ts_subject already exists, skipping" AS msg');
PREPARE stmt3 FROM @sql3;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;

SET @idx2_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_subjects' AND INDEX_NAME='idx_ts_teacher');
SET @sql4 = IF(@idx2_exists = 0,
  'ALTER TABLE teacher_subjects ADD INDEX idx_ts_teacher (teacher_user_id)',
  'SELECT "idx_ts_teacher already exists, skipping" AS msg');
PREPARE stmt4 FROM @sql4;
EXECUTE stmt4;
DEALLOCATE PREPARE stmt4;

-- STEP 4: ALTER teacher_workloads — 补齐 ORM notes 列 (如果 DB 缺)
SET @col_notes_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_workloads' AND COLUMN_NAME='notes');
SET @sql5 = IF(@col_notes_exists = 0,
  'ALTER TABLE teacher_workloads ADD COLUMN notes VARCHAR(255) NULL COMMENT "备注" AFTER total_workload_score',
  'SELECT "teacher_workloads.notes already exists, skipping" AS msg');
PREPARE stmt5 FROM @sql5;
EXECUTE stmt5;
DEALLOCATE PREPARE stmt5;

-- uk_workload_teacher_semester — ORM 要求
SET @uk3_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_workloads'
  AND CONSTRAINT_NAME='uk_workload_teacher_semester');
SET @sql6 = IF(@uk3_exists = 0,
  'ALTER TABLE teacher_workloads ADD UNIQUE KEY uk_workload_teacher_semester (school_id, teacher_user_id, semester)',
  'SELECT "uk_workload_teacher_semester already exists, skipping" AS msg');
PREPARE stmt6 FROM @sql6;
EXECUTE stmt6;
DEALLOCATE PREPARE stmt6;

-- STEP 5: CREATE teacher_role_assignments — 双重角色解耦 overlay 表
-- 一个教师可以同时拥有多个角色(科任教师+年级组长+德育处主任),
-- 每个角色有自己的作用域(scope_type + scope_id),
-- 在不同业务场景(排课/审批/大盘)切换不同权限切面。

CREATE TABLE IF NOT EXISTS teacher_role_assignments (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  school_id BIGINT NOT NULL COMMENT '租户隔离',
  teacher_user_id BIGINT NOT NULL COMMENT '教师 user_id FK',
  role_type VARCHAR(30) NOT NULL COMMENT '角色类型: subject_teacher/homeroom_teacher/grade_leader/moral_admin/research_leader/prep_leader/discipline_officer/counselor',
  scope_type VARCHAR(20) NOT NULL COMMENT '作用域类型: school/grade/class/subject_group',
  scope_id BIGINT NULL COMMENT '作用域ID(grade_id/class_id等), school级为NULL',
  is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
  assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '分配时间',
  expires_at DATETIME NULL COMMENT '过期时间(可选)',
  assigned_by BIGINT NULL COMMENT '分配人 user_id',
  notes VARCHAR(255) NULL COMMENT '备注',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  UNIQUE KEY uk_role_assignment (school_id, teacher_user_id, role_type, scope_type, scope_id),
  INDEX idx_tra_teacher (teacher_user_id),
  INDEX idx_tra_role_type (role_type),
  INDEX idx_tra_scope (scope_type, scope_id),
  INDEX idx_tra_school (school_id),

  CONSTRAINT fk_tra_school FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
  CONSTRAINT fk_tra_teacher FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE
) COMMENT='教师角色分配表（多重角色解耦overlay）';

-- ═════════════════════════════════════════════════════════════════════════════════
-- 验证 DDL 落地
-- ═════════════════════════════════════════════════════════════════════════════════

SELECT '--- teacher_extensions columns ---' AS section;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_extensions'
ORDER BY ORDINAL_POSITION;

SELECT '--- teacher_subjects columns ---' AS section;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_subjects'
ORDER BY ORDINAL_POSITION;

SELECT '--- teacher_workloads columns ---' AS section;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_workloads'
ORDER BY ORDINAL_POSITION;

SELECT '--- teacher_role_assignments columns ---' AS section;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='teacher_role_assignments'
ORDER BY ORDINAL_POSITION;
