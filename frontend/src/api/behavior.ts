import request from './request'

/**
 * Behavior & Discipline Center API
 *
 * Dual-module architecture:
 * - Behavior module:  /api/v1/behavior/*  (daily violation records + appeals)
 * - Discipline module: /api/v1/discipline/* (formal sanctions + state machine + drafts + escalation)
 *
 * Backend modules:
 * - behavior: 11 endpoints (records CRUD, stats, escalation check, appeals)
 * - discipline: 19 endpoints (sanctions CRUD + approve/reject/revoke, drafts, escalation trigger, appeals webhook)
 */

// ═════════════════════════════════════════════════════════════════
// Shared Types
// ═════════════════════════════════════════════════════════════════

/** el-tag type union — prevents TS2322 when binding to el-tag :type */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** Paginated response shape (raw dict from backend, not Pydantic response_model) */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

// ═════════════════════════════════════════════════════════════════
// Behavior Module Types (/api/v1/behavior/*)
// ═════════════════════════════════════════════════════════════════

export type BehaviorType = 'warning' | 'minor' | 'major' | 'serious'
export type BehaviorStatus = 'pending' | 'resolved' | 'appealed'

export interface BehaviorRecord {
  id: number
  student_id: number
  student_name: string
  class_id: number
  class_name: string
  grade_id: number
  type: BehaviorType
  description: string
  incident_date: string
  location: string | null
  points: number
  status: BehaviorStatus
  recorded_by: string
  created_at: string
  resolved_at: string | null
}

export interface BehaviorStats {
  total: number
  pending: number
  resolved: number
  by_type: Record<string, number>
  by_category: Record<string, number>
  by_class: Array<{ class_name: string; count: number }>
  monthly_trend: Array<{ month: string; count: number }>
}

export interface BehaviorAppeal {
  id: number
  record_id: number
  student_id: number
  student_name: string
  class_name: string
  reason: string
  status: AppealStatus
  submitted_at: string
  reviewed_at: string | null
  reviewed_by: string | null
  review_comment: string | null
}

// ═════════════════════════════════════════════════════════════════
// Discipline Module Types (/api/v1/discipline/*)
// ═════════════════════════════════════════════════════════════════

export type DisciplineLevel = 'WARNING' | 'SERIOUS_WARN' | 'DEMERIT' | 'PROBATION' | 'EXPULSION'
export type DisciplineStatus =
  | 'DRAFT_PENDING'
  | 'PENDING'
  | 'GRADE_LEADER_APPROVED'
  | 'ACTIVE'
  | 'REJECTED'
  | 'REVOKED'
export type AppealStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface Sanction {
  id: number
  student_id: number
  student_name: string
  class_id: number
  class_name: string
  grade_id: number
  level: DisciplineLevel
  reason: string
  description: string
  points: number
  status: DisciplineStatus
  submitted_by: string
  approved_by: string | null
  start_date: string
  end_date: string | null
  created_at: string
  approved_at: string | null
}

export interface SanctionStats {
  total: number
  active_count: number
  veto_count: number
  by_level: Record<string, number>
  by_status: Record<string, number>
  by_class: Array<{ class_name: string; count: number }>
}

export interface DraftEvidence {
  behavior_id: number
  incident_date: string
  description: string
  location: string | null
  points: number
}

export interface SanctionDraft {
  id: number
  student_id: number
  student_name: string
  class_id: number
  class_name: string
  level: DisciplineLevel
  evidence: DraftEvidence[]
  total_points: number
  window_start: string
  window_end: string
  status: 'DRAFT_PENDING' | 'SUBMITTED'
  created_at: string
}

export interface DisciplineAppeal {
  id: number
  sanction_id: number
  student_id: number
  student_name: string
  class_name: string
  reason: string
  status: AppealStatus
  submitted_at: string
  reviewed_at: string | null
  reviewed_by: string | null
  review_comment: string | null
}

export interface EscalationCheck {
  student_id: number
  student_name: string
  class_name: string
  serious_count_30d: number
  threshold: number
  should_escalate: boolean
  window_start: string
  window_end: string
  recent_violations: BehaviorRecord[]
}

