import request from './request'

/**
 * Classes API
 * Maps to backend: /api/v1/classes/
 */

export function getClasses(params?: {
  grade_id?: number
  page?: number
  page_size?: number
}) {
  return request.get('/classes/', { params })
}

export function getClassDetail(classId: number) {
  return request.get(`/classes/${classId}`)
}

export function getClassStudents(classId: number, params?: {
  page?: number
  page_size?: number
}) {
  return request.get(`/classes/${classId}/students`, { params })
}

/** Fetch students across classes (lightweight list for selectors) */
export function getStudents(params?: {
  grade_id?: number
  page?: number
  page_size?: number
}) {
  return request.get('/students/', { params })
}
