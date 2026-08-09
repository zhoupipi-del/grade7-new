/**
 * Wings 3.0 Type Definitions
 */

export type UserRole = 'MS_ADMIN' | 'GRADE_LEADER' | 'CLASS_TEACHER' | 'PARENT' | 'STUDENT'

export interface UserInfo {
  id: number
  username: string
  real_name: string
  role: UserRole
  school_id: number
  school_name: string
  school_phase?: string
  plugin_config?: Record<string, any> | null
  class_id?: number
  class_name?: string
  grade_id?: number
  grade_name?: string
  avatar?: string
}

export interface LoginPayload {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

export interface PaginatedResponse<T = any> {
  items: T[]
  total: number
  page: number
  page_size: number
}