// ═════════════════════════════════════════════════════════════════
// Behavior API Functions (/api/v1/behavior/*)
// ═════════════════════════════════════════════════════════════════

/** GET /behavior/records — paginated violation records */
export function getBehaviorRecords(params?: {
  class_id?: number
  grade_id?: number
  student_id?: number
  type?: BehaviorType
  status?: BehaviorStatus
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}) {
  return request.get<any, PaginatedResponse<BehaviorRecord>>('/behavior/records', { params })
}

/** GET /behavior/stats — aggregated statistics */
export function getBehaviorStats(params?: {
  class_id?: number
  grade_id?: number
  start_date?: string
  end_date?: string
}) {
  return request.get<any, BehaviorStats>('/behavior/stats', { params })
}

/** POST /behavior/records — create a violation record */
export function createBehaviorRecord(data: {
  student_id: number
  type: BehaviorType
  description: string
  incident_date: string
  location?: string
  points: number
}) {
  return request.post('/behavior/records', data)
}

/** POST /behavior/records/{id}/resolve — mark violation as resolved */
export function resolveBehaviorRecord(id: number) {
  return request.post(`/behavior/records/${id}/resolve`)
}

/** GET /behavior/escalation/{student_id} — check escalation eligibility */
export function checkBehaviorEscalation(studentId: number) {
  return request.get<any, EscalationCheck>(`/behavior/escalation/${studentId}`)
}

/** GET /behavior/appeals — list behavior appeals */
export function getBehaviorAppeals(params?: {
  status?: AppealStatus
  page?: number
  page_size?: number
}) {
  return request.get<any, PaginatedResponse<BehaviorAppeal>>('/behavior/appeals', { params })
}

/** POST /behavior/appeals — submit a behavior appeal */
export function submitBehaviorAppeal(data: {
  record_id: number
  reason: string
}) {
  return request.post('/behavior/appeals', data)
}

/** POST /behavior/appeals/{id}/review — review a behavior appeal */
export function reviewBehaviorAppeal(id: number, data: {
  status: AppealStatus
  review_comment: string
}) {
  return request.post(`/behavior/appeals/${id}/review`, data)
}

// ═════════════════════════════════════════════════════════════════
// Discipline API Functions (/api/v1/discipline/*)
// ═════════════════════════════════════════════════════════════════

/** GET /discipline/sanctions — paginated sanctions list */
export function getSanctions(params?: {
  class_id?: number
  grade_id?: number
  student_id?: number
  level?: DisciplineLevel
  status?: DisciplineStatus
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}) {
  return request.get<any, PaginatedResponse<Sanction>>('/discipline/sanctions', { params })
}

/** GET /discipline/stats — sanction statistics */
export function getSanctionStats(params?: {
  class_id?: number
  grade_id?: number
}) {
  return request.get<any, SanctionStats>('/discipline/stats', { params })
}

/** POST /discipline/sanctions — create a sanction (starts as PENDING) */
export function createSanction(data: {
  student_id: number
  level: DisciplineLevel
  reason: string
  description?: string
  points: number
  start_date: string
  end_date?: string
}) {
  return request.post('/discipline/sanctions', data)
}

/** POST /discipline/sanctions/{id}/approve — approve (grade_leader or ms_admin) */
export function approveSanction(id: number, data?: { comment?: string }) {
  return request.post(`/discipline/sanctions/${id}/approve`, data)
}

/** POST /discipline/sanctions/{id}/reject — reject a pending sanction */
export function rejectSanction(id: number, data: { comment: string }) {
  return request.post(`/discipline/sanctions/${id}/reject`, data)
}

/** POST /discipline/sanctions/{id}/revoke — revoke an active sanction */
export function revokeSanction(id: number, data: { comment: string }) {
  return request.post(`/discipline/sanctions/${id}/revoke`, data)
}

/** GET /discipline/drafts — list draft sanctions (30-day window evidence) */
export function getSanctionDrafts(params?: {
  class_id?: number
  status?: 'DRAFT_PENDING' | 'SUBMITTED'
  page?: number
  page_size?: number
}) {
  return request.get<any, PaginatedResponse<SanctionDraft>>('/discipline/drafts', { params })
}

