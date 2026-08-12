import request from './request'

export interface CopilotRunRequest {
  goal: string
  grade_id: number
  class_id?: number
  exam_id?: number
  compare_exam_ids?: number[]
}

export interface CopilotPlanStep {
  tool: string
  status: string
  reason: string
}

export interface CopilotRunResponse {
  status: string
  run_id: number
  goal: string
  plan: CopilotPlanStep[]
  overview: Record<string, any>
  findings: string[]
  recommendations: string[]
  domains?: Record<string, any>
  critic: { passed: boolean; issues: string[] }
  provider: string
  model: string
  trust: {
    permission_checked: boolean
    aggregate_before_provider: boolean
    student_pii_sent: boolean
    provenance_recorded: boolean
  }
  outcome: string
  outcome_reason: string | null
  student_count: number
  examined_count: number
  grade_record_count?: number
  domain_counts?: Record<string, number>
}

const TOOL_LABELS: Record<string, string> = {
  read_class_grade_summary: '读取成绩',
  compare_exam_performance: '比较考试',
  read_attendance_summary: '读取考勤',
  read_behavior_summary: '读取行为',
  read_risk_warning_summary: '读取风险',
}

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool
}

export const OUTCOME_LABELS: Record<string, string> = {
  success: '任务完成',
  needs_data: '需要更多数据',
  needs_input: '需要补充信息',
  denied: '权限不足',
  failed: '执行失败',
}

export const DOMAIN_ICONS: Record<string, string> = {
  grades: '📊',
  attendance: '📋',
  behavior: '⚖️',
  risk: '⚠️',
}

export const DOMAIN_NAMES: Record<string, string> = {
  grades: '学业',
  attendance: '考勤',
  behavior: '行为纪律',
  risk: '风险预警',
}

export const DOMAINS = ['grades', 'attendance', 'behavior', 'risk'] as const

export function runCopilot(data: CopilotRunRequest): Promise<CopilotRunResponse> {
  return request.post('/ai_teacher_assistant/agent/run', data)
}

export interface AvailableScopeGrade {
  id: number
  name: string
}

export interface AvailableScopesResponse {
  school: { id: number; name: string }
  grades: AvailableScopeGrade[]
  default_grade_id: number | null
}

export function getAvailableScopes(): Promise<AvailableScopesResponse> {
  return request.get("/ai_teacher_assistant/available-scopes")
}
