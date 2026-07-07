/**
 * parent_portal.ts — 家长门户 API 契约层
 *
 * 对应后端模块: modules/parent_portal (MODULE_CODE="parent_portal" → URL前缀 /api/v1/parent_portal)
 * 端点清单 (7):
 *   GET    /parent_portal/dashboard              — 家长仪表盘（孩子概览+未读通知+待处理反馈+最近反馈）
 *   GET    /parent_portal/child/overview         — 孩子概览（五维分数+考勤+违纪+时间轴+风险）
 *   POST   /parent_portal/feedbacks              — 提交反馈（血缘追踪+自动通知班主任）
 *   GET    /parent_portal/feedbacks              — 反馈列表（家长看自己的，教师看全校的）
 *   GET    /parent_portal/feedbacks/{id}         — 反馈详情
 *   POST   /parent_portal/feedbacks/{id}/reply   — 处理反馈（双向闭环+通知家长）
 *   POST   /parent_portal/appeals/proxy          — 申诉代理（Facade路由到discipline/behavior）
 *
 * 设计原则:
 *   - 血缘追踪: 每条操作通过 source_context 记录来源上下文
 *   - 双向闭环: 反馈提交→通知班主任→处理→通知家长
 *   - 性能基准: 概览<0.5s / 反馈提交<0.3s / 申诉代理<0.5s
 *   - 三层隔离: L1数据层(school_id) / L2控制层(JWT) / L3执行层(快照拷贝)
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════

/** 反馈类型 */
export type FeedbackType = 'suggestion' | 'complaint' | 'praise' | 'consultation' | 'other'

/** 反馈状态 — 双向闭环状态机 */
export type FeedbackStatus = 'pending' | 'processing' | 'resolved' | 'closed'

/** 申诉目标模块 */
export type AppealTargetModule = 'discipline' | 'behavior'

/** ── 反馈条目 ─────────────────────────────── */

export interface FeedbackItem {
  id: number
  student_id: number
  parent_id: number
  parent_name: string | null
  feedback_type: FeedbackType
  feedback_type_label: string
  title: string
  content: string
  status: FeedbackStatus
  status_label: string
  handler_id: number | null
  handler_name: string | null
  handler_reply: string | null
  handled_at: string | null
  attachments: string[] | null
  source_context: Record<string, any> | null
  created_at: string
  updated_at: string | null
}

/** ── 反馈列表响应 ─────────────────────────── */

export interface FeedbackListResponse {
  items: FeedbackItem[]
  total: number
}

/** ── 孩子概览 — 跨模块聚合 ─────────────────── */

export interface ChildOverview {
  student_id: number
  student_name: string
  student_no: string
  class_name: string
  grade_name: string

  // 评价快照（五维分数）
  total_score: number | null
  moral_score: number | null
  academic_score: number | null
  health_score: number | null
  art_score: number | null
  social_score: number | null

  // 统计计数
  attendance_normal_count: number
  attendance_abnormal_count: number
  behavior_record_count: number
  positive_score_total: number

  // 最近时间轴事件
  recent_timeline: Array<{
    event_id: string
    event_type: string
    occurred_at: string
    title: string
    description: string | null
    severity: string
  }>

  // 风险状态
  risk_level: string | null
  risk_label: string | null
}

/** ── 家长仪表盘 — 首页聚合 ─────────────────── */

export interface ParentDashboard {
  child: ChildOverview
  unread_notifications: number
  pending_feedbacks: number
  recent_feedbacks: FeedbackItem[]
  _meta?: { elapsed_ms: number }
}

/** ── 申诉代理结果 ─────────────────────────── */

export interface AppealProxyResult {
  success: boolean
  target_module: AppealTargetModule
  target_appeal_id: number | null
  message: string
  source_context: Record<string, any> | null
  _meta?: { elapsed_ms: number }
}

// ═══════════════════════════════════════════════════
// 请求体类型
// ═══════════════════════════════════════════════════

export interface FeedbackCreatePayload {
  student_id: number
  feedback_type: FeedbackType
  title: string
  content: string
  attachments?: string[]
}

export interface FeedbackReplyPayload {
  status: FeedbackStatus
  reply: string
}

export interface AppealProxyPayload {
  target_module: AppealTargetModule
  target_record_id: number
  student_id: number
  applicant_name: string
  applicant_phone?: string
  reason: string
}

// ═══════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═══════════════════════════════════════════════════

/**
 * GET /parent_portal/dashboard
 * 家长仪表盘 — 聚合孩子概览 + 未读通知 + 待处理反馈 + 最近反馈
 * 仅 PARENT 角色可访问
 */
export function getDashboard() {
  return request.get<any, ParentDashboard>('/parent_portal/dashboard')
}

/**
 * GET /parent_portal/child/overview
 * 孩子概览 — 五维分数 + 考勤 + 违纪 + 时间轴 + 风险等级
 * 仅 PARENT 角色可访问
 */
export function getChildOverview() {
  return request.get<any, ChildOverview & { _meta?: { elapsed_ms: number } }>(
    '/parent_portal/child/overview',
  )
}

