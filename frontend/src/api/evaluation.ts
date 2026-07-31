/**
 * evaluation.ts — 素质评价 API 契约层
 *
 * 对应后端模块: modules/evaluation (MODULE_CODE="evaluation" → URL前缀 /api/v1/evaluation)
 * 端点清单 (15):
 *   GET    /evaluation/indicators                        — 按维度列出指标树
 *   POST   /evaluation/indicators                        — 创建指标 (ms_admin)
 *   PUT    /evaluation/indicators/{indicator_id}          — 更新指标 (ms_admin)
 *   POST   /evaluation/indicators/{indicator_id}/toggle   — 切换启用/禁用 (ms_admin)
 *   DELETE /evaluation/indicators/{indicator_id}          — 删除指标 (ms_admin)
 *   GET    /evaluation/rules                             — 获取评分规则
 *   PUT    /evaluation/rules                             — 更新评分规则 (ms_admin)
 *   POST   /evaluation/scores                            — 手动录分
 *   POST   /evaluation/scores/batch                      — 批量录分
 *   GET    /evaluation/students/{student_id}/scores       — 学生五维分+总分
 *   GET    /evaluation/classes/{class_id}/ranking         — 班级排名
 *   GET    /evaluation/students/{student_id}/logs         — 评分流水审计
 *   POST   /evaluation/seed                              — 初始化种子数据 (ms_admin)
 *   GET    /evaluation/students/{student_id}/final-evaluation  — 期末综合评价(含处分)
 *   GET    /evaluation/students/{student_id}/discipline-veto   — 一票否决检查
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════

/** 五维评价维度 */
export type EvalDimension = 'moral' | 'academic' | 'health' | 'art' | 'social'

export const DIMENSION_LABELS: Record<EvalDimension, string> = {
  moral: '道德品质',
  academic: '学业水平',
  health: '身心健康',
  art: '艺术素养',
  social: '社会实践',
}

export const DIMENSION_COLORS: Record<EvalDimension, string> = {
  moral: '#ef4444',
  academic: '#3b82f6',
  health: '#10b981',
  art: '#f59e0b',
  social: '#8b5cf6',
}

/** 评分人类型 */
export type ScorerType = 'teacher' | 'self' | 'peer' | 'parent' | 'ms_admin'

/** ── 评价指标树 ─────────────────────────────── */

export interface IndicatorItem {
  id: number
  parent_id: number | null
  name: string
  weight: number
  max_score: number
  sort_order: number
  enabled: boolean
  children?: IndicatorItem[]
}

export interface IndicatorGroupedOut {
  dimension: EvalDimension
  dimension_name: string
  indicators: IndicatorItem[]
}

export interface IndicatorCreate {
  name: string
  parent_id?: number | null
  dimension: EvalDimension
  weight: number
  max_score: number
  sort_order?: number
}

export interface IndicatorUpdate {
  name?: string
  parent_id?: number | null
  dimension?: EvalDimension
  weight?: number
  max_score?: number
  sort_order?: number
}

export interface IndicatorOut {
  id: number
  parent_id: number | null
  name: string
  dimension: EvalDimension
  weight: number
  max_score: number
  sort_order: number
  enabled: boolean
  school_id: number
  created_at: string
  updated_at: string
}

/** ── 评分规则 ─────────────────────────────── */

export interface RuleOut {
  id: number
  school_id: number
  semester: string
  base_score: number
  weight_moral: number
  weight_academic: number
  weight_health: number
  weight_art: number
  weight_social: number
  discipline_bridge_enabled: boolean
  discipline_severity_map: Record<string, number> | null
  created_at: string
  updated_at: string
}

export interface RuleUpdate {
  base_score?: number
  weight_moral?: number
  weight_academic?: number
  weight_health?: number
  weight_art?: number
  weight_social?: number
  discipline_bridge_enabled?: boolean
  discipline_severity_map?: Record<string, number> | null
}

