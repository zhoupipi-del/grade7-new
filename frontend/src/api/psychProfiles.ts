/**
 * psychProfiles.ts — 心理档案 + 双轨预警 Nexus API 契约层
 *
 * 对应后端模块: modules/psych_profiles
 * URL前缀: /api/v1/psych_profiles (underscore — module_loader覆盖规则)
 *
 * 端点清单 (14):
 *   ── 心理档案 ──
 *   GET    /profiles                           — 档案列表
 *   GET    /profiles/{student_id}              — 档案详情
 *   POST   /profiles/{student_id}              — 初始化档案
 *   PUT    /profiles/{student_id}              — 更新档案
 *   PUT    /profiles/{student_id}/tags         — 更新标签云
 *   DELETE /profiles/{student_id}              — 删除档案
 *   POST   /profiles/{student_id}/recompute     — 重算统计
 *
 *   ── 心理筛查 ──
 *   POST   /screenings                         — 录入筛查
 *   GET    /screenings                         — 筛查列表
 *   GET    /screenings/{student_id}            — 筛查历史
 *
 *   ── 双轨预警 Nexus ──
 *   GET    /nexus/comprehensive-risks          — 双轨预警合成视图 (NexusBoard核心)
 *   GET    /nexus/student/{student_id}         — 单学生双轨画像 (抽屉详情)
 *
 *   ── 仪表盘 ──
 *   GET    /dashboard                          — 仪表盘统计
 *   GET    /tags/suggestions                   — 标签建议
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

/** el-tag type union */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** 学业风险等级 */
export type AcademicRiskLevel = 'RED' | 'YELLOW' | 'NONE'

/** 心理风险等级 */
export type PsyRiskLevel = 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN'

/** 行动优先级 */
export type ActionPriority = 'CRITICAL' | 'URGENT' | 'WATCH' | 'NORMAL'

/** 学业风险信息 */
export interface AcademicRisk {
  level: AcademicRiskLevel
  z_score: number | null
  trigger_subjects: string[]
  trigger_reason: string | null
  source: string
}

/** 心理风险信息 */
export interface PsyRisk {
  level: PsyRiskLevel
  factors: string[]
  last_screening_date: string | null
  scale_name: string | null
  source: string
}

/** RDI 风险信息 */
export interface RdiRisk {
  score: number | null
  level: string | null
  psych_deviation: number | null
  score_deviation: number | null
  behavior_deviation: number | null
  attendance_deviation: number | null
  is_escalating: boolean
  source: string
}

/** Nexus 风险项 — 双轨预警矩阵行数据 */
export interface NexusRiskItem {
  student_id: number
  student_name: string
  class_name: string
  academic_risk: AcademicRisk
  psy_risk: PsyRisk
  rdi_risk: RdiRisk
  co_trigger: boolean
  action_priority: ActionPriority
  recommended_actions: string[]
}

/** Nexus 列表响应 */
export interface NexusListResponse {
  total: number
  critical_count: number
  urgent_count: number
  watch_count: number
  items: NexusRiskItem[]
}

/** 学业历史快照 */
export interface AcademicHistoryItem {
  exam_name: string
  exam_date: string
  z_score: number | null
  rank_in_class: number | null
  rank_in_grade: number | null
  risk_level: AcademicRiskLevel
}

/** 心理筛查历史 */
export interface PsyScreeningHistoryItem {
  id: number
  scale_name: string
  screening_date: string
  risk_level: PsyRiskLevel
  key_findings: string[]
  conducted_by: string
}

/** 咨询摘要 */
export interface PsyCounselingSummary {
  total_sessions: number
  last_session_date: string | null
  main_concerns: string[]
  risk_trend: 'improving' | 'stable' | 'worsening' | 'unknown'
}

/** 心理档案 */
export interface PsyProfile {
  student_id: number
  student_name: string
  class_name: string
  risk_flag: PsyRiskLevel
  risk_factors: string[]
  tags: string[]
  family_background: string | null
  personality_traits: string | null
  counseling_history_summary: string | null
  last_screening_date: string | null
  last_screening_scale: string | null
  total_screenings: number
  total_counselings: number
  created_at: string
  updated_at: string
}

/** 单学生 Nexus 详细画像 — 抽屉用 */
export interface NexusStudentDetail {
  student_id: number
  student_name: string
  class_name: string
  academic_risk: AcademicRisk
  academic_history: AcademicHistoryItem[]
  psy_risk: PsyRisk
  psy_profile: PsyProfile | null
  psy_screening_history: PsyScreeningHistoryItem[]
  psy_counseling_summary: PsyCounselingSummary | null
  rdi_risk: RdiRisk
  co_trigger: boolean
  action_priority: ActionPriority
  recommended_actions: string[]
}

