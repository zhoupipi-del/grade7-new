/**
 * growth.ts — 成长档案 API 契约层
 *
 * 对应后端模块: modules/growth (MODULE_CODE="growth" -> URL前缀 /api/v1/growth)
 *
 * 端点清单 (9):
 *   [旧] GET /growth/timeline/{student_id}   — 7路数据源融合时间轴
 *   [旧] GET /growth/my-timeline             — 家长便捷端点
 *   [新] GET /growth/dashboard               — 成长档案看板统计
 *   [新] POST /growth/events                 — 创建成长事件
 *   [新] GET /growth/events                  — 列出成长事件(分页+筛选)
 *   [新] GET /growth/profile/{student_id}    — 学生全息成长画像(支持semester_label)
 *   [新] POST /growth/snapshots/generate     — 生成周期快照(五维引擎)
 *   [新] GET /growth/snapshots               — 列出成长快照
 *   [新] PUT /growth/snapshots/{id}/comment  — 更新班主任评语
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 旧版类型定义 (7路融合时间轴, 保留兼容)
// ═══════════════════════════════════════════════════

export type GrowthEventType =
  | 'behavior'
  | 'sanction'
  | 'sanction_revoked'
  | 'attendance'
  | 'score_log'
  | 'recovery'
  | 'risk_milestone'
  | 'evaluation'
  | 'gap_critical'
  | 'gap_warning'
  | 'honor'
  | 'psych_alert'
  | 'pipeline_test_event'

/** 事件级别 — 与后端 schemas.py 对齐: info/bonus/warning/critical */
export type EventSeverity = 'info' | 'bonus' | 'warning' | 'critical'

export interface TimelineItem {
  event_id: string
  event_type: GrowthEventType | string
  occurred_at: string
  event_date: string
  title: string
  description: string | null
  severity: EventSeverity | string
  related_id: number | null
  source_table: string | null
}

export interface GrowthTimelineResponse {
  student_id: number
  student_name: string
  class_name: string
  total_events: number
  timeline: TimelineItem[]
}

// ═══════════════════════════════════════════════════
// P0 新增类型定义 — 与后端 schemas.py 严格对齐
// ═══════════════════════════════════════════════════

/** 成长事件维度 — 后端用 psychology 不是 psych */
export type GrowthDimension = 'academic' | 'attendance' | 'behavior' | 'psychology' | 'activity'

/** 快照类型 */
export type SnapshotType = 'monthly' | 'semester'

/** ── 五维雷达得分 (后端 RadarDimensions) ─────────── */

export interface RadarDimensions {
  academic: number
  attendance: number
  behavior: number
  psychology: number  // 后端用 psychology
  activity: number
}

/** ── 快照统计摘要 (后端 SnapshotMetricsSummary) ──── */

export interface SnapshotMetricsSummary {
  total_absent_count: number
  critical_gap_count: number
  behavior_violation_count: number
  honor_count: number
  additional_info: Record<string, any>
}

/** ── 周期快照响应 (后端 GrowthSnapshotResponse) ───── */

export interface GrowthSnapshotResponse {
  id: number
  student_id: number
  snapshot_type: SnapshotType | string
  period_label: string
  scores: RadarDimensions
  metrics_summary: SnapshotMetricsSummary
  teacher_comment: string | null
  ai_growth_prescription: string | null
  created_at: string
}

/** ── 成长事件 (P0双表) ────────────────────────────── */

export interface TimelineEventCreate {
  student_id: number
  dimension: GrowthDimension
  severity: EventSeverity
  event_type: string
  title: string
  occurred_at: string  // 后端必填
  payload?: Record<string, any> | null
}

export interface TimelineEventResponse {
  id: number
  student_id: number
  dimension: string
  severity: string
  event_type: string
  title: string
  occurred_at: string
  payload: Record<string, any> | null
  reporter_name: string | null
  created_at: string
}

export interface TimelineEventListResponse {
  items: TimelineEventResponse[]
  total: number
  page: number
  page_size: number
}

