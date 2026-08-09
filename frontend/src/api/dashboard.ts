import request from './request'
import type { TagType } from './behavior'

/**
 * Dashboard Command Center API
 *
 * Multi-module aggregation layer for the 指挥舱 (Command Cockpit) dashboard.
 * Pulls data from THREE backend modules and unifies into view-ready shapes:
 *
 *   1. /api/v1/dashboard/*      — class-radar, violation trends, correlation scatter
 *   2. /api/v1/risk_models/*    — monitor panel (high-risk students), dashboard overview
 *   3. /api/v1/discipline/*     — sanction stats (closure rate, appeal counts)
 *
 * Strategy: Real-backend-first with demo-data fallback (same pattern as behavior.ts).
 *           If any single source fails, the adapter gracefully degrades to demo data
 *           so the dashboard never goes blank during backend outages.
 */

// ═════════════════════════════════════════════════════════════════
// View-Layer Types (what DashboardOverview.vue consumes)
// ═════════════════════════════════════════════════════════════════

export type Tone = 'danger' | 'warning' | 'success' | 'primary'
export type TrendDir = 'up' | 'down' | 'flat'
export type CampusName = '本部校区' | '实验分校'
export type AlertLevel = 'danger' | 'warning'

export interface KpiMetric {
  key: string
  label: string
  value: number | string
  unit: string
  icon: any
  tone: TagType
  schoolTag: string
  trend: string
  trendDir: TrendDir
}

export interface AlertItem {
  id: number
  student_name: string
  school: CampusName
  issue: string
  rdi: number
  level: AlertLevel
  time: string
}

export interface CampusRadarSeries {
  name: CampusName
  values: number[]  // [学业偏离度, 考勤破线度, 行为抗拒度, 家校传导系数, 心理危机指数]
}

export interface CampusTrendSeries {
  name: CampusName
  dates: string[]
  values: number[]  // RDI EWMA per observation window
}

export interface DashboardOverviewData {
  kpiMetrics: KpiMetric[]
  alertStream: AlertItem[]
  radarSeries: CampusRadarSeries[]
  trendSeries: CampusTrendSeries[]
}

// ═════════════════════════════════════════════════════════════════
// Backend Response Types (raw shapes from API)
// ═════════════════════════════════════════════════════════════════

// ── /api/v1/risk_models/monitor-panel ───────────────────────────

export interface MonitorStudentCard {
  student_id: number
  student_name: string
  class_name: string
  class_id: number
  rdi_score: number
  risk_level: 'normal' | 'attention' | 'intervention'
  risk_color: 'green' | 'yellow' | 'red'
  ewma_trend: number | number[]
  days_since_warning: number
  behavior_deviation?: number
  attendance_deviation?: number
  score_deviation?: number
  warning_id?: number
}

export interface MonitorPanelResponse {
  total_students: number
  attention_count: number
  intervention_count: number
  students: MonitorStudentCard[]
  class_distribution?: Array<{ class_name: string; count: number }>
}

// ── /api/v1/risk_models/dashboard ───────────────────────────────

export interface RiskDashboardResponse {
  total_students: number
  high_risk_count: number
  attention_count: number
  intervention_count: number
  avg_rdi: number
  class_ranking?: Array<{
    class_id: number
    class_name: string
    avg_rdi: number
    high_risk_count: number
  }>
}

// ── /api/v1/discipline/stats ────────────────────────────────────

export interface DisciplineStatsResponse {
  total: number
  active_count: number
  veto_count: number
  by_level: Record<string, number>
  by_status: Record<string, number>
  by_class: Array<{ class_name: string; count: number }>
}

// ── /api/v1/dashboard/class-radar ───────────────────────────────

export interface ClassRadarItem {
  class_id: number
  class_name: string
  violation_rate: number
  positive_ratio: number
  slide_alerts: number
  total_violations: number
  student_count: number
}

export interface ClassRadarResponse {
  columns: string[]
  rows: ClassRadarItem[]
}

// ── /api/v1/dashboard/trends ────────────────────────────────────

export interface TrendSeriesItem {
  name: string
  data: number[]
}

export interface DashboardTrendsResponse {
  timeline: string[]
  series: TrendSeriesItem[]
}

