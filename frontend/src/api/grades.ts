/**
 * grades.ts — 成绩管理 API 契约层
 *
 * 对应后端模块: modules/grades (MODULE_CODE="grades" → URL前缀 /api/v1/grades)
 * 端点清单 (12):
 *   科目 CRUD (4):
 *     POST   /grades/subjects              — 创建科目 (ms_admin)
 *     GET    /grades/subjects              — 科目列表 (ms_admin)
 *     PUT    /grades/subjects/{id}         — 更新科目 (ms_admin)
 *     PATCH  /grades/subjects/{id}/toggle  — 启停科目 (ms_admin)
 *
 *   考试 CRUD (4):
 *     POST   /grades/exams                 — 创建考试 (ms_admin)
 *     GET    /grades/exams                 — 考试列表 (ms_admin)
 *     PUT    /grades/exams/{id}            — 更新考试 (ms_admin)
 *     PATCH  /grades/exams/{id}/status     — 状态变更 (ms_admin)
 *
 *   成绩管理 (3):
 *     POST   /grades/scores/upload         — 批量录入 (ms_admin)
 *     GET    /grades/scores/results        — 成绩查询分页 (认证用户)
 *     GET    /grades/scores/{exam_id}/student/{student_id} — 单人成绩 (认证用户)
 *
 *   审计日志 (1):
 *     GET    /grades/audit-logs            — 审计日志分页 (ms_admin)
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════

/** 考试类型枚举 */
export type ExamType = 'monthly' | 'midterm' | 'final' | 'quiz'

/** 考试状态枚举 */
export type ExamStatus = 'draft' | 'published' | 'archived'

/** 审计操作类型 */
export type AuditAction = 'upsert' | 'delete'

// ── 科目管理 ──────────────────────────────────

export interface SubjectCreate {
  name: string
  code: string
  full_score: number  // Decimal → number (前端统一用 number)
  sort_order?: number
}

export interface SubjectUpdate {
  name?: string
  code?: string
  full_score?: number
  sort_order?: number
  is_active?: boolean
}

export interface SubjectOut {
  id: number
  name: string
  code: string
  full_score: number
  sort_order: number
  is_active: boolean
  created_at: string | null
}

export interface SubjectItem {
  id: number
  name: string
  code: string
  full_score: number
  is_active: boolean
}

// ── 考试管理 ──────────────────────────────────

export interface ExamCreate {
  name: string
  exam_type: ExamType
  grade_id: number
  semester?: string
  exam_date?: string | null  // datetime → ISO string
}

export interface ExamUpdate {
  name?: string
  exam_type?: ExamType
  semester?: string
  exam_date?: string | null
  status?: ExamStatus
}