/** ── 快照生成请求 ─────────────────────────────────── */

export interface SnapshotGenerateRequest {
  student_id: number
  snapshot_type: SnapshotType
  period_label: string
}

export interface SnapshotListResponse {
  items: GrowthSnapshotResponse[]
  total: number
  page: number
  page_size: number
}

/** ── 全息画像 (后端 StudentHolisticProfile) ───────── */
/** 后端返回扁平结构: student_id/student_name/class_name */

export interface StudentHolisticProfile {
  student_id: number
  student_name: string
  class_name: string
  current_snapshot: GrowthSnapshotResponse | null
  historical_snapshots: GrowthSnapshotResponse[]
  recent_events: TimelineEventResponse[]
}

/** ── 班主任评语 ───────────────────────────────────── */

export interface TeacherCommentUpdate {
  teacher_comment: string
}

/** ── 看板 (后端 GrowthDashboard) ──────────────────── */
/** dimension_distribution 后端返回 List[Dict] 非 Dict */

export interface GrowthDashboard {
  total_students: number
  total_events: number
  total_snapshots: number
  critical_events: number
  warning_events: number
  bonus_events: number
  dimension_distribution: Array<{ dimension: string; count: number }>
  recent_critical_events: TimelineEventResponse[]
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

// ── 旧版: 7路融合时间轴 ──

export function getGrowthTimeline(studentId: number, semester?: string) {
  return request.get<any, GrowthTimelineResponse>(`/growth/timeline/${studentId}`, {
    params: semester ? { semester } : undefined,
  })
}

export function getMyTimeline(semester?: string) {
  return request.get<any, GrowthTimelineResponse>('/growth/my-timeline', {
    params: semester ? { semester } : undefined,
  })
}

// ── P0 新增: 看板 ──

export function getGrowthDashboard() {
  return request.get<any, GrowthDashboard>('/growth/dashboard')
}

// ── P0 新增: 成长事件 ──

/** POST /events 后端返回 {id, title, dimension} 而非完整 TimelineEventResponse */
export function createTimelineEvent(data: TimelineEventCreate) {
  return request.post<any, { id: number; title: string; dimension: string }>('/growth/events', data)
}

export function listTimelineEvents(params?: {
  student_id?: number
  dimension?: GrowthDimension
  severity?: EventSeverity
  page?: number
  page_size?: number
}) {
  return request.get<any, TimelineEventListResponse>('/growth/events', { params })
}

// ── P0 新增: 全息画像 ──

/** GET /profile/{student_id}?semester_label=2025-2026-2 */
export function getHolisticProfile(studentId: number, semesterLabel?: string) {
  return request.get<any, StudentHolisticProfile>(`/growth/profile/${studentId}`, {
    params: semesterLabel ? { semester_label: semesterLabel } : undefined,
  })
}

// ── P0 新增: 快照 ──

export function generateSnapshot(data: SnapshotGenerateRequest) {
  return request.post<any, GrowthSnapshotResponse>('/growth/snapshots/generate', data)
}

export function listSnapshots(params?: {
  student_id?: number
  snapshot_type?: SnapshotType
  page?: number
  page_size?: number
}) {
  return request.get<any, SnapshotListResponse>('/growth/snapshots', { params })
}

/** PUT /snapshots/{id}/comment 后端返回 {id, teacher_comment} 而非完整快照 */
export function updateTeacherComment(snapshotId: number, data: TeacherCommentUpdate) {
  return request.put<any, { id: number; teacher_comment: string }>(`/growth/snapshots/${snapshotId}/comment`, data)
}

// ═══════════════════════════════════════════════════
// 业务常量 & 映射工具
// ═══════════════════════════════════════════════════

export const EVENT_TYPE_META: Record<string, { label: string; icon: string; color: string }> = {
  behavior: { label: '行为记录', icon: 'Warning', color: '#e6a23c' },
  sanction: { label: '行政处分', icon: 'Stamp', color: '#f56c6c' },
  sanction_revoked: { label: '处分撤销', icon: 'CircleCheckFilled', color: '#67c23a' },
  attendance: { label: '考勤异常', icon: 'AlarmClock', color: '#909399' },
  score_log: { label: '评分变动', icon: 'Tickets', color: '#409eff' },
  recovery: { label: '回血进展', icon: 'RefreshRight', color: '#67c23a' },
  risk_milestone: { label: '风险预警', icon: 'Monitor', color: '#f56c6c' },
  evaluation: { label: '素质评价', icon: 'TrendCharts', color: '#8b5cf6' },
  gap_critical: { label: '断层危机', icon: 'Filter', color: '#f56c6c' },
  gap_warning: { label: '断层预警', icon: 'WarningFilled', color: '#e6a23c' },
  honor: { label: '荣誉表彰', icon: 'Trophy', color: '#67c23a' },
  psych_alert: { label: '心理预警', icon: 'Sunny', color: '#db6d28' },
  pipeline_test_event: { label: '测试事件', icon: 'InfoFilled', color: '#909399' },
}

/** 后端 severity 枚举: info/bonus/warning/critical (兼容旧版 success/danger) */
export const SEVERITY_TAG_TYPE: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  info: 'info',
  bonus: 'success',
  warning: 'warning',
  critical: 'danger',
  // 旧版7路融合时间轴兼容
  success: 'success',
  danger: 'danger',
}

