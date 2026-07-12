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

/** 干预类型 */
export type InterventionType = 'counseling' | 'parent_notify' | 'crisis' | 'referral' | 'followup' | 'other'

/** 干预状态 */
export type InterventionStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

/** 效果评定 */
export type EffectRating = 'improved' | 'stable' | 'worsened' | 'pending'

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
  verify_status: 'valid' | 'invalid' | 'pending'
  completed_at: string
  dimensions: DimensionScore[]
}

/** 问卷答案项 */
export interface SurveyAnswer {
  question_id: number
  score: number
  dimension_code: string
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

/** 干预记录 */
export interface InterventionRecord {
  id: number
  student_id: number
  student_name: string
  class_name: string
  assessment_id?: number
  intervention_type: InterventionType
  status: InterventionStatus
  severity: RiskLevel
  description: string
  outcome?: string
  effect_rating?: EffectRating
  assigned_to?: string
  started_at?: string
  completed_at?: string
  followups: InterventionFollowup[]
}

/** 干预随访 */
export interface InterventionFollowup {
  id: number
  content: string
  effect_rating?: EffectRating
  recorded_by: string
  created_at: string
}

/** 仪表盘统计 */
export interface PsychDashboardStats {
  overview: {
    total_surveys: number
    high_risk_count: number
    medium_risk_count: number
    low_risk_count: number
    critical_count: number
    mssmhs_count?: number
    pce_count?: number
  }
  dimension_ranking: Array<{
    code: string
    name: string
    avg_score: number
    deviation_pct: number
  }>
  risk_distribution: Array<{
    level: string
    count: number
    percentage: number
  }>
  intervention_summary: {
    total: number
    pending: number
    in_progress: number
    completed: number
    crisis_count: number
  }
  trend: Array<{
    date: string
    new_surveys: number
    new_high_risk: number
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
  return request.get('/psych_screening/metadata')
}

/** 获取筛查问卷列表 */
export function listSurveys(params: {
  grade_id?: number
  class_id?: number
  survey_type?: string
  limit?: number
  offset?: number
}) {
  return request.get('/psych_screening/surveys', { params })
}

/** 提交 MSSMHS-55 筛查问卷 */
export function submitSurvey(body: {
  student_id: number
  survey_type: string
  answers: SurveyAnswer[]
}) {
  return request.post('/psych_screening/surveys/submit', body)
}

/** 获取维度聚合数据 */
export function getDimensionData(params: {
  grade_id?: number
  class_id?: number
  survey_type?: string
}) {
  return request.get('/psych_screening/surveys/dimension-data', { params })
}

/** AI 白皮书诊断 */
export function runAIAnalysis(body: { survey_id: number }) {
  return request.post('/psych_screening/surveys/ai-analysis', body)
}

/** 同步问卷到评估档案 */
export function syncToAssessment(body: { survey_ids: number[] }) {
  return request.post('/psych_screening/surveys/sync-to-assessment', body)
}

/** 获取评估列表 */
export function listAssessments(params: {
  student_id?: number
  risk_level?: RiskLevel
  assessment_type?: AssessmentType
  limit?: number
  offset?: number
}) {
  return request.get('/psych_screening/assessments', { params })
}

/** 获取评估详情 */
export function getAssessment(id: number) {
  return request.get(`/psych_screening/assessments/${id}`)
}

/** 创建评估 */
export function createAssessment(body: {
  student_id: number
  risk_level: RiskLevel
  total_score: number
  assessment_type: AssessmentType
  summary: string
}) {
  return request.post('/psych_screening/assessments', body)
}

/** 更新评估 */
export function updateAssessment(id: number, body: {
  risk_level?: RiskLevel
  total_score?: number
  summary?: string
  llm_output?: string
}) {
  return request.put(`/psych_screening/assessments/${id}`, body)
}

/** 删除评估 */
export function deleteAssessment(id: number) {
  return request.delete(`/psych_screening/assessments/${id}`)
}

/** 获取干预记录列表 */
export function listInterventions(params: {
  student_id?: number
  status?: InterventionStatus
  severity?: RiskLevel
  limit?: number
  offset?: number
}) {
  return request.get('/psych_screening/interventions', { params })
}

/** 创建干预记录 */
export function createIntervention(body: {
  student_id: number
  assessment_id?: number
  intervention_type: InterventionType
  severity: RiskLevel
  description: string
  assigned_to?: string
}) {
  return request.post('/psych_screening/interventions', body)
}

/** 干预随访 */
export function followupIntervention(id: number, body: {
  content: string
  effect_rating?: EffectRating
}) {
  return request.post(`/psych_screening/interventions/${id}/followup`, body)
}

/** 获取学生干预时间线 */
export function getInterventionTimeline(studentId: number) {
  return request.get(`/psych_screening/interventions/timeline/${studentId}`)
}

/** 获取量表题目列表 */
export function listQuestions() {
  return request.get('/psych_screening/questions')
}

/** 种子初始化 MSSMHS-55 题目 */
export function seedQuestions() {
  return request.post('/psych_screening/questions/seed')
}

/** 学生搜索 */
export function searchStudents(params: {
  keyword?: string
  grade_id?: number
  class_id?: number
  risk_level?: RiskLevel
}) {
  return request.get('/psych_screening/students/search', { params })
}

/** 统计仪表盘 */
export function getDashboard(params?: {
  grade_id?: number
  period?: string
}) {
  return request.get('/psych_screening/dashboard', { params })
}