/** ── 评分录入 ─────────────────────────────── */

export interface ScoreCreate {
  student_id: number
  class_id: number
  grade_id: number
  indicator_id: number
  score: number
  scorer_type: ScorerType
  semester?: string
  comment?: string
}

export interface ScoreOut {
  id: number
  student_id: number
  class_id: number
  grade_id: number
  indicator_id: number
  indicator_name: string | null
  score: number
  scorer_type: ScorerType
  scorer_id: number
  semester: string
  comment: string | null
  created_at: string
}

export interface BatchScoreCreate {
  scores: ScoreCreate[]
}

export interface BatchScoreError {
  index: number
  student_id: number
  indicator_id: number
  error: string
}

export interface BatchScoreResult {
  success: number
  failed: number
  errors: BatchScoreError[]
}

/** ── 学生五维分 ─────────────────────────────── */

export interface StudentScoreOut {
  student_id: number
  class_id: number
  grade_id: number
  semester: string
  total_score: number
  moral_score: number
  academic_score: number
  health_score: number
  art_score: number
  social_score: number
  base_score: number
}

/** ── 班级排名 ─────────────────────────────── */

export interface RankedStudent {
  rank: number
  student_id: number
  student_name: string
  student_no: string | null
  class_id: number
  total_score: number
  moral_score: number
  academic_score: number
  health_score: number
  art_score: number
  social_score: number
}

export interface ClassRankingOut {
  class_id: number
  semester: string
  total_students: number
  avg_score: number
  ranking: RankedStudent[]
}

/** ── 评分流水审计 ─────────────────────────────── */

export interface ScoreLogItem {
  id: number
  student_id: number
  student_name: string
  dimension: string
  change_amount: number
  before_score: number
  after_score: number
  reason: string | null
  source_type: string | null
  source_id: number | null
  created_by: number
  creator_name: string
  created_at: string
  policy_tag?: string | null
}

export interface ScoreLogListOut {
  items: ScoreLogItem[]
  total: number
  page: number
  per_page: number
}

/** ── 期末综合评价 ─────────────────────────────── */

export interface DisciplinePenaltyDetail {
  sanction_id: number
  level: string
  status: string
  deduction: number
  issued_date: string
}

export interface FinalEvaluationOut {
  student_id: number
  student_name: string
  semester: string
  base_scores: Record<string, number>
  discipline_penalty: DisciplinePenaltyDetail[]
  adjusted_scores: Record<string, number>
  veto: {
    is_veto: boolean
    reason: string | null
    grade: string | null
  }
  revoked_sanctions: Array<{ sanction_id: number; level: string; revoked_date: string }>
  final_grade: string
  grade_label: string
}

/** ── 一票否决检查 ─────────────────────────────── */

export interface DisciplineVetoOut {
  student_id: number
  is_veto: boolean
  reason: string | null
  active_sanctions: Array<{ id: number; level: string; description: string | null }>
  semester: string
}

// ═══════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═══════════════════════════════════════════════════

// ── 指标管理 ──────────────────────────────────

/** GET /evaluation/indicators — 按维度分组列出评价指标树 */
export function listIndicators(dimension?: EvalDimension) {
  return request.get<any, IndicatorGroupedOut[]>('/evaluation/indicators', {
    params: dimension ? { dimension } : undefined,
  })
}

/** POST /evaluation/indicators — 创建评价指标 (ms_admin) */
export function createIndicator(data: IndicatorCreate) {
  return request.post<any, IndicatorOut>('/evaluation/indicators', data)
}

/** PUT /evaluation/indicators/{id} — 更新评价指标 (ms_admin) */
export function updateIndicator(id: number, data: IndicatorUpdate) {
  return request.put<any, IndicatorOut>(`/evaluation/indicators/${id}`, data)
}

/** POST /evaluation/indicators/{id}/toggle — 切换启用/禁用 (ms_admin) */
export function toggleIndicator(id: number) {
  return request.post<any, IndicatorOut>(`/evaluation/indicators/${id}/toggle`)
}