/** 维度元数据 — psychology 不是 psych */
export const DIMENSION_META: Record<string, { label: string; color: string; icon: string }> = {
  academic: { label: '学术', color: '#409eff', icon: 'Reading' },
  attendance: { label: '考勤', color: '#67c23a', icon: 'Calendar' },
  behavior: { label: '行为', color: '#e6a23c', icon: 'Warning' },
  psychology: { label: '心理', color: '#8b5cf6', icon: 'Sunny' },
  activity: { label: '活动', color: '#f56c6c', icon: 'Trophy' },
}

export const EVENT_TYPE_OPTIONS = Object.entries(EVENT_TYPE_META).map(([value, meta]) => ({
  value,
  label: meta.label,
  color: meta.color,
}))

export const DIMENSION_OPTIONS = Object.entries(DIMENSION_META).map(([value, meta]) => ({
  value,
  label: meta.label,
  color: meta.color,
}))

/** Severity 选项 — 对齐后端枚举 */
export const SEVERITY_OPTIONS: Array<{ value: EventSeverity; label: string; color: string }> = [
  { value: 'info', label: '信息', color: '#909399' },
  { value: 'bonus', label: '荣誉', color: '#67c23a' },
  { value: 'warning', label: '预警', color: '#e6a23c' },
  { value: 'critical', label: '危机', color: '#f56c6c' },
]

export function eventTypeLabel(type: string): string {
  return EVENT_TYPE_META[type]?.label || type
}

export function eventTypeIcon(type: string): string {
  return EVENT_TYPE_META[type]?.icon || 'InfoFilled'
}

export function eventTypeColor(type: string): string {
  return EVENT_TYPE_META[type]?.color || '#909399'
}

export function severityTagType(severity: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  return SEVERITY_TAG_TYPE[severity] || 'info'
}

export function severityLabel(severity: string): string {
  const meta: Record<string, string> = {
    info: '信息', bonus: '荣誉', warning: '预警', critical: '危机',
    success: '进步', danger: '严重',  // 旧版兼容
  }
  return meta[severity] || severity
}

export function dimensionLabel(dim: string): string {
  return DIMENSION_META[dim]?.label || dim
}

export function dimensionColor(dim: string): string {
  return DIMENSION_META[dim]?.color || '#909399'
}

/** 快照类型 -> 中文标签 */
export function snapshotTypeLabel(type: string): string {
  return type === 'monthly' ? '月度快照' : '学期快照'
}

/** 五维分数 -> 等级标签 */
export function scoreLevelLabel(score: number): string {
  if (score >= 90) return '优秀'
  if (score >= 75) return '良好'
  if (score >= 60) return '及格'
  return '待提升'
}

