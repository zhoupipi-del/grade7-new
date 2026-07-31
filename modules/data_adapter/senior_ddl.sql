-- ═══════════════════════════════════════════════════════════════════════
-- 高中「行政班 vs 教学班」+「选科赋分」数据库血缘 DDL
-- Wings 3.0 — Phase: Senior (高中) 新高考 3+1+2 走班制支持
-- ═══════════════════════════════════════════════════════════════════════
--
-- 设计思路:
--   1. classes 表加 class_type 字段，行政班(administrative)与教学班(teaching)共存
--   2. 新建 student_teaching_class_enrollments 中间表实现多对多走班
--   3. grades_subjects 加 subject_category 三分类(mandatory/preferred/elective)
--   4. 新建 student_subject_selections 登记高中生选科组合
--   5. 新建 scaling_rule_sets 存储赋分规则(新高考 A-E 五级)
--   6. exam_grades_detail 启用 teaching_class_id + 补 UK/索引
--
-- 兼容性原则:
--   - 所有 ALTER 均加 DEFAULT 值，初中/小学存量数据零影响
--   - 新表全部继承 SchoolMixin(school_id FK)
--   - 逻辑外键(BigInteger 列+comment)，与现有 Wings 3.0 一致
--   - Student.class_id NOT NULL 不改，继续指向行政班

-- ───────────────────────────────────────────────────────────────────────
-- STEP 1: ALTER classes — 双轨制字段注入
-- ───────────────────────────────────────────────────────────────────────

ALTER TABLE `classes`
  ADD COLUMN `class_type` VARCHAR(20) NOT NULL DEFAULT 'administrative'
    COMMENT '班级类型: administrative(行政班)/teaching(教学班/选科班)',
  ADD COLUMN `subject_group` VARCHAR(50) NULL
    COMMENT '教学班选科组合: physics_group(物化生)/history_group(史政地)/custom',
  ADD COLUMN `grade_level` VARCHAR(10) NULL
    COMMENT '年级层级: senior_1(高一)/senior_2(高二)/senior_3(高三)';

-- 紧急索引：按学校+班级类型快速筛选
CREATE INDEX `idx_class_type` ON `classes` (`school_id`, `class_type`);
CREATE INDEX `idx_class_subject_group` ON `classes` (`school_id`, `subject_group`);

-- ───────────────────────────────────────────────────────────────────────
-- STEP 2: ALTER grades_subjects — 科目三分类注入
-- ───────────────────────────────────────────────────────────────────────

ALTER TABLE `grades_subjects`
  ADD COLUMN `subject_category` VARCHAR(20) NOT NULL DEFAULT 'mandatory'
    COMMENT '科目分类: mandatory(必考:语数英)/preferred(首选:物史)/elective(再选:化生政地)',
  ADD COLUMN `is_scaling_target` BOOLEAN NOT NULL DEFAULT FALSE
    COMMENT '是否需要等级赋分(仅再选科目为TRUE)',
  ADD COLUMN `scaling_score_range` VARCHAR(20) NULL
    COMMENT '赋分分值区间(如 "30-100" 表示再选科目赋分区间)';

-- ───────────────────────────────────────────────────────────────────────
-- STEP 3: CREATE student_subject_selections — 学生选科登记表
-- ───────────────────────────────────────────────────────────────────────
-- 每个高中生在特定学期登记其选科组合:
--   首选1科(物理或历史) + 再选2科(化/生/政/地)
--   is_active 标记当前生效选科组合(每学期只能有1条active)

