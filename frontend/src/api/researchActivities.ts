/**
 * researchActivities.ts — 教研活动管理 API 契约层
 *
 * 对应后端模块: modules/research_activities
 * URL前缀: /api/v1/research_activities
 *
 * 端点清单 (17):
 *   POST   /research_activities/                              — 创建教研活动
 *   GET    /research_activities/                              — 活动列表(筛选+分页)
 *   GET    /research_activities/dashboard                     — 活动统计看板
 *   GET    /research_activities/{act_id}                      — 活动详情(含参与人+议题)
 *   PUT    /research_activities/{act_id}                      — 更新活动信息
 *   DELETE /research_activities/{act_id}                      — 删除活动(仅planned/cancelled)
 *   POST   /research_activities/{act_id}/start                — PLANNED→IN_PROGRESS
 *   POST   /research_activities/{act_id}/complete             — IN_PROGRESS→COMPLETED
 *   POST   /research_activities/{act_id}/cancel               — PLANNED→CANCELLED
 *   POST   /research_activities/{act_id}/participants         — 添加参与人
 *   GET    /research_activities/{act_id}/participants         — 参与人列表
 *   PUT    /research_activities/{act_id}/participants/{pid}   — 更新参与人(签到/签退/贡献度)
 *   DELETE /research_activities/{act_id}/participants/{pid}   — 移除参与人
 *   POST   /research_activities/{act_id}/agendas              — 添加议题
 *   GET    /research_activities/{act_id}/agendas              — 议题列表
 *   PUT    /research_activities/{act_id}/agendas/{aid}        — 更新议题(决议/状态/关联)
 *   DELETE /research_activities/{act_id}/agendas/{aid}        — 删除议题
 */

import request from './request'

/* ──────────────── 类型定义 ──────────────── */

export type ActivityStatus = 'planned' | 'in_progress' | 'completed' | 'cancelled'
export type ActivityType = 'regular_meeting' | 'lesson_study' | 'thematic_research' | 'grade_meeting' | 'cross_grade' | 'training'
export type ParticipantRole = 'organizer' | 'presenter' | 'recorder' | 'participant'
export type AttendanceStatus = 'registered' | 'checked_in' | 'checked_out' | 'absent' | 'late'
export type AgendaStatus = 'planned' | 'in_discussion' | 'resolved' | 'deferred'

export interface ActivityResponse {
  id: number
  school_id: number
  title: string
  description: string | null
  activity_type: ActivityType
  subject_code: string
  grade_level: string | null
  planned_at: string
  planned_end_at: string | null
  actual_start_at: string | null
  actual_end_at: string | null
  location: string | null
  status: ActivityStatus
  status_updated_at: string | null
  cancel_reason: string | null
  organizer_id: number
  organizer_name: string | null
  summary: string | null
  decisions: string[]
  attachments: Record<string, any>[]
  linked_plan_ids: number[]
  linked_observation_ids: number[]
  participant_count: number
  agenda_count: number
  created_at: string
  updated_at: string
}

export interface ParticipantResponse {
  id: number
  activity_id: number
  user_id: number
  user_name: string | null
  role: ParticipantRole
  attendance_status: AttendanceStatus
  check_in_at: string | null
  check_out_at: string | null
  contribution_score: number | null
  contribution_note: string | null
  note: string | null
  created_at: string
}

export interface AgendaResponse {
  id: number
  activity_id: number
  seq: number
  title: string
  presenter_id: number | null
  presenter_name: string | null
  content: string | null
  planned_duration: number | null
  actual_duration: number | null
  decision: string | null
  status: AgendaStatus
  linked_plan_id: number | null
  linked_observation_id: number | null
  created_at: string
  updated_at: string
}

export interface ActivityDetailResponse extends ActivityResponse {
  participants: ParticipantResponse[]
  agendas: AgendaResponse[]
}

export interface DashboardStats {
  total_activities: number
  planned: number
  in_progress: number
  completed: number
  cancelled: number
  total_participants: number
  total_agendas: number
  resolved_agendas: number
  by_type: Record<string, number>
  by_subject: Record<string, number>
  by_month: Record<string, number>
  top_organizers: Array<{ user_id: number; user_name: string; count: number }>
}

