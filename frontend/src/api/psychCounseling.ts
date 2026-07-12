/**
 * psychCounseling.ts — 心理咨询预约与工作台 API 契约层
 *
 * 对应后端模块: modules/psych_counseling
 * URL前缀: /api/v1/psych_counseling (underscore — module_loader覆盖规则)
 *
 * 端点清单 (14):
 *   ── 时间槽位 ──
 *   POST   /psych_counseling/slots                    — 心理老师创建可预约时段
 *   GET    /psych_counseling/slots                    — 查询可用时段列表
 *   PUT    /psych_counseling/slots/{slot_id}/status   — 锁定/解锁时段
 *   DELETE /psych_counseling/slots/{slot_id}          — 删除空闲时段
 *
 *   ── 预约管理 ──
 *   POST   /psych_counseling/appointments             — 发起预约
 *   GET    /psych_counseling/appointments             — 查询预约列表
 *   GET    /psych_counseling/appointments/{id}        — 预约详情
 *   PUT    /psych_counseling/appointments/{id}        — 审核/更新预约
 *   GET    /psych_counseling/appointments/my          — 我的预约
 *
 *   ── 咨询记录(工作台) ──
 *   POST   /psych_counseling/records                  — 提交加密咨询记录
 *   GET    /psych_counseling/records                  — 咨询记录列表
 *   GET    /psych_counseling/records/{id}             — 单条记录(按角色解密)
 *   GET    /psych_counseling/records/student/{sid}    — 某学生全部咨询历史
 *
 *   ── 统计 ──
 *   GET    /psych_counseling/stats                    — 工作台统计概览
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

/** el-tag type union */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** 风险标记色阶 */
export type RiskFlag = 'green' | 'yellow' | 'orange' | 'red'

/** 预约状态 */
export type AppointmentStatus = 'pending' | 'confirmed' | 'cancelled' | 'completed' | 'no_show'

/** 咨询类别 */
export type ConsultCategory = 'emotion' | 'interpersonal' | 'academic' | 'family' | 'self_harm' | 'other'

/** 时段状态 */
export type SlotStatus = 'open' | 'locked' | 'booked' | 'closed'

// ── 时间槽位 ──

export interface ConsultSlot {
  id: number
  teacher_id: number
  teacher_name: string | null
  date: string
  start_time: string
  end_time: string
  location: string | null
  max_capacity: number
  current_booked: number
  status: SlotStatus
  week_pattern: string
  is_recurring: boolean
  created_at: string | null
}

export interface SlotCreatePayload {
  date: string
  start_time: string
  end_time: string
  location?: string
  max_capacity?: number
  week_pattern?: string
  is_recurring?: boolean
}

export interface SlotListResponse {
  status: string
  slots: ConsultSlot[]
}

// ── 预约 ──

export interface Appointment {
  id: number
  student_id: number
  student_name: string | null
  applicant_id: number
  applicant_name: string | null
  slot_id: number
  source: string
  reason_summary: string | null
  status: AppointmentStatus
  risk_flag: RiskFlag
  counselor_note: string | null
  slot_date: string | null
  slot_time: string | null
  slot_location: string | null
  created_at: string | null
  confirmed_at: string | null
  completed_at: string | null
}

export interface AppointmentCreatePayload {
  student_id: number
  slot_id: number
  source: string
  reason_summary?: string
  risk_flag?: RiskFlag
}

export interface AppointmentUpdatePayload {
  status?: AppointmentStatus
  risk_flag?: RiskFlag
  counselor_note?: string
}

export interface AppointmentListResponse {
  status: string
  appointments: Appointment[]
  total: number
}

// ── 咨询记录 ──

export interface ConsultRecord {
  id: number
  appointment_id: number
  student_id: number
  student_name: string | null
  counselor_id: number
  counselor_name: string | null
  clog_display: string
  risk_level: RiskFlag
  consult_category: ConsultCategory | null
  is_crisis: boolean
  is_referred: boolean
  referral_target: string | null
  followup_date: string | null
  session_duration_min: number | null
  created_at: string | null
  updated_at: string | null
}

export interface ConsultRecordCreatePayload {
  appointment_id: number
  student_id: number
  clog_plaintext: string
  risk_level?: RiskFlag
  consult_category?: ConsultCategory
  is_crisis?: boolean
  is_referred?: boolean
  referral_target?: string
  followup_date?: string
  session_duration_min?: number
}

export interface ConsultRecordListResponse {
  status: string
  records: ConsultRecord[]
  total: number
}

// ── 工作台统计 ──