/**
 * POST /parent_portal/feedbacks
 * 家长提交反馈 — 血缘追踪 + 自动通知班主任
 * @param payload 反馈内容
 */
export function createFeedback(payload: FeedbackCreatePayload) {
  return request.post<any, FeedbackItem>('/parent_portal/feedbacks', payload)
}

/**
 * GET /parent_portal/feedbacks
 * 查询反馈列表
 * - 家长: 只看自己的反馈
 * - 班主任/年级组长/德育处: 看全校反馈
 * @param params 筛选+分页参数
 */
export function listFeedbacks(params?: {
  status?: FeedbackStatus
  feedback_type?: FeedbackType
  offset?: number
  limit?: number
}) {
  return request.get<any, FeedbackListResponse>('/parent_portal/feedbacks', { params })
}

/**
 * GET /parent_portal/feedbacks/{id}
 * 查看单条反馈详情
 */
export function getFeedback(feedbackId: number) {
  return request.get<any, FeedbackItem>(`/parent_portal/feedbacks/${feedbackId}`)
}

/**
 * POST /parent_portal/feedbacks/{id}/reply
 * 班主任/德育处处理反馈 — 双向闭环
 * 处理后自动通知家长
 * @param feedbackId 反馈ID
 * @param payload 处理状态+回复内容
 */
export function replyFeedback(feedbackId: number, payload: FeedbackReplyPayload) {
  return request.post<any, FeedbackItem>(
    `/parent_portal/feedbacks/${feedbackId}/reply`,
    payload,
  )
}

/**
 * POST /parent_portal/appeals/proxy
 * 申诉代理 — Facade模式路由到discipline/behavior已有模块
 * @param payload 申诉内容
 */
export function proxyAppeal(payload: AppealProxyPayload) {
  return request.post<any, AppealProxyResult>('/parent_portal/appeals/proxy', payload)
}

// ═══════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════

/** 反馈类型 → 中文标签 + 图标 + 颜色 */
export const FEEDBACK_TYPE_META: Record<
  FeedbackType,
  { label: string; icon: string; color: string }
> = {
  suggestion: { label: '建议', icon: 'ChatLineSquare', color: '#409eff' },
  complaint: { label: '投诉', icon: 'WarningFilled', color: '#f56c6c' },
  praise: { label: '表扬', icon: 'CircleCheckFilled', color: '#67c23a' },
  consultation: { label: '咨询', icon: 'QuestionFilled', color: '#e6a23c' },
  other: { label: '其他', icon: 'MoreFilled', color: '#909399' },
}

/** 反馈状态 → 中文标签 + el-tag type + 颜色 */
export const FEEDBACK_STATUS_META: Record<
  FeedbackStatus,
  { label: string; tagType: 'info' | 'warning' | 'success' | 'danger'; color: string }
> = {
  pending: { label: '待处理', tagType: 'warning', color: '#e6a23c' },
  processing: { label: '处理中', tagType: 'info', color: '#409eff' },
  resolved: { label: '已解决', tagType: 'success', color: '#67c23a' },
  closed: { label: '已关闭', tagType: 'danger', color: '#909399' },
}

/** 申诉目标模块 → 中文标签 + 描述 */
export const APPEAL_TARGET_META: Record<
  AppealTargetModule,
  { label: string; description: string }
> = {
  discipline: {
    label: '处分申诉',
    description: '对已生效的行政处分（警告/严重警告/记过等）提出申诉',
  },
  behavior: {
    label: '违纪申诉',
    description: '对违纪行为记录（课堂违纪/考勤违纪等）提出申诉',
  },
}

/** 反馈类型选项（用于下拉选择） */
export const FEEDBACK_TYPE_OPTIONS = Object.entries(FEEDBACK_TYPE_META).map(
  ([value, meta]) => ({ value: value as FeedbackType, label: meta.label }),
)

/** 反馈状态选项（用于筛选） */
export const FEEDBACK_STATUS_OPTIONS = Object.entries(FEEDBACK_STATUS_META).map(
  ([value, meta]) => ({ value: value as FeedbackStatus, label: meta.label }),
)

/** 申诉目标模块选项 */
export const APPEAL_TARGET_OPTIONS = Object.entries(APPEAL_TARGET_META).map(
  ([value, meta]) => ({ value: value as AppealTargetModule, label: meta.label }),
)

/** 五维分数维度元数据 */
export const SCORE_DIMENSIONS = [
  { key: 'moral_score', label: '道德品质', color: '#409eff', max: 100 },
  { key: 'academic_score', label: '学业水平', color: '#67c23a', max: 100 },
  { key: 'health_score', label: '身心健康', color: '#e6a23c', max: 100 },
  { key: 'art_score', label: '艺术素养', color: '#f56c6c', max: 100 },
  { key: 'social_score', label: '社会实践', color: '#8b5cf6', max: 100 },
] as const

// ═══════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════

/** 反馈类型 → 中文标签 */
export function feedbackTypeLabel(type: FeedbackType | string): string {
  return FEEDBACK_TYPE_META[type as FeedbackType]?.label || type
}