/** DELETE /evaluation/indicators/{id} — 删除指标 (ms_admin) */
export function deleteIndicator(id: number) {
  return request.delete<any, { message: string }>(`/evaluation/indicators/${id}`)
}

// ── 评分规则 ──────────────────────────────────

/** GET /evaluation/rules — 获取学校评分规则 */
export function getRules() {
  return request.get<any, RuleOut>('/evaluation/rules')
}

/** PUT /evaluation/rules — 更新评分规则 (ms_admin) */
export function updateRules(data: RuleUpdate) {
  return request.put<any, RuleOut>('/evaluation/rules', data)
}

// ── 评分录入 ──────────────────────────────────

/** POST /evaluation/scores — 手动手动录分 */
export function recordScore(data: ScoreCreate) {
  return request.post<any, ScoreOut>('/evaluation/scores', data)
}

/** POST /evaluation/scores/batch — 批量录分 */
export function batchRecordScores(data: BatchScoreCreate) {
  return request.post<any, BatchScoreResult>('/evaluation/scores/batch', data)
}

// ── 学生查询 ──────────────────────────────────

/** GET /evaluation/students/{student_id}/scores — 学生五维分+总分 */
export function getStudentScores(studentId: number, semester?: string) {
  return request.get<any, StudentScoreOut>(`/evaluation/students/${studentId}/scores`, {
    params: semester ? { semester } : undefined,
  })
}

/** GET /evaluation/classes/{class_id}/ranking — 班级排名 */
export function getClassRanking(classId: number, semester?: string, limit: number = 50) {
  return request.get<any, ClassRankingOut>(`/evaluation/classes/${classId}/ranking`, {
    params: { semester, limit },
  })
}

// ── 审计日志 ──────────────────────────────────

/** GET /evaluation/students/{student_id}/logs — 评分流水审计 */
export function getScoreLogs(
  studentId: number,
  page: number = 1,
  perPage: number = 50,
) {
  return request.get<any, ScoreLogListOut>(`/evaluation/students/${studentId}/logs`, {
    params: { page, per_page: perPage },
  })
}

// ── 种子数据 ──────────────────────────────────

/** POST /evaluation/seed — 初始化评价引擎种子数据 (ms_admin) */
export function seedEvaluationData() {
  return request.post<any, { rules_created: boolean; indicators_count: number; message: string }>(
    '/evaluation/seed',
  )
}

// ── 期末综合评价 + 一票否决 ─────────────────

/** GET /evaluation/students/{student_id}/final-evaluation — 期末综合评价(含处分) */
export function getFinalEvaluation(studentId: number, semester?: string) {
  return request.get<any, FinalEvaluationOut>(
    `/evaluation/students/${studentId}/final-evaluation`,
    { params: semester ? { semester } : undefined },
  )
}

/** GET /evaluation/students/{student_id}/discipline-veto — 一票否决检查 */
export function checkDisciplineVeto(studentId: number, semester?: string) {
  return request.get<any, DisciplineVetoOut>(
    `/evaluation/students/${studentId}/discipline-veto`,
    { params: semester ? { semester } : undefined },
  )
}

// ═══════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════

/** 评分人类型标签 */
export const SCORER_TYPE_LABELS: Record<ScorerType, string> = {
  teacher: '教师',
  self: '自评',
  peer: '互评',
  parent: '家长',
  ms_admin: '德育处',
}

/** 期末评价等级 */
export const FINAL_GRADE_LABELS: Record<string, { label: string; color: string }> = {
  A: { label: '优秀', color: '#10b981' },
  B: { label: '良好', color: '#3b82f6' },
  C: { label: '合格', color: '#f59e0b' },
  D: { label: '不合格', color: '#ef4444' },
}

/** 五维雷达图默认最大值 (超过按实际值) */
export const RADAR_MAX = 100

