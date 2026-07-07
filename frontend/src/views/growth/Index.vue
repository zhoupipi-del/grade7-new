<template>
  <div class="growth-timeline-page">
    <!-- ═══════════════════════════════════════════════ -->
    <!-- Header: Student selector + semester + stats    -->
    <!-- ═══════════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon><TrendCharts /></el-icon>
          成长时间轴
        </h2>
        <div class="student-selector" v-if="!isParent">
          <span class="selector-label">查看学生：</span>
          <el-input
            v-model="studentIdInput"
            placeholder="输入学生ID（如 100）"
            size="small"
            style="width: 160px"
            @keyup.enter="fetchTimeline"
          >
            <template #append>
              <el-button @click="fetchTimeline" :loading="loading">
                <el-icon><Search /></el-icon>
              </el-button>
            </template>
          </el-input>
        </div>
      </div>

      <div class="header-right">
        <el-select
          v-model="semester"
          placeholder="全部学期"
          size="small"
          clearable
          style="width: 180px"
          @change="fetchTimeline"
        >
          <el-option label="2025-2026-2 (当前)" value="2025-2026-2" />
          <el-option label="2025-2026-1" value="2025-2026-1" />
          <el-option label="全部学期" value="" />
        </el-select>
        <el-button size="small" @click="useDemoData" :type="useDemo ? 'warning' : 'default'">
          <el-icon><VideoPlay /></el-icon>
          {{ useDemo ? 'Demo 模式' : '演示数据' }}
        </el-button>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Student info card (when loaded)                 -->
    <!-- ═══════════════════════════════════════════════ -->
    <div v-if="studentInfo" class="student-card">
      <div class="student-avatar">
        <span class="avatar-text">{{ studentInfo.student_name.charAt(0) }}</span>
      </div>
      <div class="student-info">
        <h3>{{ studentInfo.student_name }}</h3>
        <p>{{ studentInfo.class_name }} · 共 {{ studentInfo.total_events }} 个成长记录</p>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Event type filter chips                         -->
    <!-- ═══════════════════════════════════════════════ -->
    <div v-if="studentInfo" class="event-filters">
      <el-radio-group
        v-model="activeFilter"
        size="small"
        @change="applyFilter"
      >
        <el-radio-button value="all">
          全部 ({{ studentInfo.total_events }})
        </el-radio-button>
        <el-radio-button
          v-for="opt in EVENT_TYPE_OPTIONS"
          :key="opt.value"
          :value="opt.value"
        >
          <span class="filter-dot" :style="{ background: opt.color }"></span>
          {{ opt.label }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Loading state                                   -->
    <!-- ═══════════════════════════════════════════════ -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>正在加载成长时间轴...</p>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Empty state (no student selected)               -->
    <!-- ═══════════════════════════════════════════════ -->
    <div v-else-if="!studentInfo" class="empty-prompt">
      <el-icon class="prompt-icon"><UserFilled /></el-icon>
      <p v-if="isParent">正在加载孩子的成长记录...</p>
      <p v-else>输入学生 ID 查看成长时间轴</p>
      <el-button type="primary" size="small" @click="useDemoData" v-if="!isParent">
        加载演示数据
      </el-button>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Vertical Timeline                               -->
    <!-- ═══════════════════════════════════════════════ -->
    <div v-else-if="filteredTimeline.length > 0" class="timeline-container">
      <div class="timeline-track">
        <div
          v-for="(group, gIdx) in groupedTimeline"
          :key="group.date"
          class="timeline-group"
        >
          <!-- Date divider -->
          <div class="date-divider">
            <span class="date-badge">{{ formatDateLabel(group.date) }}</span>
          </div>

          <!-- Events for this date -->
          <div
            v-for="(item, eIdx) in group.events"
            :key="item.event_id"
            class="timeline-event"
            :class="`severity-${item.severity}`"
          >
            <!-- Timeline node -->
            <div class="timeline-node" :style="{ background: eventTypeColor(item.event_type) }">
              <el-icon :size="14">
                <component :is="eventTypeIcon(item.event_type)" />
              </el-icon>
            </div>

            <!-- Event card -->
            <div class="event-card">
              <div class="event-header">
                <el-tag
                  :type="severityTagType(item.severity)"
                  size="small"
                  effect="dark"
                >
                  {{ eventTypeLabel(item.event_type) }}
                </el-tag>
                <el-tag
                  :type="item.severity === 'danger' ? 'danger' : item.severity === 'warning' ? 'warning' : item.severity === 'success' ? 'success' : 'info'"
                  size="small"
                  effect="plain"
                  class="severity-tag"
                >
                  {{ severityLabel(item.severity) }}
                </el-tag>
                <span class="event-time">{{ formatTime(item.occurred_at) }}</span>
              </div>
              <h4 class="event-title">{{ item.title }}</h4>
              <p v-if="item.description" class="event-desc">{{ item.description }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state for filtered results -->
      <div v-if="groupedTimeline.length === 0" class="empty-filtered">
        <el-empty description="当前过滤条件下无事件记录" :image-size="80" />
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════ -->
    <!-- Empty timeline                                  -->
    <!-- ═══════════════════════════════════════════════ -->
    <div v-else-if="studentInfo && !loading" class="empty-timeline">
      <el-empty description="该学生暂无成长记录" :image-size="120" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GrowthTimeline — 成长时间轴视图
 *
 * 7路数据源融合，按时间倒序展示学生的全方位成长轨迹。
 * 支持事件类型过滤、学期选择、RBAC防越权。
 */

import { ref, computed, onMounted } from 'vue'
import { useUserStore } from '@/store/user'
import {
  Search,
  Loading,
  TrendCharts,
  UserFilled,
  VideoPlay,
} from '@element-plus/icons-vue'
import {
  getGrowthTimeline,
  getMyTimeline,
  getDemoTimeline,
  EVENT_TYPE_OPTIONS,
  eventTypeLabel,
  eventTypeIcon,
  eventTypeColor,
  severityTagType,
  type GrowthTimelineResponse,
  type TimelineItem,
  type GrowthEventType,
  type EventSeverity,
} from '@/api/growth'

const userStore = useUserStore()

// ── State ───────────────────────────────────

const loading = ref(false)
const useDemo = ref(false)
const studentIdInput = ref('100')
const semester = ref('')
const activeFilter = ref('all')
const timelineData = ref<GrowthTimelineResponse | null>(null)

// ── Computed ────────────────────────────────

const isParent = computed(() => userStore.currentRole === 'PARENT')

const studentInfo = computed(() => {
  if (!timelineData.value) return null
  return {
    student_name: timelineData.value.student_name,
    class_name: timelineData.value.class_name,
    total_events: timelineData.value.total_events,
  }
})

const filteredTimeline = computed(() => {
  if (!timelineData.value) return []
  if (activeFilter.value === 'all') return timelineData.value.timeline
  return timelineData.value.timeline.filter(
    (e) => e.event_type === activeFilter.value,
  )
})

/** 按日期分组 */
interface TimelineGroup {
  date: string
  events: TimelineItem[]
}

const groupedTimeline = computed(() => {
  const groups: TimelineGroup[] = []
  const seen = new Set<string>()

  for (const event of filteredTimeline.value) {
    if (!seen.has(event.event_date)) {
      seen.add(event.event_date)
      groups.push({ date: event.event_date, events: [event] })
    } else {
      const g = groups.find((g) => g.date === event.event_date)
      if (g) g.events.push(event)
    }
  }
  return groups
})

// ── Helpers ─────────────────────────────────

function formatDateLabel(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / (86400000))

  const month = d.getMonth() + 1
  const day = d.getDate()
  const weekday = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]

  if (diffDays === 0) return `今天 · ${month}月${day}日`
  if (diffDays === 1) return `昨天 · ${month}月${day}日`
  return `${month}月${day}日 星期${weekday}`
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function severityLabel(s: EventSeverity): string {
  return { info: '信息', warning: '提醒', danger: '严重', success: '进步' }[s] || s
}

// ── Data fetching ───────────────────────────

async function fetchTimeline() {
  if (useDemo.value) {
    useDemoData()
    return
  }

  const sid = isParent.value ? undefined : parseInt(studentIdInput.value, 10)
  if (!isParent.value && (!sid || isNaN(sid))) {
    return
  }

  loading.value = true
  try {
    let res: GrowthTimelineResponse
    if (isParent.value) {
      res = await getMyTimeline(semester.value || undefined)
    } else {
      res = await getGrowthTimeline(sid!, semester.value || undefined)
    }
    timelineData.value = res
  } catch {
    // Fallback to demo on error
    useDemoData()
  } finally {
    loading.value = false
  }
}

function useDemoData() {
  useDemo.value = true
  const sid = isParent.value ? 100 : parseInt(studentIdInput.value, 10) || 100
  timelineData.value = getDemoTimeline(sid)
}

function applyFilter() {
  // Filter is reactive via computed
}

// ── Lifecycle ───────────────────────────────

onMounted(() => {
  if (isParent.value) {
    fetchTimeline()
  }
  // For teachers/admins, wait for student ID input
})
</script>

<style scoped>
.growth-timeline-page {
  max-width: 900px;
  margin: 0 auto;
  padding-bottom: 40px;
}

/* ── Page Header ──────────────────────────── */

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  white-space: nowrap;
}

