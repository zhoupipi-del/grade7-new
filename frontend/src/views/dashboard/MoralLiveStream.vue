<template>
  <div class="moral-stream-container">
    <!-- ═══ 头部：标题 + 统计 + 在线状态 ═══ -->
    <div class="stream-header">
      <div class="stream-title">
        <el-icon class="stream-icon" :class="{ 'stream-pulse': !isOffline }"><Connection /></el-icon>
        <span>德育动态广播</span>
        <span class="stream-sub">班主任 · 学生会巡查日志</span>
      </div>
      <div class="stream-stats">
        <span class="stat-chip stat-positive">
          <el-icon :size="12"><CirclePlus /></el-icon>
          {{ positiveCount }} 加分
        </span>
        <span class="stat-chip stat-negative">
          <el-icon :size="12"><Minus /></el-icon>
          {{ negativeCount }} 扣分
        </span>
        <el-tag v-if="!isOffline" type="success" effect="plain" size="small">
          <el-icon class="pulse-dot"><CircleCheck /></el-icon>
          实时 · 60s
        </el-tag>
        <el-tag v-else type="warning" effect="dark" size="small" class="animate-pulse">
          ⚠️ 离线 · 缓存
        </el-tag>
      </div>
    </div>

    <!-- ═══ 动态流水 — TransitionGroup 滚动入场 ═══ -->
    <div class="stream-body" ref="streamBodyRef">
      <TransitionGroup name="stream" tag="div" class="stream-list">
        <div
          v-for="item in streamItems"
          :key="item.id"
          class="stream-item"
          :class="`stream-${item.type}`"
        >
          <!-- 左侧：类型标识 -->
          <div class="item-badge" :class="`badge-${item.type}`">
            <el-icon :size="16">
              <CaretTop v-if="item.type === 'positive'" />
              <CaretBottom v-else />
            </el-icon>
          </div>

          <!-- 中间：内容主体 -->
          <div class="item-content">
            <div class="item-top">
              <span class="item-student">{{ item.student_name }}</span>
              <span class="item-class">{{ item.class_name }}</span>
              <el-tag
                size="small"
                :type="item.type === 'positive' ? 'success' : 'danger'"
                effect="plain"
              >
                {{ item.category }}
              </el-tag>
              <el-tag
                v-if="item.verify_status && item.verify_status !== 'pending'"
                size="small"
                :type="item.verify_status === 'verified' ? 'success' : 'warning'"
                effect="dark"
              >
                {{ item.verify_status === 'verified' ? '已核实' : '已驳回' }}
              </el-tag>
            </div>
            <div class="item-desc">{{ item.description }}</div>
            <div class="item-footer">
              <span class="item-creator">{{ item.creator_name }}</span>
              <span class="item-time">{{ formatTime(item.created_at) }}</span>
              <span v-if="item.action_taken" class="item-action">
                处置: {{ item.action_taken }}
              </span>
            </div>
          </div>

          <!-- 右侧：积分变动 -->
          <div class="item-points" :class="`points-${item.type}`">
            <span class="points-sign">{{ item.type === 'positive' ? '+' : '' }}</span>
            <span class="points-num">{{ item.points }}</span>
          </div>
        </div>
      </TransitionGroup>

      <!-- 空状态 -->
      <el-empty
        v-if="streamItems.length === 0"
        description="暂无巡查记录"
        :image-size="60"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  Connection, CirclePlus, Minus, CircleCheck,
  CaretTop, CaretBottom,
} from '@element-plus/icons-vue'
import {
  getRecentBehaviorRecords,
  getDemoBehaviorRecords,
  type BehaviorRecord,
} from '@/api/dashboard'

// ─── 响应式数据 ──────────────────────────────────────────────────
const streamItems = ref<BehaviorRecord[]>(getDemoBehaviorRecords().items)
const isOffline = ref(!navigator.onLine)
const streamBodyRef = ref<HTMLDivElement | null>(null)
let poller: ReturnType<typeof setInterval> | null = null

// ─── 计算属性 ────────────────────────────────────────────────────
const positiveCount = computed(() =>
  streamItems.value.filter((r) => r.type === 'positive').length,
)
const negativeCount = computed(() =>
  streamItems.value.filter((r) => r.type === 'negative').length,
)

// ─── 工具函数 ────────────────────────────────────────────────────
const formatTime = (isoStr: string): string => {
  try {
    const d = new Date(isoStr)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  } catch {
    return isoStr
  }
}

// ─── 数据拉取 (含 demo 降级) ────────────────────────────────────
const fetchData = async () => {
  if (!navigator.onLine) {
    isOffline.value = true
    return
  }
  isOffline.value = false

  try {
    const data = await getRecentBehaviorRecords({ page: 1, per_page: 15 })
    // 按创建时间倒序排列 (最新在前)
    streamItems.value = data.items.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
  } catch {
    // 后端不可用 → demo 数据降级
    streamItems.value = getDemoBehaviorRecords().items
  }
}

// ─── 生命周期 ────────────────────────────────────────────────────
onMounted(async () => {
  await fetchData()
  // 60s 轮询刷新
  poller = setInterval(fetchData, 60_000)
})

onBeforeUnmount(() => {
  if (poller) clearInterval(poller)
})
</script>

<style scoped>
.moral-stream-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 320px;
}

/* ═══ 头部 ═══ */
.stream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.stream-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.stream-icon {
  color: #10b981;
  font-size: 16px;
}

.stream-pulse {
  animation: pulseGreen 2s ease-in-out infinite;
}

@keyframes pulseGreen {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.stream-sub {
  font-size: 12px;
  color: #909399;
  font-weight: 400;
  margin-left: 4px;
}

.stream-stats {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-chip {
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 10px;
}

.stat-positive {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.stat-negative {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.pulse-dot {
  animation: dotPulse 1.5s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ═══ 流水列表 ═══ */
.stream-body {
  flex: 1;
  overflow-y: auto;
  max-height: 360px;
}

.stream-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stream-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fafafa;
  border-left: 3px solid transparent;
  transition: box-shadow 0.2s ease;
}

.stream-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.stream-positive {
  border-left-color: #10b981;
  background: rgba(16, 185, 129, 0.03);
}

.stream-negative {
  border-left-color: #ef4444;
  background: rgba(239, 68, 68, 0.03);
}

/* ═══ 类型徽章 ═══ */
.item-badge {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.badge-positive {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.badge-negative {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

/* ═══ 内容主体 ═══ */
.item-content {
  flex: 1;
  min-width: 0;
}

.item-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.item-student {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.item-class {
  font-size: 11px;
  color: #909399;
}

.item-desc {
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 3px;
}

.item-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #909399;
}

.item-action {
  color: #606266;
  font-style: italic;
}

/* ═══ 积分变动 ═══ */
.item-points {
  display: flex;
  align-items: baseline;
  gap: 1px;
  flex-shrink: 0;
  font-family: 'DIN Alternate', sans-serif;
  font-weight: 700;
}

.points-positive {
  color: #10b981;
}

.points-negative {
  color: #ef4444;
}

.points-sign {
  font-size: 14px;
}

.points-num {
  font-size: 20px;
}

/* ═══ TransitionGroup 动画 ═══ */
.stream-enter-active {
  transition: all 0.5s ease;
}

.stream-leave-active {
  transition: all 0.3s ease;
  position: absolute;
}

.stream-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.stream-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.stream-move {
  transition: transform 0.5s ease;
}
</style>
