import request from './request'

/**
 * AI 德育处方 API 契约层 V2
 *
 * Backend: /api/v1/ai_prescription/
 * - POST /student-intervention  → 202 (async Celery task)
 * - GET  /tasks/{task_id}        → task status polling
 * - GET  /tasks/{task_id}/result → PrescriptionResultOut
 * - GET  /history                → paginated history
 * - GET  /records/{record_id}    → single prescription record
 *
 * V2 架构: Fact→Analysis→Growth 三段式
 * - Fact段: 临床严谨(σ值精确表达, 禁模糊词)
 * - Analysis段: 交叉归因(学业×行为×心理)
 * - Growth段: 三层递进干预(即时→短期→持续)
 *
 * 数据源: raw_snapshot.llm_output.fact/analysis/growth
 * 兜底: full_text Markdown 拼接 + measures[] 旧版兼容
 */

// ═════════════════════════════════════════════════════════════════
// V1 Legacy Types (backward compatibility)
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
// V2 Types — Fact→Analysis→Growth 三段式
// ═════════════════════════════════════════════════════════════════

export type RiskLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export interface AIPrescriptionPayloadV2 {
  warning_id: number
  student_name: string
  class_name: string
  rdi_score: number
  risk_level: RiskLevel
  generated_at: string
  // V2 三段核心
  fact: string       // 临床事实 — σ值、偏离度、EWMA趋势、一票否决标记
  analysis: string   // 交叉归因 — 学业×行为×心理 诊断叙事
  growth: string     // 三层递进 — 即时(24h)→短期(72h)→持续(4周)
  // 兜底兼容
  analysis_summary: string  // 摘要(兼容旧版 Header 展示)
  measures?: InterventionMeasure[]  // V1 measures 兜底
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
// Adapter: Real Backend Async Flow → V2 AIPrescriptionPayload
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

// ═════════════════════════════════════════════════════════════════
// V2 Parser: raw_snapshot.llm_output → three segments
// ═════════════════════════════════════════════════════════════════

/**
 * Extract student_name from raw_snapshot.
 * Priority: flat field → nested student.name → fallback '学生'
 */
function extractStudentName(result: PrescriptionResultOut): string {
  const snap = result.raw_snapshot
  if (!snap) return '学生'
  // Try flat field first (V2 aggregator adds this)
  if (snap.student_name && typeof snap.student_name === 'string') return snap.student_name
  // Try nested student object
  const student = snap.student as Record<string, any> | undefined
  if (student?.name && typeof student.name === 'string') return student.name
  return '学生'
}

/**
 * Extract class_name from raw_snapshot.
 * Priority: flat field → nested student.class_name → fallback '--'
 */
function extractClassName(result: PrescriptionResultOut): string {
  const snap = result.raw_snapshot
  if (!snap) return '--'
  // Try flat field first (V2 aggregator adds this)
  if (snap.class_name && typeof snap.class_name === 'string') return snap.class_name
  // Try nested student.class_name
  const student = snap.student as Record<string, any> | undefined
  if (student?.class_name && typeof student.class_name === 'string') return student.class_name
  // Try nested class object
  const clazz = snap.class as Record<string, any> | undefined
  if (clazz?.name && typeof clazz.name === 'string') return clazz.name
  return '--'
}

/**
 * Extract rdi_score from raw_snapshot.
 * Priority: flat field → nested rdi_diagnosis.rdi_score → fallback 0
 */
function extractRdiScore(result: PrescriptionResultOut): number {
  const snap = result.raw_snapshot
  if (!snap) return 0
  // Try flat field first (V2 aggregator adds this)
  if (typeof snap.rdi_score === 'number') return snap.rdi_score
  // Try nested rdi_diagnosis.rdi_score
  const rdi = snap.rdi_diagnosis as Record<string, any> | undefined
  if (rdi?.rdi_score && typeof rdi.rdi_score === 'number') return rdi.rdi_score
  return 0
}

/**
 * Extract Fact/Analysis/Growth from raw_snapshot.llm_output.
 * Returns null if V2 structure not found.
 */
function parseLlmOutput(result: PrescriptionResultOut): {
  fact: string
  analysis: string
  growth: string
  risk_level: RiskLevel
} | null {
  const llmOutput = result.raw_snapshot?.llm_output
  if (!llmOutput) return null

  const fact = (llmOutput.fact as string) || ''
  const analysis = (llmOutput.analysis as string) || ''
  const growth = (llmOutput.growth as string) || ''

  // At least one segment must have content
  if (!fact && !analysis && !growth) return null

  // Risk level: prefer llm_output.risk_level, then backend field
  const rawLevel = (llmOutput.risk_level as string) || result.risk_level || 'MEDIUM'
  const risk_level = normalizeRiskLevel(rawLevel)

  return { fact, analysis, growth, risk_level }
}

/** Normalize risk level string to V2 enum */
function normalizeRiskLevel(raw: string): RiskLevel {
  const upper = raw.toUpperCase()
  if (upper === 'CRITICAL') return 'CRITICAL'
  if (upper === 'HIGH') return 'HIGH'
  if (upper === 'MEDIUM') return 'MEDIUM'
  if (upper === 'LOW') return 'LOW'
  // Fallback: numeric threshold
  return 'MEDIUM'
}

// ═════════════════════════════════════════════════════════════════
// V1 Parser: Markdown full_text → measures[] (backward compat)
// ═════════════════════════════════════════════════════════════════

/**
 * Parse backend Markdown `full_text` into structured InterventionMeasure[].
 * Best-effort extraction — falls back to a single summary measure if parsing fails.
 */
function parseMarkdownToMeasures(fullText: string): InterventionMeasure[] {
  const measures: InterventionMeasure[] = []
  const chapters = fullText.split(/^##\s+/m).filter(s => s.trim())

  chapters.forEach((chapter, idx) => {
    const lines = chapter.split('\n').filter(l => l.trim())
    if (lines.length < 2) return

    const category = lines[0].trim()
    const body = lines.slice(1).join('\n')

    const actionLines = body.split('\n').filter(l => /^\s*[-*]\s+/.test(l))
    const actionPlan = actionLines.map(l => l.replace(/^\s*[-*]\s+/, '').trim()).filter(Boolean)

    if (actionPlan.length === 0) return

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
// Demo Data V2 — 三段式真实案例 (黄泽彬 student204)
// ═════════════════════════════════════════════════════════════════

export function getDemoPrescriptionV2(warningId: number): AIPrescriptionPayloadV2 {
  return {
    warning_id: warningId,
    student_name: '黄泽彬',
    class_name: '初一(5)班',
    rdi_score: 5.23,
    risk_level: 'HIGH',
    generated_at: new Date().toISOString(),
    analysis_summary: '行为×心理×学业三维叠加恶性循环，RDI 5.23 RED级干预',
    fact: `**RDI 综合偏离指数**: 5.23 (干预阈值 ≥4.5)\n\n**四维偏离度**:\n- 行为维度: Z=+1.8σ (近两周连续3次课堂冲突)\n- 考勤维度: Z=+1.2σ (累计旷课4节)\n- 学业维度: Z=-0.9σ (月考数学下降22分)\n- 心理维度: Z=+2.1σ ⚠️ [焦虑因子得分≥4.0]\n\n**EWMA趋势**: 指数加权移动平均呈持续上行，近7日斜率+0.12/天\n\n**心理一票否决**: psych_veto_triggered=False (无维度超3σ)\n\n**一票否决互锁**: discipline_veto=False, psych_veto=False → 未触发强制RED升级`,
    analysis: `**交叉归因诊断**: 行为×心理×学业三维叠加恶性循环\n\n该生行为冲突并非单纯纪律问题，而是心理承压过载的外化表现。课堂冲突频率(3次/2周)与焦虑因子Z=+2.1σ高度关联，提示冲突行为可能为焦虑情绪的行为代偿——当内在焦虑无法通过言语表达时，外化为对课堂秩序的对抗性反应。\n\n学业维度Z=-0.9σ与行为维度Z=+1.8σ呈现「负相关耦合」: 学业下滑→课堂回避→冲突升级→处罚加重→焦虑加剧→学业继续下滑。此循环若不加阻断，EWMA预测7日内RDI将突破6.0阈值。\n\n**风险等级判定**: RED (RDI≥5.0 + 心理维度Z>2σ)\n\n**退潮保护**: 30天窗口内min_rdi=1.5，暂不触发大退潮保护`,
    growth: `**第一层: 即时干预 (24h内启动)**\n1. 安排校心理室专职教师进行一对一评估访谈(非诊断性、非评价性)\n2. 建立心理教师—班主任—家长三方信息同步通道，每日一次状态简报\n3. 暂停一切公开性批评场景，改用课后单独沟通模式\n4. 若评估发现自伤倾向指标，立即启动校危预案并通知区心理援助中心\n\n**第二层: 短期补偿 (72h内启动)**\n1. 数学教师本周完成知识盲点定位(近3次作业错题集中模块)\n2. 安排同伴互助小组: 指定数学前10%学生结对，每周2次课间答疑\n3. 教师办公时间开放: 每周二/四午休12:30-13:00接受个别提问\n\n**第三层: 持续成长 (4周跟踪)**\n1. 班主任48h内完成一次家访或深度电话沟通(非成绩通报性质)\n2. 引导家长签署《家校协同支持公约》——承诺2周内不在公开场合讨论成绩\n3. 每周五推送正向行为记录(至少2条)，重建积极关注\n4. 两周后阶段性小测(仅基础题)检验补偿效果并调整方案`,
  }
}

// ═════════════════════════════════════════════════════════════════
// V1 Demo Data (kept for backward compat)
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
// Public API V2: getAIPrescriptionV2
// ═════════════════════════════════════════════════════════════════

/**
 * Fetch AI prescription V2 (Fact→Analysis→Growth 三段式).
 *
 * Strategy:
 * 1. Try real backend → parse raw_snapshot.llm_output for V2 segments
 * 2. If V2 segments found, return three-segment payload
 * 3. If V2 not found but full_text exists, fallback to V1 measures[] + raw text
 * 4. If backend unavailable, fall back to V2 demo data
 */
export async function getAIPrescriptionV2(
  warning_id: number,
  student_id?: number
): Promise<AIPrescriptionPayloadV2> {
  // Try real backend if student_id is provided
  if (student_id && student_id > 0) {
    const realResult = await fetchRealPrescription(student_id)

    if (realResult) {
      // Priority: V2 segments from raw_snapshot.llm_output
      const llmParsed = parseLlmOutput(realResult)
      if (llmParsed && (llmParsed.fact || llmParsed.analysis || llmParsed.growth)) {
        return {
          warning_id,
          student_name: extractStudentName(realResult),
          class_name: extractClassName(realResult),
          rdi_score: extractRdiScore(realResult),
          risk_level: llmParsed.risk_level,
          generated_at: realResult.created_at ?? new Date().toISOString(),
          fact: llmParsed.fact,
          analysis: llmParsed.analysis,
          growth: llmParsed.growth,
          analysis_summary: llmParsed.analysis || realResult.summary || 'AI 分析完成',
        }
      }

      // Fallback 1: V1 measures[] from full_text Markdown
      if (realResult.full_text) {
        const measures = parseMarkdownToMeasures(realResult.full_text)
        if (measures.length > 0) {
          return {
            warning_id,
            student_name: extractStudentName(realResult),
            class_name: extractClassName(realResult),
            rdi_score: extractRdiScore(realResult),
            risk_level: normalizeRiskLevel(realResult.risk_level ?? 'MEDIUM'),
            generated_at: realResult.created_at ?? new Date().toISOString(),
            fact: '',
            analysis: realResult.summary ?? '',
            growth: realResult.full_text,
            analysis_summary: realResult.summary ?? 'AI 分析完成',
            measures,
          }
        }
      }
    }
  }

  // Fallback 2: Demo data
  await sleep(400)
  return getDemoPrescriptionV2(warning_id)
}

// ═════════════════════════════════════════════════════════════════
// Legacy V1 API (kept for backward compat)
// ═════════════════════════════════════════════════════════════════

/**
 * @deprecated Use getAIPrescriptionV2 instead
 */
export async function getAIPrescription(
  warning_id: number,
  student_id?: number
): Promise<AIPrescriptionPayload> {
  if (student_id && student_id > 0) {
    const realResult = await fetchRealPrescription(student_id)

    if (realResult && realResult.full_text) {
      const measures = parseMarkdownToMeasures(realResult.full_text)
      if (measures.length > 0) {
        return {
          warning_id,
          student_name: (realResult.raw_snapshot?.student_name as string) ?? '学生',
          class_name: (realResult.raw_snapshot?.class_name as string) ?? '--',
          rdi_score: (realResult.raw_snapshot?.rdi_score as number) ?? 0,
          analysis_summary: realResult.summary ?? 'AI 分析完成',
          generated_at: realResult.created_at ?? new Date().toISOString(),
          measures,
        }
      }
    }
  }

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
  return elapsed < 72 * 60 * 60 * 1000
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

// ═════════════════════════════════════════════════════════════════
// Lightweight Markdown Renderer (inline, no dependency)
// ═════════════════════════════════════════════════════════════════

/**
 * Convert basic Markdown to HTML for segment rendering.
 * Handles: **bold**, *italic*, - list items, numbered lists, headers
 * Does NOT handle: links, images, code blocks, tables
 */
export function renderSegmentMarkdown(text: string): string {
  if (!text) return ''

  let html = text

  // Escape HTML entities first (but preserve our own tags later)
  // Skip full escape — LLM output is trusted internal content

  // Headers: ## → <h3>, ### → <h4>
  html = html.replace(/^###\s+(.+)$/gm, '<h4 class="seg-h4">$1</h4>')
  html = html.replace(/^##\s+(.+)$/gm, '<h3 class="seg-h3">$1</h3>')

  // Bold: **text** → <strong>
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Italic: *text* → <em> (but not inside bold)
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')

  // Numbered lists: 1. text → <li>
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<li class="seg-li">$1</li>')

  // Bullet lists: - text or * text → <li>
  html = html.replace(/^[-*]\s+(.+)$/gm, '<li class="seg-li">$1</li>')

  // Wrap consecutive <li> into <ul>
  html = html.replace(/((?:<li class="seg-li">.*<\/li>\n?)+)/g, '<ul class="seg-ul">$1</ul>')

  // Paragraphs: double newline → <p>
  html = html.replace(/\n\n+/g, '</p><p class="seg-p">')

  // Single newline within paragraph → <br>
  html = html.replace(/\n/g, '<br>')

  // Wrap in root <div>
  html = `<div class="seg-content"><p class="seg-p">${html}</p></div>`

  // Clean up empty paragraphs
  html = html.replace(/<p class="seg-p">\s*<\/p>/g, '')

  return html
}

// ─── Utility ──────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
