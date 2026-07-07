/**
 * growth.ts — 成长时间轴 API 契约层
 *
 * 对应后端模块: modules/growth (MODULE_CODE="growth" → URL前缀 /api/v1/growth)
 * 端点清单 (2):
 *   GET    /growth/timeline/{student_id}  — 7路数据源融合时间轴（RBAC 防越权守卫）
 *   GET    /growth/my-timeline            — 家长便捷端点（自动用 Token bound_student_id）
 *
 * 7路数据源: discipline_records / discipline_sanctions / attendance_records /
 *            score_logs / recovery_states / risk_warnings / evaluation_scores
 *
 * 防越权: Parent 强制比对 bound_student_id，ClassTeacher/Leader 按班级/年级过滤
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════

/** 时间轴事件类型 */
export type GrowthEventType =
  | 'behavior'
  | 'sanction'
  | 'sanction_revoked'
  | 'attendance'
  | 'score_log'
  | 'recovery'
  | 'risk_milestone'
  | 'evaluation'

/** 严重程度 */
export type EventSeverity = 'info' | 'warning' | 'danger' | 'success'

/** ── 时间轴单项 ─────────────────────────────── */

export interface TimelineItem {
  /** 事件唯一ID，格式: {type}_{id} */
  event_id: string
  /** 事件类型 */
  event_type: GrowthEventType
  /** 事件发生时间（用于排序） */
  occurred_at: string
  /** 事件发生日期（用于视图分组） */
  event_date: string
  /** 事件标题（已脱敏柔化） */
  title: string
  /** 事件详情描述 */
  description: string | null
  /** 严重程度: info/warning/danger/success */
  severity: EventSeverity
  /** 关联表主键ID */
  related_id: number | null
  /** 数据源表名 */
  source_table: string | null
}

/** ── 时间轴完整响应 ─────────────────────────── */

export interface GrowthTimelineResponse {
  student_id: number
  student_name: string
  class_name: string
  total_events: number
  timeline: TimelineItem[]
}

// ═══════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═══════════════════════════════════════════════════

/**
 * GET /growth/timeline/{student_id}
 * 7路数据源融合 — 成长时间轴核心 API
 * @param studentId 学生ID
 * @param semester  学期过滤（如 2025-2026-2）
 */
export function getGrowthTimeline(studentId: number, semester?: string) {
  return request.get<any, GrowthTimelineResponse>(`/growth/timeline/${studentId}`, {
    params: semester ? { semester } : undefined,
  })
}

/**
 * GET /growth/my-timeline
 * 家长便捷端点 — 自动用 Token 中的 bound_student_id
 * 非家长角色访问 → 403
 */
export function getMyTimeline(semester?: string) {
  return request.get<any, GrowthTimelineResponse>('/growth/my-timeline', {
    params: semester ? { semester } : undefined,
  })
}

// ═══════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════

/** 事件类型 → 元数据（标签/图标/侧边颜色） */
export const EVENT_TYPE_META: Record<GrowthEventType, { label: string; icon: string; color: string }> = {
  behavior: { label: '行为记录', icon: 'Warning', color: '#e6a23c' },
  sanction: { label: '行政处分', icon: 'Stamp', color: '#f56c6c' },
  sanction_revoked: { label: '处分撤销', icon: 'CircleCheckFilled', color: '#67c23a' },
  attendance: { label: '考勤异常', icon: 'AlarmClock', color: '#909399' },
  score_log: { label: '评分变动', icon: 'Tickets', color: '#409eff' },
  recovery: { label: '回血进展', icon: 'RefreshRight', color: '#67c23a' },
  risk_milestone: { label: '风险预警', icon: 'Monitor', color: '#f56c6c' },
  evaluation: { label: '素质评价', icon: 'TrendCharts', color: '#8b5cf6' },
}

/** 严重程度 → el-tag type */
export const SEVERITY_TAG_TYPE: Record<EventSeverity, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  info: 'info',
  warning: 'warning',
  danger: 'danger',
  success: 'success',
}

/** 事件类型过滤选项 */
export const EVENT_TYPE_OPTIONS = Object.entries(EVENT_TYPE_META).map(([value, meta]) => ({
  value,
  label: meta.label,
  color: meta.color,
}))

// ═══════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════

/** 事件类型 → 中文标签 */
export function eventTypeLabel(type: GrowthEventType | string): string {
  return EVENT_TYPE_META[type as GrowthEventType]?.label || type
}

/** 事件类型 → 图标名 */
export function eventTypeIcon(type: GrowthEventType | string): string {
  return EVENT_TYPE_META[type as GrowthEventType]?.icon || 'InfoFilled'
}

/** 事件类型 → 颜色 */
export function eventTypeColor(type: GrowthEventType | string): string {
  return EVENT_TYPE_META[type as GrowthEventType]?.color || '#909399'
}

/** 严重程度 → tag type */
export function severityTagType(severity: EventSeverity | string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  return SEVERITY_TAG_TYPE[severity as EventSeverity] || 'info'
}

// ═══════════════════════════════════════════════════
// Demo Data (后端不可用时降级)
// ═══════════════════════════════════════════════════