.student-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-label {
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Student Card ─────────────────────────── */

.student-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  margin-bottom: 16px;
  color: #fff;
}

.student-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.avatar-text {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}

.student-info h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 4px;
}

.student-info p {
  font-size: 13px;
  opacity: 0.85;
  margin: 0;
}

/* ── Event Filters ────────────────────────── */

.event-filters {
  margin-bottom: 20px;
  overflow-x: auto;
  white-space: nowrap;
  padding-bottom: 4px;
}

.filter-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

/* ── Loading / Empty ──────────────────────── */

.loading-state,
.empty-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #909399;
  gap: 16px;
}

.prompt-icon {
  font-size: 48px;
  color: #c0c4cc;
}

.loading-state p,
.empty-prompt p {
  margin: 0;
  font-size: 14px;
}

.empty-filtered,
.empty-timeline {
  padding: 40px 0;
}

/* ── Timeline Track ───────────────────────── */

.timeline-container {
  position: relative;
}

.timeline-track {
  position: relative;
  padding-left: 36px;
}

.timeline-track::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #e4e7ed;
  border-radius: 1px;
}

/* ── Date Divider ─────────────────────────── */

.date-divider {
  position: relative;
  display: flex;
  align-items: center;
  margin: 24px 0 12px -36px;
  padding-left: 36px;
}

