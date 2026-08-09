<template>
  <!-- 通知铃铛入口 — 始终显示 Bell icon + 未读 Badge -->
  <el-popover
    :visible="popoverVisible"
    :width="380"
    placement="bottom-end"
    trigger="click"
    popper-class="notification-popover"
    @show="onPopoverShow"
    @hide="popoverVisible = false"
  >
    <template #reference>
      <div class="bell-trigger" @click="popoverVisible = !popoverVisible">
        <el-badge :value="unreadCount" :max="99" :hidden="unreadCount === 0">
          <el-icon :size="20" class="bell-icon">
            <Bell />
          </el-icon>
        </el-badge>
      </div>
    </template>

    <!-- ── 弹窗内容 ─────────────────────────────── -->
    <div class="notification-panel">
      <!-- Header -->
      <div class="panel-header">
        <span class="panel-title">通知中心</span>
        <div class="panel-actions">
          <el-button
            v-if="unreadCount > 0"
            link
            type="primary"
            size="small"
            :loading="markingAllRead"
            @click="handleMarkAllRead"
          >
            <el-icon><Finished /></el-icon> 全部已读
          </el-button>
          <el-dropdown trigger="click" @command="handleTypeFilter">
            <el-button link size="small">
              <el-icon><Filter /></el-icon> {{ activeFilter === 'all' ? '全部' : notificationTypeLabel(activeFilter) }}
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="all">全部通知</el-dropdown-item>
                <el-dropdown-item command="unread">仅未读</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="panel-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <!-- Empty state -->
      <div v-else-if="notifications.length === 0" class="panel-empty">
        <el-icon class="empty-icon"><BellFilled /></el-icon>
        <p class="empty-text">暂无通知</p>
        <p class="empty-hint">当有新的审批、预警或系统消息时将出现在这里</p>
      </div>

      <!-- Notification list -->
      <div v-else class="notification-list">
        <div
          v-for="item in notifications"
          :key="item.id"
          class="notification-item"
          :class="{ 'is-unread': !item.is_read }"
          @click="handleItemClick(item)"
        >
          <!-- Type icon -->
          <div class="item-icon" :style="{ color: notificationTypeColor(item.type) }">
            <el-icon :size="18">
              <component :is="notificationTypeIcon(item.type)" />
            </el-icon>
          </div>

          <!-- Content -->
          <div class="item-body">
            <div class="item-title">
              <span class="item-title-text">{{ item.title }}</span>
              <span v-if="!item.is_read" class="unread-dot"></span>
            </div>
            <p v-if="item.body" class="item-preview">{{ truncateText(item.body, 60) }}</p>
            <span class="item-time">{{ formatRelativeTime(item.created_at) }}</span>
          </div>

          <!-- Mark read action for unread items -->
          <el-button
            v-if="!item.is_read"
            link
            size="small"
            class="item-mark-read"
            @click.stop="handleMarkRead(item)"
          >
            <el-icon><Check /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- Footer: view all -->
      <div v-if="notifications.length > 0" class="panel-footer">
        <el-button link type="primary" size="small" @click="handleViewAll">
          查看全部通知
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
/**
 * NotificationBell — 通知铃铛组件
 *
 * 嵌入 MainLayout header，提供：
 * - 未读数 Badge 实时轮询 (30s)
 * - Popover 下拉面板展示最近 5 条通知
 * - 全部已读 / 单条已读 / 类型过滤
 * - Demo 降级模式
 * - "查看全部" → 全屏通知列表
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Bell,
  BellFilled,
  Loading,
  Finished,
  Filter,
  Check,
  ArrowRight,
} from '@element-plus/icons-vue'
import {
  listNotifications,
  getUnreadCount,
  markAsRead,
  markAllAsRead,
  notificationTypeLabel,
  notificationTypeIcon,
  notificationTypeColor,
  formatRelativeTime,
  getDemoNotifications,
  getDemoUnreadCount,
  UNREAD_POLL_INTERVAL,
  type NotificationItem,
} from '@/api/notifications'

const emit = defineEmits<{
  (e: 'view-all'): void
}>()

// ── State ───────────────────────────────────

const popoverVisible = ref(false)
const unreadCount = ref(0)
const notifications = ref<NotificationItem[]>([])
const loading = ref(false)
const markingAllRead = ref(false)
const activeFilter = ref<'all' | 'unread'>('all')

let pollTimer: ReturnType<typeof setInterval> | null = null
let useDemo = false

// ── Helpers ─────────────────────────────────

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

// ── Data fetching ───────────────────────────

async function fetchUnreadCount() {
  try {
    if (useDemo) {
      const demo = getDemoUnreadCount()
      unreadCount.value = demo.unread_count
      return
    }
    const res = await getUnreadCount()
    unreadCount.value = res.unread_count
  } catch {
    // Silent fail, fallback to demo
    if (!useDemo) {
      useDemo = true
      const demo = getDemoUnreadCount()
      unreadCount.value = demo.unread_count
    }
  }
}

async function fetchNotifications() {
  loading.value = true
  try {
    if (useDemo) {
      const demo = getDemoNotifications()
      notifications.value = activeFilter.value === 'unread'
        ? demo.filter((n) => !n.is_read)
        : demo
      loading.value = false
      return
    }

    const params: Record<string, any> = {
      limit: 5,
      offset: 0,
    }
    if (activeFilter.value === 'unread') {
      params.is_read = false
    }
    const res = await listNotifications(params)
    notifications.value = res.items
  } catch {
    // Fallback to demo
    useDemo = true
    const demo = getDemoNotifications()
    notifications.value = activeFilter.value === 'unread'
      ? demo.filter((n) => !n.is_read)
      : demo
  } finally {
    loading.value = false
  }
}

// ── Handlers ────────────────────────────────

function onPopoverShow() {
  fetchNotifications()
}

async function handleMarkRead(item: NotificationItem) {
  try {
    if (!useDemo) {
      await markAsRead(item.id)
    }
    // Optimistic update
    item.is_read = true
    item.read_at = new Date().toISOString()
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
    ElMessage.warning('标记已读失败')
  }
}

async function handleMarkAllRead() {
  markingAllRead.value = true
  try {
    if (!useDemo) {
      await markAllAsRead()
    }
    // Optimistic: mark all as read
    notifications.value.forEach((n) => {
      n.is_read = true
      n.read_at = new Date().toISOString()
    })
    unreadCount.value = 0
    ElMessage.success('已全部标记为已读')
  } catch {
    ElMessage.warning('操作失败')
  } finally {
    markingAllRead.value = false
  }
}

function handleTypeFilter(command: string) {
  activeFilter.value = command as 'all' | 'unread'
  fetchNotifications()
}

function handleItemClick(item: NotificationItem) {
  // Mark as read on click
  if (!item.is_read) {
    handleMarkRead(item)
  }
  // TODO: Navigate to entity detail page based on entity_type
  // e.g. discipline_sanction → /discipline/detail/{entity_id}
}

function handleViewAll() {
  popoverVisible.value = false
  emit('view-all')
}

// ── Lifecycle ───────────────────────────────

onMounted(() => {
  fetchUnreadCount()
  pollTimer = setInterval(fetchUnreadCount, UNREAD_POLL_INTERVAL)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
/* ── Trigger ──────────────────────────────── */