/** POST /discipline/drafts/{id}/submit — submit a draft as a formal sanction */
export function submitDraft(id: number) {
  return request.post(`/discipline/drafts/${id}/submit`)
}

/** GET /discipline/escalation/{student_id} — check escalation status */
export function checkDisciplineEscalation(studentId: number) {
  return request.get<any, EscalationCheck>(`/discipline/escalation/${studentId}`)
}

/** POST /discipline/escalation/{student_id} — manually trigger escalation */
export function triggerDisciplineEscalation(studentId: number) {
  return request.post(`/discipline/escalation/${studentId}`)
}

/** GET /discipline/escalation-trigger/{student_id} — 30-day sliding window auto-check */
export function checkSlidingWindow(studentId: number) {
  return request.get<any, EscalationCheck>(`/discipline/escalation-trigger/${studentId}`)
}

/** GET /discipline/appeals — list discipline appeals */
export function getDisciplineAppeals(params?: {
  status?: AppealStatus
  page?: number
  page_size?: number
}) {
  return request.get<any, PaginatedResponse<DisciplineAppeal>>('/discipline/appeals', { params })
}

/** POST /discipline/appeals — webhook: create appeal from external system */
export function createDisciplineAppeal(data: {
  sanction_id: number
  student_id: number
  reason: string
}) {
  return request.post('/discipline/appeals', data)
}

/** POST /discipline/appeals/{id}/review — review a discipline appeal */
export function reviewDisciplineAppeal(id: number, data: {
  status: AppealStatus
  review_comment: string
}) {
  return request.post(`/discipline/appeals/${id}/review`, data)
}

// ═════════════════════════════════════════════════════════════════
// Adapter: Real Backend → Demo Fallback
// ═════════════════════════════════════════════════════════════════

/**
 * Fetch behavior records with demo-data fallback.
 *
 * Strategy:
 * 1. Try real backend GET /behavior/records
 * 2. If backend unavailable or returns empty, fall back to demo data
 */
export async function fetchBehaviorWithFallback(params?: {
  type?: BehaviorType
  status?: BehaviorStatus
}): Promise<{ items: BehaviorRecord[]; total: number }> {
  try {
    const result = await getBehaviorRecords({ page: 1, page_size: 50, ...params })
    return result
  } catch (error) {
    if (
      import.meta.env.DEV &&
      import.meta.env.VITE_ALLOW_DEMO_FALLBACK === 'true'
    ) {
      await sleep(300)
      let items = getDemoBehaviorRecords()
      if (params?.type) items = items.filter(r => r.type === params.type)
      if (params?.status) items = items.filter(r => r.status === params.status)
      return { items, total: items.length }
    }
    throw error
  }
}

/**
 * Fetch sanctions with demo-data fallback.
 */
export async function fetchSanctionsWithFallback(params?: {
  level?: DisciplineLevel
  status?: DisciplineStatus
}): Promise<{ items: Sanction[]; total: number }> {
  try {
    const result = await getSanctions({ page: 1, page_size: 50, ...params })
    return result
  } catch (error) {
    if (
      import.meta.env.DEV &&
      import.meta.env.VITE_ALLOW_DEMO_FALLBACK === 'true'
    ) {
      await sleep(300)
      let items = getDemoSanctions()
      if (params?.level) items = items.filter(s => s.level === params.level)
      if (params?.status) items = items.filter(s => s.status === params.status)
      return { items, total: items.length }
    }
    throw error
  }
}

/**
 * Fetch sanction drafts with demo-data fallback.
 */
export async function fetchDraftsWithFallback(): Promise<{ items: SanctionDraft[]; total: number }> {
  try {
    const result = await getSanctionDrafts({ page: 1, page_size: 50 })
    return result
  } catch (error) {
    if (
      import.meta.env.DEV &&
      import.meta.env.VITE_ALLOW_DEMO_FALLBACK === 'true'
    ) {
      await sleep(300)
      const items = getDemoDrafts()
      return { items, total: items.length }
    }
    throw error
  }
}

