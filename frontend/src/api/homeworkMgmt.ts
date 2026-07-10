/**
 * homeworkMgmt.ts — 结构化作业管理 API 契约层
 *
 * 对应后端模块: modules/homework_mgmt
 * URL前缀: /api/v1/homework_mgmt
 *
 * 端点清单 (11):
 *   GET    /homework_mgmt/                              — 作业列表(筛选+分页)
 *   POST   /homework_mgmt/                              — 发布作业
 *   GET    /homework_mgmt/dashboard                     — 作业统计看板
 *   GET    /homework_mgmt/my-homework                    — 学生视角作业列表
 *   GET    /homework_mgmt/{assignment_id}               — 作业详情
 *   PUT    /homework_mgmt/{assignment_id}               — 更新作业
 *   POST   /homework_mgmt/{assignment_id}/close          — 关闭作业
 *   GET    /homework_mgmt/{assignment_id}/submissions    — 提交列表
 *   POST   /homework_mgmt/{assignment_id}/submit         — 学生提交作业
 *   GET    /homework_mgmt/{assignment_id}/submission/{student_id} — 学生提交详情
 *   POST   /homework_mgmt/submissions/{submission_id}/grade — 教师批改
 */

import request from './request'

/* ──────────────── 类型定义 ──────────────── */

export type HomeworkType = 'daily' | 'weekly' | 'unit' | 'holiday' | 'project'
export type AssignmentStatus = 'published' | 'closed'
export type SubmissionStatus = 'submitted' | 'late' | 'graded' | 'missing'
export type ErrorType = 'conceptual' | 'procedural' | 'careless' | 'omission' | 'unknown'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type GradeLevel = 'excellent' | 'good' | 'pass' | 'needs_improvement'

export interface ErrorItemPayload {
  question_no?: string | null
  question_content: string
  question_type?: string | null
  student_answer?: string | null
  correct_answer?: string | null
  error_type: ErrorType
  knowledge_point_ids?: number[] | null
  difficulty?: Difficulty | null
}

export interface AssignmentResponse {
  id: number
  school_id: number
  teacher_id: number
  teacher_name: string | null
  subject_id: number
  subject_name: string | null
  class_id: number | null
  class_name: string | null
  grade_id: number | null
  title: string
  description: string | null
  homework_type: HomeworkType
  assigned_date: string
  due_date: string
  status: AssignmentStatus
  knowledge_point_ids: number[] | null
  attachment_url: string | null
  total_score: number
  submission_count: number
  graded_count: number
  total_students: number
  created_at: string | null
}

export interface AssignmentCreatePayload {
  subject_id: number
  class_id?: number | null
  grade_id?: number | null
  title: string
  description?: string | null
  homework_type?: HomeworkType
  assigned_date: string
  due_date: string
  knowledge_point_ids?: number[] | null
  attachment_url?: string | null
  total_score?: number
}

export interface AssignmentUpdatePayload {
  title?: string
  description?: string
  homework_type?: HomeworkType
  due_date?: string
  knowledge_point_ids?: number[] | null
  attachment_url?: string | null
  total_score?: number
  status?: AssignmentStatus
}

export interface SubmissionResponse {
  id: number
  assignment_id: number
  student_id: number
  student_name: string | null
  content: string | null
  attachment_url: string | null
  submitted_at: string | null
  status: SubmissionStatus
  late_minutes: number
  created_at: string | null
  grading: GradingResponse | null
}

export interface GradingResponse {
  id: number
  submission_id: number
  teacher_id: number
  teacher_name: string | null
  score: number | null
  max_score: number
  score_percentage: number | null
  grade: string | null
  feedback: string | null
  error_items: Record<string, any>[] | null
  error_count: number
  graded_at: string | null
}

export interface GradingPayload {
  score: number
  max_score?: number
  feedback?: string | null
  error_items?: ErrorItemPayload[] | null
}

export interface DashboardResponse {
  total_assignments: number
  active_assignments: number
  total_submissions: number
  pending_grading: number
  avg_score: number | null
  avg_completion_rate: number | null
  by_type: Record<string, number>
  recent_assignments: Record<string, any>[]
  error_hotspots: Record<string, any>[]
}

export interface ListResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/* ──────────────── API 函数 ──────────────── */

export function listAssignments(params?: {
  status?: AssignmentStatus
  class_id?: number
  subject_id?: number
  homework_type?: HomeworkType
  page?: number
  page_size?: number
}) {
  return request.get<any, ListResponse<AssignmentResponse>>('/homework_mgmt/', { params })
}

