/**
 * reports.ts — 德育报告异步引擎 API 契约层
 *
 * 对应后端模块: modules/reports (MODULE_CODE="reports" → URL前缀 /api/v1/reports)
 * 端点清单 (3):
 *   POST   /reports/export/moral-report     — 触发单个班级德育报告异步导出 → 202 + task_id
 *   GET    /reports/tasks/{task_id}         — 任务状态轮询 (PENDING/PROGRESS/SUCCESS/FAILURE)
 *   POST   /reports/export/grade-report     — 触发全年级批量导出 → 202 + task_ids
 *
 * 工作流: 提交导出 → 获得 task_id → 轮询状态 → 下载完成报告
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════

/** ── 单班导出请求 ─────────────────────────────── */

export interface ExportMoralReportRequest {
  /** 班级 ID */
  class_id: number
  /** 学期标识，如 2025-2026-2 */
  semester?: string
  /** 报告类型: class_moral | student_individual */
  report_type?: string
  /** 指定学生 ID（student_individual 时必填） */
  student_id?: number
}

/** ── 任务提交响应 ─────────────────────────────── */

export interface TaskAcceptedResponse {
  task_id: string
  status: string
  message: string
}

/** ── 任务状态响应 ─────────────────────────────── */

export type TaskState = 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE'

export interface TaskResult {
  filename: string
  download_url: string
  file_size_kb?: number
  generated_at?: string
}

export interface TaskStatusResponse {
  task_id: string
  state: TaskState
  progress?: number
  status_text?: string
  result?: TaskResult
  error?: string
}

/** ── 全年级批量导出请求 ───────────────────────── */

export interface ExportGradeReportRequest {
  /** 年级 ID */
  grade_id: number
  /** 学期标识 */
  semester?: string
  /** 指定班级 ID 列表（为空则全年级导出） */
  include_classes?: number[]
}

/** ── 批量任务响应 ─────────────────────────────── */

export interface GradeTaskAcceptedResponse {
  task_ids: string[]
  total_classes: number
  status: string
  message: string
}

/** ── 前端本地任务追踪 ─────────────────────────── */

export interface TaskTracker {
  id: string
  classId: number
  className: string
  reportType: string
  state: TaskState
  progress: number
  statusText: string
  result?: TaskResult
  error?: string
  createdAt: Date
}

/** ── 班级信息 (用于选择器) ─────────────────────── */

export interface ClassOption {
  id: number
  name: string
  grade_id: number
}

/** ── 年级信息 ─────────────────────────────────── */

export interface GradeOption {
  id: number
  name: string
}

// ═══════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═══════════════════════════════════════════════════

/**
 * POST /reports/export/moral-report
 * 触发单班德育报告异步导出
 * 返回 202 Accepted + task_id，前端轮询 GET /tasks/{task_id} 获取进度
 */
export function exportMoralReport(data: ExportMoralReportRequest) {
  return request.post<any, TaskAcceptedResponse>('/reports/export/moral-report', data)
}

/**
 * GET /reports/tasks/{task_id}
 * 轮询任务状态: PENDING → PROGRESS(含进度%) → SUCCESS(含下载链接) → FAILURE(含错误)
 */
export function getTaskStatus(taskId: string) {
  return request.get<any, TaskStatusResponse>(`/reports/tasks/${taskId}`)
}

/**
 * POST /reports/export/grade-report
 * 触发全年级批量导出
 * 为每个班级派发独立任务，返回 task_ids 列表
 */
export function exportGradeReport(data: ExportGradeReportRequest) {
  return request.post<any, GradeTaskAcceptedResponse>('/reports/export/grade-report', data)
}

// ═══════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════

/** 报告类型选项 */
export const REPORT_TYPES = [
  { value: 'class_moral', label: '班级德育报告' },
  { value: 'student_individual', label: '学生个人报告' },
] as const

/** 任务状态标签映射 */
export const TASK_STATE_LABELS: Record<TaskState, { label: string; type: 'info' | 'warning' | 'success' | 'danger' }> = {
  PENDING: { label: '排队中', type: 'info' },
  PROGRESS: { label: '生成中', type: 'warning' },
  SUCCESS: { label: '已完成', type: 'success' },
  FAILURE: { label: '失败', type: 'danger' },
}

/** 轮询间隔 (ms) */
export const POLL_INTERVAL = 2000

/** 最大轮询次数 (2s × 150 = 5 分钟超时) */
export const MAX_POLL_COUNT = 150

// ═══════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════

/** 任务状态 → el-tag type */
export function taskStateTagType(state: TaskState): 'info' | 'warning' | 'success' | 'danger' {
  return TASK_STATE_LABELS[state]?.type || 'info'
}