export function getDemoTimeline(studentId: number): GrowthTimelineResponse {
  const baseDate = new Date('2026-06-01')
  const addDays = (d: Date, n: number) => {
    const r = new Date(d)
    r.setDate(r.getDate() + n)
    return r
  }
  const fmt = (d: Date) => d.toISOString()
  const fmtDate = (d: Date) => d.toISOString().split('T')[0]

  return {
    student_id: studentId,
    student_name: '陈博裕',
    class_name: '七(1)班',
    total_events: 12,
    timeline: [
      {
        event_id: 'evaluation_1',
        event_type: 'evaluation',
        occurred_at: fmt(addDays(baseDate, 33)),
        event_date: fmtDate(addDays(baseDate, 33)),
        title: '期末综合评价完成',
        description: '2025-2026-2 学期综合评价等级：B（良好）。道德品质 85 分，学业水平 78 分，身心健康 90 分，艺术素养 75 分，社会实践 88 分。处分扣分 5 分。',
        severity: 'success',
        related_id: 100,
        source_table: 'evaluation_scores',
      },
      {
        event_id: 'recovery_2',
        event_type: 'recovery',
        occurred_at: fmt(addDays(baseDate, 30)),
        event_date: fmtDate(addDays(baseDate, 30)),
        title: '回血进展：行为改善中',
        description: '处分满 15 天，行为回血进度 60%（3/5 项达标）。连续 12 天无新的违纪记录，继续保持可恢复 5 分评价分。',
        severity: 'success',
        related_id: 42,
        source_table: 'recovery_states',
      },
      {
        event_id: 'score_log_3',
        event_type: 'score_log',
        occurred_at: fmt(addDays(baseDate, 25)),
        event_date: fmtDate(addDays(baseDate, 25)),
        title: '社会实践 +3 分',
        description: '志愿者活动积极参与，由班主任王老师手动加分。社会实践分：85 → 88。',
        severity: 'success',
        related_id: 1153,
        source_table: 'score_logs',
      },
      {
        event_id: 'sanction_1',
        event_type: 'sanction',
        occurred_at: fmt(addDays(baseDate, 22)),
        event_date: fmtDate(addDays(baseDate, 22)),
        title: '行政处分：警告',
        description: '因"携带手机进校"被给予警告处分。处分期间 30 天（至 7月22日），道德品质扣 5 分。期间可申请行为回血。',
        severity: 'danger',
        related_id: 42,
        source_table: 'discipline_sanctions',
      },
      {
        event_id: 'behavior_2',
        event_type: 'behavior',
        occurred_at: fmt(addDays(baseDate, 22)),
        event_date: fmtDate(addDays(baseDate, 22)),
        title: '行为提醒：携带手机进校',
        description: '在上午课堂中被发现使用手机，已由年级组长李主任进行谈话教育。',
        severity: 'danger',
        related_id: 156,
        source_table: 'discipline_records',
      },
      {
        event_id: 'risk_milestone_1',
        event_type: 'risk_milestone',
        occurred_at: fmt(addDays(baseDate, 20)),
        event_date: fmtDate(addDays(baseDate, 20)),
        title: 'RDI 风险预警：需要关注',
        description: '综合风险指数 Z=2.1，行为维度偏离 +1.8σ。近 7 天内发生 1 次违纪，建议班主任加强关注和谈心。',
        severity: 'warning',
        related_id: 15,
        source_table: 'risk_warnings',
      },
      {
        event_id: 'attendance_1',
        event_type: 'attendance',
        occurred_at: fmt(addDays(baseDate, 18)),
        event_date: fmtDate(addDays(baseDate, 18)),
        title: '考勤提醒：2 次迟到',
        description: '本周累计迟到 2 次（6月18日早上、6月19日早上），请注意时间管理。',
        severity: 'warning',
        related_id: 88,
        source_table: 'attendance_records',
      },
      {
        event_id: 'score_log_2',
        event_type: 'score_log',
        occurred_at: fmt(addDays(baseDate, 15)),
        event_date: fmtDate(addDays(baseDate, 15)),
        title: '道德品质 -3 分',
        description: '课堂使用手机被扣分，道德品质分：88 → 85。此扣分可通过行为回血申请恢复。',
        severity: 'warning',
        related_id: 1140,
        source_table: 'score_logs',
      },
      {
        event_id: 'behavior_1',
        event_type: 'behavior',
        occurred_at: fmt(addDays(baseDate, 15)),
        event_date: fmtDate(addDays(baseDate, 15)),
        title: '行为提醒：课堂使用手机',
        description: '在数学课上使用手机被任课老师发现并记录。',
        severity: 'warning',
        related_id: 153,
        source_table: 'discipline_records',
      },
      {
        event_id: 'recovery_1',
        event_type: 'recovery',
        occurred_at: fmt(addDays(baseDate, 7)),
        event_date: fmtDate(addDays(baseDate, 7)),
        title: '回血完成：历史扣分已恢复',
        description: '5月份行为表现良好，道德品质 3 分扣分已成功恢复。回血率 100%，继续加油！',
        severity: 'success',
        related_id: 30,
        source_table: 'recovery_states',
      },
      {
        event_id: 'score_log_1',
        event_type: 'score_log',
        occurred_at: fmt(addDays(baseDate, 5)),
        event_date: fmtDate(addDays(baseDate, 5)),
        title: '学业水平 -5 分',
        description: '期中数学未达标，学业水平分：83 → 78。已标记为可修复（repairable）。',
        severity: 'warning',
        related_id: 1120,
        source_table: 'score_logs',
      },
      {
        event_id: 'evaluation_0',
        event_type: 'evaluation',
        occurred_at: fmt(addDays(baseDate, 1)),
        event_date: fmtDate(addDays(baseDate, 1)),
        title: '学期初评价基线建立',
        description: '2025-2026-2 学期评价引擎已初始化。基线分 100，五维权重：道德 0.3 / 学业 0.3 / 健康 0.15 / 艺术 0.1 / 社会 0.15。',
        severity: 'info',
        related_id: null,
        source_table: 'evaluation_scores',
      },
    ],
  }
}
