-- ═══════════════════════════════════════════════════════════════
-- growth_ddl.sql — 成长档案模块 DDL
-- P0 重型增强：从只读融合升级为双表驱动母舰
-- ═══════════════════════════════════════════════════════════════

-- 1. 成长时光轴事件表（多态JSON事件流）
CREATE TABLE IF NOT EXISTS growth_timeline_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    school_id INT NOT NULL,
    student_id INT NOT NULL,
    dimension VARCHAR(20) NOT NULL COMMENT '五育维度: academic/attendance/behavior/psychology/activity',
    severity VARCHAR(20) NOT NULL DEFAULT 'info' COMMENT '级别: info/bonus/warning/critical',
    event_type VARCHAR(50) NOT NULL COMMENT '事件标识',
    title VARCHAR(200) NOT NULL COMMENT '事件标题',
    occurred_at DATETIME NOT NULL COMMENT '事件真实发生时间',
    payload JSON COMMENT '多态结构化载荷',
    reporter_id INT NULL COMMENT '记录人ID（系统触发为NULL）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_growth_events_school (school_id),
    INDEX ix_growth_events_student (student_id),
    INDEX ix_growth_events_dim (dimension),
    INDEX ix_growth_events_time (occurred_at),
    INDEX ix_growth_events_student_time (student_id, occurred_at),
    INDEX ix_growth_events_school_dim (school_id, dimension)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='成长时光轴事件表';

-- 2. 周期性成长快照表（月度/学期五维雷达）
CREATE TABLE IF NOT EXISTS growth_periodical_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    school_id INT NOT NULL,
    student_id INT NOT NULL,
    snapshot_type VARCHAR(20) NOT NULL COMMENT 'monthly / semester',
    period_label VARCHAR(20) NOT NULL COMMENT '时间标签: 2026-07 / 2025-2026-2',
    academic_score FLOAT NOT NULL DEFAULT 100.0 COMMENT '学业指数 0-100（满分基准，扣分制）',
    attendance_score FLOAT NOT NULL DEFAULT 100.0 COMMENT '考勤表现 0-100（满分基准，扣分制）',
    behavior_score FLOAT NOT NULL DEFAULT 100.0 COMMENT '日常品行 0-100（满分基准，扣分制）',
    psych_score FLOAT NOT NULL DEFAULT 100.0 COMMENT '心理韧性 0-100（满分基准，扣分制）',
    activity_score FLOAT NOT NULL DEFAULT 100.0 COMMENT '活动实践 0-100（满分基准，扣分制）',
    summary_metrics JSON COMMENT '统计元数据',
    teacher_comment TEXT COMMENT '班主任手工评语',
    ai_growth_prescription TEXT COMMENT 'AI全息综合发展处方',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_growth_snap_school (school_id),
    INDEX ix_growth_snap_student (student_id),
    INDEX ix_growth_snap_type (snapshot_type),
    INDEX ix_growth_snap_period (period_label),
    INDEX ix_growth_snap_student_period (student_id, period_label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='周期性成长快照表';

-- 3. 主动复合预警表 (CEP 拦截器持久化)
-- 当考勤危机 × 学业断层在 48h 滑动时间窗内交汇时，
-- CEP 拦截器自动唤醒 V3 AI 引擎生成靶向处方，持久化至此表。
CREATE TABLE IF NOT EXISTS growth_active_composite_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    school_id INT NOT NULL,
    student_id INT NOT NULL,
    alert_type VARCHAR(50) NOT NULL DEFAULT 'CRITICAL_COMPOSITE' COMMENT '预警类型',
    title VARCHAR(200) NOT NULL COMMENT '预警标题',
    reason_meta TEXT NOT NULL COMMENT '触发元数据 JSON (哪两个事件交汇)',
    ai_prescription TEXT NOT NULL COMMENT 'V3 AI 引擎生成的靶向处方 (Markdown)',
    is_resolved TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已处置',
    resolved_at DATETIME NULL COMMENT '处置时间',
    resolved_by INT NULL COMMENT '处置人 user_id',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_growth_alert_school (school_id),
    INDEX ix_growth_alert_student (student_id),
    INDEX ix_growth_alert_resolved (is_resolved),
    INDEX ix_growth_alert_created (created_at),
    INDEX ix_growth_alert_school_student (school_id, student_id),
    INDEX ix_growth_alert_unresolved (is_resolved, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='主动复合预警表 (CEP拦截器)';