/**
 * Fetch appeals with demo-data fallback (unified behavior + discipline).
 */
export async function fetchAppealsWithFallback(): Promise<{
  behavior: BehaviorAppeal[]
  discipline: DisciplineAppeal[]
}> {
  try {
    const [dRes, bRes] = await Promise.all([
      getDisciplineAppeals({ page: 1, page_size: 50 }),
      getBehaviorAppeals({ page: 1, page_size: 50 }),
    ])
    return {
      discipline: dRes?.items ?? [],
      behavior: bRes?.items ?? [],
    }
  } catch (error) {
    if (
      import.meta.env.DEV &&
      import.meta.env.VITE_ALLOW_DEMO_FALLBACK === 'true'
    ) {
      await sleep(300)
      return {
        behavior: getDemoBehaviorAppeals(),
        discipline: getDemoDisciplineAppeals(),
      }
    }
    throw error
  }
}

// ═════════════════════════════════════════════════════════════════
// Demo Data — 梨江中学德育场景
// ═════════════════════════════════════════════════════════════════

const STUDENTS = [
  { id: 101, name: '陈博裕', class_id: 2501, class_name: '七(1)班', grade_id: 7 },
  { id: 102, name: '黎梓萱', class_id: 2501, class_name: '七(1)班', grade_id: 7 },
  { id: 103, name: '周子轩', class_id: 2502, class_name: '七(2)班', grade_id: 7 },
  { id: 104, name: '王浩然', class_id: 2502, class_name: '七(2)班', grade_id: 7 },
  { id: 105, name: '林思雨', class_id: 2503, class_name: '七(3)班', grade_id: 7 },
  { id: 106, name: '赵嘉乐', class_id: 2503, class_name: '七(3)班', grade_id: 7 },
  { id: 107, name: '刘梓涵', class_id: 2504, class_name: '七(4)班', grade_id: 7 },
  { id: 108, name: '黄子墨', class_id: 2504, class_name: '七(4)班', grade_id: 7 },
]

const TEACHERS = ['张明远', '李红', '王建国', '刘芳', '陈晓燕']

function daysAgo(d: number): string {
  const date = new Date()
  date.setDate(date.getDate() - d)
  return date.toISOString()
}

