import request from './request'

/**
 * Data Adapter API — 数据并网适配层
 *
 * 支持初中/高中成绩 Excel 上传，高中走 3+1+2 等级赋分管道
 */

export interface PipelineSubjectMetrics {
  total: number
  active: number
}

export interface CleanError {
  row: number
  column: string
  raw_value: string | null
  error_type: string
  message: string
}

export interface UploadScoresResponse {
  status: string
  phase: string
  template_code: string
  template_name: string
  total_rows: number
  success_rows: number
  failed_rows: number
  skipped_rows: number
  errors: CleanError[]
  preview_data?: any[]
  message: string
  task_id: number
  pipeline_summary?: Record<string, PipelineSubjectMetrics>
}

/**
 * POST /data_adapter/upload-scores — 上传成绩 Excel
 * 高中学段自动触发 3+1+2 等级赋分级联落盘管道
 */
export function uploadScores(file: File, examId?: number) {
  const formData = new FormData()
  formData.append('file', file)
  if (examId !== undefined && examId !== null) {
    formData.append('exam_id', examId.toString())
  }
  return request.post<any, UploadScoresResponse>(
    '/data_adapter/upload-scores',
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }
  )
}

/**
 * GET /data_adapter/templates — 获取可用模板列表
 */
export function getTemplates() {
  return request.get<any, any[]>('/data_adapter/templates')
}

/**
 * GET /data_adapter/health — 健康检查
 */
export function healthCheck() {
  return request.get<any, { status: string; module: string }>('/data_adapter/health')
}

/**
 * GET /data_adapter/exams/{exam_id}/zscore-matrix — Z-Score 热力图矩阵
 */
export function getZscoreMatrix(examId: number) {
  return request.get<any, {
    status: string
    exam_id: number
    data: {
      classes: string[]
      class_ids: number[]
      subjects: string[]
      matrix_data: [number, number, number][]
      global_subject_stats: Record<string, { mean: number; std: number }>
    }
  }>(`/data_adapter/exams/${examId}/zscore-matrix`)
}

// ============================================================
// RDI 风险预警 & AI 处方
// ============================================================

export interface RiskAlert {
  id: number
  student_id: number
  exam_id: number
  risk_type: string
  risk_level: string
  trigger_reason: string
  lineage_graph: {
    nodes: Array<{
      id: string
      layer: string
      label: string
      data: Record<string, any>
    }>
    edges: Array<{ source: string; target: string; label?: string }>
  }
  status: string
  created_at: string | null
}

export interface Prescription {
  id: number
  alert_id: number | null
  student_id: number
  subject_code: string
  raw_score: number | null
  scaled_score: number | null
  z_score: number | null
  weakness_analysis: string
  action_prescription: string
  model_metadata: Record<string, any> | null
  created_at: string | null
}

/**
 * GET /data_adapter/exams/{exam_id}/alerts — 拉取考试的活动预警
 */
export function getRiskAlerts(examId: number) {
  return request.get<any, {
    status: string
    exam_id: number
    total: number
    alerts: RiskAlert[]
  }>(`/data_adapter/exams/${examId}/alerts`)
}

/**
 * GET /data_adapter/alerts/{alert_id}/prescriptions — 调阅预警关联的 AI 处方
 */
export function getPrescriptions(alertId: number) {
  return request.get<any, {
    status: string
    alert_id: number
    total: number
    prescriptions: Prescription[]
  }>(`/data_adapter/alerts/${alertId}/prescriptions`)
}

/**
 * POST /data_adapter/exams/{exam_id}/rdi-analysis — 触发 RDI + AI 全链路
 */
export function triggerRdiAnalysis(examId: number) {
  return request.post<any, {
    status: string
    exam_id: number
    data: Record<string, any>
    ai_prescriptions: Record<string, any> | null
  }>(`/data_adapter/exams/${examId}/rdi-analysis`)
}

// ============================================================
// AI 处方全景大盘 V3
// ============================================================

export interface PrescriptionV3Item {
  id: number
  alert_id: number | null
  student_id: number
  student_name: string
  class_name: string
  subject_code: string
  raw_score: number | null
  scaled_score: number | null
  z_score: number | null
  weakness_analysis: string
  action_prescription: string
  habit_diagnosis: string
  emotion_anchor: string
  weekly_plan_json: any
  parent_guide: string
  model_metadata: Record<string, any> | null
  created_at: string | null
}

export interface PrescriptionListResponse {
  status: string
  total: number
  page: number
  page_size: number
  prescriptions: PrescriptionV3Item[]
}

export interface PrescriptionListQuery {
  exam_id?: number
  subject_code?: string
  risk_level?: string
  student_name?: string
  page?: number
  page_size?: number
}

/**
 * GET /data_adapter/prescriptions — AI 处方全景大盘
 * 支持按考试、学科、风险等级、学生姓名分页过滤
 */
export function listPrescriptions(params: PrescriptionListQuery) {
  return request.get<any, PrescriptionListResponse>('/data_adapter/prescriptions', { params })
}