/** 仪表盘统计 */
export interface DashboardResponse {
  total_profiles: number
  risk_distribution: Record<string, number>
  co_trigger_count: number
  total_screenings: number
  total_counselings: number
  total_referrals: number
  recent_screenings: PsyScreeningHistoryItem[]
  top_risk_students: NexusRiskItem[]
  /** 学业侧统计 (四源union新增) */
  total_academic_alerts: number
  academic_red_count: number
  academic_yellow_count: number
  total_rdi_warnings: number
}

/** 筛查录入 payload */
export interface ScreeningCreatePayload {
  student_id: number
  scale_name: string
  screening_date: string
  risk_level: PsyRiskLevel
  key_findings: string[]
  raw_scores?: Record<string, number>
  notes?: string
}

/** 档案初始化/更新 payload */
export interface ProfileUpsertPayload {
  risk_flag?: PsyRiskLevel
  risk_factors?: string[]
  tags?: string[]
  family_background?: string
  personality_traits?: string
  counseling_history_summary?: string
}

/** 标签更新 payload */
export interface TagsUpdatePayload {
  tags: string[]
}

/** 标签建议响应 */
export interface TagSuggestionsResponse {
  suggestions: string[]
  popular_tags: string[]
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

// ── 心理档案 ──

/** GET /psych_profiles/profiles — 档案列表 */
export function getProfiles(params?: {
  risk_flag?: PsyRiskLevel
  search?: string
  page?: number
  page_size?: number
}) {
  return request.get<any, { items: PsyProfile[]; total: number }>('/psych_profiles/profiles', { params })
}

/** GET /psych_profiles/profiles/{student_id} — 档案详情 */
export function getProfileDetail(studentId: number) {
  return request.get<any, PsyProfile>(`/psych_profiles/profiles/${studentId}`)
}

/** POST /psych_profiles/profiles/{student_id} — 初始化档案 */
export function initProfile(studentId: number, data: ProfileUpsertPayload) {
  return request.post<any, { profile_id: number; status: string }>(`/psych_profiles/profiles/${studentId}`, data)
}

/** PUT /psych_profiles/profiles/{student_id} — 更新档案 */
export function updateProfile(studentId: number, data: ProfileUpsertPayload) {
  return request.put<any, { status: string }>(`/psych_profiles/profiles/${studentId}`, data)
}

/** PUT /psych_profiles/profiles/{student_id}/tags — 更新标签云 */
export function updateProfileTags(studentId: number, data: TagsUpdatePayload) {
  return request.put<any, { tags: string[] }>(`/psych_profiles/profiles/${studentId}/tags`, data)
}

/** DELETE /psych_profiles/profiles/{student_id} — 删除档案 */
export function deleteProfile(studentId: number) {
  return request.delete<any, { status: string }>(`/psych_profiles/profiles/${studentId}`)
}

/** POST /psych_profiles/profiles/{student_id}/recompute — 重算统计 */
export function recomputeProfile(studentId: number) {
  return request.post<any, { status: string; total_screenings: number; total_counselings: number }>(
    `/psych_profiles/profiles/${studentId}/recompute`
  )
}

// ── 心理筛查 ──

/** POST /psych_profiles/screenings — 录入筛查 */
export function createScreening(data: ScreeningCreatePayload) {
  return request.post<any, { screening_id: number; status: string }>('/psych_profiles/screenings', data)
}

/** GET /psych_profiles/screenings — 筛查列表 */
export function getScreenings(params?: {
  scale_name?: string
  risk_level?: PsyRiskLevel
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}) {
  return request.get<any, { items: PsyScreeningHistoryItem[]; total: number }>(
    '/psych_profiles/screenings',
    { params }
  )
}

/** GET /psych_profiles/screenings/{student_id} — 筛查历史 */
export function getStudentScreenings(studentId: number) {
  return request.get<any, PsyScreeningHistoryItem[]>(`/psych_profiles/screenings/${studentId}`)
}

// ── 双轨预警 Nexus ──

/** GET /psych_profiles/nexus/comprehensive-risks — 双轨预警合成视图 (NexusBoard核心) */
export function getComprehensiveRisks(params?: {
  co_trigger_only?: boolean
  min_priority?: ActionPriority
  class_id?: number
  page?: number
  page_size?: number
}) {
  return request.get<any, NexusListResponse>('/psych_profiles/nexus/comprehensive-risks', { params })
}

/** GET /psych_profiles/nexus/student/{student_id} — 单学生双轨画像 (抽屉详情) */
export function getStudentNexusDetail(studentId: number) {
  return request.get<any, NexusStudentDetail>(`/psych_profiles/nexus/student/${studentId}`)
}

// ── 仪表盘 ──

/** GET /psych_profiles/dashboard — 仪表盘统计 */
export function getDashboardStats() {
  return request.get<any, DashboardResponse>('/psych_profiles/dashboard')
}

/** GET /psych_profiles/tags/suggestions — 标签建议 */
export function getTagSuggestions(params?: { q?: string }) {
  return request.get<any, TagSuggestionsResponse>('/psych_profiles/tags/suggestions', { params })
}

// ═══════════════════════════════════════════════════
// Display Helpers
// ═══════════════════════════════════════════════════

/** 行动优先级 -> 中文标签 */
export function priorityLabel(p: ActionPriority): string {
  const map: Record<ActionPriority, string> = {
    CRITICAL: '危急',
    URGENT: '紧急',
    WATCH: '关注',
    NORMAL: '正常',
  }
  return map[p] || p
}

/** 行动优先级 -> el-tag type */
export function priorityTag(p: ActionPriority): TagType {
  const map: Record<ActionPriority, TagType> = {
    CRITICAL: 'danger',
    URGENT: 'warning',
    WATCH: 'primary',
    NORMAL: 'success',
  }
  return map[p] || 'info'
}

/** 行动优先级 -> 暗色主题色值 */
export function priorityColor(p: ActionPriority): string {
  const map: Record<ActionPriority, string> = {
    CRITICAL: '#f85149',
    URGENT: '#d29922',
    WATCH: '#58a6ff',
    NORMAL: '#3fb950',
  }
  return map[p] || '#8b949e'
}

/** 学业风险等级 -> 中文标签 */
export function academicRiskLevelLabel(l: AcademicRiskLevel): string {
  const map: Record<AcademicRiskLevel, string> = {
    RED: '红灯',
    YELLOW: '黄灯',
    NONE: '正常',
  }
  return map[l] || l
}

/** 学业风险等级 -> el-tag type */
export function academicRiskLevelTag(l: AcademicRiskLevel): TagType {
  const map: Record<AcademicRiskLevel, TagType> = {
    RED: 'danger',
    YELLOW: 'warning',
    NONE: 'success',
  }
  return map[l] || 'info'
}

/** 学业风险等级 -> 暗色主题色值 */
export function academicRiskLevelColor(l: AcademicRiskLevel): string {
  const map: Record<AcademicRiskLevel, string> = {
    RED: '#f85149',
    YELLOW: '#d29922',
    NONE: '#3fb950',
  }
  return map[l] || '#8b949e'
}

/** 心理风险等级 -> 中文标签 */
export function psyRiskLevelLabel(l: PsyRiskLevel): string {
  const map: Record<PsyRiskLevel, string> = {
    RED: '高危',
    ORANGE: '中危',
    YELLOW: '低危',
    GREEN: '正常',
  }
  return map[l] || l
}

/** 心理风险等级 -> el-tag type */
export function psyRiskLevelTag(l: PsyRiskLevel): TagType {
  const map: Record<PsyRiskLevel, TagType> = {
    RED: 'danger',
    ORANGE: 'warning',
    YELLOW: 'primary',
    GREEN: 'success',
  }
  return map[l] || 'info'
}

/** 心理风险等级 -> 暗色主题色值 */
export function psyRiskLevelColor(l: PsyRiskLevel): string {
  const map: Record<PsyRiskLevel, string> = {
    RED: '#f85149',
    ORANGE: '#d29922',
    YELLOW: '#58a6ff',
    GREEN: '#3fb950',
  }
  return map[l] || '#8b949e'
}

/** 咨询趋势 -> 中文标签 */
export function riskTrendLabel(t: string): string {
  const map: Record<string, string> = {
    improving: '好转',
    stable: '平稳',
    worsening: '恶化',
    unknown: '未知',
  }
  return map[t] || t
}

/** 咨询趋势 -> 暗色主题色值 */
export function riskTrendColor(t: string): string {
  const map: Record<string, string> = {
    improving: '#3fb950',
    stable: '#58a6ff',
    worsening: '#f85149',
    unknown: '#8b949e',
  }
  return map[t] || '#8b949e'
}

/** Z-Score -> 格式化字符串 */
export function formatZScore(z: number | null): string {
  if (z === null || z === undefined) return '—'
  return z.toFixed(2)
}

/** 偏离度 -> 格式化字符串 */
export function formatDeviation(d: number | null): string {
  if (d === null || d === undefined) return '—'
  const sign = d >= 0 ? '+' : ''
  return `${sign}${d.toFixed(2)}σ`
}