function getDemoBehaviorRecords(): BehaviorRecord[] {
  return [
    {
      id: 1, student_id: 101, student_name: '陈博裕', class_id: 2501, class_name: '七(1)班', grade_id: 7,
      type: 'serious', description: '课堂使用手机被没收，且拒不配合老师管理',
      incident_date: daysAgo(3), location: '教学楼三楼', points: -5,
      status: 'pending', recorded_by: '张明远', created_at: daysAgo(3), resolved_at: null,
    },
    {
      id: 2, student_id: 102, student_name: '黎梓萱', class_id: 2501, class_name: '七(1)班', grade_id: 7,
      type: 'minor', description: '课间追逐打闹，撞倒走廊展板',
      incident_date: daysAgo(5), location: '二楼走廊', points: -2,
      status: 'resolved', recorded_by: '张明远', created_at: daysAgo(5), resolved_at: daysAgo(4),
    },
    {
      id: 3, student_id: 103, student_name: '周子轩', class_id: 2502, class_name: '七(2)班', grade_id: 7,
      type: 'major', description: '体育课与同学发生肢体冲突',
      incident_date: daysAgo(7), location: '操场', points: -3,
      status: 'resolved', recorded_by: '李红', created_at: daysAgo(7), resolved_at: daysAgo(5),
    },
    {
      id: 4, student_id: 104, student_name: '王浩然', class_id: 2502, class_name: '七(2)班', grade_id: 7,
      type: 'warning', description: '早自习迟到三次',
      incident_date: daysAgo(10), location: '教室', points: -1,
      status: 'resolved', recorded_by: '李红', created_at: daysAgo(10), resolved_at: daysAgo(9),
    },
    {
      id: 5, student_id: 105, student_name: '林思雨', class_id: 2503, class_name: '七(3)班', grade_id: 7,
      type: 'serious', description: '考试期间传递纸条（作弊未遂）',
      incident_date: daysAgo(12), location: '考场', points: -5,
      status: 'appealed', recorded_by: '王建国', created_at: daysAgo(12), resolved_at: null,
    },
    {
      id: 6, student_id: 106, student_name: '赵嘉乐', class_id: 2503, class_name: '七(3)班', grade_id: 7,
      type: 'minor', description: '未穿校服入校',
      incident_date: daysAgo(15), location: '校门口', points: -2,
      status: 'resolved', recorded_by: '王建国', created_at: daysAgo(15), resolved_at: daysAgo(14),
    },
    {
      id: 7, student_id: 107, student_name: '刘梓涵', class_id: 2504, class_name: '七(4)班', grade_id: 7,
      type: 'major', description: '午休期间外出购买零食，翻墙被巡查发现',
      incident_date: daysAgo(18), location: '围墙', points: -3,
      status: 'resolved', recorded_by: '刘芳', created_at: daysAgo(18), resolved_at: daysAgo(16),
    },
    {
      id: 8, student_id: 108, student_name: '黄子墨', class_id: 2504, class_name: '七(4)班', grade_id: 7,
      type: 'warning', description: '上课频繁交头接耳，影响课堂秩序',
      incident_date: daysAgo(20), location: '教室', points: -1,
      status: 'resolved', recorded_by: '刘芳', created_at: daysAgo(20), resolved_at: daysAgo(19),
    },
    {
      id: 9, student_id: 101, student_name: '陈博裕', class_id: 2501, class_name: '七(1)班', grade_id: 7,
      type: 'serious', description: '与宿管发生言语冲突，辱骂管理人员',
      incident_date: daysAgo(22), location: '宿舍楼', points: -5,
      status: 'resolved', recorded_by: '张明远', created_at: daysAgo(22), resolved_at: daysAgo(20),
    },
    {
      id: 10, student_id: 101, student_name: '陈博裕', class_id: 2501, class_name: '七(1)班', grade_id: 7,
      type: 'serious', description: '校园欺凌——对低年级学生进行言语威胁',
      incident_date: daysAgo(25), location: '教学楼后', points: -5,
      status: 'resolved', recorded_by: '张明远', created_at: daysAgo(25), resolved_at: daysAgo(23),
    },
  ]
}

function getDemoSanctions(): Sanction[] {
  return [
    {
      id: 1, student_id: 101, student_name: '陈博裕', class_id: 2501, class_name: '七(1)班', grade_id: 7,
      level: 'SERIOUS_WARN', reason: '30天内3次严重违纪（手机+辱骂+欺凌），触发升级评估',
      description: '根据30天滑动窗口规则，该生累计3次serious违纪，自动生成处分草案并经班主任提交。',
      points: -10, status: 'PENDING',
      submitted_by: '张明远', approved_by: null,
      start_date: daysAgo(2), end_date: null,
      created_at: daysAgo(2), approved_at: null,
    },
    {
      id: 2, student_id: 102, student_name: '黎梓萱', class_id: 2501, class_name: '七(1)班', grade_id: 7,
      level: 'WARNING', reason: '课间打闹损坏公共财物',
      description: '黎梓萱课间追逐打闹撞倒走廊展板，经班主任批评教育后态度端正，给予警告处分。',
      points: -5, status: 'ACTIVE',
      submitted_by: '张明远', approved_by: '李红',
      start_date: daysAgo(4), end_date: daysAgo(4 + 30),
      created_at: daysAgo(5), approved_at: daysAgo(4),
    },
    {
      id: 3, student_id: 105, student_name: '林思雨', class_id: 2503, class_name: '七(3)班', grade_id: 7,
      level: 'DEMERIT', reason: '考试作弊（传递纸条）',
      description: '期中考试期间传递纸条，监控录像确认作弊行为。该生已提交申诉，申诉审核中。',
      points: -20, status: 'ACTIVE',
      submitted_by: '王建国', approved_by: '陈晓燕',
      start_date: daysAgo(11), end_date: daysAgo(11 + 60),
      created_at: daysAgo(12), approved_at: daysAgo(11),
    },
    {
      id: 4, student_id: 103, student_name: '周子轩', class_id: 2502, class_name: '七(2)班', grade_id: 7,
      level: 'WARNING', reason: '体育课肢体冲突',
      description: '体育课与同学发生推搡，经调解后双方和解，给予警告处分。',
      points: -5, status: 'GRADE_LEADER_APPROVED',
      submitted_by: '李红', approved_by: '李红',
      start_date: daysAgo(6), end_date: daysAgo(6 + 30),
      created_at: daysAgo(7), approved_at: daysAgo(6),
    },
    {
      id: 5, student_id: 107, student_name: '刘梓涵', class_id: 2504, class_name: '七(4)班', grade_id: 7,
      level: 'SERIOUS_WARN', reason: '翻墙外出，严重违反校规',
      description: '午休期间翻越围墙外出购买零食，被巡查教师当场发现。性质恶劣，给予严重警告。',
      points: -10, status: 'REVOKED',
      submitted_by: '刘芳', approved_by: '王建国',
      start_date: daysAgo(17), end_date: null,
      created_at: daysAgo(18), approved_at: daysAgo(17),
    },
    {
      id: 6, student_id: 108, student_name: '黄子墨', class_id: 2504, class_name: '七(4)班', grade_id: 7,
      level: 'WARNING', reason: '屡次扰乱课堂秩序',
      description: '多次上课交头接耳影响教学，班主任多次提醒无效，提交处分申请。',
      points: -5, status: 'REJECTED',
      submitted_by: '刘芳', approved_by: '王建国',
      start_date: daysAgo(19), end_date: null,
      created_at: daysAgo(20), approved_at: daysAgo(19),
    },
  ]
}