.bell-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 60px;
  cursor: pointer;
  transition: background 0.2s;
  border-radius: 4px;
}

.bell-trigger:hover {
  background: #f5f7fa;
}

.bell-icon {
  color: #5a5e66;
  transition: color 0.2s;
}

.bell-trigger:hover .bell-icon {
  color: #409eff;
}

/* ── Panel Layout ─────────────────────────── */

.notification-panel {
  display: flex;
  flex-direction: column;
  max-height: 520px;
}

/* ── Panel Header ─────────────────────────── */

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Loading ──────────────────────────────── */

.panel-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  gap: 12px;
  color: #909399;
  font-size: 13px;
}

/* ── Empty State ──────────────────────────── */

.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  color: #909399;
}

.empty-icon {
  font-size: 40px;
  color: #c0c4cc;
  margin-bottom: 12px;
}

.empty-text {
  font-size: 14px;
  color: #606266;
  margin: 0 0 6px;
}

.empty-hint {
  font-size: 12px;
  color: #909399;
  margin: 0;
  text-align: center;
  line-height: 1.5;
}

/* ── Notification List ────────────────────── */

.notification-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  gap: 12px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid #f5f7fa;
}

.notification-item:hover {
  background: #f5f7fa;
}

.notification-item.is-unread {
  background: #ecf5ff;
}

.notification-item.is-unread:hover {
  background: #d9ecff;
}

.item-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.item-body {
  flex: 1;
  min-width: 0;
}

.item-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.item-title-text {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  line-height: 1.3;
}

.unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #409eff;
  flex-shrink: 0;
}

.item-preview {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin: 0 0 6px;
  word-break: break-all;
}

.item-time {
  font-size: 11px;
  color: #c0c4cc;
}

.item-mark-read {
  flex-shrink: 0;
  margin-top: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}

.notification-item:hover .item-mark-read {
  opacity: 1;
}

/* ── Panel Footer ─────────────────────────── */

.panel-footer {
  display: flex;
  justify-content: center;
  padding: 10px 16px;
  border-top: 1px solid #ebeef5;
  flex-shrink: 0;
}
</style>

<!-- ── Global popover style (non-scoped) ──────── -->
<style>
.notification-popover {
  padding: 0 !important;
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(0, 21, 41, 0.12);
}
</style>