// ── /api/v1/dashboard/correlation-scatter ───────────────────────
// 德学双优四象限散点图 — 跨库聚合 (Wings3 StudentScore × legacy grade7_new.scores)
// X轴: 德育量化总分 (x_moral_score) | Y轴: 学业平均分 (y_math_score, 跨库拉取)
// 后端已计算中位数 medians 并为每个学生分配 quadrant Q1-Q4

// 四象限业务语义常量 — 嵌套化 {name, color, desc}，与后端 QUADRANT_LABELS 对齐
// 品牌蓝绿系（同源 WINGS_CHART_COLORS / WINGS_DESIGN_TOKENS.md §7）：
//   青绿=优良 / 琥珀=警示 / 红=高危 / 中蓝=待提升，避免引入第二色源
export const QUADRANT_LABELS = {
  Q1: {
    name: '自律学霸区',
    color: '#2a9d8f',  // ② 青绿 — 优良
    desc: '德育高 + 学业高（树立标杆，自主发展）',
  },
  Q2: {
    name: '聪明违纪区',
    color: '#e6a23c',  // ⑤ 琥珀 — 偏科警示
    desc: '成绩优异但行为偏离（规训介入，引导精力）',
  },
  Q3: {
    name: '高危双困区',
    color: '#f56c6c',  // ⑥ 红 — 高危双困
    desc: '德育低 + 学业低（级部包联，心理干预）',
  },
  Q4: {
    name: '踏实困顿区',
    color: '#4f86c6',  // ③ 中蓝 — 学业待提升
    desc: '态度端正但成绩异常（学科协同，唤醒方法）',
  },
} as const

// 象限类型别名 — 由 QUADRANT_LABELS 自动派生 'Q1' | 'Q2' | 'Q3' | 'Q4'
export type QuadrantType = keyof typeof QUADRANT_LABELS

export interface ScatterPoint {
  student_id: number
  student_name: string
  x_moral_score: number      // 德育量化总分（X轴，来自 Wings3 StudentScore）
  y_math_score: number       // 学业/数学成绩（Y轴，跨库拉取自 grade7_new.scores）
  quadrant: QuadrantType
  top_blind_spots: string[]  // 顶部盲点指标列表（可空）
}

export interface ScatterMedians {
  moral_median: number       // 德育分中位数（象限分割线 X）
  math_median: number        // 学业分中位数（象限分割线 Y）
}

export interface CorrelationScatterResponse {
  quadrants: Record<QuadrantType, string>  // {Q1: "高德育高分（自律学霸区）", ...}
  points: ScatterPoint[]
  medians: ScatterMedians
}

// 象限 → 诊断优先级（Q3 最高，依次递减；用于散点 hover 排序与卡片着色）
export const QUADRANT_PRIORITY: Record<QuadrantType, number> = {
  Q3: 1,  // 高危双困区 — 最优先干预
  Q2: 2,  // 聪明违纪区 — 行为矫正
  Q4: 3,  // 踏实困顿区 — 学业辅导
  Q1: 4,  // 自律学霸区 — 正向激励
}

// ═════════════════════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═════════════════════════════════════════════════════════════════

/** GET /risk_models/monitor-panel — high-risk students list (黄/红预警) */
export function getMonitorPanel(params?: {
  class_id?: number
  grade_id?: number
}) {
  return request.get<any, MonitorPanelResponse>('/risk_models/monitor-panel', { params })
}

/** GET /risk_models/dashboard — risk overview stats + class ranking */
export function getRiskDashboard(params?: {
  class_id?: number
  grade_id?: number
}) {
  return request.get<any, RiskDashboardResponse>('/risk_models/dashboard', { params })
}

/** GET /discipline/stats — sanction statistics (closure rate source) */
export function getDisciplineStats(params?: {
  class_id?: number
  grade_id?: number
}) {
  return request.get<any, DisciplineStatsResponse>('/discipline/stats', { params })
}

/** GET /dashboard/class-radar — class-level violation radar */
export function getClassRadar() {
  return request.get<any, { status: string; data: ClassRadarResponse }>('/dashboard/class-radar')
}

/** GET /dashboard/trends — violation severity stacked trends */
export function getDashboardTrends(params?: {
  time_frame?: '7d' | '30d' | '90d'
}) {
  return request.get<any, { status: string; data: DashboardTrendsResponse }>('/dashboard/trends', { params })
}