function getDemoDrafts(): SanctionDraft[] {
  return [
    {
      id: 1, student_id: 101, student_name: '陈博裕', class_id: 2501, class_name: '七(1)班',
      level: 'SERIOUS_WARN',
      evidence: [
        {
          behavior_id: 9, incident_date: daysAgo(22), description: '与宿管发生言语冲突，辱骂管理人员',
          location: '宿舍楼', points: -5,
        },
        {
          behavior_id: 10, incident_date: daysAgo(25), description: '校园欺凌——对低年级学生进行言语威胁',
          location: '教学楼后', points: -5,
        },
        {
          behavior_id: 1, incident_date: daysAgo(3), description: '课堂使用手机被没收，且拒不配合老师管理',
          location: '教学楼三楼', points: -5,
        },
      ],
      total_points: -15,
      window_start: daysAgo(30), window_end: daysAgo(0),
      status: 'DRAFT_PENDING', created_at: daysAgo(2),
    },
    {
      id: 2, student_id: 105, student_name: '林思雨', class_id: 2503, class_name: '七(3)班',
      level: 'DEMERIT',
      evidence: [
        {
          behavior_id: 5, incident_date: daysAgo(12), description: '考试期间传递纸条（作弊未遂）',
          location: '考场', points: -5,
        },
        {
          behavior_id: 99, incident_date: daysAgo(8), description: '上次月考提前交卷并携带试卷离场',
          location: '考场', points: -5,
        },
        {
          behavior_id: 100, incident_date: daysAgo(5), description: '晚自习期间被发现在课桌内藏有小抄',
          location: '教室', points: -5,
        },
      ],
      total_points: -15,
      window_start: daysAgo(30), window_end: daysAgo(0),
      status: 'DRAFT_PENDING', created_at: daysAgo(1),
    },
  ]
}

function getDemoBehaviorAppeals(): BehaviorAppeal[] {
  return [
    {
      id: 1, record_id: 5, student_id: 105, student_name: '林思雨', class_name: '七(3)班',
      reason: '纸条系同学主动传递，本人并未主动索取，且考试开始后即将纸条归还。请求从轻处理。',
      status: 'PENDING', submitted_at: daysAgo(11), reviewed_at: null,
      reviewed_by: null, review_comment: null,
    },
  ]
}

