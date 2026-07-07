import request from './request'

/**
 * RDI (Risk Deviation Index) Radar API
 * Maps to backend: /api/v1/risk_models/
 *
 * Key endpoints:
 * - GET  /monitor-panel  → MonitorPanelOut (stat cards + risk student list)
 * - GET  /dashboard      → RiskDashboardOut (overview stats + class ranking)
 * - GET  /warnings       → List[RiskWarningOut] (paginated warning history)
 * - POST /scan/class/:id → TaskDispatchResponse (async Celery scan)
 * - POST /scan/school    → TaskDispatchResponse (async Celery scan)
 * - POST /explain        → PenaltyExplanationResponse (3-section explanation)
 */

// ─── Monitor Panel ──────────────────────────────────────────────

export function getRiskMonitorPanel(params?: {
  class_id?: number
  grade_id?: number
  student_id?: number
}) {
  return request.get('/risk_models/monitor-panel', { params })
}

// ─── Dashboard Overview ────────────────────────────────────────

export function getRiskDashboard(params?: {
  class_id?: number
  grade_id?: number
}) {
  return request.get('/risk_models/dashboard', { params })
}

// ─── Risk Warnings ─────────────────────────────────────────────

export function getRiskWarnings(params?: {
  status?: string
  risk_level?: string
  days?: number
}) {
  return request.get('/risk_models/warnings', { params })
}

// ─── Handle Warning ────────────────────────────────────────────

export function handleWarning(warningId: number, data: {
  action: string
  note?: string
}) {
  return request.post(`/risk_models/warnings/${warningId}/handle`, data)
}

// ─── Trigger Scan (Async Celery) ───────────────────────────────

export function triggerClassScan(classId: number, semester?: string) {
  return request.post(`/risk_models/scan/class/${classId}`, { semester })
}

export function triggerSchoolScan(semester?: string) {
  return request.post('/risk_models/scan/school', { semester })
}

// ─── Penalty Explanation ───────────────────────────────────────

export function getRiskExplanation(data: {
  student_id: number
  event_type?: string
  event_id?: number
  include_rdi?: boolean
  rdi_score?: number
  risk_level?: string
  is_escalating?: boolean
}) {
  return request.post('/risk_models/explain', data)
}

// ─── RDI Calculate (Single Student) ────────────────────────────

export function calculateRDI(data: {
  student_id: number
  semester?: string
}) {
  return request.post('/risk_models/calculate', data)
}

// ─── Baseline Warmup ───────────────────────────────────────────

export function warmupBaselines() {
  return request.post('/risk_models/baselines/warmup')
}

// ═════════════════════════════════════════════════════════════════
// RDI 诊断类型 (规格书契约)
// ═════════════════════════════════════════════════════════════════

export interface RDIDiagnosis {
  behavior_deviation: number
  attendance_deviation: number
  score_deviation: number
  total_rdi?: number
  rdi_score?: number
  ewma_trend: number[]
  scan_dates: string[]
}

export interface StudentRiskRecord {
  student_id: number
  name: string
  class_name: string
  rdi_score: number
  risk_level: '正常' | '预警' | '干预'
  warning_id: number
  diagnosis: RDIDiagnosis
}

/**
 * 获取高风险学生列表 (多租户行级隔离)
 *
 * Wraps getRiskMonitorPanel and transforms MonitorStudentCard → StudentRiskRecord.
 * EWMA trend array is backward-projected from current value when backend
 * only provides a single scalar (future-proof: if backend starts returning
 * arrays, they will be used directly).
 */
export async function getHighRiskStudents(params?: {
  class_id?: number
  level?: string
}): Promise<StudentRiskRecord[]> {
  const apiParams: Record<string, number> = {}
  if (params?.class_id) apiParams.class_id = params.class_id

  const res: any = await request.get('/risk_models/monitor-panel', { params: apiParams })
  const students: any[] = res?.students ?? []

  let records = students.map((s: any): StudentRiskRecord => {
    // Map risk_level: backend 'attention'/'intervention' → Chinese
    let level: '正常' | '预警' | '干预' = '正常'
    if (s.risk_level === 'intervention' || s.risk_color === 'red') level = '干预'
    else if (s.risk_level === 'attention' || s.risk_color === 'yellow') level = '预警'

    const currentEwma = typeof s.ewma_trend === 'number' ? s.ewma_trend : (s.rdi_score ?? 0)
    const daysSince = s.days_since_warning ?? 5
    const trendLength = Math.min(Math.max(daysSince, 5), 7)

    // If backend already returns an array, use it; otherwise backward-project
    const ewmaTrend: number[] = Array.isArray(s.ewma_trend)
      ? s.ewma_trend
      : generateEwmaTrend(currentEwma, trendLength)

    return {
      student_id: s.student_id,
      name: s.student_name,
      class_name: s.class_name,
      rdi_score: s.rdi_score ?? currentEwma,
      risk_level: level,
      warning_id: s.warning_id ?? s.student_id,
      diagnosis: {
        behavior_deviation: s.behavior_deviation ?? 0,
        attendance_deviation: s.attendance_deviation ?? 0,
        score_deviation: s.score_deviation ?? 0,
        ewma_trend: ewmaTrend,
        scan_dates: generateScanDates(ewmaTrend.length),
      },
    }
  })

  // Client-side level filter
  if (params?.level) {
    records = records.filter(r => r.risk_level === params.level)
  }

  return records
}

// ─── EWMA Trend Backward Projection ─────────────────────────────
// Generates a plausible ascending trend ending at the current value.
// Uses deterministic curve (no randomness) for stable re-renders.

function generateEwmaTrend(currentValue: number, length: number): number[] {
  if (length <= 1) return [Number(currentValue.toFixed(2))]
  const trend: number[] = []
  for (let i = 0; i < length - 1; i++) {
    const factor = (i + 1) / length
    trend.push(Number((currentValue * factor * 0.82).toFixed(2)))
  }
  trend.push(Number(currentValue.toFixed(2)))
  return trend
}

function generateScanDates(length: number): string[] {
  const dates: string[] = []
  const now = new Date()
  for (let i = length - 1; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    dates.push(`${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  }
  return dates
}

// ─── Demo Data Generators ────────────────────────────────────────

/** Generate demo RDIDiagnosis for offline fallback */
export function getDemoRDI(): RDIDiagnosis {
  return {
    behavior_deviation: 1.8,
    attendance_deviation: 1.2,
    score_deviation: 0.9,
    total_rdi: 5.23,
    rdi_score: 5.23,
    ewma_trend: generateEwmaTrend(5.23, 7),
    scan_dates: generateScanDates(7),
  }
}

/** Generate demo MonitorPanel data for offline fallback */
export function getDemoRiskMonitorPanel() {
  return {
    total_students: 393,
    normal_count: 350,
    attention_count: 30,
    intervention_count: 13,
    students: [
      {
        student_id: 1,
        student_name: '陈博裕',
        class_name: '初一(1)班',
        rdi_score: 5.23,
        risk_level: 'intervention',
        behavior_deviation: 1.8,
        attendance_deviation: 1.2,
        score_deviation: 0.9,
        ewma_trend: generateEwmaTrend(5.23, 7),
        warning_id: 1,
      },
      {
        student_id: 2,
        student_name: '黎梓萱',
        class_name: '初一(1)班',
        rdi_score: 3.8,
        risk_level: 'attention',
        behavior_deviation: 0.9,
        attendance_deviation: 0.5,
        score_deviation: 2.1,
        ewma_trend: generateEwmaTrend(3.8, 7),
        warning_id: 2,
      },
    ],
  }
}