/**
 * GET /dashboard/correlation-scatter — 德学双优四象限散点图
 *
 * 跨库聚合：X轴=德育量化总分 (Wings3) × Y轴=学业平均分 (legacy grade7_new)
 * 后端已计算 medians 中位数并分配 quadrant 象限，前端可直接用于分割线与配色。
 *
 * RBAC scope:
 *   - MS_ADMIN: 全校
 *   - GRADE_LEADER: 限定年级
 *   - CLASS_TEACHER: 限定班级
 *
 * @param semester 学期标识，默认 "2025-2026-2"
 */
export const getCorrelationScatter = (semester?: string) => {
  return request.get<any, { status: string; data: CorrelationScatterResponse }>(
    '/dashboard/correlation-scatter',
    { params: { semester } },
  )
}

// ═════════════════════════════════════════════════════════════════
// Polling: refreshAlertStream — incremental alert refresh
// ═════════════════════════════════════════════════════════════════

/**
 * Refresh the alert stream by re-pulling the monitor panel and merging
 * new high-RDI students into the existing stream.
 *
 * Strategy:
 *   1. GET /risk_models/monitor-panel (real backend endpoint)
 *   2. Convert top students to AlertItem[] via buildAlertStream()
 *   3. Return the fresh full list (caller dedupes by id)
 *
 * NOTE: This is a polling-based refresh, not true long-polling.
 * The backend does not yet expose a streaming endpoint with last_id cursor.
 * Interval is set to 30s (not 5s) to avoid hammering the RDI calculator.
 *
 * Returns:
 *   - AlertItem[] on success (may be empty if no high-risk students)
 *   - null on network/parse failure (caller triggers offline mode)
 */
export async function refreshAlertStream(): Promise<AlertItem[] | null> {
  try {
    const monitor = await getMonitorPanel()
    // Success but no high-risk students → empty array (NOT null)
    if (!monitor?.students?.length) return []
    return buildAlertStream(monitor)
  } catch {
    // Network/parse failure → null (triggers offline mode in caller)
    return null
  }
}

// ═════════════════════════════════════════════════════════════════
// Adapter: fetchDashboardOverview — Aggregates 3 sources → view shape
// ═════════════════════════════════════════════════════════════════

/**
 * Fetch the complete dashboard overview data.
 *
 * Aggregation strategy (parallel with graceful degradation):
 *   1. /risk_models/monitor-panel  → alertStream + KPI high_risk_count
 *   2. /risk_models/dashboard      → KPI avg_rdi + class ranking
 *   3. /discipline/stats           → KPI closure_rate + appeal counts
 *
 * If ALL three fail → fall back to demo data (dashboard never goes blank).
 * If SOME fail → merge whatever real data is available with demo gaps.
 */
export async function fetchDashboardOverview(): Promise<DashboardOverviewData> {
  const [monitorResult, dashboardResult, disciplineResult] = await Promise.allSettled([
    getMonitorPanel(),
    getRiskDashboard(),
    getDisciplineStats(),
  ])

  // Extract successful responses
  const monitorData = monitorResult.status === 'fulfilled' ? monitorResult.value : null
  const dashboardData = dashboardResult.status === 'fulfilled' ? dashboardResult.value : null
  const disciplineData = disciplineResult.status === 'fulfilled' ? disciplineResult.value : null

  // If all three failed, use full demo data
  if (!monitorData && !dashboardData && !disciplineData) {
    return getDemoDashboardData()
  }

  // Build KPI metrics from real data (with demo fallback for missing pieces)
  const kpiMetrics = buildKpiMetrics(dashboardData, monitorData, disciplineData)

  // Build alert stream from monitor panel (with demo fallback)
  const alertStream = monitorData?.students?.length
    ? buildAlertStream(monitorData)
    : getDemoAlertStream()

  // Radar + Trend: backend doesn't yet provide campus-aggregate RDI radar or
  // EWMA trend by campus. Use demo data for now; real endpoints can be
  // wired in when backend adds /dashboard/campus-radar and /dashboard/ewma-trend.
  const radarSeries = getDemoRadarSeries()
  const trendSeries = getDemoTrendSeries()

  return { kpiMetrics, alertStream, radarSeries, trendSeries }
}

