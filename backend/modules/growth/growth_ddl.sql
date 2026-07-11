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
    academic_score FLOAT NOT NULL DEFAULT 0.0 COMMENT '学业指数 0-100',
    attendance_score FLOAT NOT NULL DEFAULT 0.0 COMMENT '考勤表现 0-100',
    behavior_score FLOAT NOT NULL DEFAULT 0.0 COMMENT '日常品行 0-100',
    psych_score FLOAT NOT NULL DEFAULT 0.0 COMMENT '心理韧性 0-100',
    activity_score FLOAT NOT NULL DEFAULT 0.0 COMMENT '活动实践 0-100',
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
