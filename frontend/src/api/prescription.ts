import request from './request'

/**
 * AI 德育处方 API 契约层
 *
 * Backend: /api/v1/ai_prescription/
 * - POST /student-intervention  → 202 (async Celery task)
 * - GET  /tasks/{task_id}        → task status polling
 * - GET  /tasks/{task_id}/result → PrescriptionResultOut
 * - GET  /history                → paginated history
 * - GET  /records/{record_id}    → single prescription record
 *
 * Real backend returns Markdown `full_text` (not structured measures[]).
 * This layer adapts async flow → structured AIPrescriptionPayload,
 * with demo-data fallback when backend is unavailable.
 */

// ═════════════════════════════════════════════════════════════════
// Spec-defined Types (user specification)
// ═════════════════════════════════════════════════════════════════

export interface InterventionMeasure {
  id: number
  category: string
  icon_name: string
  tag_type: 'danger' | 'warning' | 'success' | 'info'
  core_issue: string
  action_plan: string[]
  timeline: string
}

export interface AIPrescriptionPayload {
  warning_id: number
  student_name: string
  class_name: string
  rdi_score: number
  analysis_summary: string
  generated_at: string
  measures: InterventionMeasure[]
}

// ═════════════════════════════════════════════════════════════════
// Backend Schema Types (from ai_prescription/schemas.py)
// ═════════════════════════════════════════════════════════════════

export interface PrescriptionTaskOut {
  task_id: string
  status: 'PENDING'
  message: string
}

export interface TaskStatusOut {
  task_id: string
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE' | 'REVOKED'
  result?: Record<string, any>
  error?: string
}

export interface PrescriptionResultOut {
  record_id: number
  prescription_type: 'CLASS_DIAGNOSIS' | 'STUDENT_INTV'
  target_id: number
  target_type: string
  risk_level?: 'HIGH' | 'MEDIUM' | 'LOW'
  summary?: string
  full_text: string
  raw_snapshot?: Record<string, any>
  creator_id?: number
  created_at?: string
}

export interface PrescriptionHistoryItem {
  id: number
  prescription_type: string
  target_id: number
  target_type: string
  risk_level?: string
  summary?: string
  created_at: string
  creator_name?: string
}

export interface PrescriptionHistoryOut {
  total: number
  items: PrescriptionHistoryItem[]
}

// ═════════════════════════════════════════════════════════════════
// Raw Backend API Functions
// ═════════════════════════════════════════════════════════════════

/** POST /student-intervention — trigger async AI prescription generation */
export function triggerStudentIntervention(data: {
  student_id: number
  analysis_days?: number
}) {
  return request.post<any, PrescriptionTaskOut>('/ai_prescription/student-intervention', data)
}

/** GET /tasks/{task_id} — poll Celery task status */
export function pollTaskStatus(taskId: string) {
  return request.get<any, TaskStatusOut>(`/ai_prescription/tasks/${taskId}`)
}

/** GET /tasks/{task_id}/result — fetch completed prescription result */
export function getTaskResult(taskId: string) {
  return request.get<any, PrescriptionResultOut>(`/ai_prescription/tasks/${taskId}/result`)
}

/** GET /history — paginated prescription history */
export function getPrescriptionHistory(params?: {
  page?: number
  page_size?: number
  prescription_type?: string
}) {
  return request.get<any, PrescriptionHistoryOut>('/ai_prescription/history', { params })
}

/** GET /records/{record_id} — single prescription record */
export function getPrescriptionRecord(recordId: number) {
  return request.get<any, PrescriptionResultOut>(`/ai_prescription/records/${recordId}`)
}

// ═════════════════════════════════════════════════════════════════
// Adapter: Real Backend Async Flow → Structured AIPrescriptionPayload
// ═════════════════════════════════════════════════════════════════

/**
 * Trigger + Poll + Result — full async flow with timeout.
 * Returns null if any step fails or times out.
 */