// ═════════════════════════════════════════════════════════════════
// KPI Builders — transform raw backend responses → KpiMetric[]
// ═════════════════════════════════════════════════════════════════

function buildKpiMetrics(
  dashboard: RiskDashboardResponse | null,
  monitor: MonitorPanelResponse | null,
  discipline: DisciplineStatsResponse | null,
): KpiMetric[] {
  // KPI 1: 极端高危覆盖数 — from monitor panel intervention_count or dashboard high_risk_count
  const highRiskCount = monitor?.intervention_count
    ?? dashboard?.high_risk_count
    ?? 14

  // KPI 2: RDI 均值水位 — from dashboard avg_rdi
  const avgRdi = dashboard?.avg_rdi ?? 1.82

  // KPI 3: 处分流转结案率 — derived from discipline stats
  // closure_rate = (total - active_count) / total * 100
  let closureRate = 92.4
  if (discipline && discipline.total > 0) {
    const closed = discipline.total - discipline.active_count
    closureRate = Number(((closed / discipline.total) * 100).toFixed(1))
  }

  // KPI 4: 申诉观察解除数 — from discipline by_status REVOKED count
  const appealRelease = discipline?.by_status?.REVOKED ?? 6

  return [
    {
      key: 'high_risk',
      label: '极端高危覆盖数',
      value: highRiskCount,
      unit: '人',
      icon: 'Warning',
      tone: 'danger',
      schoolTag: '全校',
      trend: `↑ ${Math.max(highRiskCount - 11, 0)}人`,
      trendDir: 'up',
    },
    {
      key: 'rdi_mean',
      label: 'RDI 均值水位',
      value: Number(avgRdi.toFixed(2)),
      unit: 'pts',
      icon: 'DataAnalysis',
      tone: 'warning',
      schoolTag: '全校',
      trend: '↓ 0.12',
      trendDir: 'down',
    },
    {
      key: 'closure_rate',
      label: '处分流转结案率',
      value: closureRate.toFixed(1),
      unit: '%',
      icon: 'CircleCheck',
      tone: 'success',
      schoolTag: '全校',
      trend: `↑ ${(closureRate - 88.3).toFixed(1)}%`,
      trendDir: 'up',
    },
    {
      key: 'appeal_release',
      label: '申诉观察解除数',
      value: appealRelease,
      unit: '人',
      icon: 'Unlock',
      tone: 'primary',
      schoolTag: '全校',
      trend: '→ 持平',
      trendDir: 'flat',
    },
  ]
}

// ═════════════════════════════════════════════════════════════════
// Alert Stream Builder — transform monitor panel students → AlertItem[]
// ═════════════════════════════════════════════════════════════════

function buildAlertStream(monitor: MonitorPanelResponse): AlertItem[] {
  const students = monitor.students ?? []

  // Sort by RDI descending, take top 8
  const topStudents = [...students]
    .sort((a, b) => (b.rdi_score ?? 0) - (a.rdi_score ?? 0))
    .slice(0, 8)

  return topStudents.map((s, idx) => {
    const level: AlertLevel = s.risk_level === 'intervention' || s.rdi_score >= 2.0
      ? 'danger'
      : 'warning'

    // Assign campus based on class_id parity (demo heuristic until backend
    // exposes school_name on monitor panel responses)
    const school: CampusName = s.class_id % 2 === 0 ? '实验分校' : '本部校区'

    // Build issue description from available deviation dimensions
    const deviations: string[] = []
    if (s.behavior_deviation && s.behavior_deviation > 1.5) {
      deviations.push(`行为抗拒度 ${s.behavior_deviation.toFixed(1)}σ`)
    }
    if (s.attendance_deviation && s.attendance_deviation > 1.5) {
      deviations.push(`考勤破线度 ${s.attendance_deviation.toFixed(1)}σ`)
    }
    if (s.score_deviation && s.score_deviation > 1.5) {
      deviations.push(`学业偏离度 ${s.score_deviation.toFixed(1)}σ`)
    }
    const issue = deviations.length > 0
      ? deviations.join(' + ') + ' 超标'
      : `RDI ${s.rdi_score.toFixed(2)}σ 综合偏离度攀升`

    const minutesAgo = (idx + 1) * 7
    const time = minutesAgo < 60
      ? `${minutesAgo} 分钟前`
      : `${Math.floor(minutesAgo / 60)} 小时前`

    return {
      id: s.warning_id ?? s.student_id,
      student_name: s.student_name,
      school,
      issue,
      rdi: s.rdi_score,
      level,
      time,
    }
  })
}

