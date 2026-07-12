/**
 * teacher_mgmt API 封装
 *
 * 端点:
 *   GET    /teachers                      — 教师列表
 *   GET    /teachers/{user_id}            — 教师详情
 *   PUT    /teachers/{user_id}/extension  — 更新扩展信息
 *   PUT    /teachers/{user_id}/subjects   — 分配任教学科
 *   GET    /teachers/{user_id}/workloads  — 查询工作量
 *   POST   /teachers/{user_id}/workloads  — 新增工作量
 *   GET    /teachers/{user_id}/workload-stats — 工作量统计
 */

import request from './request'

// ── 类型定义 ──

export interface TeacherListItem {
  id: number
  display_name: string
  username: string
  role: string
  phone?: string
  employee_no?: string
  subject?: string
  title?: string
  is_homeroom: boolean
  homeroom_class_id?: number
  homeroom_class_name?: string
  subjects_taught: string[]
  is_active: boolean
  created_at?: string
}

export interface TeacherListResponse {
  teachers: TeacherListItem[]
  total: number
  page: number
  page_size: number
}

export interface TeacherExtension {
  id: number
  user_id: number
  teacher_id?: number
  title?: string
  hired_at?: string
  office_phone?: string
  office_location?: string
  qualifications?: string[]
  education?: string
  major?: string
  graduate_school?: string
  is_head_teacher: boolean
  homeroom_grade?: string
  is_active: boolean
}

export interface SubjectAssignment {
  id?: number
  subject_code: string
  subject_name: string
  is_primary: boolean
  grade_level?: string
}

export interface TeacherDetail {
  user_id: number
  display_name: string
  username: string
  role: string
  phone?: string
  employee_no?: string
  subject?: string
  extension?: TeacherExtension
  subjects_taught: SubjectAssignment[]
  is_homeroom: boolean
  homeroom_class_id?: number
  homeroom_class_name?: string
  is_active: boolean
}

export interface WorkloadRecord {
  id: number
  teacher_user_id: number
  semester: string
  weekly_periods: number
  class_count: number
  subject_count: number
  is_head_teacher: boolean
  head_teacher_class_id?: number
  extra_duties?: string[]
  total_workload_score?: number
  notes?: string
  created_at: string
}

export interface WorkloadStats {
  teacher_user_id: number
  display_name: string
  total_semesters: number
  avg_weekly_periods: number
  avg_class_count: number
  total_subjects: number
  workloads: WorkloadRecord[]
}

// ── API 函数 ──

/** 教师列表 */
export function listTeachers(params?: {
  page?: number
  page_size?: number
  role?: string
  is_active?: boolean
  keyword?: string
}) {
  return request.get<TeacherListResponse>('/teacher_mgmt/teachers', { params })
}

/** 教师详情 */
export function getTeacherDetail(userId: number) {
  return request.get<TeacherDetail>(`/teacher_mgmt/teachers/${userId}`)
}

/** 更新教师扩展信息 */
export function upsertTeacherExtension(userId: number, data: {
  title?: string
  hired_at?: string
  office_phone?: string
  office_location?: string
  qualifications?: string[]
  education?: string
  major?: string
  graduate_school?: string
  is_active?: boolean
}) {
  return request.put<TeacherExtension>(`/teacher_mgmt/teachers/${userId}/extension`, data)
}

/** 分配任教学科 */
export function assignSubjects(userId: number, subjects: SubjectAssignment[]) {
  return request.put(`/teacher_mgmt/teachers/${userId}/subjects`, { subjects })
}

/** 查询教师工作量列表 */
export function listWorkloads(userId: number) {
  return request.get<WorkloadRecord[]>(`/teacher_mgmt/teachers/${userId}/workloads`)
}

/** 新增/更新工作量记录 */
export function addWorkload(userId: number, data: {
  semester: string
  weekly_periods: number
  class_count: number
  subject_count: number
  extra_duties?: string[]
}) {
  return request.post<WorkloadRecord>(`/teacher_mgmt/teachers/${userId}/workloads`, data)
}

/** 工作量统计汇总 */
export function getWorkloadStats(userId: number) {
  return request.get<WorkloadStats>(`/teacher_mgmt/teachers/${userId}/workload-stats`)
}
