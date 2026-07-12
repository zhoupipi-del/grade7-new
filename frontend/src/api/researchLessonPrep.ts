/**
 * researchLessonPrep.ts — 集体备课协同编辑引擎 API 契约层
 *
 * 对应后端模块: modules/research_lesson_prep
 * URL前缀: /api/v1/research_lesson_prep (module_loader 覆盖为下划线)
 *
 * 端点清单 (16):
 *   POST   /research_lesson_prep/                      — 创建备课主案(+V1初始版本)
 *   GET    /research_lesson_prep/                      — 教案列表(分页+筛选)
 *   GET    /research_lesson_prep/dashboard             — 教案统计看板
 *   GET    /research_lesson_prep/{plan_id}             — 教案详情(含最新版本+未解决批注数)
 *   PUT    /research_lesson_prep/{plan_id}             — 更新教案元信息
 *   DELETE /research_lesson_prep/{plan_id}             — 删除教案(PUBLISHED不可删)
 *   POST   /research_lesson_prep/{plan_id}/versions    — 创建新版本快照
 *   GET    /research_lesson_prep/{plan_id}/versions    — 版本历史列表
 *   GET    /research_lesson_prep/{plan_id}/versions/{version_number} — 获取特定版本
 *   POST   /research_lesson_prep/{plan_id}/reviews     — 添加批注(组长/管理员)
 *   GET    /research_lesson_prep/{plan_id}/reviews     — 批注列表
 *   PUT    /research_lesson_prep/{plan_id}/reviews/{review_id} — 解决批注
 *   POST   /research_lesson_prep/{plan_id}/submit      — DRAFT→COLLECTIVE_REVIEW
 *   POST   /research_lesson_prep/{plan_id}/approve     — COLLECTIVE_REVIEW→ADMIN_APPROVE
 *   POST   /research_lesson_prep/{plan_id}/publish     — ADMIN_APPROVE→PUBLISHED
 *   POST   /research_lesson_prep/{plan_id}/reject      — REVIEW/APPROVED→DRAFT
 *   POST   /research_lesson_prep/{plan_id}/fork        — Fork派生新教案
 */

import request from './request'

/* ──────────────── 类型定义 ──────────────── */

export type PlanStatus = 'DRAFT' | 'COLLECTIVE_REVIEW' | 'ADMIN_APPROVE' | 'PUBLISHED'
export type LessonType = 'new' | 'review' | 'exam' | 'test' | 'activity'
export type ReviewSeverity = 'suggestion' | 'issue' | 'critical'

export interface TeachingProcessStep {
  phase: string
  duration: number
  content: string
  activities: string[]
  resources: string[]
}

export interface LessonContent {
  teaching_objectives: string[]
  key_points: string[]
  difficulties: string[]
  teaching_methods: string[]
  teaching_process: TeachingProcessStep[]
  homework: string[]
  blackboard_design: string
  reflection: string
}

export interface PlanResponse {
  id: number
  school_id: number
  title: string
  description: string | null
  subject_code: string
  grade_level: string
  lesson_type: LessonType
  duration: number
  tags: string[]
  status: PlanStatus
  status_updated_at: string | null
  current_version: number
  published_version: number | null
  reference_count: number
  fork_count: number
  creator_id: number
  creator_name: string | null
  grade_leader_id: number | null
  forked_from_id: number | null
  created_at: string
  updated_at: string
}

export interface PlanDetailResponse extends PlanResponse {
  latest_content: LessonContent | null
  latest_version_number: number | null
  unresolved_review_count: number
}

export interface VersionResponse {
  id: number
  plan_id: number
  version_number: number
  editor_id: number
  editor_name: string | null
  content: LessonContent
  change_log: string | null
  is_major: boolean
  created_at: string
}

export interface ReviewResponse {
  id: number
  plan_id: number
  version_number: number
  reviewer_id: number
  reviewer_name: string | null
  target_section: string
  target_anchor: string | null
  comment: string
  severity: ReviewSeverity
  is_resolved: boolean
  resolved_by: number | null
  resolved_at: string | null
  resolution_note: string | null
  parent_review_id: number | null
  created_at: string
}

export interface DashboardStats {
  total_plans: number
  draft_count: number
  review_count: number
  approved_count: number
  published_count: number
  total_versions: number
  total_reviews: number
  unresolved_reviews: number
  by_subject: Record<string, number>
  by_grade: Record<string, number>
  top_creators: Array<{ user_id: number; user_name: string; count: number }>
}

/* ──────────────── 请求 Payload ──────────────── */

export interface PlanCreatePayload {
  title: string
  description?: string
  subject_code: string
  grade_level: string
  lesson_type?: LessonType
  duration?: number
  tags?: string[]
  content: LessonContent
  change_log?: string
}

export interface PlanUpdatePayload {
  title?: string
  description?: string
  lesson_type?: LessonType
  duration?: number
  tags?: string[]
}

export interface VersionCreatePayload {
  content: LessonContent
  change_log?: string
  is_major?: boolean
}

export interface ReviewCreatePayload {
  version_number: number
  target_section: string
  target_anchor?: string
  comment: string
  severity?: ReviewSeverity
  parent_review_id?: number
}

export interface ReviewResolvePayload {
  resolution_note?: string
}

export interface StatusTransitionPayload {
  reject_reason?: string
}

export interface PlanForkPayload {
  title: string
}