async function fetchRealPrescription(studentId: number, maxPolls = 20): Promise<PrescriptionResultOut | null> {
  try {
    // Step 1: Trigger
    const task = await triggerStudentIntervention({ student_id: studentId })
    if (!task?.task_id) return null

    // Step 2: Poll
    for (let i = 0; i < maxPolls; i++) {
      await sleep(1500)
      const status = await pollTaskStatus(task.task_id)
      if (status.status === 'SUCCESS') break
      if (status.status === 'FAILURE' || status.status === 'REVOKED') return null
    }

    // Step 3: Get result
    const result = await getTaskResult(task.task_id)
    return result || null
  } catch {
    return null
  }
}

/**
 * Parse backend Markdown `full_text` into structured InterventionMeasure[].
 * Best-effort extraction — falls back to a single summary measure if parsing fails.
 */
function parseMarkdownToMeasures(fullText: string): InterventionMeasure[] {
  const measures: InterventionMeasure[] = []
  // Split by ## headers (Markdown chapters)
  const chapters = fullText.split(/^##\s+/m).filter(s => s.trim())

  chapters.forEach((chapter, idx) => {
    const lines = chapter.split('\n').filter(l => l.trim())
    if (lines.length < 2) return

    const category = lines[0].trim()
    const body = lines.slice(1).join('\n')

    // Extract action items (lines starting with - or *)
    const actionLines = body.split('\n').filter(l => /^\s*[-*]\s+/.test(l))
    const actionPlan = actionLines.map(l => l.replace(/^\s*[-*]\s+/, '').trim()).filter(Boolean)

    if (actionPlan.length === 0) return

    // Determine tag_type by keywords
    let tagType: InterventionMeasure['tag_type'] = 'info'
    if (/危机|心理|自伤|安全/i.test(category)) tagType = 'danger'
    else if (/学业|成绩|补偿/i.test(category)) tagType = 'warning'
    else if (/家校|契约|沟通/i.test(category)) tagType = 'success'

    measures.push({
      id: idx + 1,
      category,
      icon_name: tagType === 'danger' ? 'WarningFilled' : tagType === 'warning' ? 'Notebook' : 'HomeFilled',
      tag_type: tagType,
      core_issue: body.split('\n').find(l => !/^\s*[-*]/.test(l) && l.trim())?.trim() || '见详细方案',
      action_plan: actionPlan,
      timeline: '建议 72 小时内启动',
    })
  })

  return measures
}

// ═════════════════════════════════════════════════════════════════
// Demo Data (from user specification — realistic student case)
// ═════════════════════════════════════════════════════════════════

export function getDemoPrescription(warningId: number): AIPrescriptionPayload {
  return {
    warning_id: warningId,
    student_name: '黎梓萱',
    class_name: '初一(3)班',
    rdi_score: 5.23,
    analysis_summary:
      '该生 RDI 综合偏离指数 5.23，已突破干预阈值(≥4.5)。行为维度 Z-Score 偏离 +1.8σ（近两周连续 3 次课堂冲突），考勤维度偏离 +1.2σ（累计旷课 4 节），学业维度偏离 -0.9σ（月考数学下降 22 分）。EWMA 指数加权移动平均呈持续上行趋势，建议立即启动三级干预方案。',
    generated_at: new Date().toISOString(),
    measures: [
      {
        id: 1,
        category: '心理危机防御',
        icon_name: 'WarningFilled',
        tag_type: 'danger',
        core_issue:
          '连续课堂冲突事件 + 学业断崖式下跌，存在潜在心理承压过载风险。班主任反馈该生近期沉默寡言，课间独处频率显著上升。',
        action_plan: [
          '24 小时内安排校心理室专职教师进行一对一评估访谈（非诊断性、非评价性）',
          '建立心理教师—班主任—家长三方信息同步通道，每日一次状态简报',
          '暂停一切公开性批评场景，改用课后单独沟通模式',
          '若评估发现自伤倾向指标，立即启动校危预案并通知区心理援助中心',
        ],
        timeline: '即时启动 · 首次评估 24h 内完成',
      },
      {
        id: 2,
        category: '学业补偿教学',
        icon_name: 'Notebook',
        tag_type: 'warning',
        core_issue:
          '数学月考下降 22 分（82→60），RDI 学业维度 Z-Score 偏离 -0.9σ。疑似基础知识链条断裂导致课堂跟不上进度，进而引发回避行为。',
        action_plan: [
          '数学教师本周内完成知识盲点定位（选取近 3 次作业错题集中模块）',
          '安排同伴互助小组：指定数学前 10% 学生结对，每周 2 次课间答疑',
          '教师办公时间开放：每周二/四午休 12:30-13:00 接受个别提问',
          '两周后进行阶段性小测（仅基础题），检验补偿效果并调整方案',
        ],
        timeline: '本周启动 · 首次检验 14 天后',
      },
      {
        id: 3,
        category: '家校契约柔化',
        icon_name: 'HomeFilled',
        tag_type: 'success',
        core_issue:
          '家长群内多次公开批评该生成绩，家校沟通记录显示家长焦虑情绪传导明显。家庭压力与学校压力叠加，形成负反馈循环。',
        action_plan: [
          '班主任 48h 内完成一次家访或深度电话沟通（非成绩通报性质）',
          '引导家长签署《家校协同支持公约》——承诺 2 周内不在公开场合讨论成绩',
          '每周五向家长推送该生正向行为记录（至少 2 条），重建积极关注',
          '若家长焦虑指数未降，推荐参加校家长课堂《青春期沟通策略》专题讲座',
        ],
        timeline: '48h 内启动 · 持续跟踪 4 周',
      },
    ],
  }
}

// ═════════════════════════════════════════════════════════════════
// Public API: getAIPrescription (user spec signature)
// ═════════════════════════════════════════════════════════════════

/**
 * Fetch AI prescription by warning_id.
 *
 * Strategy:
 * 1. Try real backend async flow (trigger → poll → result)
 * 2. If successful, parse Markdown full_text into structured measures
 * 3. If backend unavailable or returns insufficient data, fall back to demo data
 *
 * @param warning_id - RDI warning ID (used as student_id proxy in demo mode)
 * @param student_id - Optional explicit student_id for real backend call
 */
export async function getAIPrescription(
  warning_id: number,
  student_id?: number
): Promise<AIPrescriptionPayload> {
  // Try real backend if student_id is provided
  if (student_id && student_id > 0) {
    const realResult = await fetchRealPrescription(student_id)

    if (realResult && realResult.full_text) {
      const measures = parseMarkdownToMeasures(realResult.full_text)
      if (measures.length > 0) {
        return {
          warning_id,
          student_name: realResult.raw_snapshot?.student_name ?? '学生',
          class_name: realResult.raw_snapshot?.class_name ?? '--',
          rdi_score: realResult.raw_snapshot?.rdi_score ?? 0,
          analysis_summary: realResult.summary ?? 'AI 分析完成',
          generated_at: realResult.created_at ?? new Date().toISOString(),
          measures,
        }
      }
    }
  }

  // Fallback to demo data
  await sleep(400)
  return getDemoPrescription(warning_id)
}

// ═════════════════════════════════════════════════════════════════
// 72-Hour Circuit Breaker (Redis-backed on backend, localStorage on frontend)
// ═════════════════════════════════════════════════════════════════

const BREAKER_KEY_PREFIX = 'prescription_breaker_'

/** Check if 72-hour breaker is active for this warning */
export function isBreakerActive(warningId: number): boolean {
  const key = BREAKER_KEY_PREFIX + warningId
  const ts = localStorage.getItem(key)
  if (!ts) return false
  const elapsed = Date.now() - parseInt(ts, 10)
  return elapsed < 72 * 60 * 60 * 1000 // 72 hours
}

/** Get remaining time (ms) for active breaker */
export function getBreakerRemaining(warningId: number): number {
  const key = BREAKER_KEY_PREFIX + warningId
  const ts = localStorage.getItem(key)
  if (!ts) return 0
  const elapsed = Date.now() - parseInt(ts, 10)
  const remaining = 72 * 60 * 60 * 1000 - elapsed
  return Math.max(0, remaining)
}

/** Activate 72-hour breaker — called when teacher confirms implementation */
export function activateBreaker(warningId: number): void {
  const key = BREAKER_KEY_PREFIX + warningId
  localStorage.setItem(key, Date.now().toString())
}

// ─── Utility ──────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