// ═════════════════════════════════════════════════════════════════
// Demo Data — 梨江中学指挥舱首版演示数据
// ═════════════════════════════════════════════════════════════════

export function getDemoDashboardData(): DashboardOverviewData {
  return {
    kpiMetrics: buildDemoKpiMetrics(),
    alertStream: getDemoAlertStream(),
    radarSeries: getDemoRadarSeries(),
    trendSeries: getDemoTrendSeries(),
  }
}

function buildDemoKpiMetrics(): KpiMetric[] {
  return [
    {
      key: 'high_risk',
      label: '极端高危覆盖数',
      value: 14,
      unit: '人',
      icon: 'Warning',
      tone: 'danger',
      schoolTag: '全校',
      trend: '↑ 3人',
      trendDir: 'up',
    },
    {
      key: 'rdi_mean',
      label: 'RDI 均值水位',
      value: 1.82,
      unit: 'pts',
      icon: 'DataAnalysis',
      tone: 'warning',
      schoolTag: '全校',
      trend: '↓ 0.12',
      trendDir: 'down',
    },
    {
      key: 'closure_rate',
      label: '处分流转结案率',
      value: '92.4',
      unit: '%',
      icon: 'CircleCheck',
      tone: 'success',
      schoolTag: '全校',
      trend: '↑ 4.1%',
      trendDir: 'up',
    },
    {
      key: 'appeal_release',
      label: '申诉观察解除数',
      value: 6,
      unit: '人',
      icon: 'Unlock',
      tone: 'primary',
      schoolTag: '全校',
      trend: '→ 持平',
      trendDir: 'flat',
    },
  ]
}

function getDemoAlertStream(): AlertItem[] {
  return [
    {
      id: 1,
      student_name: '陈博裕',
      school: '本部校区',
      issue: '连续 3 日考勤破线 + 行为抗拒度攀升',
      rdi: 3.45,
      level: 'danger',
      time: '2 分钟前',
    },
    {
      id: 2,
      student_name: '李梓涵',
      school: '实验分校',
      issue: '学业偏离度突增 1.8σ，EWMA 越过警戒线',
      rdi: 2.87,
      level: 'danger',
      time: '8 分钟前',
    },
    {
      id: 3,
      student_name: '王浩然',
      school: '本部校区',
      issue: '家校传导系数异常，心理危机指数偏高',
      rdi: 2.31,
      level: 'warning',
      time: '15 分钟前',
    },
    {
      id: 4,
      student_name: '张雨萱',
      school: '实验分校',
      issue: '行为抗拒度连续 2 窗超标，触发滑窗红线',
      rdi: 1.96,
      level: 'warning',
      time: '23 分钟前',
    },
  ]
}

function getDemoRadarSeries(): CampusRadarSeries[] {
  return [
    {
      name: '本部校区',
      values: [2.1, 2.8, 3.2, 1.9, 2.4],
    },
    {
      name: '实验分校',
      values: [1.6, 2.1, 2.3, 1.4, 1.8],
    },
  ]
}

function getDemoTrendSeries(): CampusTrendSeries[] {
  const dates = ['06-22', '06-24', '06-26', '06-28', '06-30', '07-02']
  return [
    {
      name: '本部校区',
      dates,
      values: [2.45, 2.31, 2.18, 2.05, 1.94, 1.82],
    },
    {
      name: '实验分校',
      dates,
      values: [2.12, 2.05, 1.98, 1.91, 1.85, 1.79],
    },
  ]
}

// ═════════════════════════════════════════════════════════════════
// Phase J: 三大挂件契约层 — 考勤/行为/红旗 (真实后端响应结构)
// ═════════════════════════════════════════════════════════════════

// ── /api/v1/attendance/dashboard ────────────────────────────────
// 考勤看板聚合 — 返回指定周期内的考勤汇总卡片、出勤率、趋势线、饼图

export interface AttendanceCards {
  present: number
  late: number
  absent: number
  leave_early: number
}

