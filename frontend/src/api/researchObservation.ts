/**
 * researchObservation.ts — 听课评课量化追踪 API 契约层
 *
 * 对应后端模块: modules/research_observation
 * URL前缀: /api/v1/research_observation
 *
 * 端点清单 (13):
 *   POST   /research_observation/                        — 创建听课记录(不能听自己的课)
 *   GET    /research_observation/                        — 听课列表(多维度筛选)
 *   GET    /research_observation/dashboard               — 听课统计看板
 *   GET    /research_observation/teacher/{teacher_id}    — 教师被听课历史
 *   GET    /research_observation/{obs_id}                — 听课详情(含评分矩阵+申诉历史)
 *   PUT    /research_observation/{obs_id}                — 更新听课记录(仅pending)
 *   DELETE /research_observation/{obs_id}                — 删除听课记录(仅pending)
 *   POST   /research_observation/{obs_id}/rubric         — 提交多维评分
 *   GET    /research_observation/{obs_id}/rubric         — 获取评分矩阵
 *   POST   /research_observation/{obs_id}/confirm        — 教师确认评课 PENDING→CONFIRMED
 *   POST   /research_observation/{obs_id}/appeal         — 教师申诉 PENDING→APPEALED
 *   POST   /research_observation/{obs_id}/resolve        — 处理申诉 APPEALED→RESOLVED
 *   GET    /research_observation/{obs_id}/appeals        — 申诉/反馈历史
 */

import request from './request'

/* ──────────────── 类型定义 ──────────────── */

export type FeedbackStatus = 'pending' | 'confirmed' | 'appealed' | 'resolved'
export type ObservationType = 'routine' | 'thematic' | 'follow_up' | 'open_class'
export type PlanAdherence = 'full' | 'partial' | 'deviated'

export interface RubricDimension {
  name: string
  score: number
  max: number
  weight: number | null
  comment: string
}

export interface TextFeedback {
  highlights: string[]
  suggestions: string[]
  overall_comment: string
}

export interface RubricResponse {
  id: number
  observation_id: number
  template_name: string | null
  rubric_metrics: Record<string, any>[]
  total_score: number
  max_score: number
  percentage: number | null
  scorer_id: number
  scorer_name: string | null
  created_at: string
}

export interface AppealResponse {
  id: number
  observation_id: number
  teacher_id: number
  teacher_name: string | null
  action_type: string
  appeal_reason: string | null
  appealed_dimensions: string[]
  resolution: string | null
  resolved_by: number | null
  score_adjusted: boolean
  adjusted_total_score: number | null
  created_at: string
  resolved_at: string | null
}

export interface ObservationResponse {
  id: number
  school_id: number
  observer_id: number
  observer_name: string | null
  teacher_id: number
  teacher_name: string | null
  class_id: number
  class_name: string | null
  subject_code: string
  lesson_title: string | null
  observation_type: ObservationType
  lesson_plan_id: number | null
  plan_version_number: number | null
  score_total: number | null
  score_max: number
  score_percentage: number | null
  grade: string | null
  text_feedback: TextFeedback | null
  plan_adherence: PlanAdherence | null
  plan_deviation_note: string | null
  feedback_status: FeedbackStatus
  feedback_status_updated_at: string | null
  teacher_viewed_at: string | null
  observed_at: string
  duration_minutes: number
  created_at: string
  updated_at: string
}

export interface ObservationDetailResponse extends ObservationResponse {
  rubric: RubricResponse | null
  appeals: AppealResponse[]
  plan_title: string | null
  plan_status: string | null
}

export interface DashboardStats {
  total_observations: number
  pending_feedback: number
  confirmed: number
  appealed: number
  resolved: number
  avg_score: number | null
  by_type: Record<string, number>
  by_grade: Record<string, number>
  by_subject: Record<string, number>
  top_observers: Array<{ user_id: number; user_name: string; count: number }>
  top_teachers: Array<{ user_id: number; user_name: string; count: number }>
}

/* ──────────────── 请求 Payload ──────────────── */

export interface ObservationCreatePayload {
  teacher_id: number
  class_id: number
  subject_code: string
  lesson_title?: string
  observation_type?: ObservationType
  lesson_plan_id?: number
  plan_version_number?: number
  observed_at: string
  duration_minutes?: number
  text_feedback?: TextFeedback
  plan_adherence?: PlanAdherence
  plan_deviation_note?: string
}

export interface ObservationUpdatePayload {
  lesson_title?: string
  observation_type?: ObservationType
  text_feedback?: TextFeedback
  plan_adherence?: PlanAdherence
  plan_deviation_note?: string
}

export interface RubricSubmitPayload {
  template_name?: string
  dimensions: RubricDimension[]
}

export interface TeacherAppealPayload {
  appeal_reason: string
  appealed_dimensions?: string[]
}

export interface AppealResolvePayload {
  resolution: string
  score_adjusted?: boolean
  adjusted_total_score?: number
}

