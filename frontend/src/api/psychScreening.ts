/**
 * psychScreening.ts — 心理筛查与干预 API 契约层
 *
 * 对应后端模块: modules/psych_screening (MODULE_CODE="psych_screening" -> URL前缀 /api/v1/psych_screening)
 * 端点清单 (18):
 *   GET    /psych_screening/metadata              — 元数据（维度/风险等级/干预类型枚举）
 *   GET    /psych_screening/surveys               — 问卷列表（含统计）
 *   POST   /psych_screening/surveys/submit        — 提交 MSSMHS-55 筛查问卷
 *   GET    /psych_screening/surveys/dimension-data — 维度聚合数据
 *   POST   /psych_screening/surveys/ai-analysis   — AI 白皮书诊断
 *   POST   /psych_screening/surveys/sync-to-assessment — 同步问卷到评估档案
 *   GET    /psych_screening/assessments           — 评估列表
 *   POST   /psych_screening/assessments           — 创建评估
 *   GET    /psych_screening/assessments/{id}      — 评估详情
 *   PUT    /psych_screening/assessments/{id}      — 更新评估
 *   DELETE /psych_screening/assessments/{id}      — 删除评估
 *   GET    /psych_screening/interventions         — 干预记录列表
 *   POST   /psych_screening/interventions         — 创建干预记录
 *   POST   /psych_screening/interventions/{id}/followup — 干预随访
 *   GET    /psych_screening/interventions/timeline/{student_id} — 干预时间线
 *   GET    /psych_screening/questions             — 量表题目列表
 *   POST   /psych_screening/questions/seed        — 种子初始化 MSSMHS-55 题目
 *   GET    /psych_screening/students/search       — 学生搜索
 *   GET    /psych_screening/dashboard             — 统计仪表盘
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

/** 风险等级 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

/** 风险等级标签映射 */
export const RISK_LABELS: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '极高风险',
}

/** 风险等级颜色映射 (暖色调) */
export const RISK_COLORS: Record<RiskLevel, string> = {
  low: '#67c23a',
  medium: '#e6a23c',
  high: '#f56c6c',
  critical: '#ff4444',
}

/** 评估类型 */
export type AssessmentType = 'MSSMHS-55' | 'PCE-55' | 'SDS' | 'SAS' | 'clinical' | 'other'

/** 干预类型 (对齐后端 INTERVENTION_TYPE_CHOICES) */
export type InterventionType = '心理谈话' | '家长联动' | '心理辅导' | '危机干预' | '转介专业机构' | '其他'

/** 干预状态 */
export type InterventionStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

/** 效果评定 (对齐后端 EFFECT_RATING_CHOICES) */
export type EffectRating = '显著好转' | '略有好转' | '无变化' | '恶化'

/** MSSMHS-55 维度定义 */
export interface DimensionDef {
  code: string
  name: string
  description: string
  max_score: number
}

/** 问卷维度得分 */
export interface DimensionScore {
  code: string
  name: string
  score: number
  max_score: number
  percentage: number
}

/** 心理筛查问卷 */
export interface PsychSurvey {
  id: number
  student_id: number
  student_name: string
  class_name: string
  grade_name?: string
  survey_type: string
  total_score: number
  verify_status: string  // "VERIFIED" / "PENDING" 等
  completed_at: string
  dimensions: DimensionScore[]
}

/** 问卷答案项 (对齐后端 SurveyAnswer schema) */
export interface SurveyAnswer {
  question_no: number
  score: number
}

/** 量表题目 */
export interface PsychQuestion {
  id: number
  code: string
  dimension_code: string
  dimension_name: string
  text: string
  order_no: number
  is_reverse: boolean
}

/** 评估档案 */
export interface MentalHealthAssessment {
  id: number
  student_id: number
  student_name?: string
  class_name?: string
  survey_id?: number
  risk_level: RiskLevel
  total_score: number
  assessment_type: AssessmentType
  summary: string
  llm_output?: string
  diagnosed_at?: string
  evaluated_by?: string
  created_at: string
}

/** 干预记录 (对齐后端 InterventionOut) */
export interface InterventionRecord {
  id: number
  student_id: number
  student_name?: string
  class_name?: string
  teacher_id?: number
  teacher_name?: string
  assessment_id?: number
  mh_risk_before?: string
  mh_risk_after?: string
  intervention_type: InterventionType
  notes?: string
  parent_feedback?: string
  effect_rating?: EffectRating
  intervention_date?: string
  follow_up_date?: string
  follow_up_done: boolean
  follow_up_notes?: string
  status: string
  is_effective: boolean
  mh_risk_improved?: boolean
  created_at?: string
}

/** 干预随访 */
export interface InterventionFollowup {
  id: number
  content: string
  effect_rating?: EffectRating
  recorded_by: string
  created_at: string
}

