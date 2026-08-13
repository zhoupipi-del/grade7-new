import request from './request'

/** GET /behavior/quick-register/students — 按角色可见范围返回可选学生（复用） */
export interface TaskStudentOption {
  id: number
  name: string
  student_no?: string
  class_id?: number
  class_name?: string
  grade_id?: number
}

/** 责任快照 */
export interface TaskResponsibility {
  owner_user_id: number | null
  owner_name_snapshot: string | null
  responsibility_role: string | null
  responsibility_scope_type: string | null
  responsibility_scope_id: number | null
  resolution_source: string | null
  resolution_confidence: string | null
  resolved_at: string | null
  assignment_id: number | null
  unresolved_reason: string | null
}

export interface TaskEvent {
  id: number
  event_type: string
  actor_user_id: number | null
  actor_name: string | null
  detail: Record<string, unknown> | null
  created_at: string | null
}

export interface TaskEvidence {
  id: number
  kind: string
  content: string | null
  file_path: string | null
  file_name: string | null
  created_by: number | null
  created_at: string | null
}

export interface TaskComment {
  id: number
  content: string
  created_by: number | null
  created_at: string | null
}

export interface TaskItem extends TaskResponsibility {
  id: number
  school_id: number
  task_type: string
  title: string
  description: string | null
  status: string
  priority: string
  due_at: string | null
  closure_status: string | null
  closed_at: string | null
  created_by: number
  created_at: string | null
  updated_at: string | null
  events: TaskEvent[]
  evidence: TaskEvidence[]
  comments: TaskComment[]
}

export interface TaskCreateBody {
  title: string
  description?: string
  priority?: string
  due_at?: string | null
  student_id?: number
  grade_id?: number
  subject?: string
}

export function getTaskStudents() {
  return request.get<any, TaskStudentOption[]>('/behavior/quick-register/students', { params: {} })
}

export function createTask(data: TaskCreateBody) {
  return request.post<any, TaskItem>('/tasks', data)
}

export function listTasks(params: { status?: string; limit?: number; offset?: number } = {}) {
  return request.get<any, { total: number; items: TaskItem[] }>('/tasks', { params })
}

export function getTask(id: number) {
  return request.get<any, TaskItem>(`/tasks/${id}`)
}

export function acceptTask(id: number) {
  return request.post<any, { id: number; status: string; message: string }>(`/tasks/${id}/accept`)
}

export function startTask(id: number) {
  return request.post<any, { id: number; status: string; message: string }>(`/tasks/${id}/start`)
}

export function completeTask(id: number, note?: string) {
  return request.post<any, { id: number; status: string; message: string }>(
    `/tasks/${id}/complete`,
    null,
    { params: note ? { note } : {} },
  )
}

export function rejectTask(id: number, note?: string) {
  return request.post<any, { id: number; status: string; message: string }>(
    `/tasks/${id}/reject`,
    null,
    { params: note ? { note } : {} },
  )
}

export function cancelTask(id: number, note?: string) {
  return request.post<any, { id: number; status: string; message: string }>(
    `/tasks/${id}/cancel`,
    null,
    { params: note ? { note } : {} },
  )
}

export function reassignTask(id: number, new_owner_user_id: number, reason?: string) {
  return request.post<any, TaskItem>(`/tasks/${id}/reassign`, { new_owner_user_id, reason })
}

export function addEvidence(id: number, body: { kind?: string; content?: string }) {
  return request.post<any, TaskItem>(`/tasks/${id}/evidence`, body)
}

export function addComment(id: number, content: string) {
  return request.post<any, TaskItem>(`/tasks/${id}/comments`, { content })
}