/* ──────────────── 请求 Payload ──────────────── */

export interface ActivityCreatePayload {
  title: string
  description?: string
  activity_type?: ActivityType
  subject_code: string
  grade_level?: string
  planned_at: string
  planned_end_at?: string
  location?: string
  linked_plan_ids?: number[]
  linked_observation_ids?: number[]
  participant_ids?: number[]
}

export interface ActivityUpdatePayload {
  title?: string
  description?: string
  activity_type?: ActivityType
  grade_level?: string
  planned_at?: string
  planned_end_at?: string
  location?: string
  summary?: string
  decisions?: string[]
  attachments?: Record<string, any>[]
  linked_plan_ids?: number[]
  linked_observation_ids?: number[]
}

export interface CancelReasonPayload {
  cancel_reason?: string
}

export interface ParticipantAddPayload {
  user_id: number
  role?: ParticipantRole
}

export interface ParticipantUpdatePayload {
  role?: ParticipantRole
  attendance_status?: AttendanceStatus
  check_in_at?: string
  check_out_at?: string
  contribution_score?: number
  contribution_note?: string
  note?: string
}

export interface AgendaCreatePayload {
  title: string
  presenter_id?: number
  content?: string
  planned_duration?: number
  linked_plan_id?: number
  linked_observation_id?: number
}

export interface AgendaUpdatePayload {
  title?: string
  presenter_id?: number
  content?: string
  planned_duration?: number
  actual_duration?: number
  decision?: string
  status?: AgendaStatus
  linked_plan_id?: number
  linked_observation_id?: number
}

