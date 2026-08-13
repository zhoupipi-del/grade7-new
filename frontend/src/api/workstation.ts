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

// ── Workspace Summary（工作台摘要，2026-08-13 班主任工作台 V1）──

export interface WorkspaceSummary {
  workspace: string
  scope: { type: string; id: number | null; name: string }
  cards: {
    student_count: number | null
    trusted_behavior_count: number | null
    trusted_praise_count: number | null
    open_tasks: unknown[] | null
  }
  attention: Array<{ type: string; level: string; title: string; hint: string }>
  data_quality: {
    behavior: string
    praise: string
    attendance: string
  }
}

/** GET /api/v1/me/workspace-summary — 当前工作台摘要（后端验权 + 组装 ViewModel） */
export function getWorkspaceSummary(params: {
  identity: string
  scope_type: string
  scope_id?: number | null
}) {
  return request.get<any, WorkspaceSummary>('/me/workspace-summary', { params })
}

