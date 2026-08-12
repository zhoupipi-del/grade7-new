/**
 * AI Copilot API client — Agent V1
 *
 * POST /api/v1/ai_teacher_assistant/agent/run
 */

import request from './request'

export interface CopilotRunRequest {
  goal: string
  grade_id: number
  class_id?: number
  exam_id?: number
  compare_exam_ids?: number[]
}

export interface CopilotStepView {
  tool: string
  status: string
  reason: string
}

export interface CopilotCriticView {
  passed: boolean
  issues: string[]
}

export interface CopilotRunResponse {
  status: string
  run_id: number
  goal: string
  plan: CopilotStepView[]
  overview: Record<string, any>
  findings: string[]
  recommendations: string[]
  critic: CopilotCriticView
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
}

export function runCopilot(data: CopilotRunRequest): Promise<CopilotRunResponse> {
  return request.post<any, CopilotRunResponse>(
    '/ai_teacher_assistant/agent/run',
    data
  )
}