/** 反馈状态 → 中文标签 */
export function feedbackStatusLabel(status: FeedbackStatus | string): string {
  return FEEDBACK_STATUS_META[status as FeedbackStatus]?.label || status
}

/** 反馈状态 → el-tag type */
export function feedbackStatusTagType(
  status: FeedbackStatus | string,
): 'info' | 'warning' | 'success' | 'danger' {
  return FEEDBACK_STATUS_META[status as FeedbackStatus]?.tagType || 'info'
}

/** 相对时间格式化 */
export function formatRelativeTime(dateStr: string): string {
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diff = now - date

  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 60) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  if (days < 30) return `${Math.floor(days / 7)} 周前`
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// ═══════════════════════════════════════════════════
// Demo Data (后端不可用时降级)
// ═══════════════════════════════════════════════════

export function getDemoDashboard(): ParentDashboard {
  return {
    child: getDemoChildOverview(),
    unread_notifications: 3,
    pending_feedbacks: 1,
    recent_feedbacks: [
      {
        id: 101,
        student_id: 100,
        parent_id: 50,
        parent_name: '陈爸爸',
        feedback_type: 'consultation',
        feedback_type_label: '咨询',
        title: '关于孩子近期数学成绩下滑的咨询',
        content: '陈老师您好，最近发现孩子数学成绩有下滑趋势，想了解一下在校情况，是否需要额外辅导？',
        status: 'resolved',
        status_label: '已解决',
        handler_id: 10,
        handler_name: '陈老师',
        handler_reply: '家长您好，陈博裕近期数学确实有些波动，主要原因是几何模块基础不牢。已安排课后辅导，建议家中配合练习。',
        handled_at: new Date(Date.now() - 2 * 3600000).toISOString(),
        attachments: null,
        source_context: { channel: 'web', action: 'submit_feedback' },
        created_at: new Date(Date.now() - 24 * 3600000).toISOString(),
        updated_at: new Date(Date.now() - 2 * 3600000).toISOString(),
      },
    ],
  }
}

export function getDemoChildOverview(): ChildOverview {
  return {
    student_id: 100,
    student_name: '陈博裕',
    student_no: '2025001',
    class_name: '七(1)班',
    grade_name: '七年级',
    total_score: 82.4,
    moral_score: 85,
    academic_score: 78,
    health_score: 90,
    art_score: 75,
    social_score: 88,
    attendance_normal_count: 72,
    attendance_abnormal_count: 2,
    behavior_record_count: 1,
    positive_score_total: 12,
    recent_timeline: [
      {
        event_id: 'evaluation_1',
        event_type: 'evaluation',
        occurred_at: new Date(Date.now() - 3 * 86400000).toISOString(),
        title: '期末综合评价完成',
        description: '综合评价等级：B（良好），总分 82.4',
        severity: 'success',
      },
      {
        event_id: 'score_log_1',
        event_type: 'score_log',
        occurred_at: new Date(Date.now() - 7 * 86400000).toISOString(),
        title: '社会实践 +3 分',
        description: '志愿者活动积极参与',
        severity: 'success',
      },
      {
        event_id: 'behavior_1',
        event_type: 'behavior',
        occurred_at: new Date(Date.now() - 14 * 86400000).toISOString(),
        title: '行为提醒：课堂使用手机',
        description: '在数学课上使用手机被任课老师发现',
        severity: 'warning',
      },
    ],
    risk_level: 'moderate',
    risk_label: '需要关注',
  }
}

export function getDemoFeedbacks(): FeedbackItem[] {
  return [
    {
      id: 101,
      student_id: 100,
      parent_id: 50,
      parent_name: '陈爸爸',
      feedback_type: 'consultation',
      feedback_type_label: '咨询',
      title: '关于孩子近期数学成绩下滑的咨询',
      content: '陈老师您好，最近发现孩子数学成绩有下滑趋势，想了解一下在校情况，是否需要额外辅导？',
      status: 'resolved',
      status_label: '已解决',
      handler_id: 10,
      handler_name: '陈老师',
      handler_reply: '家长您好，陈博裕近期数学确实有些波动，主要原因是几何模块基础不牢。已安排课后辅导，建议家中配合练习。',
      handled_at: new Date(Date.now() - 2 * 3600000).toISOString(),
      attachments: null,
      source_context: { channel: 'web' },
      created_at: new Date(Date.now() - 24 * 3600000).toISOString(),
      updated_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    },
    {
      id: 102,
      student_id: 100,
      parent_id: 50,
      parent_name: '陈爸爸',
      feedback_type: 'praise',
      feedback_type_label: '表扬',
      title: '感谢班主任的悉心教导',
      content: '陈老师，感谢您这段时间对陈博裕的关心和辅导，孩子回家后学习态度有明显改善，谢谢您！',
      status: 'pending',
      status_label: '待处理',
      handler_id: null,
      handler_name: null,
      handler_reply: null,
      handled_at: null,
      attachments: null,
      source_context: { channel: 'web' },
      created_at: new Date(Date.now() - 6 * 3600000).toISOString(),
      updated_at: null,
    },
  ]
}