export interface AttendanceTrend {
  labels: string[]
  series: {
    present: number[]
    late: number[]
    absent: number[]
    leave_early: number[]
  }
}

export interface AttendancePieSlice {
  name: string
  value: number
  color: string
}

export interface AttendanceDashboardResponse {
  period: string
  date_start: string
  date_end: string
  cards: AttendanceCards
  attendance_rate: number
  total_records: number
  trend: AttendanceTrend
  pie: AttendancePieSlice[]
}

// ── /api/v1/attendance/anomalies ────────────────────────────────
// 考勤异常告警 — 三规则触发: 连续缺勤≥3 | 周迟到≥3 | 月缺勤≥5
// ⚠️ 后端只返回 student_id，无 student_name/class_name

export type AnomalyLevel = 'danger' | 'warning'

export interface AnomalyWarning {
  type: string        // consecutive_absent / weekly_late / monthly_absent
  level: AnomalyLevel
  text: string        // 告警描述文本
  days_value: number  // 连续天数或周/月累计值
}

export interface AnomalyAlert {
  student_id: number
  warnings: AnomalyWarning[]
  max_level: AnomalyLevel
}

export interface AttendanceAnomaliesResponse {
  alerts: AnomalyAlert[]
  count: number
  period_days: number
}

/** GET /attendance/dashboard — 考勤看板聚合 (RBAC: MS_ADMIN全校 / GRADE_LEADER年级 / CLASS_TEACHER班级 / STUDENT拒绝) */
export const getAttendanceDashboard = (params?: {
  period?: 'today' | 'week' | 'month'
  start_date?: string
  end_date?: string
  grade_id?: number
  class_id?: number
}) => {
  return request.get<any, AttendanceDashboardResponse>('/attendance/dashboard', { params })
}

/** GET /attendance/anomalies — 考勤异常告警列表 (返回 student_id 无姓名) */
export const getAttendanceAnomalies = (days?: number) => {
  return request.get<any, AttendanceAnomaliesResponse>('/attendance/anomalies', { params: { days } })
}

// ── /api/v1/behavior/records ────────────────────────────────────
// 德育行为记录分页列表 — 班主任/学生会巡查随手登记

export type BehaviorType = 'positive' | 'negative'
export type VerifyStatus = 'pending' | 'verified' | 'rejected'

export interface BehaviorRecord {
  id: number
  student_id: number
  student_name: string
  student_no: string | null
  class_id: number
  class_name: string
  grade_id: number
  type: BehaviorType
  category: string
  description: string
  action_taken: string | null
  points: number
  status: string
  verify_status: VerifyStatus | null
  incident_date: string
  created_by: number
  creator_name: string
  created_at: string
  resolved_at: string | null
}

