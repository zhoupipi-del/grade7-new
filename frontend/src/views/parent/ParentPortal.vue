<template>
  <div class="parent-portal">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><HomeFilled /></el-icon>
        家长门户
      </h2>
      <p class="page-subtitle">关注孩子成长，家校协同育人</p>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 主体内容 -->
    <div v-else class="portal-content">
      <!-- 概要卡片栏 -->
      <el-row :gutter="16" class="summary-row">
        <el-col :span="6">
          <el-card shadow="hover" class="summary-card summary-notifications">
            <div class="summary-icon">
              <el-icon :size="32"><BellFilled /></el-icon>
            </div>
            <div class="summary-info">
              <div class="summary-value">{{ dashboard.unread_notifications }}</div>
              <div class="summary-label">未读通知</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="summary-card summary-pending">
            <div class="summary-icon">
              <el-icon :size="32"><ChatDotRound /></el-icon>
            </div>
            <div class="summary-info">
              <div class="summary-value">{{ dashboard.pending_feedbacks }}</div>
              <div class="summary-label">待处理反馈</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="summary-card summary-positive">
            <div class="summary-icon">
              <el-icon :size="32"><TrophyBase /></el-icon>
            </div>
            <div class="summary-info">
              <div class="summary-value">{{ child.positive_score_total.toFixed(1) }}</div>
              <div class="summary-label">正向加分</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="summary-card" :class="riskCardClass">
            <div class="summary-icon">
              <el-icon :size="32"><Monitor /></el-icon>
            </div>
            <div class="summary-info">
              <div class="summary-value">{{ child.risk_label || '正常' }}</div>
              <div class="summary-label">风险状态</div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <!-- 左栏: 孩子信息 + 五维雷达图 -->
        <el-col :span="14">
          <el-card shadow="hover" class="child-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">
                  <el-icon><User /></el-icon>
                  孩子概况
                </span>
                <el-tag :type="riskTagType" size="small">{{ child.risk_label || '正常' }}</el-tag>
              </div>
            </template>

            <!-- 基本信息 -->
            <el-descriptions :column="2" border size="default" class="child-info">
              <el-descriptions-item label="姓名">{{ child.student_name }}</el-descriptions-item>
              <el-descriptions-item label="学号">{{ child.student_no }}</el-descriptions-item>
              <el-descriptions-item label="年级">{{ child.grade_name }}</el-descriptions-item>
              <el-descriptions-item label="班级">{{ child.class_name }}</el-descriptions-item>
              <el-descriptions-item label="综合总分">
                <span class="total-score">{{ child.total_score?.toFixed(1) ?? '--' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="违纪记录">
                <el-tag :type="child.behavior_record_count > 0 ? 'danger' : 'success'" size="small">
                  {{ child.behavior_record_count }} 次
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>

            <!-- 五维雷达图 -->
            <div ref="radarChartRef" class="radar-chart"></div>
          </el-card>
        </el-col>

        <!-- 右栏: 考勤统计 + 快捷操作 -->
        <el-col :span="10">
          <!-- 考勤统计 -->
          <el-card shadow="hover" class="attendance-card">
            <template #header>
              <span class="card-title">
                <el-icon><Calendar /></el-icon>
                考勤统计
              </span>
            </template>
            <div class="attendance-stats">
              <div class="stat-item stat-normal">
                <div class="stat-value">{{ child.attendance_normal_count }}</div>
                <div class="stat-label">正常出勤</div>
              </div>
              <div class="stat-item stat-abnormal">
                <div class="stat-value">{{ child.attendance_abnormal_count }}</div>
                <div class="stat-label">异常天数</div>
              </div>
            </div>
            <el-progress
              :percentage="attendanceRate"
              :color="attendanceRate >= 95 ? '#67c23a' : attendanceRate >= 85 ? '#e6a23c' : '#f56c6c'"
              :stroke-width="10"
              class="attendance-progress"
            >
              <span class="attendance-rate-text">出勤率 {{ attendanceRate }}%</span>
            </el-progress>
          </el-card>

          <!-- 快捷操作 -->
          <el-card shadow="hover" class="quick-actions-card">
            <template #header>
              <span class="card-title">
                <el-icon><Operation /></el-icon>
                快捷操作
              </span>
            </template>
            <div class="quick-actions">
              <el-button
                type="primary"
                :icon="ChatLineSquare"
                @click="$router.push('/parent/feedback')"
                class="action-btn"
              >
                提交反馈
              </el-button>
              <el-button
                type="warning"
                :icon="WarningFilled"
                @click="$router.push('/parent/appeal')"
                class="action-btn"
              >
                提交申诉
              </el-button>
              <el-button
                :icon="Timer"
                @click="$router.push('/growth')"
                class="action-btn"
              >
                成长时间轴
              </el-button>
              <el-button
                :icon="Bell"
                @click="$router.push('/notifications')"
                class="action-btn"
              >
                通知中心
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 下方: 最近反馈 + 成长动态 -->
      <el-row :gutter="16" class="bottom-row">
        <!-- 最近反馈 -->
        <el-col :span="12">
          <el-card shadow="hover" class="recent-feedbacks-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">
                  <el-icon><ChatDotRound /></el-icon>
                  最近反馈
                </span>
                <el-button text type="primary" @click="$router.push('/parent/feedback')">
                  查看全部
                </el-button>
              </div>
            </template>
            <div v-if="dashboard.recent_feedbacks.length === 0" class="empty-state">
              <el-empty description="暂无反馈记录" :image-size="60" />
            </div>
            <div v-else class="feedback-list">
              <div
                v-for="fb in dashboard.recent_feedbacks"
                :key="fb.id"
                class="feedback-item"
                @click="$router.push('/parent/feedback')"
              >
                <div class="feedback-header">
                  <el-tag size="small" :type="feedbackStatusTagType(fb.status)">
                    {{ fb.status_label }}
                  </el-tag>
                  <span class="feedback-title">{{ fb.title }}</span>
                </div>
                <div class="feedback-meta">
                  <span class="feedback-type">{{ fb.feedback_type_label }}</span>
                  <span class="feedback-time">{{ formatRelativeTime(fb.created_at) }}</span>
                </div>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 成长动态 -->
        <el-col :span="12">
          <el-card shadow="hover" class="timeline-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">
                  <el-icon><Timer /></el-icon>
                  成长动态
                </span>
                <el-button text type="primary" @click="$router.push('/growth')">
                  完整时间轴
                </el-button>
              </div>
            </template>
            <div v-if="child.recent_timeline.length === 0" class="empty-state">
              <el-empty description="暂无成长记录" :image-size="60" />
            </div>
            <el-timeline v-else class="growth-timeline">
              <el-timeline-item
                v-for="event in child.recent_timeline"
                :key="event.event_id"
                :type="timelineItemType(event.severity)"
                :timestamp="formatRelativeTime(event.occurred_at)"
                placement="top"
              >
                <div class="timeline-content">
                  <div class="timeline-title">{{ event.title }}</div>
                  <div v-if="event.description" class="timeline-desc">
                    {{ event.description }}
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import {
  getDashboard,
  getDemoDashboard,
  feedbackStatusTagType,
  formatRelativeTime,
  SCORE_DIMENSIONS,
  type ParentDashboard,
  type ChildOverview,
} from '@/api/parent_portal'
import { ChatLineSquare, WarningFilled, Timer, Bell, Operation } from '@element-plus/icons-vue'

const loading = ref(true)
const dashboard = ref<ParentDashboard>(getDemoDashboard())
const radarChartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

const child = computed<ChildOverview>(() => dashboard.value.child)

const attendanceRate = computed(() => {
  const total = child.value.attendance_normal_count + child.value.attendance_abnormal_count
  if (total === 0) return 100
  return Math.round((child.value.attendance_normal_count / total) * 100)
})

const riskTagType = computed<'info' | 'warning' | 'danger' | 'success'>(() => {
  const level = child.value.risk_level
  if (!level || level === 'low') return 'success'
  if (level === 'moderate') return 'warning'
  return 'danger'
})

const riskCardClass = computed(() => {
  const level = child.value.risk_level
  if (!level || level === 'low') return 'summary-normal'
  if (level === 'moderate') return 'summary-warning'
  return 'summary-danger'
})

function timelineItemType(severity: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    info: 'info',
    warning: 'warning',
    danger: 'danger',
    success: 'success',
  }
  return map[severity] || 'primary'
}

function renderRadarChart() {
  if (!radarChartRef.value) return

  chartInstance?.dispose()
  chartInstance = echarts.init(radarChartRef.value)

  const values = SCORE_DIMENSIONS.map((d) => {
    const val = (child.value as any)[d.key]
    return val ?? 0
  })

  chartInstance.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        let html = '<div style="font-weight:600;margin-bottom:4px">五维评价</div>'
        SCORE_DIMENSIONS.forEach((d, i) => {
          html += `<div>${d.label}: <b>${values[i]}</b></div>`
        })
        return html
      },
    },
    radar: {
      indicator: SCORE_DIMENSIONS.map((d) => ({ name: d.label, max: d.max })),
      radius: '65%',
      axisName: { color: '#606266', fontSize: 12 },
      splitArea: {
        areaStyle: {
          color: ['rgba(64,158,255,0.05)', 'rgba(64,158,255,0.1)'],
        },
      },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: values,
            name: '当前评价',
            areaStyle: { color: 'rgba(64,158,255,0.25)' },
            lineStyle: { color: '#409eff', width: 2 },
            itemStyle: { color: '#409eff' },
          },
        ],
      },
    ],
  })
}