.date-divider::before {
  content: '';
  position: absolute;
  left: 8px;
  width: 16px;
  height: 16px;
  background: #409eff;
  border-radius: 50%;
  border: 3px solid #ecf5ff;
  z-index: 1;
}

.date-badge {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  background: #f0f2f5;
  padding: 3px 12px;
  border-radius: 12px;
}

/* ── Timeline Event ───────────────────────── */

.timeline-event {
  position: relative;
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding-left: 0;
}

.timeline-node {
  position: absolute;
  left: -26px;
  top: 16px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
  z-index: 1;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

.event-card {
  flex: 1;
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.06);
  transition: box-shadow 0.2s, transform 0.15s;
  border-left: 3px solid #e4e7ed;
}

.timeline-event.severity-danger .event-card {
  border-left-color: #f56c6c;
}

.timeline-event.severity-warning .event-card {
  border-left-color: #e6a23c;
}

.timeline-event.severity-success .event-card {
  border-left-color: #67c23a;
}

.timeline-event.severity-info .event-card {
  border-left-color: #409eff;
}

.event-card:hover {
  box-shadow: 0 4px 16px rgba(0, 21, 41, 0.1);
  transform: translateX(4px);
}

/* ── Event Card Content ───────────────────── */

.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.severity-tag {
  margin-left: 2px;
}

.event-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-left: auto;
}

.event-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 6px;
  line-height: 1.4;
}

.event-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.65;
  margin: 0;
}
</style>