export function createAssignment(data: AssignmentCreatePayload) {
  return request.post<any, AssignmentResponse>('/homework_mgmt/', data)
}

export function getDashboard() {
  return request.get<any, DashboardResponse>('/homework_mgmt/dashboard')
}

export function getMyHomework(params?: { status?: SubmissionStatus }) {
  return request.get<any, ListResponse<SubmissionResponse>>('/homework_mgmt/my-homework', { params })
}

export function getAssignment(assignmentId: number) {
  return request.get<any, AssignmentResponse>(`/homework_mgmt/${assignmentId}`)
}

export function updateAssignment(assignmentId: number, data: AssignmentUpdatePayload) {
  return request.put<any, AssignmentResponse>(`/homework_mgmt/${assignmentId}`, data)
}

export function closeAssignment(assignmentId: number) {
  return request.post<any, { message: string }>(`/homework_mgmt/${assignmentId}/close`)
}

export function getSubmissions(assignmentId: number, params?: {
  status?: SubmissionStatus
  page?: number
  page_size?: number
}) {
  return request.get<any, ListResponse<SubmissionResponse>>(`/homework_mgmt/${assignmentId}/submissions`, { params })
}

export function submitHomework(assignmentId: number, data: {
  content?: string | null
  attachment_url?: string | null
}) {
  return request.post<any, SubmissionResponse>(`/homework_mgmt/${assignmentId}/submit`, data)
}

export function getStudentSubmission(assignmentId: number, studentId: number) {
  return request.get<any, SubmissionResponse>(`/homework_mgmt/${assignmentId}/submission/${studentId}`)
}

export function gradeSubmission(submissionId: number, data: GradingPayload) {
  return request.post<any, GradingResponse>(`/homework_mgmt/submissions/${submissionId}/grade`, data)
}

/* ──────────────── 映射工具 ──────────────── */

export function homeworkTypeLabel(type: HomeworkType): string {
  const map: Record<HomeworkType, string> = {
    daily: '日常作业',
    weekly: '周作业',
    unit: '单元作业',
    holiday: '假期作业',
    project: '项目作业',
  }
  return map[type] || type
}

export function homeworkTypeTag(type: HomeworkType): string {
  const map: Record<HomeworkType, string> = {
    daily: 'primary',
    weekly: 'success',
    unit: 'warning',
    holiday: 'info',
    project: 'danger',
  }
  return map[type] || 'info'
}

export function assignmentStatusLabel(status: AssignmentStatus): string {
  return status === 'published' ? '进行中' : '已关闭'
}

export function assignmentStatusTag(status: AssignmentStatus): string {
  return status === 'published' ? 'success' : 'info'
}

export function submissionStatusLabel(status: SubmissionStatus): string {
  const map: Record<SubmissionStatus, string> = {
    submitted: '已提交',
    late: '迟交',
    graded: '已批改',
    missing: '未提交',
  }
  return map[status] || status
}

export function submissionStatusTag(status: SubmissionStatus): string {
  const map: Record<SubmissionStatus, string> = {
    submitted: 'primary',
    late: 'warning',
    graded: 'success',
    missing: 'danger',
  }
  return map[status] || 'info'
}

export function errorTypeLabel(type: ErrorType): string {
  const map: Record<ErrorType, string> = {
    conceptual: '概念性错误',
    procedural: '程序性错误',
    careless: '粗心错误',
    omission: '遗漏错误',
    unknown: '未知错误',
  }
  return map[type] || type
}

export function errorTypeTag(type: ErrorType): string {
  const map: Record<ErrorType, string> = {
    conceptual: 'danger',
    procedural: 'warning',
    careless: 'info',
    omission: 'warning',
    unknown: 'info',
  }
  return map[type] || 'info'
}

export function difficultyLabel(d: Difficulty): string {
  const map: Record<Difficulty, string> = { easy: '简单', medium: '中等', hard: '困难' }
  return map[d] || d
}

export function difficultyTag(d: Difficulty): string {
  const map: Record<Difficulty, string> = { easy: 'success', medium: 'warning', hard: 'danger' }
  return map[d] || 'info'
}

export function gradeLabel(grade: string | null): string {
  if (!grade) return '-'
  const map: Record<string, string> = {
    excellent: '优秀',
    good: '良好',
    pass: '及格',
    needs_improvement: '待提高',
  }
  return map[grade] || grade
}

export function gradeTag(grade: string | null): string {
  if (!grade) return 'info'
  const map: Record<string, string> = {
    excellent: 'success',
    good: 'success',
    pass: 'warning',
    needs_improvement: 'danger',
  }
  return map[grade] || 'info'
}
