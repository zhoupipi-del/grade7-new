/**
 * classMgmt.ts — 班级管理 API 契约层
 *
 * 对应后端模块: modules/class_mgmt (MODULE_CODE="class_mgmt" -> URL前缀 /api/v1/class_mgmt)
 * 端点清单 (9):
 *   POST   /class_mgmt/classes                        — 创建班级
 *   GET    /class_mgmt/classes                        — 班级列表
 *   GET    /class_mgmt/classes/{id}                   — 班级详情
 *   PUT    /class_mgmt/classes/{id}                   — 更新班级
 *   POST   /class_mgmt/classes/{id}/assign-students   — 学生分班
 *   POST   /class_mgmt/classes/transfer-student       — 学生调班
 *   POST   /class_mgmt/classes/{id}/assign-teacher    — 分配班主任
 *   GET    /class_mgmt/classes/{id}/students          — 班级学生名单
 *   GET    /class_mgmt/stats                          — 班级统计
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

/** 班级创建请求 */
export interface ClassCreateRequest {
  name: string
  grade_id: number
  head_teacher_id?: number
  class_slogan?: string
}

/** 班级更新请求 */
export interface ClassUpdateRequest {
  name?: string
  head_teacher_id?: number
  is_active?: boolean
  class_slogan?: string
}

/** 班级信息 */
export interface ClassDetail {
  id: number
  name: string
  school_id: number
  grade_id: number
  head_teacher_id?: number
  head_teacher_name?: string
  student_count: number
  is_active: boolean
  class_slogan?: string
  class_features?: string[]
  created_at?: string
}

/** 学生分班请求 */
export interface AssignStudentsRequest {
  student_ids: number[]
}

/** 学生调班请求 */
export interface TransferStudentRequest {
  student_id: number
  target_class_id: number
  reason?: string
}

/** 班主任分配请求 */
export interface AssignTeacherRequest {
  head_teacher_id: number
}

/** 班级变更日志 */
export interface ClassChangeLog {
  id: number
  class_id: number
  change_type: string
  affected_students?: number[]
  from_class_id?: number
  to_class_id?: number
  operated_by: number
  operator_name?: string
  remark?: string
  created_at?: string
}

/** 班级统计 */
export interface ClassStats {
  total_classes: number
  total_students: number
  avg_class_size: number
  by_grade: Record<string, { classes: number; students: number }>
  largest_class?: { id: number; name: string; student_count: number }
  smallest_class?: { id: number; name: string; student_count: number }
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

/** 创建班级 */
export function createClass(body: ClassCreateRequest) {
  return request.post('/class_mgmt/classes', body)
}

/** 班级列表（按年级分组） */
export function listClasses(params?: {
  grade_id?: number
  page?: number
  page_size?: number
}) {
  return request.get('/class_mgmt/classes', { params })
}

/** 班级详情 */
export function getClassDetail(id: number) {
  return request.get(`/class_mgmt/classes/${id}`)
}

/** 更新班级 */
export function updateClass(id: number, body: ClassUpdateRequest) {
  return request.put(`/class_mgmt/classes/${id}`, body)
}

/** 学生分班 */
export function assignStudentsToClass(classId: number, body: AssignStudentsRequest) {
  return request.post(`/class_mgmt/classes/${classId}/assign-students`, body)
}

/** 学生调班 */
export function transferStudent(body: TransferStudentRequest) {
  return request.post('/class_mgmt/classes/transfer-student', body)
}

/** 分配班主任 */
export function assignHeadTeacher(classId: number, body: AssignTeacherRequest) {
  return request.post(`/class_mgmt/classes/${classId}/assign-teacher`, body)
}

/** 班级学生名单 */
export function getClassStudents(classId: number, params?: { page?: number; page_size?: number }) {
  return request.get(`/class_mgmt/classes/${classId}/students`, { params })
}

/** 班级统计 */
export function getClassStats() {
  return request.get('/class_mgmt/stats')
}