export interface CounselorStats {
  status: string
  counselor_id: number
  total_sessions: number
  total_students: number
  crisis_count: number
  referral_count: number
  avg_duration_min: number | null
  risk_distribution: Record<string, number>
  category_distribution: Record<string, number>
  upcoming_appointments: number
  pending_appointments: number
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

// ── 时间槽位 ──

/** GET /psych_counseling/slots — 查询可用时段列表 */
export function getSlots(params?: {
  date_from?: string
  date_to?: string
  status?: SlotStatus
}) {
  return request.get<any, SlotListResponse>('/psych_counseling/slots', { params })
}

/** POST /psych_counseling/slots — 创建可预约时段 */
export function createSlot(data: SlotCreatePayload) {
  return request.post<any, { slot_id: number; status: string }>('/psych_counseling/slots', data)
}

/** PUT /psych_counseling/slots/{slot_id}/status — 锁定/解锁时段 */
export function updateSlotStatus(slotId: number, data: { status: SlotStatus }) {
  return request.put<any, { status: string }>(`/psych_counseling/slots/${slotId}/status`, data)
}

/** DELETE /psych_counseling/slots/{slot_id} — 删除空闲时段 */
export function deleteSlot(slotId: number) {
  return request.delete<any, { status: string }>(`/psych_counseling/slots/${slotId}`)
}

// ── 预约管理 ──

/** GET /psych_counseling/appointments — 查询预约列表 */
export function getAppointments(params?: {
  status?: AppointmentStatus
  risk_flag?: RiskFlag
  page?: number
  page_size?: number
}) {
  return request.get<any, AppointmentListResponse>('/psych_counseling/appointments', { params })
}

/** POST /psych_counseling/appointments — 发起预约 (家长端核心入口) */
export function createAppointment(data: AppointmentCreatePayload) {
  return request.post<any, { appointment_id: number; status: string }>('/psych_counseling/appointments', data)
}

/** GET /psych_counseling/appointments/{id} — 预约详情 */
export function getAppointmentDetail(id: number) {
  return request.get<any, Appointment>(`/psych_counseling/appointments/${id}`)
}

/** PUT /psych_counseling/appointments/{id} — 审核/更新预约 */
export function updateAppointment(id: number, data: AppointmentUpdatePayload) {
  return request.put<any, { status: string }>(`/psych_counseling/appointments/${id}`, data)
}

/** GET /psych_counseling/appointments/my — 我的预约 */
export function getMyAppointments() {
  return request.get<any, AppointmentListResponse>('/psych_counseling/appointments/my')
}

// ── 咨询记录(工作台) ──

/** GET /psych_counseling/records — 咨询记录列表 */
export function getConsultRecords(params?: {
  student_id?: number
  risk_level?: RiskFlag
  page?: number
  page_size?: number
}) {
  return request.get<any, ConsultRecordListResponse>('/psych_counseling/records', { params })
}

/** POST /psych_counseling/records — 提交加密咨询记录 */
export function createConsultRecord(data: ConsultRecordCreatePayload) {
  return request.post<any, { record_id: number; status: string }>('/psych_counseling/records', data)
}

/** GET /psych_counseling/records/{id} — 单条记录(按角色解密) */
export function getConsultRecordDetail(id: number) {
  return request.get<any, ConsultRecord>(`/psych_counseling/records/${id}`)
}

/** GET /psych_counseling/records/student/{sid} — 某学生全部咨询历史 */
export function getStudentConsultHistory(studentId: number) {
  return request.get<any, ConsultRecordListResponse>(`/psych_counseling/records/student/${studentId}`)
}

// ── 统计 ──

/** GET /psych_counseling/stats — 工作台统计概览 */
export function getCounselorStats() {
  return request.get<any, CounselorStats>('/psych_counseling/stats')
}

// ═══════════════════════════════════════════════════
// Display Helpers (el-tag mapping)
// ═══════════════════════════════════════════════════

/** 风险标记 -> 中文标签 */
export function riskFlagLabel(flag: RiskFlag): string {
  const map: Record<RiskFlag, string> = {
    green: '正常',
    yellow: '关注',
    orange: '预警',
    red: '危机',
  }
  return map[flag] || flag
}

/** 风险标记 -> el-tag type */
export function riskFlagTag(flag: RiskFlag): TagType {
  const map: Record<RiskFlag, TagType> = {
    green: 'success',
    yellow: 'warning',
    orange: 'warning',
    red: 'danger',
  }
  return map[flag] || 'info'
}

/** 风险标记 -> 颜色值(暗色主题) */
export function riskFlagColor(flag: RiskFlag): string {
  const map: Record<RiskFlag, string> = {
    green: '#3fb950',
    yellow: '#d29922',
    orange: '#db6d28',
    red: '#f85149',
  }
  return map[flag] || '#8b949e'
}

/** 预约状态 -> 中文标签 */
export function appointmentStatusLabel(s: AppointmentStatus): string {
  const map: Record<AppointmentStatus, string> = {
    pending: '待确认',
    confirmed: '已确认',
    cancelled: '已取消',
    completed: '已完成',
    no_show: '缺席',
  }
  return map[s] || s
}

/** 预约状态 -> el-tag type */
export function appointmentStatusTag(s: AppointmentStatus): TagType {
  const map: Record<AppointmentStatus, TagType> = {
    pending: 'warning',
    confirmed: 'primary',
    cancelled: 'info',
    completed: 'success',
    no_show: 'danger',
  }
  return map[s] || 'info'
}

/** 咨询类别 -> 中文标签 */
export function consultCategoryLabel(c: ConsultCategory): string {
  const map: Record<ConsultCategory, string> = {
    emotion: '情绪困扰',
    interpersonal: '人际关系',
    academic: '学业压力',
    family: '家庭问题',
    self_harm: '自伤风险',
    other: '其他',
  }
  return map[c] || c
}

/** 咨询类别 -> el-tag type */
export function consultCategoryTag(c: ConsultCategory): TagType {
  const map: Record<ConsultCategory, TagType> = {
    emotion: 'primary',
    interpersonal: 'warning',
    academic: 'info',
    family: 'warning',
    self_harm: 'danger',
    other: 'info',
  }
  return map[c] || 'info'
}

/** 时段状态 -> 中文标签 */
export function slotStatusLabel(s: SlotStatus): string {
  const map: Record<SlotStatus, string> = {
    open: '可预约',
    locked: '已锁定',
    booked: '已满',
    closed: '已关闭',
  }
  return map[s] || s
}

/** 时段状态 -> el-tag type */
export function slotStatusTag(s: SlotStatus): TagType {
  const map: Record<SlotStatus, TagType> = {
    open: 'success',
    locked: 'warning',
    booked: 'danger',
    closed: 'info',
  }
  return map[s] || 'info'
}

/** 预约来源 -> 中文标签 */
export function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    self: '学生自荐',
    teacher: '班主任转介',
    parent: '家长申请',
  }
  return map[source] || source
}
