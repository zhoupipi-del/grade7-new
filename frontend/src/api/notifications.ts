/**
 * notifications.ts — 通知中心 API 契约层
 *
 * 对应后端模块: modules/notifications (MODULE_CODE="notifications" → URL前缀 /api/v1/notifications)
 * 端点清单 (4):
 *   GET    /notifications/               — 通知列表（分页，支持 type/is_read 过滤）
 *   GET    /notifications/unread         — 未读计数（含 by_type 分组）
 *   PUT    /notifications/{id}/read      — 标记单条已读
 *   PUT    /notifications/read-all       — 全部已读（可选 type 过滤）
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义 (1:1 映射后端 Pydantic schemas)
// ═══════════════════════════════════════════════════

/** ── 通知条目 ─────────────────────────────── */

export interface NotificationItem {
  id: number
  type: string
  title: string
  body: string | null
  entity_type: string | null
  entity_id: number | null
  is_read: boolean
  read_at: string | null
  created_at: string
}

/** ── 通知分页列表 ─────────────────────────── */

export interface NotificationListResponse {
  items: NotificationItem[]
  total: number
  limit: number
  offset: number
}

/** ── 未读计数（含按类型分组） ───────────────── */

export interface UnreadCountResponse {
  unread_count: number
  /** 按类型分组的未读数，如 {"discipline_pending": 3, "rdi_alert": 1} */
  by_type: Record<string, number>
}

// ═══════════════════════════════════════════════════
// Raw API Functions (thin wrappers, 1:1 with backend routes)
// ═══════════════════════════════════════════════════

/**
 * GET /notifications/
 * 获取当前用户的通知分页列表
 * @param type   按类型过滤
 * @param isRead 按已读状态过滤
 * @param limit  每页条数 (1-100)
 * @param offset 偏移量
 */
export function listNotifications(params?: {
  type?: string
  is_read?: boolean
  limit?: number
  offset?: number
}) {
  return request.get<any, NotificationListResponse>('/notifications/', { params })
}

/**
 * GET /notifications/unread
 * 获取当前用户的未读通知计数（含 by_type 分组）
 */
export function getUnreadCount() {
  return request.get<any, UnreadCountResponse>('/notifications/unread')
}

/**
 * PUT /notifications/{id}/read
 * 标记指定通知为已读
 */
export function markAsRead(notificationId: number) {
  return request.put<any, { ok: boolean; notification_id: number }>(
    `/notifications/${notificationId}/read`,
  )
}

/**
 * PUT /notifications/read-all
 * 标记所有未读通知为已读
 * @param type 可选：只标记指定类型的通知
 */
export function markAllAsRead(type?: string) {
  return request.put<any, { ok: boolean; marked_count: number }>('/notifications/read-all', {
    type,
  })
}

// ═══════════════════════════════════════════════════
// 业务常量
// ═══════════════════════════════════════════════════

/** 通知类型 → 中文标签 + 图标 */
export const NOTIFICATION_TYPE_META: Record<string, { label: string; icon: string; color: string }> = {
  discipline_pending: { label: '处分待审批', icon: 'Clock', color: '#e6a23c' },
  discipline_activated: { label: '处分已生效', icon: 'WarningFilled', color: '#f56c6c' },
  discipline_appeal: { label: '申诉处理', icon: 'ChatLineSquare', color: '#909399' },
  discipline_revoked: { label: '处分已撤销', icon: 'CircleCheckFilled', color: '#67c23a' },
  approval_timeout: { label: '审批超时', icon: 'AlarmClock', color: '#f56c6c' },
  approval_assigned: { label: '待审批', icon: 'Checked', color: '#e6a23c' },
  ai_prescription: { label: 'AI 德育处方', icon: 'MagicStick', color: '#409eff' },
  rdi_alert: { label: 'RDI 风险预警', icon: 'Monitor', color: '#f56c6c' },
  recovery_available: { label: '回血可申请', icon: 'RefreshRight', color: '#67c23a' },
  score_change: { label: '评分变更', icon: 'Tickets', color: '#409eff' },
  growth_milestone: { label: '成长里程碑', icon: 'TrendCharts', color: '#67c23a' },
  system: { label: '系统通知', icon: 'Setting', color: '#909399' },
}

/** 默认未读数轮询间隔 (ms) */
export const UNREAD_POLL_INTERVAL = 30000

/** 通知类型过滤选项 */
export const NOTIFICATION_TYPE_OPTIONS = Object.entries(NOTIFICATION_TYPE_META).map(
  ([value, meta]) => ({
    value,
    label: meta.label,
    color: meta.color,
  }),
)

