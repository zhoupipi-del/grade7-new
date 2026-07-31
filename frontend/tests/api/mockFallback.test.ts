/**
 * W3-FE-DATA-TRUTH-001 — Batch A 验收测试
 *
 * 目标：验证 3 个 API 文件的 7 个 WithFallback 函数，生产环境绝不静默回退 demo：
 *  1. 后端成功返回空数组 → 原样返回空数组（真实"无记录"）
 *  2. 后端成功返回非空数据 → 原样返回真实数据
 *  3. 后端 4xx/5xx/网络失败 → 生产环境抛错
 *  4. 仅 DEV 且 VITE_ALLOW_DEMO_FALLBACK=true 时允许 demo
 *  5. 写操作失败 → 不得返回 success=true（demo 须带 demo:true 标记）
 *
 * 通过 mock `./request`（axios 实例）统一控制真实 API 行为。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import request from '@/api/request'
import { fetchDisciplineWithFallback, submitAppealWithFallback } from '@/api/discipline'
import {
  fetchBehaviorWithFallback,
  fetchSanctionsWithFallback,
  fetchDraftsWithFallback,
  fetchAppealsWithFallback,
} from '@/api/behavior'
import { fetchTicketsWithFallback } from '@/api/approval'

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

const mockRequest = request as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

const DEMO_OFF = 'false'
const DEMO_ON = 'true'

beforeEach(() => {
  mockRequest.get.mockReset()
  mockRequest.post.mockReset()
  // 默认模拟生产：禁止 demo 回退
  vi.stubEnv('VITE_ALLOW_DEMO_FALLBACK', DEMO_OFF)
})

afterEach(() => {
  vi.unstubAllEnvs()
})

// ── 读取类：空数组必须原样返回，绝不落入 demo ──────────────────────
describe('真实空态（后端 200 + []）', () => {
  it('discipline: 200+[] → 返回空数组，非 demo', async () => {
    mockRequest.get.mockResolvedValue([])
    const res = await fetchDisciplineWithFallback()
    expect(res).toEqual([])
  })

  it('behavior: 200+{items:[],total:0} → 返回真实空态', async () => {
    mockRequest.get.mockResolvedValue({ items: [], total: 0 })
    const res = await fetchBehaviorWithFallback()
    expect(res).toEqual({ items: [], total: 0 })
  })

  it('sanctions: 200+{items:[],total:0} → 返回真实空态', async () => {
    mockRequest.get.mockResolvedValue({ items: [], total: 0 })
    const res = await fetchSanctionsWithFallback()
    expect(res).toEqual({ items: [], total: 0 })
  })

  it('drafts: 200+{items:[],total:0} → 返回真实空态', async () => {
    mockRequest.get.mockResolvedValue({ items: [], total: 0 })
    const res = await fetchDraftsWithFallback()
    expect(res).toEqual({ items: [], total: 0 })
  })

  it('appeals: 两个 API 均返回空 → 真实空对象', async () => {
    mockRequest.get.mockResolvedValue({ items: [], total: 0 })
    const res = await fetchAppealsWithFallback()
    expect(res).toEqual({ behavior: [], discipline: [] })
  })

  it('approval tickets: 200+[] → 返回空数组', async () => {
    mockRequest.get.mockResolvedValue([])
    const res = await fetchTicketsWithFallback('todo')
    expect(res).toEqual([])
  })
})

// ── 读取类：非空数据原样返回 ──────────────────────────────────────
describe('真实非空数据（后端 200 + 数据）', () => {
  it('discipline: 返回真实记录数组', async () => {
    mockRequest.get.mockResolvedValue([{ punishment_id: 'p1', probation_status: '观察中' }])
    const res = await fetchDisciplineWithFallback()
    expect(res).toHaveLength(1)
    expect(res[0].probation_status).toBe('观察中')
  })

  it('behavior: 返回真实 {items,total}', async () => {
    mockRequest.get.mockResolvedValue({ items: [{ id: 9 }], total: 1 })
    const res = await fetchBehaviorWithFallback()
    expect(res.items).toHaveLength(1)
  })
})

// ── 读取类：失败必须抛错（生产禁 demo） ─────────────────────────────
describe('失败处理（生产环境必须抛错）', () => {
  const FAILURE = new Error('Network Error')

  it('discipline: 网络失败 → 抛错', async () => {
    mockRequest.get.mockRejectedValue(FAILURE)
    await expect(fetchDisciplineWithFallback()).rejects.toThrow()
  })

  it('behavior: 500 → 抛错', async () => {
    mockRequest.get.mockRejectedValue(new Error('500'))
    await expect(fetchBehaviorWithFallback()).rejects.toThrow()
  })

  it('sanctions: 403 → 抛错', async () => {
    mockRequest.get.mockRejectedValue(new Error('403'))
    await expect(fetchSanctionsWithFallback()).rejects.toThrow()
  })

  it('drafts: 404 → 抛错', async () => {
    mockRequest.get.mockRejectedValue(new Error('404'))
    await expect(fetchDraftsWithFallback()).rejects.toThrow()
  })

  it('appeals: 后端拒绝 → 抛错', async () => {
    mockRequest.get.mockRejectedValue(new Error('500'))
    await expect(fetchAppealsWithFallback()).rejects.toThrow()
  })

  it('approval: 网络失败 → 抛错', async () => {
    mockRequest.get.mockRejectedValue(FAILURE)
    await expect(fetchTicketsWithFallback('done')).rejects.toThrow()
  })
})

// ── 读取类：仅 DEV + 显式开关允许 demo ─────────────────────────────
describe('DEV + 显式开关才允许 demo', () => {
  it('discipline: DEV+demo开关 → 返回 demo 非空数组', async () => {
    vi.stubEnv('VITE_ALLOW_DEMO_FALLBACK', DEMO_ON)
    mockRequest.get.mockRejectedValue(new Error('Network Error'))
    const res = await fetchDisciplineWithFallback()
    expect(Array.isArray(res)).toBe(true)
    expect(res.length).toBeGreaterThan(0)
  })

  it('production 构建（开关未开启）→ 永不 demo，仍抛错', async () => {
    vi.stubEnv('VITE_ALLOW_DEMO_FALLBACK', DEMO_OFF)
    mockRequest.get.mockRejectedValue(new Error('Network Error'))
    await expect(fetchBehaviorWithFallback()).rejects.toThrow()
  })
})

// ── 写操作：失败不得假 success ─────────────────────────────────────
describe('submitAppealWithFallback（写操作）', () => {
  it('真实成功 → success=true，无 demo 标记', async () => {
    mockRequest.post.mockResolvedValue({})
    const res = await submitAppealWithFallback('p1', '理由')
    expect(res.success).toBe(true)
    expect(res.demo).toBeUndefined()
  })

  it('后端拒绝/网络失败（生产）→ 抛错，不假成功', async () => {
    vi.stubEnv('VITE_ALLOW_DEMO_FALLBACK', DEMO_OFF)
    mockRequest.post.mockRejectedValue(new Error('500'))
    await expect(submitAppealWithFallback('p1', '理由')).rejects.toThrow()
  })

  it('DEV+开关下失败 → 返回 demo:true 且 success:false，绝不伪装为真实写入', async () => {
    vi.stubEnv('VITE_ALLOW_DEMO_FALLBACK', DEMO_ON)
    mockRequest.post.mockRejectedValue(new Error('500'))
    const res = await submitAppealWithFallback('p1', '理由')
    expect(res.success).toBe(false)
    expect(res.demo).toBe(true)
  })
})