// ═══════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════

/** 维度 → 中文标签 */
export function dimensionLabel(d: EvalDimension | string): string {
  return DIMENSION_LABELS[d as EvalDimension] || d
}

/** 维度 → 图表颜色 */
export function dimensionColor(d: EvalDimension | string): string {
  return DIMENSION_COLORS[d as EvalDimension] || '#909399'
}

/** 期末等级 → el-tag type */
export function gradeTagType(grade: string): 'success' | 'primary' | 'warning' | 'danger' | 'info' {
  return (
    ({ A: 'success', B: 'primary', C: 'warning', D: 'danger' } as Record<string, string>)[grade] || 'info'
  ) as 'success' | 'primary' | 'warning' | 'danger' | 'info'
}

/** 期末等级 → 中文 */
export function gradeLabel(grade: string): string {
  return FINAL_GRADE_LABELS[grade]?.label || grade
}

// ═══════════════════════════════════════════════════
// Demo Data (后端不可用时降级)
// ═══════════════════════════════════════════════════

export function getDemoIndicators(): IndicatorGroupedOut[] {
  const dimensions: EvalDimension[] = ['moral', 'academic', 'health', 'art', 'social']
  return dimensions.map((dim, di) => ({
    dimension: dim,
    dimension_name: DIMENSION_LABELS[dim],
    indicators: [
      {
        id: di * 10 + 1,
        parent_id: null,
        name: `${DIMENSION_LABELS[dim]}主项`,
        weight: 1,
        max_score: 20,
        sort_order: 1,
        enabled: true,
        children: [
          {
            id: di * 10 + 2,
            parent_id: di * 10 + 1,
            name: `${DIMENSION_LABELS[dim]}子项A`,
            weight: 0.5,
            max_score: 10,
            sort_order: 1,
            enabled: true,
          },
          {
            id: di * 10 + 3,
            parent_id: di * 10 + 1,
            name: `${DIMENSION_LABELS[dim]}子项B`,
            weight: 0.5,
            max_score: 10,
            sort_order: 2,
            enabled: true,
          },
        ],
      },
    ],
  }))
}

export function getDemoRules(): RuleOut {
  return {
    id: 1,
    school_id: 1,
    semester: '2025-2026-2',
    base_score: 100,
    weight_moral: 0.3,
    weight_academic: 0.3,
    weight_health: 0.15,
    weight_art: 0.1,
    weight_social: 0.15,
    discipline_bridge_enabled: true,
    discipline_severity_map: { warning: -5, minor: -10, major: -20, serious: -40 },
    created_at: '2026-06-19T08:00:00Z',
    updated_at: '2026-06-30T14:00:00Z',
  }
}

export function getDemoStudentScores(studentId: number): StudentScoreOut {
  return {
    student_id: studentId,
    class_id: 1,
    grade_id: 1,
    semester: '2025-2026-2',
    total_score: 82.4,
    moral_score: 85.0,
    academic_score: 78.0,
    health_score: 90.0,
    art_score: 75.0,
    social_score: 88.0,
    base_score: 100,
  }
}

export function getDemoClassRanking(classId: number): ClassRankingOut {
  const names = ['陈博裕', '李梓涵', '王浩然', '张雨萱', '刘子轩', '赵文博', '孙梦琪', '周思远']
  return {
    class_id: classId,
    semester: '2025-2026-2',
    total_students: 8,
    avg_score: 76.3,
    ranking: names.map((name, i) => ({
      rank: i + 1,
      student_id: 100 + i,
      student_name: name,
      student_no: `20250${String(i + 1).padStart(2, '0')}`,
      class_id: classId,
      total_score: [92.5, 88.3, 85.1, 79.8, 74.2, 71.6, 68.9, 60.0][i],
      moral_score: [90, 85, 88, 75, 80, 72, 70, 65][i],
      academic_score: [95, 91, 82, 84, 68, 71, 68, 55][i],
      health_score: [92, 88, 90, 85, 82, 78, 75, 72][i],
      art_score: [88, 85, 80, 78, 75, 70, 68, 62][i],
      social_score: [95, 90, 85, 82, 78, 75, 70, 68][i],
    })),
  }
}

