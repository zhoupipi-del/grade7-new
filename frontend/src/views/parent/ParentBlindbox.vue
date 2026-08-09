<template>
  <div class="blindbox-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <el-button class="back-btn" text @click="$router.push('/parent')">
        <el-icon><ArrowLeft /></el-icon>
        返回门户
      </el-button>
      <h2 class="page-title">
        <el-icon><Present /></el-icon>
        金色盲盒
      </h2>
      <p class="page-subtitle">查看孩子的荣誉卡牌与表彰信</p>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-container">
      <div class="box-loading">
        <div class="box-icon">🎁</div>
        <p>正在开启金色盲盒...</p>
      </div>
    </div>

    <!-- 空状态：无卡牌 -->
    <div v-else-if="status === 'empty'" class="empty-state">
      <div class="empty-box">📦</div>
      <h3>暂无卡牌资产</h3>
      <p>{{ data?.ai_praise_letter || '小勇士还在修炼中，请等待班主任为他充能第一张卡牌！' }}</p>
      <el-button type="primary" @click="goBack">返回门户</el-button>
    </div>

    <!-- 翻牌结果 -->
    <div v-else-if="data" class="blindbox-result">
      <!-- 卡牌展示区 -->
      <div class="card-reveal" :class="`rarity-${data.card_rarity}`">
        <div class="card-glow"></div>
        <div class="card-body">
          <div class="card-rarity-badge">{{ rarityLabel }}</div>
          <div class="card-icon-box">
            <span class="card-emoji">{{ cardEmoji }}</span>
          </div>
          <div class="card-name">{{ data.card_name }}</div>
          <div class="card-first-badge" v-if="data.is_first_open">首次开启</div>
        </div>
      </div>

      <!-- 钱包摘要 -->
      <div class="wallet-summary" v-if="data.total_cards > 0">
        <div class="summary-item">
          <span class="summary-value">{{ data.total_cards }}</span>
          <span class="summary-label">卡牌种类</span>
        </div>
        <div class="summary-divider"></div>
        <div class="summary-item">
          <span class="summary-value">{{ data.total_points }}</span>
          <span class="summary-label">成长积分</span>
        </div>
      </div>

      <!-- AI 表彰信 -->
      <div class="praise-section" ref="praiseRef">
        <div class="praise-header">
          <el-icon><TrophyBase /></el-icon>
          <span>高光少年家校表彰信</span>
        </div>
        <div class="praise-student">致 {{ data.student_name }} 的家长：</div>
        <div class="praise-content">{{ data.ai_praise_letter }}</div>
        <div class="praise-footer">— Wings 集团化金牌育人导师 · 荣誉签发 —</div>
      </div>

      <!-- 操作按钮 -->
      <div class="action-bar">
        <el-button
          type="primary"
          size="large"
          round
          class="share-btn"
          @click="handleShare"
          :loading="sharing"
        >
          <el-icon><Share /></el-icon>
          保存表彰信长图
        </el-button>
        <el-button size="large" round @click="showHistory = true">
          <el-icon><Timer /></el-icon>
          历史盲盒
        </el-button>
      </div>

      <!-- 历史记录抽屉 -->
      <el-drawer
        v-model="showHistory"
        title="金色盲盒开启记录"
        direction="btt"
        size="55%"
        :with-header="true"
      >
        <div class="history-list" v-if="history.length > 0">
          <div
            v-for="item in history"
            :key="item.id"
            class="history-card"
          >
            <div class="hist-icon">{{ historyEmoji(item.card_rarity) }}</div>
            <div class="hist-info">
              <div class="hist-name">{{ item.card_name }}</div>
              <div class="hist-meta">
                <el-tag :type="rarityTagType(item.card_rarity)" size="small">
                  {{ rarityCN(item.card_rarity) }}
                </el-tag>
                <span class="hist-time">{{ formatTime(item.opened_at) }}</span>
              </div>
            </div>
            <div class="hist-share" v-if="item.shared_to">
              <el-tag size="small" type="success">已分享</el-tag>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无开启记录" />
      </el-drawer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, Present, TrophyBase, Share, Timer,
} from '@element-plus/icons-vue'
import { getParentBlindbox, getParentBlindboxHistory, markShare } from '@/api/habitCards'
import type { ParentBlindboxResponse, BlindboxHistoryItem } from '@/api/habitCards'

const router = useRouter()
const praiseRef = ref<HTMLElement | null>(null)

const loading = ref(true)
const sharing = ref(false)
const showHistory = ref(false)
const data = ref<ParentBlindboxResponse | null>(null)
const status = ref<string>('')
const history = ref<BlindboxHistoryItem[]>([])

// ── 计算属性 ──