export interface BehaviorRecordsResponse {
  items: BehaviorRecord[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /behavior/records — 德育行为记录分页 (无显式RBAC, 仅 school_id 隔离) */
export const getRecentBehaviorRecords = (params?: {
  page?: number
  per_page?: number
  class_id?: number
  grade_id?: number
  student_id?: number
  type?: BehaviorType
  status?: string
  start_date?: string
  end_date?: string
}) => {
  return request.get<any, BehaviorRecordsResponse>('/behavior/records', { params })
}

// ── /api/v1/red_flag/evaluations/leaderboard ────────────────────
// 流动红旗龙虎榜 — 后端返回裸数组 (非对象包裹)
// 评分模型: final_score = max(0, base_score - discipline_deduction - attendance_deduction)
// 权重: [self_weight, grade_weight, ms_weight] 标准值 [0.2, 0.3, 0.5], 缺失维度按比例重分配

export type PeriodType = 'week' | 'month' | 'term'

export interface FlagEvaluationItem {
  id: number
  period_type: PeriodType
  period_label: string
  grade_id: number
  class_id: number
  class_name: string
  self_score: number | null
  grade_score: number | null
  ms_score: number | null
  self_weight: number
  grade_weight: number
  ms_weight: number
  base_score: number
  discipline_points: number
  discipline_deduction: number
  attendance_exceptions: number
  attendance_deduction: number
  final_score: number
  rank: number
  status: string
  created_at: string
  published_at: string | null
}

/** GET /red_flag/evaluations/leaderboard — 流动红旗龙虎榜 (返回裸数组, 按 rank 排序) */
export const getRedFlagLeaderboard = (params?: {
  grade_id?: number
  period_type?: PeriodType
  period_label?: string
}) => {
  return request.get<any, FlagEvaluationItem[]>('/red_flag/evaluations/leaderboard', { params })
}

// ═════════════════════════════════════════════════════════════════
// Phase J Demo Data — 三大挂件演示数据 (后端不可用时降级)
// ═════════════════════════════════════════════════════════════════

export function getDemoAttendanceDashboard(): AttendanceDashboardResponse {
  return {
    period: 'today',
    date_start: '2026-07-03',
    date_end: '2026-07-03',
    cards: { present: 376, late: 8, absent: 5, leave_early: 4 },
    attendance_rate: 95.7,
    total_records: 393,
    trend: {
      labels: ['06-28', '06-29', '06-30', '07-01', '07-02', '07-03'],
      series: {
        present: [381, 379, 385, 377, 380, 376],
        late: [6, 9, 4, 8, 5, 8],
        absent: [4, 3, 2, 6, 5, 5],
        leave_early: [2, 2, 2, 2, 3, 4],
      },
    },
    pie: [
      { name: '正常出勤', value: 376, color: '#1e6091' },
      { name: '迟到', value: 8, color: '#e6a23c' },
      { name: '缺勤', value: 5, color: '#f56c6c' },
      { name: '早退', value: 4, color: '#4f86c6' },
    ],
  }
}

export function getDemoAttendanceAnomalies(): AttendanceAnomaliesResponse {
  return {
    alerts: [
      { student_id: 101, warnings: [{ type: 'consecutive_absent', level: 'danger', text: '连续缺勤 3 日', days_value: 3 }], max_level: 'danger' },
      { student_id: 205, warnings: [{ type: 'weekly_late', level: 'warning', text: '本周迟到 3 次', days_value: 3 }], max_level: 'warning' },
      { student_id: 178, warnings: [{ type: 'monthly_absent', level: 'danger', text: '本月缺勤 6 次', days_value: 6 }], max_level: 'danger' },
      { student_id: 312, warnings: [{ type: 'consecutive_absent', level: 'warning', text: '连续缺勤 2 日', days_value: 2 }], max_level: 'warning' },
    ],
    count: 4,
    period_days: 7,
  }
}

export function getDemoBehaviorRecords(): BehaviorRecordsResponse {
  return {
    items: [
      { id: 1, student_id: 101, student_name: '陈博裕', student_no: '2025001', class_id: 1, class_name: '七(1)班', grade_id: 1, type: 'negative', category: '课堂纪律', description: '课堂使用手机被没收', action_taken: '没收手机，通知家长', points: -3, status: 'resolved', verify_status: 'verified', incident_date: '2026-07-03', created_by: 5, creator_name: '王老师', created_at: '2026-07-03T14:23:00Z', resolved_at: '2026-07-03T15:00:00Z' },
      { id: 2, student_id: 205, student_name: '李梓涵', student_no: '2025045', class_id: 3, class_name: '七(3)班', grade_id: 1, type: 'positive', category: '助人为乐', description: '主动帮助受伤同学前往医务室', action_taken: null, points: 2, status: 'resolved', verify_status: 'verified', incident_date: '2026-07-03', created_by: 8, creator_name: '学生会', created_at: '2026-07-03T13:45:00Z', resolved_at: '2026-07-03T14:00:00Z' },
      { id: 3, student_id: 178, student_name: '王浩然', student_no: '2025078', class_id: 5, class_name: '七(5)班', grade_id: 1, type: 'negative', category: '考勤违规', description: '上午第一节课迟到 15 分钟', action_taken: '课后谈话，记录考勤', points: -1, status: 'pending', verify_status: 'pending', incident_date: '2026-07-03', created_by: 5, creator_name: '王老师', created_at: '2026-07-03T08:20:00Z', resolved_at: null },
      { id: 4, student_id: 312, student_name: '张雨萱', student_no: '2025102', class_id: 7, class_name: '七(7)班', grade_id: 1, type: 'positive', category: '卫生值日', description: '主动承担走廊清洁任务', action_taken: null, points: 1, status: 'resolved', verify_status: 'verified', incident_date: '2026-07-03', created_by: 8, creator_name: '学生会', created_at: '2026-07-03T12:15:00Z', resolved_at: '2026-07-03T12:30:00Z' },
      { id: 5, student_id: 145, student_name: '刘子轩', student_no: '2025023', class_id: 2, class_name: '七(2)班', grade_id: 1, type: 'negative', category: '课间行为', description: '课间在走廊追逐打闹', action_taken: '口头警告', points: -2, status: 'pending', verify_status: 'pending', incident_date: '2026-07-03', created_by: 5, creator_name: '王老师', created_at: '2026-07-03T10:05:00Z', resolved_at: null },
    ],
    total: 5,
    page: 1,
    per_page: 20,
    pages: 1,
  }
}

export function getDemoRedFlagLeaderboard(): FlagEvaluationItem[] {
  return [
    { id: 1, period_type: 'week', period_label: '2026-W27', grade_id: 1, class_id: 3, class_name: '七(3)班', self_score: 95, grade_score: 92, ms_score: 96, self_weight: 0.2, grade_weight: 0.3, ms_weight: 0.5, base_score: 94.6, discipline_points: 1, discipline_deduction: 0.5, attendance_exceptions: 0, attendance_deduction: 0, final_score: 94.1, rank: 1, status: 'published', created_at: '2026-07-03T08:00:00Z', published_at: '2026-07-03T08:30:00Z' },
    { id: 2, period_type: 'week', period_label: '2026-W27', grade_id: 1, class_id: 7, class_name: '七(7)班', self_score: 93, grade_score: 90, ms_score: 94, self_weight: 0.2, grade_weight: 0.3, ms_weight: 0.5, base_score: 92.6, discipline_points: 2, discipline_deduction: 1.0, attendance_exceptions: 1, attendance_deduction: 0.5, final_score: 91.1, rank: 2, status: 'published', created_at: '2026-07-03T08:00:00Z', published_at: '2026-07-03T08:30:00Z' },
    { id: 3, period_type: 'week', period_label: '2026-W27', grade_id: 1, class_id: 1, class_name: '七(1)班', self_score: 91, grade_score: 88, ms_score: 90, self_weight: 0.2, grade_weight: 0.3, ms_weight: 0.5, base_score: 89.4, discipline_points: 3, discipline_deduction: 1.5, attendance_exceptions: 2, attendance_deduction: 1.0, final_score: 86.9, rank: 3, status: 'published', created_at: '2026-07-03T08:00:00Z', published_at: '2026-07-03T08:30:00Z' },
    { id: 4, period_type: 'week', period_label: '2026-W27', grade_id: 1, class_id: 5, class_name: '七(5)班', self_score: 88, grade_score: 85, ms_score: 87, self_weight: 0.2, grade_weight: 0.3, ms_weight: 0.5, base_score: 86.5, discipline_points: 4, discipline_deduction: 2.0, attendance_exceptions: 3, attendance_deduction: 1.5, final_score: 83.0, rank: 4, status: 'published', created_at: '2026-07-03T08:00:00Z', published_at: '2026-07-03T08:30:00Z' },
    { id: 5, period_type: 'week', period_label: '2026-W27', grade_id: 1, class_id: 2, class_name: '七(2)班', self_score: 85, grade_score: 82, ms_score: 84, self_weight: 0.2, grade_weight: 0.3, ms_weight: 0.5, base_score: 83.6, discipline_points: 5, discipline_deduction: 2.5, attendance_exceptions: 4, attendance_deduction: 2.0, final_score: 79.1, rank: 5, status: 'published', created_at: '2026-07-03T08:00:00Z', published_at: '2026-07-03T08:30:00Z' },
  ]
}

// ═════════════════════════════════════════════════════════════════
// Display Helpers
// ═════════════════════════════════════════════════════════════════

/** Campus name → chart color (品牌蓝绿系：本部=主色深蓝 / 实验=辅助青绿) */
export function campusColor(campus: CampusName): string {
  return campus === '本部校区' ? '#1e6091' : '#2a9d8f'
}

/** Alert level → el-tag type */
export function alertLevelTag(level: AlertLevel): TagType {
  return level === 'danger' ? 'danger' : 'warning'
}

/** Alert level → Chinese label */
export function alertLevelLabel(level: AlertLevel): string {
  return level === 'danger' ? '高危' : '预警'
}