/** 任务状态 → 中文 */
export function taskStateLabel(state: TaskState): string {
  return TASK_STATE_LABELS[state]?.label || state
}

/** 文件大小格式化 */
export function formatFileSize(kb?: number): string {
  if (!kb) return '—'
  if (kb >= 1024) return `${(kb / 1024).toFixed(1)} MB`
  return `${kb.toFixed(1)} KB`
}

// ═══════════════════════════════════════════════════
// Demo Data (后端不可用时降级)
// ═══════════════════════════════════════════════════

export function getDemoClasses(): ClassOption[] {
  return Array.from({ length: 8 }, (_, i) => ({
    id: i + 1,
    name: `七(${i + 1})班`,
    grade_id: 1,
  }))
}

export function getDemoGrades(): GradeOption[] {
  return [
    { id: 1, name: '七年级' },
    { id: 2, name: '八年级' },
    { id: 3, name: '九年级' },
  ]
}

export function getDemoTaskTracker(classId: number, taskId: string): TaskTracker {
  return {
    id: taskId,
    classId,
    className: `七(${classId})班`,
    reportType: 'class_moral',
    state: 'SUCCESS',
    progress: 100,
    statusText: '报告生成完成',
    result: {
      filename: `班级德育报告_七(${classId})班_2026-07-05.pdf`,
      download_url: `/api/v1/reports/tasks/${taskId}/download`,
      file_size_kb: 245.6,
      generated_at: new Date().toISOString(),
    },
    createdAt: new Date(),
  }
}

export function getDemoTaskStatus(taskId: string): TaskStatusResponse {
  return {
    task_id: taskId,
    state: 'SUCCESS',
    progress: 100,
    status_text: '报告生成完成',
    result: {
      filename: `班级德育报告_七(1)班_2026-07-05.pdf`,
      download_url: `/api/v1/reports/tasks/${taskId}/download`,
      file_size_kb: 245.6,
      generated_at: new Date().toISOString(),
    },
  }
}

/**
 * 模拟任务状态流转 (仅 Demo 模式)
 * 用于离线降级演示: PENDING → PROGRESS(25%→50%→75%) → SUCCESS
 */
export function simulateTaskProgress(
  taskId: string,
  classId: number,
  onUpdate: (tracker: TaskTracker) => void,
  onComplete: (tracker: TaskTracker) => void,
) {
  const steps = [
    { state: 'PROGRESS' as const, progress: 20, text: '正在收集学生数据...', delay: 800 },
    { state: 'PROGRESS' as const, progress: 45, text: '正在计算五维评价...', delay: 1000 },
    { state: 'PROGRESS' as const, progress: 70, text: '正在生成图表...', delay: 900 },
    { state: 'PROGRESS' as const, progress: 90, text: '正在排版 PDF...', delay: 700 },
    { state: 'SUCCESS' as const, progress: 100, text: '报告生成完成', delay: 500 },
  ]

  let currentStep = 0

  function nextStep() {
    if (currentStep >= steps.length) return

    const step = steps[currentStep]
    const tracker: TaskTracker = {
      id: taskId,
      classId,
      className: `七(${classId})班`,
      reportType: 'class_moral',
      state: step.state,
      progress: step.progress,
      statusText: step.text,
      createdAt: new Date(),
    }

    if (step.state === 'SUCCESS') {
      tracker.result = {
        filename: `班级德育报告_七(${classId})班_2026-07-05.pdf`,
        download_url: `/api/v1/reports/tasks/${taskId}/download`,
        file_size_kb: 245.6,
        generated_at: new Date().toISOString(),
      }
    }

    onUpdate(tracker)

    if (step.state === 'SUCCESS') {
      onComplete(tracker)
      return
    }

    currentStep++
    setTimeout(nextStep, step.delay)
  }

  nextStep()
}

// ═══════════════════════════════════════════════════
// RDI 白皮书 API (Phase 3 新增 — 3端点)
// ═══════════════════════════════════════════════════

/** RDI 风险等级 */
export type RiskLevel = 'red_intervention' | 'yellow_attention' | 'green_normal'

/** el-tag type union (复用) */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** RDI 四维分解 */
export interface RiskBreakdown {
  behavior: number
  attendance: number
  score: number
  psych: number
}

/** 风险学生摘要 — 高危花名册行数据 */
export interface RiskStudentSummary {
  student_id: number
  student_name: string
  class_name: string
  current_rdi: number
  risk_level: RiskLevel
  breakdown: RiskBreakdown
  latest_warning_reason: string | null
  ai_prescription_snippet: string | null
}