// ═══════════════════════════════════════════════════
// 显示辅助函数
// ═══════════════════════════════════════════════════

/** 通知类型 → 中文标签 */
export function notificationTypeLabel(type: string): string {
  return NOTIFICATION_TYPE_META[type]?.label || type
}

/** 通知类型 → 图标名 */
export function notificationTypeIcon(type: string): string {
  return NOTIFICATION_TYPE_META[type]?.icon || 'InfoFilled'
}

/** 通知类型 → 颜色 */
export function notificationTypeColor(type: string): string {
  return NOTIFICATION_TYPE_META[type]?.color || '#909399'
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

export function getDemoNotifications(): NotificationItem[] {
  const now = new Date()
  return [
    {
      id: 1,
      type: 'discipline_activated',
      title: '李梓涵 处分已生效',
      body: '七(2)班 李梓涵 "携带手机进校" 处分已通过审批并生效。处分等级：警告，期间：30天。',
      entity_type: 'discipline_sanction',
      entity_id: 42,
      is_read: false,
      read_at: null,
      created_at: new Date(now.getTime() - 2 * 60000).toISOString(),
    },
    {
      id: 2,
      type: 'approval_assigned',
      title: '新的违纪审批待处理',
      body: '七(3)班 王浩然 "课堂打闹" 需要您审批。建议处分等级：警告。',
      entity_type: 'discipline_record',
      entity_id: 156,
      is_read: false,
      read_at: null,
      created_at: new Date(now.getTime() - 15 * 60000).toISOString(),
    },
    {
      id: 3,
      type: 'rdi_alert',
      title: 'RDI 高风险预警：赵文博',
      body: '七(1)班 赵文博 综合风险指数 Z=2.8（行为维度偏离 +2.4σ，学业维度 -1.8σ），建议立即介入。',
      entity_type: 'student',
      entity_id: 105,
      is_read: false,
      read_at: null,
      created_at: new Date(now.getTime() - 45 * 60000).toISOString(),
    },
    {
      id: 4,
      type: 'ai_prescription',
      title: 'AI 处方已生成：张雨萱',
      body: '针对七(4)班 张雨萱 的学业下滑趋势，AI 已生成个性化干预方案，包含 3 项行动建议。点击查看详情。',
      entity_type: 'ai_prescription',
      entity_id: 23,
      is_read: true,
      read_at: new Date(now.getTime() - 60 * 60000).toISOString(),
      created_at: new Date(now.getTime() - 90 * 60000).toISOString(),
    },
    {
      id: 5,
      type: 'discipline_appeal',
      title: '家长提交申诉申请',
      body: '七(2)班 李梓涵 的家长对 "携带手机进校" 处分提出申诉。理由：家长出具书面说明，手机为紧急联系使用。',
      entity_type: 'discipline_sanction',
      entity_id: 42,
      is_read: true,
      read_at: new Date(now.getTime() - 3 * 3600000).toISOString(),
      created_at: new Date(now.getTime() - 4 * 3600000).toISOString(),
    },
    {
      id: 6,
      type: 'recovery_available',
      title: '回血机会提醒',
      body: '七(2)班 李梓涵 的处分已满 15 天，可申请行为回血（恢复部分评价分）。请在 3 天内提交申请。',
      entity_type: 'discipline_sanction',
      entity_id: 42,
      is_read: true,
      read_at: new Date(now.getTime() - 8 * 3600000).toISOString(),
      created_at: new Date(now.getTime() - 12 * 3600000).toISOString(),
    },
    {
      id: 7,
      type: 'score_change',
      title: '评价分数更新',
      body: '七(1)班 陈博裕 道德品质维度 +3 分（来源：志愿者活动），当前道德分：88。',
      entity_type: 'evaluation_score',
      entity_id: 1153,
      is_read: true,
      read_at: new Date(now.getTime() - 24 * 3600000).toISOString(),
      created_at: new Date(now.getTime() - 25 * 3600000).toISOString(),
    },
    {
      id: 8,
      type: 'growth_milestone',
      title: '陈博裕 达成成长里程碑',
      body: '七(1)班 陈博裕 "连续 30 天无违纪" 里程碑达成！综合评价总分 82.4。',
      entity_type: 'student',
      entity_id: 100,
      is_read: true,
      read_at: new Date(now.getTime() - 48 * 3600000).toISOString(),
      created_at: new Date(now.getTime() - 50 * 3600000).toISOString(),
    },
  ]
}

export function getDemoUnreadCount(): UnreadCountResponse {
  return {
    unread_count: 3,
    by_type: {
      discipline_activated: 1,
      approval_assigned: 1,
      rdi_alert: 1,
    },
  }
}
