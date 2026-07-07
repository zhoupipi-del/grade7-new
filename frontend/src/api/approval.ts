import request from './request'

/**
 * Approval Center API
 *
 * Backend: /api/v1/approval/
 *
 * Supports multi-tenant dynamic chain_config workflows:
 * - GET  /tickets          -> ApprovalTicket[] (dynamic chain topology per tenant)
 * - POST /tickets/{id}/urge -> urge current pending node (DingTalk/WeCom push)
 *
 * Legacy CRUD endpoints (backward-compatible):
 * - GET  /requests          -> paginated approval requests
 * - GET  /requests/{id}     -> single request detail
 * - POST /requests/{id}/approve
 * - POST /requests/{id}/reject
 * - GET  /pending-count
 * - GET  /chains            -> tenant approval chain configs
 */

// ═════════════════════════════════════════════════════════════════
// Spec-defined Types (multi-tenant dynamic chain_config)
// ═════════════════════════════════════════════════════════════════

export interface ApprovalNode {
  node_id: string
  node_name: string
  assignee_role: string
  assignee_name: string | null
  status: 'approved' | 'pending' | 'waiting' | 'rejected'
  update_time: string | null
}

export interface ApprovalTicket {
  ticket_id: string
  title: string
  applicant_name: string
  tenant_school: string
  created_at: string
  deadline_at: string
  current_node_index: number
  chain_config: ApprovalNode[]
}

// ═════════════════════════════════════════════════════════════════
// New API: Dynamic Chain Workflow
// ═════════════════════════════════════════════════════════════════

export const getApprovalTickets = (type: 'todo' | 'done') => {
  return request.get<any, ApprovalTicket[]>('/approval/tickets', { params: { type } })
}

export const urgeTicketNode = (ticketId: string, nodeId: string) => {
  return request.post(`/approval/tickets/${ticketId}/urge`, { node_id: nodeId })
}

// ═════════════════════════════════════════════════════════════════
// Legacy API (backward-compatible)
// ═════════════════════════════════════════════════════════════════

export function getApprovalRequests(params?: {
  status?: string
  page?: number
  page_size?: number
}) {
  return request.get('/approval/requests', { params })
}

export function getApprovalDetail(id: number) {
  return request.get(`/approval/requests/${id}`)
}

export function approveRequest(id: number, data: {
  comment?: string
}) {
  return request.post(`/approval/requests/${id}/approve`, data)
}

export function rejectRequest(id: number, data: {
  comment: string
}) {
  return request.post(`/approval/requests/${id}/reject`, data)
}

export function getPendingCount() {
  return request.get('/approval/pending-count')
}

export function getApprovalChains() {
  return request.get('/approval/chains')
}

// ═════════════════════════════════════════════════════════════════
// Adapter: Real Backend -> Demo Fallback
// ═════════════════════════════════════════════════════════════════

/**
 * Fetch approval tickets with demo-data fallback.
 *
 * Strategy:
 * 1. Try real backend GET /approval/tickets
 * 2. If backend unavailable or returns empty, fall back to demo data
 *
 * @param type - 'todo' for pending, 'done' for completed
 */
export async function fetchTicketsWithFallback(type: 'todo' | 'done'): Promise<ApprovalTicket[]> {
  try {
    const tickets = await getApprovalTickets(type)
    if (tickets && tickets.length > 0) {
      return tickets
    }
  } catch {
    // Backend unavailable — fall through to demo
  }

  await sleep(300)
  return getDemoTickets(type)
}

// ═════════════════════════════════════════════════════════════════
// Demo Data (two tenants with completely different chain configs)
// ═════════════════════════════════════════════════════════════════

function getDemoTickets(type: 'todo' | 'done'): ApprovalTicket[] {
  const now = Date.now()
  const hoursFromNow = (h: number) => new Date(now + h * 3600_000).toISOString()
  const hoursAgo = (h: number) => new Date(now - h * 3600_000).toISOString()

  if (type === 'done') {
    return [
      {
        ticket_id: 'TKT-2026-0042',
        title: '陈博裕 严重警告处分申请',
        applicant_name: '张明远（班主任）',
        tenant_school: '一中本部',
        created_at: hoursAgo(72),
        deadline_at: hoursAgo(24),
        current_node_index: 2,
        chain_config: [
          {
            node_id: 'N1',
            node_name: '班主任初审',
            assignee_role: 'class_teacher',
            assignee_name: '张明远',
            status: 'approved',
            update_time: hoursAgo(70),
          },
          {
            node_id: 'N2',
            node_name: '年级组长复核',
            assignee_role: 'grade_leader',
            assignee_name: '李红',
            status: 'approved',
            update_time: hoursAgo(48),
          },
          {
            node_id: 'N3',
            node_name: '德育处主任终审',
            assignee_role: 'ms_admin',
            assignee_name: '王建国',
            status: 'approved',
            update_time: hoursAgo(24),
          },
        ],
      },
    ]
  }

  // type === 'todo' — two tickets with completely different chain configs
  return [
    // Ticket 1: 一中本部 — 3-node chain (班主任 -> 年级组长 -> 德育处主任)
    {
      ticket_id: 'TKT-2026-0078',
      title: '黎梓萱 留校察看处分申请',
      applicant_name: '张明远（班主任）',
      tenant_school: '一中本部',
      created_at: hoursAgo(30),
      deadline_at: hoursFromNow(18), // 18 hours remaining — urgent!
      current_node_index: 1,
      chain_config: [
        {
          node_id: 'N1',
          node_name: '班主任初审',
          assignee_role: 'class_teacher',
          assignee_name: '张明远',
          status: 'approved',
          update_time: hoursAgo(28),
        },
        {
          node_id: 'N2',
          node_name: '年级组长复核',
          assignee_role: 'grade_leader',
          assignee_name: '李红',
          status: 'pending',
          update_time: hoursAgo(6),
        },
        {
          node_id: 'N3',
          node_name: '德育处主任终审',
          assignee_role: 'ms_admin',
          assignee_name: null,
          status: 'waiting',
          update_time: null,
        },
      ],
    },
    // Ticket 2: 实验分校 — completely different 3-node chain
    {
      ticket_id: 'TKT-2026-0079',
      title: '周子轩 记过处分申请',
      applicant_name: '刘芳（级部统筹）',
      tenant_school: '实验分校',
      created_at: hoursAgo(10),
      deadline_at: hoursFromNow(38), // 38 hours remaining — normal
      current_node_index: 0,
      chain_config: [
        {
          node_id: 'M1',
          node_name: '级部统筹初审',
          assignee_role: 'grade_leader',
          assignee_name: '刘芳',
          status: 'pending',
          update_time: hoursAgo(2),
        },
        {
          node_id: 'M2',
          node_name: '政教处备案',
          assignee_role: 'ms_admin',
          assignee_name: null,
          status: 'waiting',
          update_time: null,
        },
        {
          node_id: 'M3',
          node_name: '分管校长特批',
          assignee_role: 'ms_admin',
          assignee_name: null,
          status: 'waiting',
          update_time: null,
        },
      ],
    },
  ]
}

// ─── Utility ──────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
