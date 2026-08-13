/**
 * workstation.ts — 工作台身份 API（周主任 2026-08-13：不同的人看到不同的 WINGS）
 *
 * GET /api/v1/me/workstations
 * 返回当前用户工作身份列表（teacher_role_assignments 优先，users.role fallback）。
 */

import request from '@/api/request'

export interface Workstation {
  identity: string
  label: string
  scope_type: string
  scope_id: number | null
  scope_name: string
  title: string
  is_default: boolean
}

export interface WorkstationsResponse {
  workstations: Workstation[]
  default_identity: string | null
}

/** GET /api/v1/me/workstations — 当前用户工作身份列表 */
export function getWorkstations() {
  return request.get<any, WorkstationsResponse>('/me/workstations')
}
