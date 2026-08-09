/**
 * errorFunnel.ts — 错题断层漏斗引擎 API 契约层
 *
 * 对应后端模块: modules/error_funnel
 * URL前缀: /api/v1/error_funnel
 *
 * 端点清单 (11):
 *   GET    /error_funnel/knowledge-points                    — 知识点树
 *   POST   /error_funnel/knowledge-points                    — 创建知识点
 *   PUT    /error_funnel/knowledge-points/{kp_id}            — 更新知识点
 *   GET    /error_funnel/errors                              — 错题列表(筛选+分页)
 *   POST   /error_funnel/errors                              — 手动添加错题
 *   PUT    /error_funnel/errors/{error_id}/resolve           — 标记错题已解决
 *   GET    /error_funnel/gaps                                — 断层列表(筛选+分页)
 *   POST   /error_funnel/gaps/{gap_id}/resolve               — 标记断层已解决
 *   POST   /error_funnel/gaps/{gap_id}/generate-prescription — 生成AI处方
 *   GET    /error_funnel/dashboard                           — 漏斗看板
 *   POST   /error_funnel/import-from-exam                    — 从考试批量导入错题
 */

import request from './request'

/* ──────────────── 类型定义 ──────────────── */

export type GapLevel = 'watch' | 'warning' | 'critical'
export type GapStatus = 'active' | 'resolved'
export type ErrorType = 'conceptual' | 'procedural' | 'careless' | 'omission' | 'unknown'
export type SourceType = 'homework' | 'exam' | 'manual' | 'import'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type AIStatus = 'pending' | 'analyzing' | 'analyzed' | 'failed'

export interface KnowledgePointResponse {
  id: number
  school_id: number
  subject_id: number
  subject_name: string | null
  name: string
  code: string | null
  description: string | null
  parent_id: number | null
  sort_order: number
  is_active: boolean
  created_at: string | null
  children: KnowledgePointResponse[] | null
}

export interface KnowledgePointCreatePayload {
  subject_id: number
  name: string
  code?: string | null
  description?: string | null
  parent_id?: number | null
  sort_order?: number
}

export interface KnowledgePointUpdatePayload {
  name?: string
  code?: string | null
  description?: string | null
  parent_id?: number | null
  sort_order?: number
  is_active?: boolean
}

export interface ErrorItemResponse {
  id: number
  school_id: number
  student_id: number
  student_name: string | null
  subject_id: number
  subject_name: string | null
  source_type: SourceType
  source_id: number | null
  source_desc: string | null
  question_content: string
  question_type: string | null
  student_answer: string | null
  correct_answer: string | null
  error_type: ErrorType
  knowledge_point_ids: number[] | null
  knowledge_point_names: string[] | null
  difficulty: Difficulty | null
  ai_analysis: string | null
  ai_status: AIStatus
  is_resolved: boolean
  resolved_at: string | null
  created_at: string | null
}

export interface ErrorItemCreatePayload {
  student_id: number
  subject_id: number
  source_type?: SourceType
  source_id?: number | null
  source_desc?: string | null
  question_content: string
  question_type?: string | null
  student_answer?: string | null
  correct_answer?: string | null
  error_type: ErrorType
  knowledge_point_ids?: number[] | null
  difficulty?: Difficulty | null
}