export interface ListParams {
  observer_id?: number
  teacher_id?: number
  class_id?: number
  subject_code?: string
  feedback_status?: FeedbackStatus
  observation_type?: ObservationType
  page?: number
  page_size?: number
}

export interface ListResponse<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

/* ──────────────── API 函数 ──────────────── */

/** POST — 创建听课记录 */
export function createObservation(payload: ObservationCreatePayload) {
  return request.post<any, ObservationResponse>('/research_observation/', payload)
}

/** GET — 听课列表 */
export function listObservations(params?: ListParams) {
  return request.get<any, ListResponse<ObservationResponse>>('/research_observation/', { params })
}

/** GET — 听课统计看板 */
export function getDashboard() {
  return request.get<any, DashboardStats>('/research_observation/dashboard')
}

/** GET — 教师被听课历史 */
export function getTeacherHistory(teacherId: number, params?: { page?: number; page_size?: number }) {
  return request.get<any, ListResponse<ObservationResponse>>(`/research_observation/teacher/${teacherId}`, { params })
}

/** GET — 听课详情 */
export function getObservation(obsId: number) {
  return request.get<any, ObservationDetailResponse>(`/research_observation/${obsId}`)
}

/** PUT — 更新听课记录 */
export function updateObservation(obsId: number, payload: ObservationUpdatePayload) {
  return request.put<any, ObservationResponse>(`/research_observation/${obsId}`, payload)
}

/** DELETE — 删除听课记录 */
export function deleteObservation(obsId: number) {
  return request.delete<any, { message: string }>(`/research_observation/${obsId}`)
}

/** POST — 提交多维评分 */
export function submitRubric(obsId: number, payload: RubricSubmitPayload) {
  return request.post<any, RubricResponse>(`/research_observation/${obsId}/rubric`, payload)
}

/** GET — 获取评分矩阵 */
export function getRubric(obsId: number) {
  return request.get<any, RubricResponse>(`/research_observation/${obsId}/rubric`)
}

/** POST — 教师确认评课 */
export function teacherConfirm(obsId: number) {
  return request.post<any, ObservationResponse>(`/research_observation/${obsId}/confirm`)
}

/** POST — 教师申诉 */
export function teacherAppeal(obsId: number, payload: TeacherAppealPayload) {
  return request.post<any, ObservationResponse>(`/research_observation/${obsId}/appeal`, payload)
}

/** POST — 处理申诉 */
export function resolveAppeal(obsId: number, payload: AppealResolvePayload) {
  return request.post<any, ObservationResponse>(`/research_observation/${obsId}/resolve`, payload)
}

/** GET — 申诉/反馈历史 */
export function listAppeals(obsId: number) {
  return request.get<any, ListResponse<AppealResponse>>(`/research_observation/${obsId}/appeals`)
}

/* ──────────────── 辅助函数 ──────────────── */

type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

/** 反馈状态 → el-tag type */
export function feedbackStatusTag(status: FeedbackStatus): TagType {
  const map: Record<FeedbackStatus, TagType> = {
    pending: 'warning',
    confirmed: 'success',
    appealed: 'danger',
    resolved: 'info',
  }
  return map[status] || 'info'
}

/** 反馈状态 → 中文标签 */
export function feedbackStatusLabel(status: FeedbackStatus): string {
  const map: Record<FeedbackStatus, string> = {
    pending: '待确认',
    confirmed: '已确认',
    appealed: '申诉中',
    resolved: '已裁决',
  }
  return map[status] || status
}

/** 听课类型 → 中文标签 */
export function observationTypeLabel(type: ObservationType): string {
  const map: Record<ObservationType, string> = {
    routine: '常规听课',
    thematic: '专题听课',
    follow_up: '跟踪听课',
    open_class: '公开课',
  }
  return map[type] || type
}

/** 教案执行度 → 中文标签 */
export function planAdherenceLabel(adherence: PlanAdherence): string {
  const map: Record<PlanAdherence, string> = {
    full: '完全执行',
    partial: '部分执行',
    deviated: '偏离教案',
  }
  return map[adherence] || adherence
}

/** 教案执行度 → el-tag type */
export function planAdherenceTag(adherence: PlanAdherence): TagType {
  const map: Record<PlanAdherence, TagType> = {
    full: 'success',
    partial: 'warning',
    deviated: 'danger',
  }
  return map[adherence] || 'info'
}

/** 分数 → 等级标签 */
export function scoreGrade(percentage: number | null): { label: string; tag: TagType } {
  if (percentage === null) return { label: '未评分', tag: 'info' }
  if (percentage >= 90) return { label: '优秀', tag: 'success' }
  if (percentage >= 80) return { label: '良好', tag: 'primary' }
  if (percentage >= 70) return { label: '合格', tag: 'warning' }
  return { label: '待改进', tag: 'danger' }
}
