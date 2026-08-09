/**
 * habitCards.ts — 萌卡系统 API 契约层 (Task #1400)
 *
 * 对应后端模块: modules/habit_cards (router_prefix: /api/v1/habit_cards)
 *
 * 端点:
 *   GET    /habit_cards/templates              — 全校卡牌模板
 *   POST   /habit_cards/issue                  — 教师发卡
 *   GET    /habit_cards/wallet/{id}            — 学生钱包
 *   POST   /habit_cards/blindbox/open          — 家长盲盒翻牌
 *   GET    /habit_cards/transactions/{id}      — 发卡流水
 *   GET    /habit_cards/parent/blindbox        — 家长 H5 盲盒 (自动绑定)
 *   GET    /habit_cards/parent/blindbox/history — 盲盒历史
 *   POST   /habit_cards/parent/blindbox/share   — 裂变分享标记
 */

import request from './request'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

export interface CardTemplate {
  id: number
  card_code: string
  card_name: string
  card_category: string
  card_rarity: string
  card_icon: string | null
  card_description: string | null
  reward_points: number
  is_active: boolean
  created_at: string | null
}

export interface CardTemplatesResponse {
  status: string
  cards: CardTemplate[]
}

export interface IssueCardsPayload {
  school_id: number
  teacher_id: number
  card_id: number
  student_ids: number[]
  note?: string
}

export interface IssueCardsResponse {
  status: string
  issued_count: number
}

export interface WalletItem {
  card_id: number
  card_name: string
  card_code: string
  card_icon: string | null
  card_rarity: string
  card_category: string
  quantity: number
  total_points: number
  first_earned_at: string | null
  last_earned_at: string | null
}

export interface WalletResponse {
  status: string
  student_id: number
  wallet: WalletItem[]
  ai_praise_letter: string
}

export interface BlindBoxOpenPayload {
  parent_user_id: number
  student_id: number
  school_id: number
}

export interface BlindBoxOpenResponse {
  status: string
  card_id: number
  card_name: string
  card_rarity: string
  card_icon: string | null
  is_first_open: boolean
  ai_praise_letter: string
}

/** 家长 H5 盲盒响应 (含学生信息) */
export interface ParentBlindboxResponse {
  status: string
  student_name: string
  card_id: number
  card_name: string
  card_rarity: string
  card_icon: string | null
  card_category: string | null
  is_first_open: boolean
  ai_praise_letter: string
  total_cards: number
  total_points: number
}

export interface BlindboxHistoryItem {
  id: number
  card_name: string
  card_rarity: string
  card_icon: string | null
  opened_at: string | null
  is_first_open: boolean
  shared_to: string | null
}

export interface BlindboxHistoryResponse {
  status: string
  student_id: number
  student_name: string
  history: BlindboxHistoryItem[]
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

const BASE = '/api/v1/habit_cards'

/** 获取卡牌模板库 */
export function getTemplates(schoolId: number) {
  return request.get<CardTemplatesResponse>(`${BASE}/templates`, { params: { school_id: schoolId } })
}

/** 教师批量发卡 */
export function issueCards(payload: IssueCardsPayload) {
  return request.post<IssueCardsResponse>(`${BASE}/issue`, payload)
}

/** 获取学生钱包 */
export function getWallet(studentId: number) {
  return request.get<WalletResponse>(`${BASE}/wallet/${studentId}`)
}

/** 获取学生发卡流水 */
export function getTransactions(studentId: number) {
  return request.get<any>(`${BASE}/transactions/${studentId}`)
}

// ── 家长 H5 盲盒 API (Task #1400) ──

/** 家长 H5 盲盒自动翻牌 — 无需传参, JWT 自动解析学生绑定 */
export function getParentBlindbox() {
  return request.get<ParentBlindboxResponse>(`${BASE}/parent/blindbox`)
}

/** 家长盲盒开启历史 */
export function getParentBlindboxHistory() {
  return request.get<BlindboxHistoryResponse>(`${BASE}/parent/blindbox/history`)
}

/** 家长分享标记 */
export function markShare(logId: number, sharedTo: string) {
  return request.post<any>(`${BASE}/parent/blindbox/share`, {
    log_id: logId,
    shared_to: sharedTo,
  })
}

// ═══════════════════════════════════════════════════
// 旧 API 别名 (兼容 ClassAvatarWall)
// ═══════════════════════════════════════════════════

/** @deprecated 使用 getTemplates */
export const getCardTemplates = getTemplates
/** @deprecated 使用 issueCards */
export const batchIssueCards = issueCards
/** @deprecated 使用 getWallet */
export const getStudentWallet = getWallet
/** @deprecated 使用 BlindBoxOpenResponse */
export type BlindBoxResponse = BlindBoxOpenResponse

/** 教师/管理员盲盒翻牌 (旧 API, ClassAvatarWall 使用) */
export function openBlindbox(payload: BlindBoxOpenPayload) {
  return request.post<BlindBoxOpenResponse>(`${BASE}/blindbox/open`, payload)
}