function handleResize() {
  chartInstance?.resize()
}

async function fetchData() {
  loading.value = true
  try {
    dashboard.value = await getDashboard()
  } catch {
    // 后端不可用 → 降级到Demo数据
    dashboard.value = getDemoDashboard()
  } finally {
    loading.value = false
    await nextTick()
    renderRadarChart()
  }
}

onMounted(() => {
  fetchData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<style scoped>
.parent-portal {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
  margin: 0;
}

.loading-container {
  padding: 40px;
  background: #fff;
  border-radius: 8px;
}

/* 概要卡片栏 */
.summary-row {
  margin-bottom: 16px;
}

.summary-card {
  display: flex;
  align-items: center;
  padding: 0;
}

.summary-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 16px 20px;
}

.summary-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  flex-shrink: 0;
}

.summary-notifications .summary-icon {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.summary-pending .summary-icon {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.summary-positive .summary-icon {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.summary-normal .summary-icon {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.summary-warning .summary-icon {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.summary-danger .summary-icon {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.summary-info {
  flex: 1;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.summary-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}

/* 孩子概况卡片 */
.child-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}

.child-info {
  margin-bottom: 16px;
}

.total-score {
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
}

.radar-chart {
  width: 100%;
  height: 320px;
}

/* 考勤统计 */
.attendance-card {
  margin-bottom: 16px;
}

.attendance-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}

.stat-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  border-radius: 8px;
}

.stat-normal {
  background: rgba(103, 194, 58, 0.08);
}

.stat-abnormal {
  background: rgba(245, 108, 108, 0.08);
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
}

.stat-normal .stat-value {
  color: #67c23a;
}

.stat-abnormal .stat-value {
  color: #f56c6c;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.attendance-progress {
  margin-top: 4px;
}

.attendance-rate-text {
  font-size: 13px;
  font-weight: 600;
}

/* 快捷操作 */
.quick-actions-card {
  margin-bottom: 16px;
}

.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.action-btn {
  height: 44px;
  font-size: 14px;
}

/* 底部行 */
.bottom-row {
  margin-top: 4px;
}

/* 反馈列表 */
.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feedback-item {
  padding: 12px 16px;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  transition: all 0.2s;
}

.feedback-item:hover {
  background: #ecf5ff;
}

.feedback-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.feedback-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feedback-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

/* 成长时间轴 */
.growth-timeline {
  padding: 8px 0 0 0;
}

.timeline-content {
  padding-bottom: 4px;
}

.timeline-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.timeline-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.5;
}

.empty-state {
  padding: 20px 0;
}
</style>