export interface ListParams {
  subject_code?: string
  grade_level?: string
  status?: PlanStatus
  creator_id?: number
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

/** POST — 创建备课主案 */
export function createPlan(payload: PlanCreatePayload) {
  return request.post<any, PlanDetailResponse>('/research_lesson_prep/', payload)
}

/** GET — 教案列表 */
export function listPlans(params?: ListParams) {
  return request.get<any, ListResponse<PlanResponse>>('/research_lesson_prep/', { params })
}

/** GET — 教案统计看板 */
export function getDashboard() {
  return request.get<any, DashboardStats>('/research_lesson_prep/dashboard')
}

/** GET — 教案详情 */
export function getPlan(planId: number) {
  return request.get<any, PlanDetailResponse>(`/research_lesson_prep/${planId}`)
}

/** PUT — 更新教案元信息 */
export function updatePlan(planId: number, payload: PlanUpdatePayload) {
  return request.put<any, PlanResponse>(`/research_lesson_prep/${planId}`, payload)
}

/** DELETE — 删除教案 */
export function deletePlan(planId: number) {
  return request.delete<any, { message: string }>(`/research_lesson_prep/${planId}`)
}

/** POST — 创建新版本快照 */
export function createVersion(planId: number, payload: VersionCreatePayload) {
  return request.post<any, VersionResponse>(`/research_lesson_prep/${planId}/versions`, payload)
}

/** GET — 版本历史列表 */
export function listVersions(planId: number) {
  return request.get<any, ListResponse<VersionResponse>>(`/research_lesson_prep/${planId}/versions`)
}

/** GET — 获取特定版本 */
export function getVersion(planId: number, versionNumber: number) {
  return request.get<any, VersionResponse>(`/research_lesson_prep/${planId}/versions/${versionNumber}`)
}

/** POST — 添加批注 */
export function createReview(planId: number, payload: ReviewCreatePayload) {
  return request.post<any, ReviewResponse>(`/research_lesson_prep/${planId}/reviews`, payload)
}

/** GET — 批注列表 */
export function listReviews(planId: number, params?: { version_number?: number; unresolved_only?: boolean }) {
  return request.get<any, ListResponse<ReviewResponse>>(`/research_lesson_prep/${planId}/reviews`, { params })
}

/** PUT — 解决批注 */
export function resolveReview(planId: number, reviewId: number, payload: ReviewResolvePayload) {
  return request.put<any, ReviewResponse>(`/research_lesson_prep/${planId}/reviews/${reviewId}`, payload)
}

/** POST — 提交进入集体评议 DRAFT→COLLECTIVE_REVIEW */
export function submitPlan(planId: number) {
  return request.post<any, PlanResponse>(`/research_lesson_prep/${planId}/submit`)
}

/** POST — 审核通过 COLLECTIVE_REVIEW→ADMIN_APPROVE */
export function approvePlan(planId: number) {
  return request.post<any, PlanResponse>(`/research_lesson_prep/${planId}/approve`)
}

/** POST — 发布 ADMIN_APPROVE→PUBLISHED */
export function publishPlan(planId: number) {
  return request.post<any, PlanResponse>(`/research_lesson_prep/${planId}/publish`)
}

/** POST — 打回草稿 REVIEW/APPROVED→DRAFT */
export function rejectPlan(planId: number, payload: StatusTransitionPayload) {
  return request.post<any, PlanResponse>(`/research_lesson_prep/${planId}/reject`, payload)
}

/** POST — Fork派生新教案 */
export function forkPlan(planId: number, payload: PlanForkPayload) {
  return request.post<any, PlanDetailResponse>(`/research_lesson_prep/${planId}/fork`, payload)
}

/* ──────────────── 辅助函数 ──────────────── */

type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

/** 教案状态 → el-tag type */
export function planStatusTag(status: PlanStatus): TagType {
  const map: Record<PlanStatus, TagType> = {
    DRAFT: 'info',
    COLLECTIVE_REVIEW: 'warning',
    ADMIN_APPROVE: 'primary',
    PUBLISHED: 'success',
  }
  return map[status] || 'info'
}

/** 教案状态 → 中文标签 */
export function planStatusLabel(status: PlanStatus): string {
  const map: Record<PlanStatus, string> = {
    DRAFT: '草稿',
    COLLECTIVE_REVIEW: '集体评议',
    ADMIN_APPROVE: '待发布',
    PUBLISHED: '已发布',
  }
  return map[status] || status
}

/** 课型 → 中文标签 */
export function lessonTypeLabel(type: LessonType): string {
  const map: Record<LessonType, string> = {
    new: '新授课',
    review: '复习课',
    exam: '测验课',
    test: '考试课',
    activity: '活动课',
  }
  return map[type] || type
}

/** 批注严重度 → el-tag type */
export function severityTag(severity: ReviewSeverity): TagType {
  const map: Record<ReviewSeverity, TagType> = {
    suggestion: 'info',
    issue: 'warning',
    critical: 'danger',
  }
  return map[severity] || 'info'
}

/** 批注严重度 → 中文标签 */
export function severityLabel(severity: ReviewSeverity): string {
  const map: Record<ReviewSeverity, string> = {
    suggestion: '建议',
    issue: '问题',
    critical: '严重',
  }
  return map[severity] || severity
}

/** 教学环节 → 中文标签 */
export function phaseLabel(phase: string): string {
  const map: Record<string, string> = {
    '导入': '导入',
    '新授': '新授',
    '练习': '练习',
    '小结': '小结',
    '作业': '作业',
  }
  return map[phase] || phase
}

/** 状态流转步骤（用于流水线可视化） */
export const PLAN_STATUS_PIPELINE: PlanStatus[] = ['DRAFT', 'COLLECTIVE_REVIEW', 'ADMIN_APPROVE', 'PUBLISHED']