export interface ListParams {
  subject_code?: string
  activity_type?: ActivityType
  status?: ActivityStatus
  organizer_id?: number
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

/** POST — 创建教研活动 */
export function createActivity(payload: ActivityCreatePayload) {
  return request.post<any, ActivityDetailResponse>('/research_activities/', payload)
}

/** GET — 活动列表 */
export function listActivities(params?: ListParams) {
  return request.get<any, ListResponse<ActivityResponse>>('/research_activities/', { params })
}

/** GET — 活动统计看板 */
export function getDashboard() {
  return request.get<any, DashboardStats>('/research_activities/dashboard')
}

/** GET — 活动详情 */
export function getActivity(actId: number) {
  return request.get<any, ActivityDetailResponse>(`/research_activities/${actId}`)
}

/** PUT — 更新活动信息 */
export function updateActivity(actId: number, payload: ActivityUpdatePayload) {
  return request.put<any, ActivityResponse>(`/research_activities/${actId}`, payload)
}

/** DELETE — 删除活动 */
export function deleteActivity(actId: number) {
  return request.delete<any, { message: string }>(`/research_activities/${actId}`)
}

/** POST — 启动活动 PLANNED→IN_PROGRESS */
export function startActivity(actId: number) {
  return request.post<any, ActivityResponse>(`/research_activities/${actId}/start`)
}

/** POST — 完成活动 IN_PROGRESS→COMPLETED */
export function completeActivity(actId: number) {
  return request.post<any, ActivityResponse>(`/research_activities/${actId}/complete`)
}

/** POST — 取消活动 PLANNED→CANCELLED */
export function cancelActivity(actId: number, payload: CancelReasonPayload) {
  return request.post<any, ActivityResponse>(`/research_activities/${actId}/cancel`, payload)
}

/** POST — 添加参与人 */
export function addParticipant(actId: number, payload: ParticipantAddPayload) {
  return request.post<any, ParticipantResponse>(`/research_activities/${actId}/participants`, payload)
}

/** GET — 参与人列表 */
export function listParticipants(actId: number) {
  return request.get<any, ListResponse<ParticipantResponse>>(`/research_activities/${actId}/participants`)
}

/** PUT — 更新参与人 */
export function updateParticipant(actId: number, pid: number, payload: ParticipantUpdatePayload) {
  return request.put<any, ParticipantResponse>(`/research_activities/${actId}/participants/${pid}`, payload)
}

/** DELETE — 移除参与人 */
export function removeParticipant(actId: number, pid: number) {
  return request.delete<any, { message: string }>(`/research_activities/${actId}/participants/${pid}`)
}

/** POST — 添加议题 */
export function createAgenda(actId: number, payload: AgendaCreatePayload) {
  return request.post<any, AgendaResponse>(`/research_activities/${actId}/agendas`, payload)
}

/** GET — 议题列表 */
export function listAgendas(actId: number) {
  return request.get<any, ListResponse<AgendaResponse>>(`/research_activities/${actId}/agendas`)
}

/** PUT — 更新议题 */
export function updateAgenda(actId: number, aid: number, payload: AgendaUpdatePayload) {
  return request.put<any, AgendaResponse>(`/research_activities/${actId}/agendas/${aid}`, payload)
}

/** DELETE — 删除议题 */
export function deleteAgenda(actId: number, aid: number) {
  return request.delete<any, { message: string }>(`/research_activities/${actId}/agendas/${aid}`)
}

/* ──────────────── 辅助函数 ──────────────── */

type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

/** 活动状态 → el-tag type */
export function activityStatusTag(status: ActivityStatus): TagType {
  const map: Record<ActivityStatus, TagType> = {
    planned: 'info',
    in_progress: 'warning',
    completed: 'success',
    cancelled: 'danger',
  }
  return map[status] || 'info'
}

/** 活动状态 → 中文标签 */
export function activityStatusLabel(status: ActivityStatus): string {
  const map: Record<ActivityStatus, string> = {
    planned: '已计划',
    in_progress: '进行中',
    completed: '已完成',
    cancelled: '已取消',
  }
  return map[status] || status
}

/** 活动类型 → 中文标签 */
export function activityTypeLabel(type: ActivityType): string {
  const map: Record<ActivityType, string> = {
    regular_meeting: '常规教研会',
    lesson_study: '课例研究',
    thematic_research: '专题研讨',
    grade_meeting: '年级组会',
    cross_grade: '跨年级教研',
    training: '培训活动',
  }
  return map[type] || type
}

/** 参与人角色 → 中文标签 */
export function participantRoleLabel(role: ParticipantRole): string {
  const map: Record<ParticipantRole, string> = {
    organizer: '组织者',
    presenter: '主讲人',
    recorder: '记录员',
    participant: '参与者',
  }
  return map[role] || role
}

/** 参与人角色 → el-tag type */
export function participantRoleTag(role: ParticipantRole): TagType {
  const map: Record<ParticipantRole, TagType> = {
    organizer: 'danger',
    presenter: 'warning',
    recorder: 'primary',
    participant: 'info',
  }
  return map[role] || 'info'
}

/** 考勤状态 → 中文标签 */
export function attendanceStatusLabel(status: AttendanceStatus): string {
  const map: Record<AttendanceStatus, string> = {
    registered: '已报名',
    checked_in: '已签到',
    checked_out: '已签退',
    absent: '缺席',
    late: '迟到',
  }
  return map[status] || status
}

/** 考勤状态 → el-tag type */
export function attendanceStatusTag(status: AttendanceStatus): TagType {
  const map: Record<AttendanceStatus, TagType> = {
    registered: 'info',
    checked_in: 'success',
    checked_out: 'primary',
    absent: 'danger',
    late: 'warning',
  }
  return map[status] || 'info'
}

/** 议题状态 → 中文标签 */
export function agendaStatusLabel(status: AgendaStatus): string {
  const map: Record<AgendaStatus, string> = {
    planned: '待讨论',
    in_discussion: '讨论中',
    resolved: '已决议',
    deferred: '已搁置',
  }
  return map[status] || status
}

/** 议题状态 → el-tag type */
export function agendaStatusTag(status: AgendaStatus): TagType {
  const map: Record<AgendaStatus, TagType> = {
    planned: 'info',
    in_discussion: 'warning',
    resolved: 'success',
    deferred: 'danger',
  }
  return map[status] || 'info'
}

/** 活动状态流转步骤 */
export const ACTIVITY_STATUS_PIPELINE: ActivityStatus[] = ['planned', 'in_progress', 'completed']
