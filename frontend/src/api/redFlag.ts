/**
 * redFlag.ts — 流动红旗 API 契约层
 *
 * 对应后端模块: modules/red_flag (MODULE_CODE="red_flag" -> URL前缀 /api/v1/red_flag)
 * 端点清单 (12):
 *   POST   /red_flag/routines                    — 录入常规评分
 *   POST   /red_flag/routines/batch              — 批量录入
 *   GET    /red_flag/routines                    — 查询评分列表
 *   DELETE /red_flag/routines/{id}               — 删除评分
 *   POST   /red_flag/evaluations/generate         — 生成草稿 (ms_admin)
 *   GET    /red_flag/evaluations/drafts           — 查看草稿
 *   POST   /red_flag/evaluations/publish          — 发布 (ms_admin)
 *   GET    /red_flag/evaluations/leaderboard      — 排行榜
 *   POST   /red_flag/evaluations/archive          — 归档 (ms_admin)
 *   GET    /red_flag/evaluations/history          — 归档历史
 *   GET    /red_flag/evaluations/trends/{classId} — 班级趋势
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

export type RoutineCategory = 'hygiene' | 'discipline' | 'exercise'
export type ScorerType = 'class_teacher' | 'grade_leader' | 'ms_admin'
export type PeriodType = 'weekly' | 'monthly'

export const CATEGORY_LABELS: Record<RoutineCategory, string> = {
  hygiene: '卫生',
  discipline: '纪律',
  exercise: '两操',
}

export const CATEGORY_COLORS: Record<RoutineCategory, string> = {
  hygiene: '#10b981',
  discipline: '#ef4444',
  exercise: '#3b82f6',
}

export const SCORER_LABELS: Record<ScorerType, string> = {
  class_teacher: '班主任',
  grade_leader: '年级组',
  ms_admin: '德育处',
}

export interface RoutineScore {
  id: number
  class_id: number
  class_name: string
  grade_id: number
  category: RoutineCategory
  score: number
  scorer_type: ScorerType
  record_date: string
  inspector: string
  note?: string
}

export interface FlagEvaluation {
  id: number
  class_id: number
  class_name: string
  grade_id: number
  period_type: PeriodType
  period_label: string
  routine_hygiene: number
  routine_discipline: number
  routine_exercise: number
  weighted_base: number
  discipline_deduction: number
  attendance_deduction: number
  final_score: number
  rank: number | null
  has_flag: boolean
  status: 'draft' | 'published' | 'archived'
}

export interface FlagLeaderboardItem {
  class_id: number
  class_name: string
  final_score: number
  rank: number
  has_flag: boolean
  routine_hygiene: number
  routine_discipline: number
  routine_exercise: number
  discipline_deduction: number
  attendance_deduction: number
}

export interface ArchiveHistoryItem {
  id: number
  class_id: number
  class_name: string
  period_type: PeriodType
  period_label: string
  final_score: number
  rank: number
  has_flag: boolean
  archived_at: string
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

/** 录入常规评分 */
export function addRoutine(body: {
  class_id: number
  grade_id?: number
  category: RoutineCategory
  score: number
  scorer_type: ScorerType
  record_date: string
  inspector?: string
  note?: string
}) {
  return request.post('/red_flag/routines', body)
}

/** 批量录入 */
export function addRoutineBatch(body: {
  scores: Array<{
    class_id: number
    grade_id?: number
    category: RoutineCategory
    score: number
    scorer_type: ScorerType
    record_date: string
    inspector?: string
    note?: string
  }>
}) {
  return request.post('/red_flag/routines/batch', body)
}

/** 查询评分列表 */
export function listRoutines(params: {
  grade_id?: number
  class_id?: number
  scorer_type?: string
  category?: string
  start_date?: string
  end_date?: string
  offset?: number
  limit?: number
}) {
  return request.get('/red_flag/routines', { params })
}

/** 删除评分 */
export function deleteRoutine(id: number) {
  return request.delete(`/red_flag/routines/${id}`)
}

/** 生成评价草稿 (ms_admin) */
export function generateEvaluations(body: {
  grade_id: number
  period_type: PeriodType
  period_label: string
  start_date: string
  end_date: string
}) {
  return request.post('/red_flag/evaluations/generate', body)
}

/** 查看草稿 */
export function viewDrafts(params: { grade_id?: number; period_type?: string }) {
  return request.get('/red_flag/evaluations/drafts', { params })
}

/** 发布评价 (ms_admin) */
export function publishEvaluations(params: {
  grade_id: number
  period_type: string
  period_label: string
}) {
  return request.post('/red_flag/evaluations/publish', null, { params })
}

/** 排行榜 */
export function getLeaderboard(params: {
  grade_id?: number
  period_type?: string
  period_label?: string
}) {
  return request.get('/red_flag/evaluations/leaderboard', { params })
}

/** 归档 (ms_admin) */
export function archiveEvaluations(params: {
  grade_id: number
  period_type: string
  period_label: string
}) {
  return request.post('/red_flag/evaluations/archive', null, { params })
}

/** 归档历史 */
export function getArchiveHistory(params: {
  grade_id?: number
  class_id?: number
  period_type?: string
  offset?: number
  limit?: number
}) {
  return request.get('/red_flag/evaluations/history', { params })
}

/** 班级趋势 */
export function getClassTrends(classId: number) {
  return request.get(`/red_flag/evaluations/trends/${classId}`)
}