CREATE TABLE `student_subject_selections` (
  `id`              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `school_id`       BIGINT        NOT NULL,
  `student_id`      BIGINT        NOT NULL COMMENT '学生ID(逻辑FK→students.id)',
  `preferred_subject` VARCHAR(20)  NOT NULL COMMENT '首选科目代码: physics/history',
  `elective_subjects` JSON         NOT NULL COMMENT '再选2科代码数组 ["chemistry","biology"]',
  `semester`        VARCHAR(20)   NOT NULL COMMENT '生效学期(如 2025-1)',
  `is_active`       BOOLEAN       NOT NULL DEFAULT TRUE COMMENT '是否当前生效(每学期每学生仅1条active)',
  `confirmed_at`    DATETIME      NULL COMMENT '选科确认时间(学生/家长确认)',
  `confirmed_by`    BIGINT        NULL COMMENT '确认人 user_id',
  `created_at`      DATETIME      DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  UNIQUE KEY `uk_student_selection_semester` (`school_id`, `student_id`, `semester`),
  INDEX `idx_selection_school` (`school_id`),
  INDEX `idx_selection_student` (`student_id`),
  INDEX `idx_selection_active` (`school_id`, `is_active`, `semester`),

  CONSTRAINT `fk_selection_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='高中生选科登记表(3+1+2组合)';

-- ───────────────────────────────────────────────────────────────────────
-- STEP 4: CREATE student_teaching_class_enrollments — 走班多对多中间表
-- ───────────────────────────────────────────────────────────────────────
-- 一个学生可以同时属于多个教学班(不同学科的选科班)
--   如: 学生A → 教学班"物化生组合"(物理) + 教学班"物化生组合"(化学) + ...

CREATE TABLE `student_teaching_class_enrollments` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `school_id`        BIGINT       NOT NULL,
  `student_id`       BIGINT       NOT NULL COMMENT '学生ID(逻辑FK→students.id)',
  `teaching_class_id` BIGINT      NOT NULL COMMENT '教学班ID(逻辑FK→classes.id, class_type=teaching)',
  `subject_code`     VARCHAR(20)  NOT NULL COMMENT '该教学班对应的学科代码',
  `semester`         VARCHAR(20)  NOT NULL COMMENT '学期标识(如 2025-1)',
  `is_active`        BOOLEAN      NOT NULL DEFAULT TRUE COMMENT '是否当前生效',
  `created_at`       DATETIME     DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY `uk_enrollment_student_class_semester`
    (`school_id`, `student_id`, `teaching_class_id`, `semester`),
  INDEX `idx_enrollment_school` (`school_id`),
  INDEX `idx_enrollment_student` (`student_id`, `is_active`),
  INDEX `idx_enrollment_class` (`teaching_class_id`, `semester`),
  INDEX `idx_enrollment_subject` (`school_id`, `subject_code`, `semester`),

  CONSTRAINT `fk_enrollment_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='走班多对多中间表(学生×教学班×学科×学期)';

-- ───────────────────────────────────────────────────────────────────────
-- STEP 5: CREATE scaling_rule_sets — 赋分规则配置表
-- ───────────────────────────────────────────────────────────────────────
-- 新高考等级赋分规则: 按排名百分位映射到 A-E 五级
--   A: 前15% → 100-86分区间
--   B: 16%-50% → 85-71分区间
--   C: 51%-84% → 70-56分区间
--   D: 85%-97% → 55-41分区间
--   E: 98%-100% → 40-30分区间
-- 允许不同省份/年份使用不同规则集

CREATE TABLE `scaling_rule_sets` (
  `id`              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `school_id`       BIGINT        NOT NULL,
  `name`            VARCHAR(100)  NOT NULL COMMENT '规则集名称(如 "湖南省2025新高考赋分")',
  `province_code`   VARCHAR(10)   NULL COMMENT '省份代码(如 "43" 湖南)',
  `grade_levels`    JSON          NULL COMMENT '适用年级层级数组 ["senior_1","senior_2","senior_3"]',
  `rule_entries`    JSON          NOT NULL COMMENT '赋分等级规则数组 [{"level":"A","pct_start":0,"pct_end":15,"score_start":100,"score_end":86},...]',
  `is_active`       BOOLEAN       NOT NULL DEFAULT TRUE COMMENT '是否当前生效',
  `effective_from`  DATE          NOT NULL COMMENT '生效起始日期',
  `effective_until` DATE          NULL COMMENT '生效截止日期(NULL=永久)',
  `created_by`      BIGINT        NULL COMMENT '创建人 user_id',
  `created_at`      DATETIME      DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX `idx_scaling_school` (`school_id`),
  INDEX `idx_scaling_active` (`school_id`, `is_active`, `effective_from`),

  CONSTRAINT `fk_scaling_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='新高考等级赋分规则配置表(A-E五级映射)';

-- ───────────────────────────────────────────────────────────────────────
-- STEP 6: ALTER exam_grades_detail — 启用 teaching_class_id + 补约束
-- ───────────────────────────────────────────────────────────────────────
-- exam_grades_detail 已有 teaching_class_id (nullable, 暂不用)
-- 高中走班启用后需: 去掉"暂不用"限制 + 补UK + 补索引

-- 1) 补唯一键: 一学生×一考试×一学科 只能有一条成绩明细
ALTER TABLE `exam_grades_detail`
  ADD UNIQUE KEY `uk_exam_student_subject` (`school_id`, `exam_id`, `student_id`, `subject_code`);

-- 2) 补索引: 按 teaching_class_id + exam_id 查教学班成绩
CREATE INDEX `idx_egd_teaching_class` ON `exam_grades_detail` (`teaching_class_id`, `exam_id`);

-- 3) 补索引: 按赋分等级/百分位筛选
CREATE INDEX `idx_egd_grade_level` ON `exam_grades_detail` (`school_id`, `grade_level`);

-- ───────────────────────────────────────────────────────────────────────
-- STEP 7: 种子数据 — 湖南省新高考赋分默认规则集
-- ───────────────────────────────────────────────────────────────────────
-- 此 INSERT 需在 school_id=1 (梨江中学高中部) 或 school_id=100 (高中测试沙箱) 执行
-- 以下为模板, 实际部署时替换 school_id

-- INSERT INTO `scaling_rule_sets` (
--   `school_id`, `name`, `province_code`, `grade_levels`, `rule_entries`,
--   `is_active`, `effective_from`, `created_by`
-- ) VALUES (
--   100,  -- 替换为高中 school_id
--   '湖南省2025新高考等级赋分(3+1+2)',
--   '43',
--   '["senior_1","senior_2","senior_3"]',
--   '[{"level":"A","pct_start":0,"pct_end":15,"score_start":100,"score_end":86},{"level":"B","pct_start":15,"pct_end":50,"score_start":85,"score_end":71},{"level":"C","pct_start":50,"pct_end":84,"score_start":70,"score_end":56},{"level":"D","pct_start":84,"pct_end":97,"score_start":55,"score_end":41},{"level":"E","pct_start":97,"pct_end":100,"score_start":40,"score_end":30}]',
--   TRUE,
--   '2025-09-01',
--   NULL
-- );

-- ───────────────────────────────────────────────────────────────────────
-- STEP 8: 存量兼容 — 初中/小学存量数据自动适配
-- ───────────────────────────────────────────────────────────────────────
-- 所有 ALTER 加了 DEFAULT 值，存量数据含义:
--   classes.class_type = 'administrative' → 所有现有班级默认为行政班(正确)
--   grades_subjects.subject_category = 'mandatory' → 初中所有科目默认必考(正确)
--   grades_subjects.is_scaling_target = FALSE → 初中不做赋分(正确)
--   exam_grades_detail.teaching_class_id = NULL → 初中不需要教学班(正确)

-- ═══════════════════════════════════════════════════════════════════════
-- 数据血缘结构总览
-- ═══════════════════════════════════════════════════════════════════════
--
-- 行政班轨道:
--   Student.class_id → Class(class_type=administrative)
--     → 班主任管理、考勤、德育、日常
--
-- 教学班轨道:
--   StudentSubjectSelection(preferred + elective)
--     → StudentTeachingClassEnrollment(student × teaching_class × subject × semester)
--       → Class(class_type=teaching, subject_group=组合代码)
--         → 教学班教师授课
--
-- 成绩赋分轨道:
--   GradeSubject(subject_category + is_scaling_target)
--     → ExamGradesDetail(raw_score + admin_class_id + teaching_class_id)
--       mandatory/preferred → raw_score 直接计入, scaled_score=NULL
--       elective → raw_score → ScalingRuleSet(rule_entries) → percentile → grade_level → scaled_score
--
-- 赋分公式:
--   percentile = (cohort_rank - 1) / cohort_total
--   找到 rule_entries 中 pct_start ≤ percentile < pct_end 的等级 L
--   scaled_score = L.score_start - (L.score_start - L.score_end) × (percentile - L.pct_start) / (L.pct_end - L.pct_start)
--
-- ═══════════════════════════════════════════════════════════════════════