export function getDemoScoreLogs(studentId: number): ScoreLogListOut {
  return {
    items: [
      {
        id: 1,
        student_id: studentId,
        student_name: '陈博裕',
        dimension: 'academic',
        change_amount: -5,
        before_score: 83,
        after_score: 78,
        reason: '期中数学未达标',
        source_type: 'manual',
        source_id: null,
        created_by: 5,
        creator_name: '王老师',
        created_at: '2026-06-20T14:30:00Z',
        policy_tag: 'repairable',
      },
      {
        id: 2,
        student_id: studentId,
        student_name: '陈博裕',
        dimension: 'moral',
        change_amount: -3,
        before_score: 88,
        after_score: 85,
        reason: '课堂使用手机',
        source_type: 'discipline',
        source_id: 12,
        created_by: 3,
        creator_name: '李主任',
        created_at: '2026-06-22T10:15:00Z',
        policy_tag: 'repairable',
      },
      {
        id: 3,
        student_id: studentId,
        student_name: '陈博裕',
        dimension: 'social',
        change_amount: 3,
        before_score: 85,
        after_score: 88,
        reason: '志愿者活动积极参与',
        source_type: 'manual',
        source_id: null,
        created_by: 5,
        creator_name: '王老师',
        created_at: '2026-06-25T16:00:00Z',
        policy_tag: null,
      },
      {
        id: 4,
        student_id: studentId,
        student_name: '陈博裕',
        dimension: 'academic',
        change_amount: 0,
        before_score: 78,
        after_score: 78,
        reason: '期末数学补考通过，恢复原始分',
        source_type: 'recovery',
        source_id: 3,
        created_by: 1,
        creator_name: '系统',
        created_at: '2026-07-01T09:00:00Z',
        policy_tag: 'recovered',
      },
    ],
    total: 4,
    page: 1,
    per_page: 50,
  }
}

export function getDemoFinalEvaluation(studentId: number): FinalEvaluationOut {
  return {
    student_id: studentId,
    student_name: '陈博裕',
    semester: '2025-2026-2',
    base_scores: { moral: 85, academic: 78, health: 90, art: 75, social: 88 },
    discipline_penalty: [
      {
        sanction_id: 12,
        level: 'minor',
        status: 'ACTIVE',
        deduction: 10,
        issued_date: '2026-06-22',
      },
    ],
    adjusted_scores: { moral: 80, academic: 73, health: 85, art: 70, social: 83 },
    veto: { is_veto: false, reason: null, grade: null },
    revoked_sanctions: [],
    final_grade: 'B',
    grade_label: '良好',
  }
}

// ═══════════════════════════════════════════════════════════════
// 正向加分排行榜 API
// ═══════════════════════════════════════════════════════════════

export interface PositiveRankingItem {
  rank: number
  student_id: number
  student_name: string
  class_name: string
  positive_score: number
  record_count: number
}

export interface PositiveRankingOut {
  class_id?: number
  grade_id?: number
  dimension?: string
  total: number
  ranking: PositiveRankingItem[]
}

/**
 * 获取正向加分排行榜
 *
 * @param class_id - 班级ID（不传则返回全校排名）
 * @param grade_id - 年级ID
 * @param dimension - 维度筛选（moral/academic/health/art/social）
 * @param limit - 返回记录数
 * @param offset - 偏移量
 */
export async function getPositiveScoreRanking(params: {
  class_id?: number
  grade_id?: number
  dimension?: string
  limit?: number
  offset?: number
}): Promise<PositiveRankingOut> {
  return request({
    url: '/evaluation/ranking/positive',
    method: 'get',
    params,
  })
}