/** 仪表盘统计 (对齐后端 PsychDashboardResponse) */
export interface PsychDashboardStats {
  survey_stats: {
    total: number
    mssmhs_count: number
    pce_count: number
  }
  risk_distribution: {
    high: number
    medium: number
    low: number
  }
  assessment_stats: {
    total: number
    by_type: Record<string, number>
    need_intervention: number
  }
  intervention_stats: {
    total: number
    tracking: number
    completed: number
    effective: number
  }
  dimension_alerts: Array<{
    dimension: string
    avg_score: number
    deviation_pct: number
  }>
  dimension_ranking?: Array<{
    code: string
    name: string
    deviation_pct: number
  }>
}

/** 元数据 */
export interface PsychMetadata {
  mssmhs_dimensions: DimensionDef[]
  assessment_types: Array<{ value: string; label: string }>
  risk_levels: Array<{ value: string; label: string }>
  intervention_types: Array<{ value: string; label: string }>
  effect_ratings: Array<{ value: string; label: string }>
  max_per_dim: number
  max_total: number
}

/** AI 分析结果 */
export interface AIAnalysisResult {
  survey_id: number
  student_name: string
  dimensions: DimensionScore[]
  analysis: {
    summary: string
    risks: string[]
    suggestions: string[]
  }
  prescription?: {
    fact: string
    analysis: string
    growth: string
  }
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

/** 获取元数据（维度定义、枚举值） */
export function getMetadata() {
  return request.get('/api/v1/psych_screening/metadata')
}

/** 获取筛查问卷列表 */
export function listSurveys(params: {
  grade_id?: number
  class_id?: number
  survey_type?: string
  limit?: number
  offset?: number
}) {
  return request.get('/api/v1/psych_screening/surveys', { params })
}

/** 提交 MSSMHS-55 筛查问卷 */
export function submitSurvey(body: {
  student_id: number
  survey_type: string
  answers: SurveyAnswer[]
}) {
  return request.post('/api/v1/psych_screening/surveys/submit', body)
}

/** 获取维度聚合数据 */
export function getDimensionData(params: {
  grade_id?: number
  class_id?: number
  survey_type?: string
}) {
  return request.get('/api/v1/psych_screening/surveys/dimension-data', { params })
}

/** AI 白皮书诊断 */
export function runAIAnalysis(body: { survey_id: number }) {
  return request.post('/api/v1/psych_screening/surveys/ai-analysis', body)
}

/** 同步问卷到评估档案 */
export function syncToAssessment(body: { survey_ids: number[] }) {
  return request.post('/api/v1/psych_screening/surveys/sync-to-assessment', body)
}

/** 获取评估列表 */
export function listAssessments(params: {
  student_id?: number
  risk_level?: RiskLevel
  assessment_type?: AssessmentType
  limit?: number
  offset?: number
}) {
  return request.get('/api/v1/psych_screening/assessments', { params })
}

/** 获取评估详情 */
export function getAssessment(id: number) {
  return request.get(`/api/v1/psych_screening/assessments/${id}`)
}

/** 创建评估 */
export function createAssessment(body: {
  student_id: number
  risk_level: RiskLevel
  total_score: number
  assessment_type: AssessmentType
  summary: string
}) {
  return request.post('/api/v1/psych_screening/assessments', body)
}

/** 更新评估 */
export function updateAssessment(id: number, body: {
  risk_level?: RiskLevel
  total_score?: number
  summary?: string
  llm_output?: string
}) {
  return request.put(`/api/v1/psych_screening/assessments/${id}`, body)
}

/** 删除评估 */
export function deleteAssessment(id: number) {
  return request.delete(`/api/v1/psych_screening/assessments/${id}`)
}

/** 获取干预记录列表 */
export function listInterventions(params: {
  student_id?: number
  status?: string
  limit?: number
  offset?: number
}) {
  return request.get('/api/v1/psych_screening/interventions', { params })
}

/** 创建干预记录 (对齐后端 InterventionCreateRequest) */
export function createIntervention(body: {
  student_id: number
  assessment_id?: number
  intervention_type: InterventionType
  notes?: string
  parent_feedback?: string
  intervention_date?: string
  follow_up_date?: string
}) {
  return request.post('/api/v1/psych_screening/interventions', body)
}

/** 干预随访 (对齐后端 InterventionFollowupRequest) */
export function followupIntervention(id: number, body: {
  effect_rating?: EffectRating
  follow_up_notes?: string
  parent_feedback?: string
  mh_risk_after?: string
}) {
  return request.post(`/api/v1/psych_screening/interventions/${id}/followup`, body)
}

/** 获取学生干预时间线 */
export function getInterventionTimeline(studentId: number) {
  return request.get(`/api/v1/psych_screening/interventions/timeline/${studentId}`)
}

/** 获取量表题目列表 */
export function listQuestions() {
  return request.get('/api/v1/psych_screening/questions')
}

/** 种子初始化 MSSMHS-55 题目 */
export function seedQuestions() {
  return request.post('/api/v1/psych_screening/questions/seed')
}

/** 学生搜索 */
export function searchStudents(params: {
  q?: string
  grade_id?: number
  class_id?: number
  risk_level?: RiskLevel
}) {
  return request.get('/api/v1/psych_screening/students/search', { params })
}

/** 统计仪表盘 */
export function getDashboard(params?: {
  grade_id?: number
  period?: string
}) {
  return request.get('/api/v1/psych_screening/dashboard', { params })
}
