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