function getDemoDisciplineAppeals(): DisciplineAppeal[] {
  return [
    {
      id: 1, sanction_id: 3, student_id: 105, student_name: '林思雨', class_name: '七(3)班',
      reason: '记过处分过重，该生为初犯且认错态度良好，家长已配合学校进行家庭教育。请求降级为严重警告。',
      status: 'PENDING', submitted_at: daysAgo(10), reviewed_at: null,
      reviewed_by: null, review_comment: null,
    },
  ]
}

// ═════════════════════════════════════════════════════════════════
// Display Helpers (el-tag mapping)
// ═════════════════════════════════════════════════════════════════

/** Behavior type → Chinese label */
export function behaviorTypeLabel(type: BehaviorType): string {
  const map: Record<BehaviorType, string> = {
    warning: '提醒',
    minor: '轻微',
    major: '一般',
    serious: '严重',
  }
  return map[type] || type
}

/** Behavior type → el-tag type */
export function behaviorTypeTag(type: BehaviorType): TagType {
  const map: Record<BehaviorType, TagType> = {
    warning: 'info',
    minor: 'warning',
    major: 'warning',
    serious: 'danger',
  }
  return map[type] || 'info'
}

/** Behavior status → Chinese label */
export function behaviorStatusLabel(status: BehaviorStatus): string {
  const map: Record<BehaviorStatus, string> = {
    pending: '待处理',
    resolved: '已处理',
    appealed: '申诉中',
  }
  return map[status] || status
}

/** Behavior status → el-tag type */
export function behaviorStatusTag(status: BehaviorStatus): TagType {
  const map: Record<BehaviorStatus, TagType> = {
    pending: 'danger',
    resolved: 'success',
    appealed: 'warning',
  }
  return map[status] || 'info'
}

/** Discipline level → Chinese label */
export function disciplineLevelLabel(level: DisciplineLevel): string {
  const map: Record<DisciplineLevel, string> = {
    WARNING: '警告',
    SERIOUS_WARN: '严重警告',
    DEMERIT: '记过',
    PROBATION: '留校察看',
    EXPULSION: '开除学籍',
  }
  return map[level] || level
}

/** Discipline level → el-tag type */
export function disciplineLevelTag(level: DisciplineLevel): TagType {
  const map: Record<DisciplineLevel, TagType> = {
    WARNING: 'warning',
    SERIOUS_WARN: 'warning',
    DEMERIT: 'danger',
    PROBATION: 'danger',
    EXPULSION: 'danger',
  }
  return map[level] || 'info'
}

/** Discipline status → Chinese label */
export function disciplineStatusLabel(status: DisciplineStatus): string {
  const map: Record<DisciplineStatus, string> = {
    DRAFT_PENDING: '草案待审',
    PENDING: '待审批',
    GRADE_LEADER_APPROVED: '年级已批',
    ACTIVE: '生效中',
    REJECTED: '已驳回',
    REVOKED: '已撤销',
  }
  return map[status] || status
}

/** Discipline status → el-tag type */
export function disciplineStatusTag(status: DisciplineStatus): TagType {
  const map: Record<DisciplineStatus, TagType> = {
    DRAFT_PENDING: 'info',
    PENDING: 'warning',
    GRADE_LEADER_APPROVED: 'primary',
    ACTIVE: 'danger',
    REJECTED: 'info',
    REVOKED: 'success',
  }
  return map[status] || 'info'
}

/** Appeal status → Chinese label */
export function appealStatusLabel(status: AppealStatus): string {
  const map: Record<AppealStatus, string> = {
    PENDING: '待审核',
    APPROVED: '已通过',
    REJECTED: '已驳回',
  }
  return map[status] || status
}

/** Appeal status → el-tag type */
export function appealStatusTag(status: AppealStatus): TagType {
  const map: Record<AppealStatus, TagType> = {
    PENDING: 'warning',
    APPROVED: 'success',
    REJECTED: 'info',
  }
  return map[status] || 'info'
}

/** Discipline level → points (扣分值) */
export function disciplineLevelPoints(level: DisciplineLevel): number {
  const map: Record<DisciplineLevel, number> = {
    WARNING: -5,
    SERIOUS_WARN: -10,
    DEMERIT: -20,
    PROBATION: -50,
    EXPULSION: -100,
  }
  return map[level] || 0
}

// ─── Utility ──────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