/** 五维分数 -> el-tag type */
export function scoreLevelTag(score: number): string {
  if (score >= 90) return 'success'
  if (score >= 75) return 'primary'
  if (score >= 60) return 'warning'
  return 'danger'
}

/** 五维分数 -> 颜色 */
export function scoreColor(score: number): string {
  if (score >= 90) return '#67c23a'
  if (score >= 75) return '#409eff'
  if (score >= 60) return '#e6a23c'
  return '#f56c6c'
}

// ═══════════════════════════════════════════════════
// Demo Data (后端不可用时降级, HolisticProfileCard 依赖)
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
    total_events: 8,
    timeline: [
      {
        event_id: 'evaluation_1',
        event_type: 'evaluation',
        occurred_at: fmt(addDays(baseDate, 33)),
        event_date: fmtDate(addDays(baseDate, 33)),
        title: '期末综合评价完成',
        description: '2025-2026-2 学期综合评价等级：B（良好）。',
        severity: 'bonus',
        related_id: 100,
        source_table: 'evaluation_scores',
      },
      {
        event_id: 'recovery_2',
        event_type: 'recovery',
        occurred_at: fmt(addDays(baseDate, 30)),
        event_date: fmtDate(addDays(baseDate, 30)),
        title: '回血进展：行为改善中',
        description: '连续 12 天无新的违纪记录，回血进度 60%。',
        severity: 'bonus',
        related_id: 42,
        source_table: 'recovery_states',
      },
      {
        event_id: 'sanction_1',
        event_type: 'sanction',
        occurred_at: fmt(addDays(baseDate, 22)),
        event_date: fmtDate(addDays(baseDate, 22)),
        title: '行政处分：警告',
        description: '因携带手机进校被给予警告处分。',
        severity: 'critical',
        related_id: 42,
        source_table: 'discipline_sanctions',
      },
      {
        event_id: 'behavior_2',
        event_type: 'behavior',
        occurred_at: fmt(addDays(baseDate, 22)),
        event_date: fmtDate(addDays(baseDate, 22)),
        title: '行为提醒：携带手机进校',
        description: '在上午课堂中被发现使用手机。',
        severity: 'critical',
        related_id: 156,
        source_table: 'discipline_records',
      },
      {
        event_id: 'risk_milestone_1',
        event_type: 'risk_milestone',
        occurred_at: fmt(addDays(baseDate, 20)),
        event_date: fmtDate(addDays(baseDate, 20)),
        title: 'RDI 风险预警：需要关注',
        description: '综合风险指数 Z=2.1，行为维度偏离 +1.8σ。',
        severity: 'warning',
        related_id: 15,
        source_table: 'risk_warnings',
      },
      {
        event_id: 'score_log_2',
        event_type: 'score_log',
        occurred_at: fmt(addDays(baseDate, 15)),
        event_date: fmtDate(addDays(baseDate, 15)),
        title: '道德品质 -3 分',
        description: '课堂使用手机被扣分。',
        severity: 'warning',
        related_id: 1140,
        source_table: 'score_logs',
      },
      {
        event_id: 'recovery_1',
        event_type: 'recovery',
        occurred_at: fmt(addDays(baseDate, 7)),
        event_date: fmtDate(addDays(baseDate, 7)),
        title: '回血完成：历史扣分已恢复',
        description: '5月份行为表现良好，扣分已成功恢复。',
        severity: 'bonus',
        related_id: 30,
        source_table: 'recovery_states',
      },
      {
        event_id: 'evaluation_0',
        event_type: 'evaluation',
        occurred_at: fmt(addDays(baseDate, 1)),
        event_date: fmtDate(addDays(baseDate, 1)),
        title: '学期初评价基线建立',
        description: '基线分 100，五维权重已初始化。',
        severity: 'info',
        related_id: null,
        source_table: 'evaluation_scores',
      },
    ],
  }
}
