/**
 * timetable API 封装
 *
 * 端点:
 *   GET    /classrooms                     — 教室列表
 *   POST   /classrooms                     — 新增教室
 *   GET    /courses                        — 课程列表
 *   POST   /courses                        — 新增课程
 *   GET    /slots                          — 课节列表
 *   POST   /slots                          — 新增课节 (含冲突检测)
 *   DELETE /slots/{id}                     — 删除课节
 *   POST   /slots/check-conflict           — 单独检测冲突
 *   GET    /weekly/{class_id}              — 班级周课表
 *   GET    /weekly/teacher/{teacher_id}    — 教师周课表
 *   GET    /conflicts                      — 冲突列表
 *   PUT    /conflicts/{id}/resolve         — 解决冲突
 */

import request from './request'

// ── 类型定义 ──

export interface Classroom {
  id: number
  name: string
  code?: string
  building?: string
  floor?: number
  capacity: number
  room_type: string
  is_active: boolean
}

export interface Course {
  id: number
  name: string
  subject_code: string
  grade_id: number
  periods_per_week: number
  is_exam_subject: boolean
  sort_order: number
  is_active: boolean
}

export interface CourseSlot {
  id: number
  class_id: number
  course_id: number
  course_name: string
  teacher_user_id: number
  teacher_name: string
  classroom_id?: number
  classroom_name: string
  day_of_week: number
  period_start: number
  period_end: number
  week_pattern: string
  start_week?: number
  end_week?: number
  semester: string
  is_active: boolean
}

export interface WeeklySlot {
  id: number
  course_name: string
  subject_code: string
  teacher_name: string
  classroom_name: string
  period_start: number
  period_end: number
  week_pattern: string
}

export interface WeeklySchedule {
  class_id: number
  class_name: string
  grade_name: string
  semester: string
  schedule: Record<string, WeeklySlot[]>
}

export interface TeacherWeeklySlot {
  id: number
  class_name: string
  course_name: string
  classroom_name: string
  period_start: number
  period_end: number
}

export interface TeacherWeeklySchedule {
  teacher_user_id: number
  teacher_name: string
  semester: string
  schedule: Record<string, TeacherWeeklySlot[]>
}

export interface ConflictDetail {
  conflict_type: string
  severity: string
  entity_a?: Record<string, any>
  entity_b?: Record<string, any>
  conflict_detail: string
}

export interface ConflictCheckResult {
  has_conflicts: boolean
  conflict_count: number
  conflicts: ConflictDetail[]
}

export interface ConflictRecord {
  id: number
  conflict_type: string
  severity: string
  entity_a?: any
  entity_b?: any
  conflict_detail?: string
  resolution: string
  created_at: string
}

// ── 教室 ──

export function listClassrooms(roomType?: string) {
  return request.get<Classroom[]>('/timetable/classrooms', { params: { room_type: roomType } })
}

export function createClassroom(data: {
  name: string; code?: string; building?: string; floor?: number
  capacity: number; room_type: string
}) {
  return request.post<Classroom>('/timetable/classrooms', data)
}

// ── 课程 ──

export function listCourses(gradeId?: number) {
  return request.get<Course[]>('/timetable/courses', { params: { grade_id: gradeId } })
}

export function createCourse(data: {
  name: string; subject_code: string; grade_id: number
  periods_per_week: number; is_exam_subject?: boolean; sort_order?: number
}) {
  return request.post<Course>('/timetable/courses', data)
}

// ── 课节 ──

export function listSlots(params?: { class_id?: number; teacher_user_id?: number; semester?: string }) {
  return request.get<CourseSlot[]>('/timetable/slots', { params })
}

export function createSlot(data: {
  class_id: number; course_id: number; teacher_user_id: number
  classroom_id?: number; day_of_week: number
  period_start: number; period_end: number
  week_pattern?: string; start_week?: number; end_week?: number; semester: string
}, autoResolve?: boolean) {
  return request.post('/timetable/slots', data, { params: { auto_resolve: autoResolve || false } })
}

export function deleteSlot(slotId: number) {
  return request.delete(`/timetable/slots/${slotId}`)
}

export function checkConflict(data: {
  class_id: number; course_id: number; teacher_user_id: number
  classroom_id?: number; day_of_week: number
  period_start: number; period_end: number; semester: string
}) {
  return request.post<ConflictCheckResult>('/timetable/slots/check-conflict', data)
}

// ── 周课表 ──

export function getClassWeeklySchedule(classId: number, semester: string) {
  return request.get<WeeklySchedule>(`/timetable/weekly/${classId}`, { params: { semester } })
}

export function getTeacherWeeklySchedule(teacherId: number, semester: string) {
  return request.get<TeacherWeeklySchedule>(`/timetable/weekly/teacher/${teacherId}`, { params: { semester } })
}

// ── 冲突管理 ──

export function listConflicts(params?: { resolution?: string; page?: number; page_size?: number }) {
  return request.get('/timetable/conflicts', { params })
}

export function resolveConflict(conflictId: number, resolution: string) {
  return request.put(`/timetable/conflicts/${conflictId}/resolve`, null, { params: { resolution } })
}