export interface ExamOut {
  id: number
  name: string
  exam_type: ExamType
  grade_id: number
  semester: string
  exam_date: string | null
  status: ExamStatus
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface ExamItem {
  id: number
  name: string
  exam_type: ExamType
  semester: string
  exam_date: string | null
  status: ExamStatus
}

// ── 成绩录入 ──────────────────────────────────

export interface ScoreEntry {
  student_id: number
  subject_id: number
  score: number | null       // Decimal → number | null (null = 缺考)
  is_absent: boolean
  remark?: string | null
}

export interface ScoreUploadRequest {
  exam_id: number
  scores: ScoreEntry[]
}

export interface ScoreUploadResult {
  exam_id: number
  total: number
  success: number
  failed: number
  errors: string[]
  ranks_computed: boolean
}

// ── 成绩查询 ──────────────────────────────────

export interface StudentScoreOut {
  subject_id: number
  subject_name: string
  full_score: number
  score: number | null
  is_absent: boolean
  class_rank: number | null
  grade_rank: number | null
}

export interface StudentExamResult {
  student_id: number
  student_name: string
  class_id: number
  class_name: string
  total_score: number | null
  avg_score: number | null
  class_rank: number | null
  grade_rank: number | null
  subjects: StudentScoreOut[]
}

export interface ExamResultQuery {
  exam_id: number
  class_id?: number | null
  student_name?: string | null
  sort_by?: string
  page?: number
  page_size?: number
}

export interface SubjectSummary {
  subject_id: number
  subject_name: string
  full_score: number
  avg_score: number | null
  max_score: number | null
  min_score: number | null
  pass_rate: number | null
  excellent_rate: number | null
}

export interface ClassScoreSummary {
  class_id: number
  class_name: string
  student_count: number
  avg_total: number | null
  max_total: number | null
  min_total: number | null
  pass_rate: number | null
  excellent_rate: number | null
  subjects: SubjectSummary[]
}

export interface ExamResultPage {
  exam: ExamOut
  total: number
  page: number
  page_size: number
  results: StudentExamResult[]
  class_summaries: ClassScoreSummary[]
}

// ── 审计日志 ──────────────────────────────────

export interface AuditLogOut {
  id: number
  exam_id: number
  student_id: number
  subject_id: number
  old_score: number | null
  new_score: number | null
  action: AuditAction | string
  operator_id: number | null
  operator_name: string | null
  created_at: string | null
}

export interface AuditLogQuery {
  exam_id?: number | null
  student_id?: number | null
  action?: AuditAction | string | null
  page?: number
  page_size?: number
}

export interface AuditLogPage {
  total: number
  page: number
  page_size: number
  logs: AuditLogOut[]
}

// ═══════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═══════════════════════════════════════════════════

// ── 科目 CRUD ──────────────────────────────────

/** POST /grades/subjects — 创建科目 (ms_admin) */
export function createSubject(data: SubjectCreate) {
  return request.post<any, SubjectOut>('/grades/subjects', data)
}

/** GET /grades/subjects — 科目列表 (ms_admin) */
export function listSubjects(activeOnly?: boolean) {
  return request.get<any, SubjectItem[]>('/grades/subjects', {
    params: activeOnly ? { active_only: activeOnly } : undefined,
  })
}

/** PUT /grades/subjects/{id} — 更新科目 (ms_admin) */
export function updateSubject(id: number, data: SubjectUpdate) {
  return request.put<any, SubjectOut>(`/grades/subjects/${id}`, data)
}

/** PATCH /grades/subjects/{id}/toggle — 启停科目 (ms_admin) */
export function toggleSubject(id: number) {
  return request.patch<any, SubjectOut>(`/grades/subjects/${id}/toggle`)
}

// ── 考试 CRUD ──────────────────────────────────

/** POST /grades/exams — 创建考试 (ms_admin) */
export function createExam(data: ExamCreate) {
  return request.post<any, ExamOut>('/grades/exams', data)
}

/** GET /grades/exams — 考试列表 (ms_admin) */
export function listExams(params?: {
  grade_id?: number
  semester?: string
  status?: ExamStatus
}) {
  return request.get<any, ExamItem[]>('/grades/exams', { params })
}

/** PUT /grades/exams/{id} — 更新考试 (ms_admin) */
export function updateExam(id: number, data: ExamUpdate) {
  return request.put<any, ExamOut>(`/grades/exams/${id}`, data)
}

/** PATCH /grades/exams/{id}/status — 状态变更 (ms_admin) */
export function changeExamStatus(id: number, newStatus: ExamStatus) {
  return request.patch<any, ExamOut>(`/grades/exams/${id}/status`, null, {
    params: { new_status: newStatus },
  })
}

// ── 成绩管理 ──────────────────────────────────

/** POST /grades/scores/upload — 批量录入 (ms_admin) */
export function uploadScores(data: ScoreUploadRequest) {
  return request.post<any, ScoreUploadResult>('/grades/scores/upload', data)
}

/** GET /grades/scores/results — 成绩查询分页 (认证用户) */
export function getExamResults(params: ExamResultQuery) {
  return request.get<any, ExamResultPage>('/grades/scores/results', {
    params: {
      exam_id: params.exam_id,
      class_id: params.class_id,
      student_name: params.student_name,
      sort_by: params.sort_by || 'total_score_desc',
      page: params.page || 1,
      page_size: params.page_size || 50,
    },
  })
}

/** GET /grades/scores/{exam_id}/student/{student_id} — 单人成绩 (认证用户) */
export function getStudentResult(examId: number, studentId: number) {
  return request.get<any, StudentExamResult>(
    `/grades/scores/${examId}/student/${studentId}`,
  )
}

// ── 审计日志 ──────────────────────────────────

/** GET /grades/audit-logs — 审计日志分页 (ms_admin) */
export function getAuditLogs(params: AuditLogQuery) {
  return request.get<any, AuditLogPage>('/grades/audit-logs', {
    params: {
      exam_id: params.exam_id,
      student_id: params.student_id,
      action: params.action,
      page: params.page || 1,
      page_size: params.page_size || 50,
    },
  })
}

// ═══════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════

/** 考试类型 → 中文标签 */
export const EXAM_TYPE_LABELS: Record<ExamType, string> = {
  monthly: '月考',
  midterm: '期中考试',
  final: '期末考试',
  quiz: '随堂测验',
}

/** 考试类型 → 图表配色 */
export const EXAM_TYPE_COLORS: Record<ExamType, string> = {
  monthly: '#60a5fa',
  midterm: '#f59e0b',
  final: '#ef4444',
  quiz: '#a78bfa',
}

/** 考试状态 → 中文标签 */
export const EXAM_STATUS_LABELS: Record<ExamStatus, string> = {
  draft: '草稿',
  published: '已发布',
  archived: '已归档',
}

/** 考试状态 → el-tag type 映射 */
export const EXAM_STATUS_TAG: Record<ExamStatus, 'info' | 'success' | 'warning'> = {
  draft: 'info',
  published: 'success',
  archived: 'warning',
}

/** 科目配色池（按科目顺序轮替） */
export const SUBJECT_COLORS: string[] = [
  '#ef4444', // 红 — 语文
  '#3b82f6', // 蓝 — 数学
  '#10b981', // 绿 — 英语
  '#f59e0b', // 黄 — 政治/历史
  '#8b5cf6', // 紫 — 地理/生物
  '#ec4899', // 粉 — 物理/化学
  '#14b8a6', // 青 — 体育
  '#64748b', // 灰 — 其他
]

/** 排序方式标签 */
export const SORT_BY_LABELS: Record<string, string> = {
  total_score_desc: '总分降序',
  total_score_asc: '总分升序',
}

// ═══════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════

/** 考试类型 → 中文标签 */
export function examTypeLabel(type: ExamType | string): string {
  return EXAM_TYPE_LABELS[type as ExamType] || type
}

/** 考试类型 → 图表颜色 */
export function examTypeColor(type: ExamType | string): string {
  return EXAM_TYPE_COLORS[type as ExamType] || '#909399'
}

/** 考试状态 → 中文标签 */
export function examStatusLabel(status: ExamStatus | string): string {
  return EXAM_STATUS_LABELS[status as ExamStatus] || status
}

/** 考试状态 → el-tag type */
export function examStatusTag(status: ExamStatus | string): 'info' | 'success' | 'warning' | 'danger' {
  return (EXAM_STATUS_TAG[status as ExamStatus] || 'info') as 'info' | 'success' | 'warning' | 'danger'
}

/** 科目 → 颜色（按 index 从 SUBJECT_COLORS 轮替） */
export function subjectColor(index: number): string {
  return SUBJECT_COLORS[index % SUBJECT_COLORS.length]
}

/** 成绩 → 等级标签（及格/优秀判定） */
export function scoreGradeLabel(score: number | null, fullScore: number = 100): string {
  if (score === null) return '缺考'
  const ratio = score / fullScore
  if (ratio >= 0.9) return '优秀'
  if (ratio >= 0.6) return '及格'
  return '不及格'
}

/** 成绩 → el-tag type */
export function scoreTagType(score: number | null, fullScore: number = 100): 'success' | 'warning' | 'danger' | 'info' {
  if (score === null) return 'info'
  const ratio = score / fullScore
  if (ratio >= 0.9) return 'success'
  if (ratio >= 0.6) return 'warning'
  return 'danger'
}

// ═══════════════════════════════════════════════════
// Demo Data (后端不可用时降级)
// ═══════════════════════════════════════════════════

/** Demo 科目列表 */
export function getDemoSubjects(): SubjectItem[] {
  // 🔪 Fix: 补全 physics/chemistry/pe/art/music 5科, 确保 DIMENSION_SUBJECTS 所有维度科目有覆盖
  return [
    { id: 1, name: '语文', code: 'chinese', full_score: 100, is_active: true },
    { id: 2, name: '数学', code: 'math', full_score: 100, is_active: true },
    { id: 3, name: '英语', code: 'english', full_score: 100, is_active: true },
    { id: 4, name: '政治', code: 'politics', full_score: 100, is_active: true },
    { id: 5, name: '历史', code: 'history', full_score: 100, is_active: true },
    { id: 6, name: '地理', code: 'geography', full_score: 100, is_active: true },
    { id: 7, name: '生物', code: 'biology', full_score: 100, is_active: true },
    { id: 8, name: '物理', code: 'physics', full_score: 100, is_active: true },
    { id: 9, name: '化学', code: 'chemistry', full_score: 100, is_active: true },
    { id: 10, name: '体育', code: 'pe', full_score: 100, is_active: true },
    { id: 11, name: '美术', code: 'art', full_score: 50, is_active: true },
    { id: 12, name: '音乐', code: 'music', full_score: 50, is_active: true },
  ]
}

/** Demo 考试列表 */
export function getDemoExams(): ExamItem[] {
  return [
    { id: 1, name: '初一10月月考', exam_type: 'monthly', semester: '2025-1', exam_date: '2025-10-20T00:00:00Z', status: 'published' },
    { id: 2, name: '七年级期中考试', exam_type: 'midterm', semester: '2025-1', exam_date: '2025-11-15T00:00:00Z', status: 'published' },
    { id: 3, name: '2025年初中七年一期期末质量监测', exam_type: 'final', semester: '2025-1', exam_date: '2026-01-10T00:00:00Z', status: 'published' },
  ]
}

/** Demo 成绩结果页 */
export function getDemoExamResults(): ExamResultPage {
  const names = ['陈博裕', '李梓涵', '王浩然', '张雨萱', '刘子轩', '赵文博', '孙梦琪', '周思远']
  const subjects = getDemoSubjects()

  return {
    exam: {
      id: 3,
      name: '2025年初中七年一期期末质量监测',
      exam_type: 'final',
      grade_id: 1,
      semester: '2025-1',
      exam_date: '2026-01-10T00:00:00Z',
      status: 'published',
      created_by: 1,
      created_at: '2026-01-08T08:00:00Z',
      updated_at: null,
    },
    total: 8,
    page: 1,
    page_size: 50,
    results: names.map((name, i) => ({
      student_id: 100 + i,
      student_name: name,
      class_id: 1,
      class_name: '2501班',
      total_score: [385, 362, 350, 340, 328, 318, 310, 295][i],
      avg_score: [55.0, 51.7, 50.0, 48.6, 46.9, 45.4, 44.3, 42.1][i],
      class_rank: i + 1,
      grade_rank: i + 5,
      subjects: subjects.map((s, si) => ({
        subject_id: s.id,
        subject_name: s.name,
        full_score: s.full_score,
        score: [92, 88, 85, 79, 74, 71, 68, 60][i] - si * 2,
        is_absent: false,
        class_rank: i + si + 1,
        grade_rank: i + si + 5,
      })),
    })),
    class_summaries: [
      {
        class_id: 1,
        class_name: '2501班',
        student_count: 8,
        avg_total: 336.0,
        max_total: 385,
        min_total: 295,
        pass_rate: 0.75,
        excellent_rate: 0.125,
        subjects: subjects.map((s, si) => ({
          subject_id: s.id,
          subject_name: s.name,
          full_score: s.full_score,
          avg_score: 78 - si * 1.5,
          max_score: 92 - si * 2,
          min_score: 60 - si * 1,
          pass_rate: 0.75,
          excellent_rate: 0.125,
        })),
      },
    ],
  }
}

/** Demo 审计日志 */
export function getDemoAuditLogs(): AuditLogPage {
  return {
    total: 3,
    page: 1,
    page_size: 50,
    logs: [
      {
        id: 1,
        exam_id: 3,
        student_id: 100,
        subject_id: 2,
        old_score: 85,
        new_score: 88,
        action: 'upsert',
        operator_id: 1,
        operator_name: 'admin',
        created_at: '2026-01-12T10:30:00Z',
      },
      {
        id: 2,
        exam_id: 3,
        student_id: 101,
        subject_id: 1,
        old_score: null,
        new_score: 82,
        action: 'upsert',
        operator_id: 1,
        operator_name: 'admin',
        created_at: '2026-01-12T10:35:00Z',
      },
      {
        id: 3,
        exam_id: 3,
        student_id: 105,
        subject_id: 3,
        old_score: 75,
        new_score: 79,
        action: 'upsert',
        operator_id: 1,
        operator_name: 'admin',
        created_at: '2026-01-12T10:40:00Z',
      },
    ],
  }
}

// ═══════════════════════════════════════════════════
// 组件兼容类型 & 常量 (HolisticProfileCard 专用)
// ═══════════════════════════════════════════════════

/** 科目→评价维度映射 (学业成绩 × 行为评价双模态雷达) */
export const SUBJECT_DIMENSION_MAP: Record<string, string> = {
  chinese: 'moral',
  math: 'academic',
  english: 'social',
  politics: 'moral',
  history: 'social',
  geography: 'social',
  biology: 'health',
  physics: 'academic',
  chemistry: 'academic',
  pe: 'health',
  art: 'art',
  music: 'art',
}

/** 科目→维度反向映射 (维度→科目列表) */
export const DIMENSION_SUBJECTS: Record<string, string[]> = {
  moral: ['chinese', 'politics'],
  academic: ['math', 'physics', 'chemistry'],
  health: ['biology', 'pe'],
  art: ['art', 'music'],
  social: ['english', 'history', 'geography'],
}

/** 成绩结果扁平行 (科目维度, 用于雷达图/偏离计算) */
export interface ScoreResultItem {
  student_id: number
  student_name: string
  subject_id: number
  subject_code: string
  subject_name: string
  full_score: number
  score: number | null
  is_absent: boolean
  class_rank: number | null
  grade_rank: number | null
}

/** Demo 成绩扁平行 (for HolisticProfileCard offline fallback) */
export function getDemoScoreResults(): ScoreResultItem[] {
  const subjects = getDemoSubjects()
  const names = ['陈博裕', '李梓涵', '王浩然']
  return names.flatMap((name, ni) =>
    subjects.map((subj, si) => ({
      student_id: 100 + ni,
      student_name: name,
      subject_id: subj.id,
      subject_code: subj.code,
      subject_name: subj.name,
      full_score: subj.full_score,
      score: [92, 88, 85][ni] - si * 2,
      is_absent: false,
      class_rank: ni + si + 1,
      grade_rank: ni + si + 5,
    }))
  )
}

// ── Alias exports (component compatibility) ──────────────────────

/** @deprecated Use listExams instead */
export const getExamList = listExams
/** @deprecated Use getExamResults instead */
export const getScoreResults = getExamResults
/** @deprecated Use listSubjects instead */
export const getSubjectList = listSubjects
/** @deprecated Use getDemoExams instead */
export const getDemoExamList = getDemoExams
/** @deprecated Use getDemoSubjects instead */
export const getDemoSubjectList = getDemoSubjects
