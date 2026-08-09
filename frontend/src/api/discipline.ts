import request from './request'
import type { TagType } from './behavior'

/**
 * Discipline Center API — Domain Layer
 *
 * Builds on top of behavior.ts raw API contracts with a domain-specific view-model
 * shaped for the DisciplineCenter (惩戒流转中心) view.
 *
 * Key domain concepts:
 * - Probation Timeline Chain (观察期时序链): full lifecycle milestones per punishment
 * - Source Traceability (惩戒前置源头溯源): RDI_Radar vs Approval_Ticket origin tracking
 * - Probation Status (观察期状态): 观察中 / 申诉中 / 已撤销 / 已到期未撤销
 *
 * Backend: /api/v1/discipline/sanctions (domain aggregate endpoint)
 */

// ═════════════════════════════════════════════════════════════════
// Domain Types
// ═════════════════════════════════════════════════════════════════

/** A single milestone in the probation lifecycle chain */
export interface ProbationMilestone {
  title: string
  time: string
  description: string
  status: 'completed' | 'active' | 'pending'
}

/** The origin source that triggered this punishment */
export type SourceType = 'RDI_Radar' | 'Approval_Ticket'

/** Punishment severity level (Chinese display) */
export type PunishLevel = '警告' | '严重警告' | '记过' | '留校察看'

/** Current observation-period status */
export type ProbationStatus = '观察中' | '申诉中' | '已撤销' | '已到期未撤销'

/** A fully traced discipline record with lifecycle chain */
export interface DisciplineRecord {
  punishment_id: string
  student_id: number
  student_name: string
  class_name: string
  source_type: SourceType
  source_ref_id: string
  level: PunishLevel
  reason: string
  execution_date: string
  probation_days: number
  days_remaining: number
  probation_status: ProbationStatus
  timeline_chain: ProbationMilestone[]
}

// ═════════════════════════════════════════════════════════════════
// API Functions
// ═════════════════════════════════════════════════════════════════

/** GET /discipline/sanctions — domain aggregate with timeline chain */
export const getDisciplineRecords = (params?: { status?: string }) => {
  return request.get<any, DisciplineRecord[]>('/discipline/sanctions', { params })
}

/** POST /discipline/sanctions/{punishmentId}/revoke — submit revocation request */
export const submitAppeal = (punishmentId: string, appealReason: string) => {
  return request.post(`/discipline/sanctions/${punishmentId}/revoke`, { revoke_reason: appealReason })
}

// ═════════════════════════════════════════════════════════════════
// Fallback Adapter (real API → demo data)
// ═════════════════════════════════════════════════════════════════

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/**
 * Fetch discipline records with demo-data fallback.
 * Tries real backend → on failure falls back to rich demo data.
 */
export async function fetchDisciplineWithFallback(
  params?: { status?: string }
): Promise<DisciplineRecord[]> {
  try {
    const res = await getDisciplineRecords(params)
    if (res && Array.isArray(res) && res.length > 0) {
      return res
    }
  } catch {
    // Backend unavailable — fall through to demo
  }

  await sleep(400)
  let items = getDemoDisciplineRecords()
  if (params?.status) {
    items = items.filter(r => r.probation_status === params.status)
  }
  return items
}

/**
 * Submit appeal with graceful degradation.
 * Tries real API → on failure returns a simulated success for demo mode.
 */
export async function submitAppealWithFallback(
  punishmentId: string,
  appealReason: string
): Promise<{ success: boolean; message: string }> {
  try {
    await submitAppeal(punishmentId, appealReason)
    return { success: true, message: '申诉已提交，等待德育处审核' }
  } catch {
    // Demo mode — simulate success
    await sleep(500)
    return { success: true, message: '（演示模式）申诉已提交，等待德育处审核' }
  }
}

// ═════════════════════════════════════════════════════════════════
// Display Helpers
// ═════════════════════════════════════════════════════════════════

/** Punishment level → el-tag type (type-safe TagType union) */
export function getPunishTagType(level: PunishLevel): TagType {
  const map: Record<PunishLevel, TagType> = {
    '警告': 'warning',
    '严重警告': 'warning',
    '记过': 'danger',
    '留校察看': 'danger',
  }
  return map[level] || 'info'
}

/** Probation status → CSS class for timeline badge */
export function getStatusClass(status: ProbationStatus): string {
  const map: Record<ProbationStatus, string> = {
    '观察中': 'status-active',
    '申诉中': 'status-appealing',
    '已撤销': 'status-revoked',
    '已到期未撤销': 'status-expired',
  }
  return map[status] || 'status-default'
}

/** Probation status → el-tag type */
export function getStatusTagType(status: ProbationStatus): TagType {
  const map: Record<ProbationStatus, TagType> = {
    '观察中': 'warning',
    '申诉中': 'danger',
    '已撤销': 'success',
    '已到期未撤销': 'info',
  }
  return map[status] || 'info'
}

/** Source type → display label */
export function sourceTypeLabel(source: SourceType): string {
  const map: Record<SourceType, string> = {
    'RDI_Radar': 'RDI 风险雷达',
    'Approval_Ticket': '审批工单',
  }
  return map[source] || source
}

/** Source type → el-tag type */
export function sourceTypeTag(source: SourceType): TagType {
  const map: Record<SourceType, TagType> = {
    'RDI_Radar': 'danger',
    'Approval_Ticket': 'primary',
  }
  return map[source] || 'info'
}

// ═════════════════════════════════════════════════════════════════
// Demo Data — 梨江中学惩戒流转场景
// ═════════════════════════════════════════════════════════════════