/** 班级热力排行项 */
export interface HeatRankingItem {
  class_name: string
  class_id: number
  red_count: number
  yellow_count: number
  total_rdi: number
}

/** 全校 RDI 态势响应 — GET /reports/rdi-summary */
export interface SchoolWideReportResponse {
  generated_at: string
  total_students_scanned: number
  risk_distribution: {
    red_intervention: number
    yellow_attention: number
    green_normal: number
  }
  department_heat_ranking: HeatRankingItem[]
  top_critical_list: RiskStudentSummary[]
}

/** 高危花名册导出响应 — POST /reports/export/high-risk */
export interface HighRiskExportResponse {
  exported_at: string
  total_exported: number
  students: RiskStudentSummary[]
}

/** 考勤摘要 (班主任报告子结构) */
export interface AttendanceSummary {
  total_days: number
  absent_days: number
  late_days: number
  early_leave_days: number
  attendance_rate: number
  consecutive_absence: number
  last_absence_date: string | null
}

/** 纪律摘要 (班主任报告子结构) */
export interface DisciplineSummary {
  total_incidents: number
  pending_count: number
  resolved_count: number
  max_severity: string | null
  latest_incident_date: string | null
}

/** 学业摘要 (班主任报告子结构) */
export interface AcademicSummary {
  average_score: number | null
  rank_in_grade: number | null
  subject_warnings: string[]
}

/** 班主任班级报告响应 — GET /reports/class-report/{class_id} */
export interface ClassTeacherReportResponse {
  generated_at: string
  class_id: number
  class_name: string
  student_count: number
  risk_distribution: {
    red_intervention: number
    yellow_attention: number
    green_normal: number
  }
  high_risk_students: RiskStudentSummary[]
  attendance_summary: AttendanceSummary
  discipline_summary: DisciplineSummary
  academic_summary: AcademicSummary
}

// ═══════════════════════════════════════════════════
// RDI API Functions
// ═══════════════════════════════════════════════════

/**
 * GET /reports/rdi-summary
 * 全校 RDI 态势白皮书 (ms_admin / grade_leader)
 * grade_leader 自动只看自己负责的年级
 */
export function getRdiSummary(params?: { grade_id?: number }) {
  return request.get<any, SchoolWideReportResponse>('/reports/rdi-summary', { params })
}

/**
 * POST /reports/export/high-risk
 * 导出高危学生花名册 (ms_admin / grade_leader)
 */
export function exportHighRiskStudents(data?: { grade_id?: number }) {
  return request.post<any, HighRiskExportResponse>('/reports/export/high-risk', data || {})
}

/**
 * GET /reports/class-report/{class_id}
 * 班主任本班期末德育大盘报告 (class_teacher 自动限定本班)
 */
export function getClassReport(classId: number) {
  return request.get<any, ClassTeacherReportResponse>(`/reports/class-report/${classId}`)
}

// ═══════════════════════════════════════════════════
// RDI Display Helpers
// ═══════════════════════════════════════════════════

/** 风险等级 → 中文标签 */
export function riskLevelLabel(level: RiskLevel): string {
  const map: Record<RiskLevel, string> = {
    red_intervention: '红灯干预',
    yellow_attention: '黄灯关注',
    green_normal: '绿灯正常',
  }
  return map[level] || level
}

/** 风险等级 → el-tag type */
export function riskLevelTag(level: RiskLevel): TagType {
  const map: Record<RiskLevel, TagType> = {
    red_intervention: 'danger',
    yellow_attention: 'warning',
    green_normal: 'success',
  }
  return map[level] || 'info'
}

/** 风险等级 → 色值 */
export function riskLevelColor(level: RiskLevel): string {
  const map: Record<RiskLevel, string> = {
    red_intervention: '#f56c6c',
    yellow_attention: '#e6a23c',
    green_normal: '#67c23a',
  }
  return map[level] || '#909399'
}

/** 风险等级 → 背景色 (浅色卡片) */
export function riskLevelBg(level: RiskLevel): string {
  const map: Record<RiskLevel, string> = {
    red_intervention: '#fef0f0',
    yellow_attention: '#fdf6ec',
    green_normal: '#f0f9eb',
  }
  return map[level] || '#f4f4f5'
}

/** RDI 分数格式化 */
export function formatRdiScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return '—'
  return score.toFixed(2)
}

/** 偏离度格式化 (σ) */
export function formatSigma(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  const sign = val >= 0 ? '+' : ''
  return `${sign}${val.toFixed(2)}σ`
}

/** 百分比格式化 (0-100 → xx.x%) */
export function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  return `${val.toFixed(1)}%`
}

/** 时间格式化 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