const rarityLabel = computed(() => {
  const map: Record<string, string> = {
    legendary: '传说',
    epic: '史诗',
    rare: '稀有',
    common: '普通',
  }
  return map[data.value?.card_rarity ?? ''] ?? ''
})

const cardEmoji = computed(() => {
  const map: Record<string, string> = {
    legendary: '👑',
    epic: '💎',
    rare: '⭐',
    common: '🌱',
  }
  return map[data.value?.card_rarity ?? ''] ?? '🎴'
})

// ── 数据加载 ──

async function fetchBlindbox() {
  loading.value = true
  try {
    const res = await getParentBlindbox()
    data.value = res
    status.value = res.status
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '盲盒开启失败，请稍后再试')
    status.value = 'error'
  } finally {
    loading.value = false
  }
}

async function fetchHistory() {
  try {
    const res = await getParentBlindboxHistory()
    history.value = res.history || []
  } catch {
    // 历史加载失败不阻塞主流程
  }
}

// ── 分享长图 ──

async function handleShare() {
  sharing.value = true
  try {
    // 动态加载 html2canvas
    const html2canvas = (await import('html2canvas')).default

    if (!praiseRef.value) {
      ElMessage.warning('未找到表彰信内容')
      return
    }

    const canvas = await html2canvas(praiseRef.value, {
      backgroundColor: '#1a1a2e',
      scale: 2,
      useCORS: true,
    })

    // 触发下载
    const link = document.createElement('a')
    link.download = `表彰信_${data.value?.student_name ?? '学生'}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    ElMessage.success('表彰信已保存，快去朋友圈分享吧！')

    // 标记分享
    if (history.value.length > 0 && history.value[0].id) {
      markShare(history.value[0].id, 'save_image').catch(() => {})
    }
  } catch (e) {
    ElMessage.error('长图生成失败，可尝试截图保存')
  } finally {
    sharing.value = false
  }
}

// ── 工具函数 ──

function rarityCN(rarity: string): string {
  const map: Record<string, string> = {
    legendary: '传说', epic: '史诗', rare: '稀有', common: '普通',
  }
  return map[rarity] ?? rarity
}

function rarityTagType(rarity: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    legendary: 'warning', epic: 'primary', rare: 'info', common: 'primary',
  }
  return map[rarity] ?? 'info'
}

function historyEmoji(rarity: string): string {
  const map: Record<string, string> = {
    legendary: '👑', epic: '💎', rare: '⭐', common: '🌱',
  }
  return map[rarity] ?? '🎴'
}

function formatTime(t: string | null): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

function goBack() {
  router.push('/parent')
}

// ── 生命周期 ──

onMounted(() => {
  fetchBlindbox()
  fetchHistory()
})
</script>

<style scoped>
/* ════════════════════════════════════════════
   整体布局 — 移动优先 H5 落地页
   ════════════════════════════════════════════ */
.blindbox-page {
  max-width: 480px;
  margin: 0 auto;
  padding: 16px 20px 40px;
  min-height: 100vh;
  background: linear-gradient(180deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
}

/* 页面标题 */
.page-header {
  text-align: center;
  margin-bottom: 24px;
  position: relative;
}
.back-btn {
  position: absolute;
  left: 0;
  top: 4px;
  color: #8b949e;
  font-size: 13px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #f0f6fc;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0 0 4px;
}
.page-subtitle {
  font-size: 13px;
  color: #8b949e;
  margin: 0;
}

/* 加载状态 */
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}
.box-loading {
  text-align: center;
}
.box-loading .box-icon {
  font-size: 64px;
  animation: boxBounce 1s ease-in-out infinite;
}
.box-loading p {
  color: #8b949e;
  margin-top: 12px;
  font-size: 14px;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 48px 20px;
}
.empty-box {
  font-size: 72px;
  margin-bottom: 16px;
}
.empty-state h3 {
  color: #f0f6fc;
  font-size: 18px;
  margin: 0 0 8px;
}
.empty-state p {
  color: #8b949e;
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 24px;
}

/* ════════════════════════════════════════════
   卡牌展示 — 稀有度渐变光效
   ════════════════════════════════════════════ */
.card-reveal {
  position: relative;
  border-radius: 20px;
  padding: 32px 24px;
  text-align: center;
  margin-bottom: 20px;
  overflow: hidden;
  animation: cardReveal 0.6s ease-out;
}

/* 稀有度配色 */
.card-reveal.rarity-legendary {
  background: linear-gradient(135deg, #3d2e0a 0%, #5c4313 50%, #3d2e0a 100%);
  border: 2px solid #f0b90b;
  box-shadow: 0 0 40px rgba(240, 185, 11, 0.3), inset 0 0 60px rgba(240, 185, 11, 0.05);
}
.card-reveal.rarity-epic {
  background: linear-gradient(135deg, #1a0d2e 0%, #2d1450 50%, #1a0d2e 100%);
  border: 2px solid #a855f7;
  box-shadow: 0 0 40px rgba(168, 85, 247, 0.3), inset 0 0 60px rgba(168, 85, 247, 0.05);
}
.card-reveal.rarity-rare {
  background: linear-gradient(135deg, #0d1b2e 0%, #152d50 50%, #0d1b2e 100%);
  border: 2px solid #3b82f6;
  box-shadow: 0 0 30px rgba(59, 130, 246, 0.3), inset 0 0 40px rgba(59, 130, 246, 0.05);
}
.card-reveal.rarity-common {
  background: linear-gradient(135deg, #0d1f1a 0%, #15332a 50%, #0d1f1a 100%);
  border: 2px solid #22c55e;
  box-shadow: 0 0 20px rgba(34, 197, 94, 0.2), inset 0 0 30px rgba(34, 197, 94, 0.05);
}

.card-glow {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  border-radius: 50%;
  opacity: 0.08;
  pointer-events: none;
}
.rarity-legendary .card-glow { background: radial-gradient(circle, #f0b90b, transparent 60%); }
.rarity-epic .card-glow { background: radial-gradient(circle, #a855f7, transparent 60%); }
.rarity-rare .card-glow { background: radial-gradient(circle, #3b82f6, transparent 60%); }
.rarity-common .card-glow { background: radial-gradient(circle, #22c55e, transparent 60%); }

.card-rarity-badge {
  display: inline-block;
  padding: 3px 14px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 16px;
  letter-spacing: 1px;
}
.rarity-legendary .card-rarity-badge { background: #f0b90b33; color: #f0b90b; }
.rarity-epic .card-rarity-badge { background: #a855f733; color: #a855f7; }
.rarity-rare .card-rarity-badge { background: #3b82f633; color: #3b82f7; }
.rarity-common .card-rarity-badge { background: #22c55e33; color: #22c55e; }

.card-icon-box {
  width: 88px;
  height: 88px;
  margin: 0 auto 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
}
.card-emoji {
  font-size: 44px;
}

.card-name {
  font-size: 24px;
  font-weight: 700;
  color: #f0f6fc;
  margin-bottom: 12px;
}

.card-first-badge {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  color: #f0b90b;
  background: rgba(240, 185, 11, 0.15);
  border: 1px solid rgba(240, 185, 11, 0.3);
}

/* 钱包摘要 */
.wallet-summary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  padding: 16px;
  margin-bottom: 20px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  border: 1px solid #30363d;
}
.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: #58a6ff;
}
.summary-label {
  font-size: 12px;
  color: #8b949e;
}
.summary-divider {
  width: 1px;
  height: 36px;
  background: #30363d;
}

/* ════════════════════════════════════════════
   AI 表彰信
   ════════════════════════════════════════════ */
.praise-section {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #1a1a2e 100%);
  border: 1px solid #30363d;
  border-radius: 16px;
  padding: 24px 20px;
  margin-bottom: 24px;
  position: relative;
}
.praise-section::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #f0b90b, #a855f7, #3b82f6);
  border-radius: 16px 16px 0 0;
}
.praise-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #f0b90b;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #30363d;
}
.praise-student {
  font-size: 14px;
  color: #c9d1d9;
  margin-bottom: 12px;
  font-style: italic;
}
.praise-content {
  font-size: 15px;
  line-height: 1.8;
  color: #e6edf3;
  white-space: pre-wrap;
  word-break: break-word;
}
.praise-footer {
  text-align: right;
  font-size: 12px;
  color: #484f58;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed #21262d;
}

/* 操作按钮 */
.action-bar {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
.share-btn {
  background: linear-gradient(135deg, #f0b90b, #e8a800) !important;
  border: none !important;
  color: #1a1a2e !important;
  font-weight: 600;
}

/* ════════════════════════════════════════════
   历史记录抽屉
   ════════════════════════════════════════════ */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}
.history-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 10px;
  border: 1px solid #21262d;
}
.hist-icon {
  font-size: 28px;
  width: 40px;
  text-align: center;
  flex-shrink: 0;
}
.hist-info {
  flex: 1;
  min-width: 0;
}
.hist-name {
  font-size: 14px;
  font-weight: 600;
  color: #f0f6fc;
  margin-bottom: 4px;
}
.hist-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hist-time {
  font-size: 12px;
  color: #8b949e;
}
.hist-share {
  flex-shrink: 0;
}

/* ════════════════════════════════════════════
   动画
   ════════════════════════════════════════════ */
@keyframes cardReveal {
  0% {
    opacity: 0;
    transform: translateY(30px) scale(0.95);
  }
  60% {
    opacity: 1;
    transform: translateY(-4px) scale(1.02);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
@keyframes boxBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}
</style>