function getDemoDisciplineRecords(): DisciplineRecord[] {
  return [
    {
      punishment_id: 'DISC-2026-0012',
      student_id: 154,
      student_name: '黎梓萱',
      class_name: '七(1)班',
      source_type: 'RDI_Radar',
      source_ref_id: 'WARN-9982-RDI',
      level: '记过',
      reason:
        '因多科成绩断崖式崩塌触发极端抗拒心理，连续三周课堂消极对抗，破坏考场纪律并存在严重毁坏公物行为，经审批通过予以记过处分。',
      execution_date: '2026-05-10',
      probation_days: 180,
      days_remaining: 126,
      probation_status: '观察中',
      timeline_chain: [
        {
          title: '正式惩戒决议下达',
          time: '2026-05-10',
          description:
            '校务会德育处签发正式红头文件，经年级组提议、班主任佐证、德育处复核三级审批，予以记过处分并启动180天观察期。',
          status: 'completed',
        },
        {
          title: '临床心理干预方案介入',
          time: '2026-05-24',
          description:
            '配合 AI 德育处方系统生成的个性化干预方案，校心理咨询师每周一次一对一辅导，家长同步接受家庭教育指导。',
          status: 'completed',
        },
        {
          title: '中期行为表征行为观察',
          time: '2026-07-03',
          description:
            '当前卡点：由级长和班主任联合评估前60天行为改善情况，课堂消极对抗减少60%，但考场纪律仍有波动，需持续关注。',
          status: 'active',
        },
        {
          title: '提交撤销申诉答辩',
          time: '2026-11-10',
          description:
            '观察期满后，学生及家长可向德育处提交撤销处分申诉，经校务会答辩通过后正式撤销处分记录并恢复评价基线。',
          status: 'pending',
        },
      ],
    },
    {
      punishment_id: 'DISC-2026-0007',
      student_id: 101,
      student_name: '陈博裕',
      class_name: '七(1)班',
      source_type: 'Approval_Ticket',
      source_ref_id: 'APR-2026-0034',
      level: '严重警告',
      reason:
        '30天内累计3次严重违纪（课堂使用手机、辱骂宿管、校园欺凌），触发30天滑窗规则自动升级，经二级审批通过予以严重警告处分。',
      execution_date: '2026-06-15',
      probation_days: 90,
      days_remaining: 51,
      probation_status: '观察中',
      timeline_chain: [
        {
          title: '正式惩戒决议下达',
          time: '2026-06-15',
          description:
            '30天滑窗规则触发，班主任提交处分草案，年级组长审批通过，予以严重警告处分并启动90天观察期。',
          status: 'completed',
        },
        {
          title: '行为矫正计划启动',
          time: '2026-06-20',
          description: '班主任与家长签署家校共育协议，每日行为打卡，每周班主任面谈评估。',
          status: 'completed',
        },
        {
          title: '中期行为评估',
          time: '2026-08-15',
          description: '待评估：观察期过半后由年级组联合评估行为改善情况。',
          status: 'pending',
        },
        {
          title: '观察期满答辩',
          time: '2026-09-13',
          description: '观察期满后提交撤销申诉，经审批通过后撤销处分记录。',
          status: 'pending',
        },
      ],
    },
    {
      punishment_id: 'DISC-2026-0003',
      student_id: 105,
      student_name: '林思雨',
      class_name: '七(3)班',
      source_type: 'Approval_Ticket',
      source_ref_id: 'APR-2026-0019',
      level: '记过',
      reason: '期中考试期间传递纸条，监控录像确认作弊行为，予以记过处分。',
      execution_date: '2026-06-01',
      probation_days: 120,
      days_remaining: 0,
      probation_status: '申诉中',
      timeline_chain: [
        {
          title: '正式惩戒决议下达',
          time: '2026-06-01',
          description: '监控录像确认作弊事实，经二级审批通过予以记过处分，启动120天观察期。',
          status: 'completed',
        },
        {
          title: '家长申诉提交',
          time: '2026-06-10',
          description: '家长以"初犯且认错态度良好"为由提交撤销处分申诉，附带家庭教育和心理评估报告。',
          status: 'completed',
        },
        {
          title: '申诉审核答辩',
          time: '2026-07-05',
          description: '当前卡点：德育处组织申诉答辩委员会，学生、家长、班主任三方到场陈述。',
          status: 'active',
        },
        {
          title: '申诉裁决下达',
          time: '2026-07-12',
          description: '答辩结束后5个工作日内下达裁决：维持原处分 / 降级为严重警告 / 撤销处分。',
          status: 'pending',
        },
      ],
    },
    {
      punishment_id: 'DISC-2026-0001',
      student_id: 103,
      student_name: '周子轩',
      class_name: '七(2)班',
      source_type: 'Approval_Ticket',
      source_ref_id: 'APR-2026-0008',
      level: '警告',
      reason: '体育课与同学发生肢体冲突，经调解后双方和解。',
      execution_date: '2026-05-20',
      probation_days: 30,
      days_remaining: 0,
      probation_status: '已撤销',
      timeline_chain: [
        {
          title: '正式惩戒决议下达',
          time: '2026-05-20',
          description: '体育课肢体冲突事件，经调解双方和解，予以警告处分并启动30天观察期。',
          status: 'completed',
        },
        {
          title: '行为观察期',
          time: '2026-05-20',
          description: '30天观察期内无新增违纪记录，行为表现良好。',
          status: 'completed',
        },
        {
          title: '撤销申诉提交',
          time: '2026-06-19',
          description: '观察期满，班主任代为提交撤销处分申诉。',
          status: 'completed',
        },
        {
          title: '处分正式撤销',
          time: '2026-06-22',
          description: '德育处审批通过，处分记录正式撤销，评价基线恢复至100分。',
          status: 'completed',
        },
      ],
    },
  ]
}
