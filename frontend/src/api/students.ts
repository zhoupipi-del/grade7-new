/**
 * students.ts — 学籍管理 API 契约层
 *
 * 对应后端模块: modules/student_registry (MODULE_CODE="student_registry" -> URL前缀 /api/v1/student_registry)
 * 端点清单 (10 + 1 导入):
 *   POST   /student_registry/students              — 创建学籍
 *   GET    /student_registry/students              — 学籍列表（分页/筛选/搜索）
 *   GET    /student_registry/students/{id}         — 学籍详情
 *   PUT    /student_registry/students/{id}         — 更新学籍
 *   POST   /student_registry/students/{id}/transfer — 转学
 *   POST   /student_registry/students/{id}/suspend  — 休学
 *   POST   /student_registry/students/{id}/resume   — 复学
 *   POST   /student_registry/students/{id}/graduate — 毕业
 *   GET    /student_registry/students/{id}/status-history — 状态变更历史
 *   POST   /student_registry/students/batch-import — 批量导入
 *   GET    /student_registry/stats                 — 学籍统计
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

/** 学籍状态 */
export type RegistryStatus = 'active' | 'suspended' | 'transferred' | 'graduated' | 'inactive'

/** 状态变更类型 */
export type StatusChangeType = 'transfer' | 'suspend' | 'resume' | 'graduate' | 'inactive'

/** 数据来源标签 */
export type SyncStatus = 'native' | 'legacy' | 'imported'

/** 入学方式 */
export type EnrollmentType = 'normal' | 'transfer_in' | 'repeat' | 'other'

// ── 标签映射 ──

export const REGISTRY_STATUS_LABELS: Record<RegistryStatus, string> = {
  active: '在读',
  suspended: '休学',
  transferred: '已转学',
  graduated: '已毕业',
  inactive: '已离校',
}

export const REGISTRY_STATUS_COLORS: Record<RegistryStatus, string> = {
  active: '#67c23a',
  suspended: '#e6a23c',
  transferred: '#909399',
  graduated: '#409eff',
  inactive: '#f56c6c',
}

export const SYNC_STATUS_LABELS: Record<SyncStatus, string> = {
  native: '原生数据',
  legacy: '遗留系统',
  imported: '批量导入',
}

// ── 接口 ──

/** 学籍创建请求 */
export interface StudentCreateRequest {
  name: string
  gender?: 'M' | 'F'
  birth_date?: string
  id_card?: string
  nationality?: string
  class_id: number
  grade_id: number
  address?: string
  parent1_name?: string
  parent1_phone?: string
  parent1_relation?: string
  parent2_name?: string
  parent2_phone?: string
  parent2_relation?: string
  national_student_no?: string
  enrollment_type?: EnrollmentType
  enrolled_at?: string
  auto_generate_no?: boolean
}

/** 学籍更新请求 */
export interface StudentUpdateRequest {
  name?: string
  gender?: string
  birth_date?: string
  id_card?: string
  nationality?: string
  address?: string
  parent1_name?: string
  parent1_phone?: string
  parent1_relation?: string
  parent2_name?: string
  parent2_phone?: string
  parent2_relation?: string
  national_student_no?: string
}

/** 学籍完整信息 */
export interface StudentDetail {
  id: number
  name: string
  student_no: string
  school_id: number
  class_id: number
  grade_id: number
  gender?: 'M' | 'F'
  id_card?: string
  nationality?: string
  birth_date?: string
  address?: string
  parent1_name?: string
  parent1_phone?: string
  parent1_relation?: string
  parent2_name?: string
  parent2_phone?: string
  parent2_relation?: string
  is_active: boolean
  enrolled_at?: string
  tags?: string[]
  registry_status?: RegistryStatus
  national_student_no?: string
  enrollment_type?: EnrollmentType
  sync_status?: SyncStatus
  class_name?: string
  grade_name?: string
  created_at?: string
}

/** 学籍简要信息（列表用） */
export interface StudentBrief {
  id: number
  name: string
  student_no: string
  class_id: number
  class_name?: string
  registry_status?: RegistryStatus
}

/** 状态变更请求 */
export interface StatusChangeRequest {
  change_type: StatusChangeType
  reason?: string
  target_school?: string
  expected_resume_date?: string
  remark?: string
}

/** 状态变更记录 */
export interface StatusChangeRecord {
  id: number
  student_id: number
  from_status: string
  to_status: string
  change_type: string
  reason?: string
  target_school?: string
  expected_resume_date?: string
  operated_by: number
  operator_name?: string
  sync_status?: SyncStatus
  remark?: string
  created_at?: string
}

/** 批量导入结果 */
export interface BatchImportResult {
  total: number
  success: number
  failed: number
  errors: Array<{ row: number; message: string }>
  imported_ids: number[]
}

/** 学籍统计 */
export interface RegistryStats {
  total_students: number
  by_status: Record<string, number>
  by_grade: Record<string, number>
  by_gender: Record<string, number>
  sync_summary: Record<string, number>
}

/** 分页学籍列表 */
export interface PaginatedStudents {
  total: number
  page: number
  page_size: number
  items: StudentDetail[]
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

/** 创建学籍 */
export function createStudent(body: StudentCreateRequest) {
  return request.post('/student_registry/students', body)
}

/** 学籍列表（分页+筛选） */
export function listStudents(params: {
  page?: number
  page_size?: number
  class_id?: number
  grade_id?: number
  status?: string
  keyword?: string
}) {
  return request.get('/student_registry/students', { params })
}

/** 学籍详情 */
export function getStudent(id: number) {
  return request.get(`/student_registry/students/${id}`)
}

/** 更新学籍 */
export function updateStudent(id: number, body: StudentUpdateRequest) {
  return request.put(`/student_registry/students/${id}`, body)
}

/** 转学 */
export function transferStudent(id: number, body: StatusChangeRequest) {
  return request.post(`/student_registry/students/${id}/transfer`, body)
}

/** 休学 */
export function suspendStudent(id: number, body: StatusChangeRequest) {
  return request.post(`/student_registry/students/${id}/suspend`, body)
}

/** 复学 */
export function resumeStudent(id: number, body: StatusChangeRequest) {
  return request.post(`/student_registry/students/${id}/resume`, body)
}

/** 毕业 */
export function graduateStudent(id: number, body: StatusChangeRequest) {
  return request.post(`/student_registry/students/${id}/graduate`, body)
}

/** 状态变更历史 */
export function getStatusHistory(id: number) {
  return request.get(`/student_registry/students/${id}/status-history`)
}

/** 批量导入学籍 (Excel) */
export function batchImportStudents(formData: FormData) {
  return request.post('/student_registry/students/batch-import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 学籍统计 */
export function getRegistryStats() {
  return request.get('/student_registry/stats')
}