export interface KnowledgeGapResponse {
  id: number
  school_id: number
  student_id: number
  student_name: string | null
  subject_id: number
  subject_name: string | null
  knowledge_point_id: number
  knowledge_point_name: string
  error_count: number
  consecutive_errors: number
  last_error_date: string | null
  last_error_source: string | null
  gap_level: GapLevel
  gap_status: GapStatus
  resolved_at: string | null
  ai_prescription: string | null
  ai_prescription_generated_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DashboardResponse {
  total_errors: number
  unresolved_errors: number
  total_gaps: number
  critical_gaps: number
  warning_gaps: number
  watch_gaps: number
  resolved_gaps: number
  ai_prescriptions_generated: number
  top_error_knowledge_points: Record<string, any>[]
  top_error_students: Record<string, any>[]
  error_type_distribution: Record<string, number>
  recent_errors: Record<string, any>[]
}

export interface BatchImportFromExamPayload {
  exam_id: number
  subject_id: number
  threshold?: number
}

export interface PrescriptionResponse {
  gap_id: number
  student_name: string
  knowledge_point_name: string
  gap_level: GapLevel
  prescription: {
    weakness_analysis: string
    action_prescription: string
  }
  generated_at: string
}

export interface ListResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/* ──────────────── API 函数 ──────────────── */

export function listKnowledgePoints(params?: { subject_id?: number }) {
  return request.get<any, KnowledgePointResponse[]>('/error_funnel/knowledge-points', { params })
}

export function createKnowledgePoint(data: KnowledgePointCreatePayload) {
  return request.post<any, KnowledgePointResponse>('/error_funnel/knowledge-points', data)
}

export function updateKnowledgePoint(kpId: number, data: KnowledgePointUpdatePayload) {
  return request.put<any, KnowledgePointResponse>(`/error_funnel/knowledge-points/${kpId}`, data)
}

export function listErrors(params?: {
  student_id?: number
  subject_id?: number
  knowledge_point_id?: number
  error_type?: ErrorType
  source_type?: SourceType
  is_resolved?: boolean
  page?: number
  page_size?: number
}) {
  return request.get<any, ListResponse<ErrorItemResponse>>('/error_funnel/errors', { params })
}

export function createError(data: ErrorItemCreatePayload) {
  return request.post<any, ErrorItemResponse>('/error_funnel/errors', data)
}

export function resolveError(errorId: number) {
  return request.put<any, { message: string }>(`/error_funnel/errors/${errorId}/resolve`)
}

export function listGaps(params?: {
  student_id?: number
  subject_id?: number
  knowledge_point_id?: number
  gap_level?: GapLevel
  gap_status?: GapStatus
  page?: number
  page_size?: number
}) {
  return request.get<any, ListResponse<KnowledgeGapResponse>>('/error_funnel/gaps', { params })
}

export function resolveGap(gapId: number) {
  return request.post<any, { message: string }>(`/error_funnel/gaps/${gapId}/resolve`)
}

export function generatePrescription(gapId: number) {
  return request.post<any, PrescriptionResponse>(`/error_funnel/gaps/${gapId}/generate-prescription`)
}

export function getDashboard() {
  return request.get<any, DashboardResponse>('/error_funnel/dashboard')
}

export function importFromExam(data: BatchImportFromExamPayload) {
  return request.post<any, { imported: number; message: string }>('/error_funnel/import-from-exam', data)
}

/* ──────────────── 映射工具 ──────────────── */

export function gapLevelLabel(level: GapLevel): string {
  const map: Record<GapLevel, string> = {
    watch: '关注',
    warning: '预警',
    critical: '临界',
  }
  return map[level] || level
}

export function gapLevelTag(level: GapLevel): string {
  const map: Record<GapLevel, string> = {
    watch: 'info',
    warning: 'warning',
    critical: 'danger',
  }
  return map[level] || 'info'
}

export function gapStatusLabel(status: GapStatus): string {
  return status === 'active' ? '活跃' : '已解决'
}

export function gapStatusTag(status: GapStatus): string {
  return status === 'active' ? 'danger' : 'success'
}

export function errorTypeLabel(type: ErrorType): string {
  const map: Record<ErrorType, string> = {
    conceptual: '概念性错误',
    procedural: '程序性错误',
    careless: '粗心错误',
    omission: '遗漏错误',
    unknown: '未知错误',
  }
  return map[type] || type
}

export function errorTypeTag(type: ErrorType): string {
  const map: Record<ErrorType, string> = {
    conceptual: 'danger',
    procedural: 'warning',
    careless: 'info',
    omission: 'warning',
    unknown: 'info',
  }
  return map[type] || 'info'
}

export function sourceTypeLabel(type: SourceType): string {
  const map: Record<SourceType, string> = {
    homework: '作业',
    exam: '考试',
    manual: '手动',
    import: '导入',
  }
  return map[type] || type
}

export function sourceTypeTag(type: SourceType): string {
  const map: Record<SourceType, string> = {
    homework: 'primary',
    exam: 'danger',
    manual: 'info',
    import: 'warning',
  }
  return map[type] || 'info'
}

export function difficultyLabel(d: Difficulty): string {
  const map: Record<Difficulty, string> = { easy: '简单', medium: '中等', hard: '困难' }
  return map[d] || d
}

export function difficultyTag(d: Difficulty): string {
  const map: Record<Difficulty, string> = { easy: 'success', medium: 'warning', hard: 'danger' }
  return map[d] || 'info'
}

export function aiStatusLabel(status: AIStatus): string {
  const map: Record<AIStatus, string> = {
    pending: '待分析',
    analyzing: '分析中',
    analyzed: '已分析',
    failed: '分析失败',
  }
  return map[status] || status
}

export function aiStatusTag(status: AIStatus): string {
  const map: Record<AIStatus, string> = {
    pending: 'info',
    analyzing: 'warning',
    analyzed: 'success',
    failed: 'danger',
  }
  return map[status] || 'info'
}
