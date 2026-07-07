<template>
  <div class="notification-center">
    <!-- Page Header -->
    <div class="page-header">
      <div class="header-info">
        <h2 class="page-title">
          <el-icon><Bell /></el-icon>
          通知中心
        </h2>
        <span class="page-subtitle">{{ totalCount }} 条通知，{{ unreadCount }} 条未读</span>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          :disabled="unreadCount === 0 || markingAllRead"
          :loading="markingAllRead"
          @click="handleMarkAllRead"
        >
          <el-icon><Finished /></el-icon>
          全部已读
        </el-button>
      </div>
    </div>

    <!-- Type Filter Tabs -->
    <div class="filter-bar">
      <el-radio-group v-model="activeFilter" size="small" @change="handleFilterChange">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="unread">
          <el-badge :value="unreadCount" :max="99" :hidden="unreadCount === 0">
            未读
          </el-badge>
        </el-radio-button>
        <el-radio-button
          v-for="t in typeOptions"
          :key="t.value"
          :value="t.value"
        >
          {{ t.label }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="5" animated />
    </div>

    <!-- Empty State -->
    <el-empty
      v-else-if="notifications.length === 0"
      description="暂无通知消息"
      :image-size="120"
    />

    <!-- Notification List -->
    <div v-else class="notification-list">
      <div
        v-for="item in notifications"
        :key="item.id"
        class="notification-card"
        :class="{ 'is-unread': !item.is_read }"
        @click="handleClickNotification(item)"
      >
        <!-- Left: Type Icon -->
        <div class="card-icon" :style="{ background: notificationTypeColor(item.type) }">
          <el-icon :size="18">
            <component :is="notificationTypeIcon(item.type)" />
          </el-icon>
        </div>

        <!-- Center: Content -->
        <div class="card-content">
          <div class="card-header-row">
            <el-tag
              :type="notificationTagType(item.type as string)"
              size="small"
              effect="light"
              class="card-tag"
            >
              {{ notificationTypeLabel(item.type) }}
            </el-tag>
            <span class="card-time">{{ formatRelativeTime(item.created_at) }}</span>
          </div>
          <h4 class="card-title">{{ item.title }}</h4>
          <p class="card-body">{{ item.body }}</p>
        </div>

        <!-- Right: Unread Dot + Mark Read -->
        <div class="card-actions">
          <span v-if="!item.is_read" class="unread-dot" />
          <el-button
            v-if="!item.is_read"
            text
            size="small"
            type="primary"
            @click.stop="handleMarkOneRead(item)"
          >
            标为已读
          </el-button>
          <el-icon v-else class="read-check">
            <Check />
          </el-icon>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalCount > pageSize" class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="totalCount"
        layout="total, prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import {
  Bell,
  Finished,
  Check,
} from '@element-plus/icons-vue'
import {
  listNotifications,
  markAsRead,
  markAllAsRead,
  getUnreadCount,
  notificationTypeLabel,
  notificationTypeIcon,
  notificationTypeColor,
  formatRelativeTime,
  type NotificationItem,
} from '@/api/notifications'

// ── State ──
const loading = ref(false)
const markingAllRead = ref(false)
const activeFilter = ref('all')
const currentPage = ref(1)
const pageSize = 20
const notifications = ref<NotificationItem[]>([])
const totalCount = ref(0)
const unreadCount = ref(0)

// ── Type Filter Options ──
const typeOptions = [
  { value: 'discipline_pending', label: '处分待办' },
  { value: 'approval_timeout', label: '审批超时' },
  { value: 'ai_prescription', label: 'AI处方' },
  { value: 'rdi_alert', label: '风险预警' },
  { value: 'recovery_available', label: '回血可用' },
  { value: 'score_change', label: '评分变动' },
  { value: 'growth_milestone', label: '成长里程碑' },
  { value: 'system', label: '系统通知' },
]

// ── Lifecycle ──
onMounted(async () => {
  await Promise.all([fetchNotifications(), fetchUnreadCount()])
})

// ── Data Fetching ──
async function fetchNotifications() {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize,
    }
    // is_read filter
    if (activeFilter.value === 'unread') {
      params.is_read = false
    } else if (activeFilter.value !== 'all') {
      params.type = activeFilter.value
    }
    const res: any = await listNotifications(params)
    notifications.value = res.items ?? res.data ?? []
    totalCount.value = res.total ?? 0
  } catch {
    ElMessage.warning('加载通知失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function fetchUnreadCount() {
  try {
    const res: any = await getUnreadCount()
    unreadCount.value = res?.count ?? 0
  } catch {
    // Silent fail
  }
}

// ── Filter / Pagination ──
function handleFilterChange() {
  currentPage.value = 1
  fetchNotifications()
}

function handlePageChange() {
  fetchNotifications()
}

// ── Read Actions ──
async function handleMarkOneRead(item: NotificationItem) {
  try {
    await markAsRead(item.id)
    item.is_read = true
    item.read_at = new Date().toISOString()
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
    ElMessage.error('标记失败')
  }
}

async function handleMarkAllRead() {
  markingAllRead.value = true
  try {
    await markAllAsRead()
    // Optimistic update
    notifications.value.forEach((n) => {
      if (!n.is_read) {
        n.is_read = true
        n.read_at = new Date().toISOString()
      }
    })
    unreadCount.value = 0
    ElMessage.success('已全部标记为已读')
  } catch {
    ElMessage.error('操作失败')
  } finally {
    markingAllRead.value = false
  }
}

// ── Click → Navigate ──
function handleClickNotification(item: NotificationItem) {
  // Mark as read on click
  if (!item.is_read) {
    handleMarkOneRead(item)
  }
  // Navigate to related entity (future enhancement)
  if (item.entity_type && item.entity_id) {
    // router.push(`/${item.entity_type}/${item.entity_id}`)
  }
}

// ── Tag type mapping for el-tag ──
function notificationTagType(type: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    discipline_pending: 'danger',
    discipline_activated: 'danger',
    discipline_appeal: 'warning',
    discipline_revoked: 'success',
    approval_timeout: 'danger',
    approval_assigned: 'info',
    ai_prescription: 'primary',
    rdi_alert: 'warning',
    recovery_available: 'success',
    score_change: 'info',
    growth_milestone: 'primary',
    system: 'info',
  }
  return map[type] ?? 'info'
}
</script>

<style scoped>
.notification-center {
  max-width: 900px;
  margin: 0 auto;
}

/* ── Page Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
}

.header-actions {
  flex-shrink: 0;
}

/* ── Filter Bar ── */
.filter-bar {
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  overflow-x: auto;
  white-space: nowrap;
}

/* ── Loading / Empty ── */
.loading-state {
  padding: 24px;
}

/* ── Notification List ── */
.notification-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.notification-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 20px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.2s ease;
}

.notification-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.notification-card.is-unread {
  background: #f0f7ff;
  border-left: 3px solid #409eff;
}

/* ── Card Icon ── */
.card-icon {
  width: 40px;
  height: 40px;
  min-width: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

/* ── Card Content ── */
.card-content {
  flex: 1;
  min-width: 0;
}

.card-header-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.card-tag {
  flex-shrink: 0;
}

.card-time {
  font-size: 12px;
  color: #909399;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 6px;
  line-height: 1.4;
}

.card-body {
  font-size: 13px;
  color: #606266;
  margin: 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Card Actions (Right) ── */
.card-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 60px;
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409eff;
}

.read-check {
  font-size: 16px;
  color: #67c23a;
}

/* ── Pagination ── */
.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>
