/**
 * attendance.ts — 考勤管理 API 契约层
 *
 * 对应后端模块: modules/attendance (MODULE_CODE="attendance" -> URL前缀 /api/v1/attendance)
 * 端点清单 (15):
 *   POST /attendance/records/batch          — 批量录入考勤
 *   GET  /attendance/records/class/{id}      — 班级考勤查询
 *   GET  /attendance/records/student/{id}    — 学生考勤历史
 *   GET  /attendance/calendar/{id}           — 学生日历热力图
 *   GET  /attendance/stats                   — 年级考勤统计
 *   GET  /attendance/anomalies               — 异常预警
 *   GET  /attendance/dashboard               — 仪表盘聚合
 *   GET  /attendance/ranking                 — 班级横向排行
 *   GET  /attendance/overview                — 德育处全局视图 (ms_admin)
 *   GET  /attendance/export                  — 数据导出
 *   POST /attendance/leaves                  — 提交请假
 *   POST /attendance/leaves/approve           — 审批请假
 *   GET  /attendance/leaves                  — 请假列表
 *   POST /attendance/leaves/batch-approve     — 批量审批
 *   GET  /attendance/class/{id}/history     — 班级考勤历史聚合(大盘纵深)
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

export type AttendanceStatus = 'present' | 'absent' | 'late' | 'leave' | 'early_leave'

export const STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: '正常出勤',
  absent: '缺勤',
  late: '迟到',
  leave: '请假',
  early_leave: '早退',
}

export const STATUS_COLORS: Record<AttendanceStatus, string> = {
  present: '#67c23a',
  absent: '#f56c6c',
  late: '#e6a23c',
  leave: '#409eff',
  early_leave: '#909399',
}

export interface AttendanceRecord {
  student_id: number
  student_name: string
  class_name: string
  status: AttendanceStatus
  record_date: string
  note?: string
}

export interface DashboardData {
  summary: {
    total_students: number
    present: number
    absent: number
    late: number
    leave: number
    attendance_rate: number
  }
  trend: Array<{ date: string; present: number; absent: number; late: number; leave: number }>
  distribution: Array<{ status: string; count: number }>
}

export interface AnomalyAlert {
  student_id: number
  student_name: string
  class_name: string
  alert_type: 'consecutive_absent' | 'weekly_late' | 'monthly_absent'
  detail: string
  severity: 'warning' | 'danger'
}

export interface ClassRankingItem {
  class_id: number
  class_name: string
  total_students: number
  absent_count: number
  late_count: number
  attendance_rate: number
}

export interface LeaveRecord {
  id: number
  student_id: number
  student_name: string
  class_name: string
  start_date: string
  end_date: string
  reason: string
  status: 'pending' | 'class_approved' | 'grade_approved' | 'rejected'
  submitted_at: string
  approved_by?: string
}

/** 班级单日考勤聚合指标 — 大盘纵深数据 (对齐后端 ClassHistoryMetric) */
export interface ClassHistoryMetric {
  date: string            // YYYY-MM-DD
  total: number           // 总人数
  present: number         // 出勤
  late: number            // 迟到
  early: number           // 早退
  absent: number          // 缺勤(CRITICAL)
  leave: number           // 请假(INFO)
  attendance_rate: number // 出勤率%
}

/** 班级考勤历史聚合响应 (GET /attendance/history/{class_id}) */
export interface ClassHistoryResponse {
  class_id: number
  start_date: string
  end_date: string
  days: number
  history: ClassHistoryMetric[]
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

/** 仪表盘聚合数据 */
export function getDashboard(params: {
  period?: string
  start_date?: string
  end_date?: string
  grade_id?: number
  class_id?: number
}) {
  return request.get('/attendance/dashboard', { params })
}

/** 班级考勤查询 */
export function getClassAttendance(classId: number, params: {
  record_date?: string
  start_date?: string
  end_date?: string
}) {
  return request.get(`/attendance/records/class/${classId}`, { params })
}

/** 学生考勤历史 */
export function getStudentAttendance(studentId: number, days = 30) {
  return request.get(`/attendance/records/student/${studentId}`, { params: { days } })
}

/** 学生日历热力图 */
export function getStudentCalendar(studentId: number) {
  return request.get(`/attendance/calendar/${studentId}`)
}

/** 年级考勤统计 */
export function getStats(gradeId: number, startDate: string, endDate: string) {
  return request.get('/attendance/stats', { params: { grade_id: gradeId, start_date: startDate, end_date: endDate } })
}

/** 异常预警 */
export function getAnomalies(days = 7) {
  return request.get('/attendance/anomalies', { params: { days } })
}

/** 班级横向排行 */
export function getRanking(params: { record_date?: string; grade_id?: number }) {
  return request.get('/attendance/ranking', { params })
}

/** 德育处全局视图 (ms_admin) */
export function getOverview(startDate: string, endDate: string) {
  return request.get('/attendance/overview', { params: { start_date: startDate, end_date: endDate } })
}

/** 数据导出 */
export function exportAttendance(gradeId: number, startDate: string, endDate: string) {
  return request.get('/attendance/export', { params: { grade_id: gradeId, start_date: startDate, end_date: endDate } })
}

/** 批量录入考勤 */
export function batchRecord(body: {
  class_id: number
  grade_id?: number
  record_date: string
  records: Array<{ student_id: number; status: AttendanceStatus; note?: string }>
}) {
  return request.post('/attendance/records/batch', body)
}

/** 提交请假申请 */
export function submitLeave(body: {
  student_id: number
  class_id?: number
  grade_id?: number
  start_date: string
  end_date: string
  reason: string
}) {
  return request.post('/attendance/leaves', body)
}

/** 审批请假 */
export function approveLeave(body: { leave_id: number; action: 'approve' | 'reject'; comment?: string }) {
  return request.post('/attendance/leaves/approve', body)
}

/** 请假列表 */
export function listLeaves(params: {
  status?: string
  grade_id?: number
  class_id?: number
  student_id?: number
  limit?: number
  offset?: number
}) {
  return request.get('/attendance/leaves', { params })
}

/** 批量审批请假 */
export function batchApproveLeaves(body: { leave_ids: number[]; action: 'approve' | 'reject' }) {
  return request.post('/attendance/leaves/batch-approve', body)
}

/** 班级考勤历史聚合 — 大盘纵深数据 */
export function getClassAttendanceHistory(classId: number, startDate: string, endDate: string) {
  return request.get(`/attendance/class/${classId}/history`, { params: { start_date: startDate, end_date: endDate } })
}
