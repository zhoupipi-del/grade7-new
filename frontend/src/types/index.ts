/**
 * Wings 3.0 Type Definitions
 */

// ═════════════════════════════════════════════════════════════════
// RBAC Role Model (W3-FE-RBAC-A)
// ═════════════════════════════════════════════════════════════════

export type UserRole =
  | 'MS_ADMIN'
  | 'GROUP_ADMIN'
  | 'BRANCH_ADMIN'
  | 'GRADE_LEADER'
  | 'CLASS_TEACHER'
  | 'TEACHER'
  | 'COUNSELOR'
  | 'PARENT'
  | 'STUDENT'

/** Valid role set for explicit validation — no unchecked `as UserRole` */
export const VALID_USER_ROLES: ReadonlySet<string> = new Set([
  'MS_ADMIN',
  'GROUP_ADMIN',
  'BRANCH_ADMIN',
  'GRADE_LEADER',
  'CLASS_TEACHER',
  'TEACHER',
  'COUNSELOR',
  'PARENT',
  'STUDENT',
])

/** Chinese display labels for all 9 roles */
export const ROLE_LABELS: Record<UserRole, string> = {
  MS_ADMIN: '德育处管理员',
  GROUP_ADMIN: '集团管理员',
  BRANCH_ADMIN: '片区管理员',
  GRADE_LEADER: '年级组长',
  CLASS_TEACHER: '班主任',
  TEACHER: '任课教师',
  COUNSELOR: '心理教师',
  PARENT: '家长',
  STUDENT: '学生',
}

/**
 * Safe role parsing result — fail closed, never throw.
 *
 * ok=true  → valid UserRole, safe to use in RBAC logic
 * ok=false → unknown role, must NOT be cast to UserRole;
 *            clear session, log security event, show "role not configured" page
 */
export type ParseRoleResult =
  | { ok: true; role: UserRole }
  | { ok: false; rawRole: string }

/**
 * Parse and validate a raw role string into a UserRole.
 *
 * - Normalizes to uppercase
 * - Checks against VALID_USER_ROLES
 * - Returns safe result, never throws
 * - Unknown roles → { ok: false, rawRole } — caller must handle
 */
export function parseUserRole(rawRole: string): ParseRoleResult {
  if (typeof rawRole !== 'string') return { ok: false, rawRole: String(rawRole) }
  const normalized = rawRole.trim().toUpperCase()
  if (VALID_USER_ROLES.has(normalized)) {
    return { ok: true, role: normalized as UserRole }
  }
  return { ok: false, rawRole }
}

// ═════════════════════════════════════════════════════════════════
// User Info & Auth
// ═════════════════════════════════════════════════════════════════

export interface UserInfo {
  id: number
  username: string
  real_name: string
  role: UserRole | null  // null = unknown/invalid role, fail-closed
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
