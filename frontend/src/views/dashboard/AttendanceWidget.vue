<template>
  <div class="attendance-widget">
    <!-- ═══ 左侧：今日考勤概览 + 异常指标卡 ═══ -->
    <div class="att-left">
      <!-- 考勤率主指标 -->
      <div class="att-rate-card" :class="{ 'rate-offline': isOffline }">
        <div class="rate-ring">
          <el-progress
            type="dashboard"
            :percentage="dashboardData.attendance_rate"
            :width="110"
            :stroke-width="8"
            :color="rateColor"
          >
            <template #default="{ percentage }">
              <div class="rate-inner">
                <span class="rate-num">{{ percentage.toFixed(1) }}</span>
                <span class="rate-pct">%</span>
              </div>
              <span class="rate-label">出勤率</span>
            </template>
          </el-progress>
        </div>
        <div class="rate-meta">
          <span class="rate-period">{{ periodLabel }}</span>
          <span class="rate-total">应到 {{ dashboardData.total_records }} 人</span>
        </div>
      </div>

      <!-- 三大异常指标卡 -->
      <div class="anomaly-cards">
        <div class="anomaly-card anomaly-late">
          <div class="anomaly-icon">
            <el-icon :size="20"><Clock /></el-icon>
          </div>
          <div class="anomaly-body">
            <div class="anomaly-value">{{ dashboardData.cards.late }}</div>
            <div class="anomaly-label">迟到</div>
          </div>
          <div class="anomaly-trend" v-if="lateTrendDir !== 'flat'">
            <el-icon :size="12"><CaretTop v-if="lateTrendDir === 'up'" /><CaretBottom v-else /></el-icon>
            {{ lateTrendDelta }}
          </div>
        </div>

        <div class="anomaly-card anomaly-absent">
          <div class="anomaly-icon">
            <el-icon :size="20"><CircleClose /></el-icon>
          </div>
          <div class="anomaly-body">
            <div class="anomaly-value">{{ dashboardData.cards.absent }}</div>
            <div class="anomaly-label">缺勤</div>
          </div>
          <div class="anomaly-trend" v-if="absentTrendDir !== 'flat'">
            <el-icon :size="12"><CaretTop v-if="absentTrendDir === 'up'" /><CaretBottom v-else /></el-icon>
            {{ absentTrendDelta }}
          </div>
        </div>

        <div class="anomaly-card anomaly-leave">
          <div class="anomaly-icon">
            <el-icon :size="20"><SwitchButton /></el-icon>
          </div>
          <div class="anomaly-body">
            <div class="anomaly-value">{{ dashboardData.cards.leave_early }}</div>
            <div class="anomaly-label">早退</div>
          </div>
        </div>
      </div>

      <!-- 出勤构成迷你饼图 -->
      <div class="pie-container" ref="pieChartRef"></div>
    </div>

    <!-- ═══ 右侧：异常告警学生列表 ═══ -->
    <div class="att-right">
      <div class="alert-header">
        <span class="alert-title">
          <el-icon><WarningFilled /></el-icon>
          考勤异常警戒线
        </span>
        <el-tag
          :type="anomalyData.count > 0 ? 'danger' : 'success'"
          effect="dark"
          size="small"
        >
          {{ anomalyData.count > 0 ? `${anomalyData.count} 人触发` : '全员正常' }}
        </el-tag>
      </div>
      <div class="alert-list" v-if="anomalyData.alerts.length > 0">
        <div
          v-for="(alert, idx) in anomalyData.alerts"
          :key="alert.student_id"
          class="alert-row"
          :class="`alert-${alert.max_level}`"
          :style="{ animationDelay: `${idx * 0.08}s` }"
        >
          <div class="alert-row-left">
            <div class="alert-avatar" :class="`avatar-${alert.max_level}`">
              {{ alert.student_id }}
            </div>
            <div class="alert-warnings">
              <div
                v-for="w in alert.warnings"
                :key="w.type"
                class="warning-text"
              >
                <el-tag size="small" :type="w.level === 'danger' ? 'danger' : 'warning'" effect="plain">
                  {{ anomalyTypeLabel(w.type) }}
                </el-tag>
                <span class="warning-desc">{{ w.text }}</span>
              </div>
            </div>
          </div>
          <div class="alert-row-right">
            <el-tag
              :type="alert.max_level === 'danger' ? 'danger' : 'warning'"
              effect="dark"
              size="small"
            >
              {{ alert.max_level === 'danger' ? '高危' : '预警' }}
            </el-tag>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无考勤异常记录" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { Clock, CircleClose, SwitchButton, WarningFilled, CaretTop, CaretBottom } from '@element-plus/icons-vue'
import {
  getAttendanceDashboard,
  getAttendanceAnomalies,
  getDemoAttendanceDashboard,
  getDemoAttendanceAnomalies,
  type AttendanceDashboardResponse,
  type AttendanceAnomaliesResponse,
  type AnomalyLevel,
} from '@/api/dashboard'

// ─── 响应式数据 ──────────────────────────────────────────────────
const dashboardData = ref<AttendanceDashboardResponse>(getDemoAttendanceDashboard())
const anomalyData = ref<AttendanceAnomaliesResponse>(getDemoAttendanceAnomalies())
const isOffline = ref(!navigator.onLine)

const pieChartRef = ref<HTMLDivElement | null>(null)
let pieChart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null
let poller: ReturnType<typeof setInterval> | null = null

// ─── 计算属性 ────────────────────────────────────────────────────
const periodLabel = computed(() => {
  const p = dashboardData.value.period
  if (p === 'today') return '今日'
  if (p === 'week') return '本周'
  if (p === 'month') return '本月'
  return p
})

const rateColor = computed(() => {
  const r = dashboardData.value.attendance_rate
  if (r >= 97) return '#10b981'
  if (r >= 93) return '#f59e0b'
  return '#ef4444'
})

const lateTrendDir = computed<'up' | 'down' | 'flat'>(() => {
  const s = dashboardData.value.trend.series.late
  if (s.length < 2) return 'flat'
  const diff = s[s.length - 1] - s[s.length - 2]
  if (diff > 0) return 'up'
  if (diff < 0) return 'down'
  return 'flat'
})

const lateTrendDelta = computed(() => {
  const s = dashboardData.value.trend.series.late
  if (s.length < 2) return ''
  const diff = Math.abs(s[s.length - 1] - s[s.length - 2])
  return diff.toString()
})

const absentTrendDir = computed<'up' | 'down' | 'flat'>(() => {
  const s = dashboardData.value.trend.series.absent
  if (s.length < 2) return 'flat'
  const diff = s[s.length - 1] - s[s.length - 2]
  if (diff > 0) return 'up'
  if (diff < 0) return 'down'
  return 'flat'
})

const absentTrendDelta = computed(() => {
  const s = dashboardData.value.trend.series.absent
  if (s.length < 2) return ''
  const diff = Math.abs(s[s.length - 1] - s[s.length - 2])
  return diff.toString()
})

// ─── 工具函数 ────────────────────────────────────────────────────
const anomalyTypeLabel = (type: string): string => {
  const map: Record<string, string> = {
    consecutive_absent: '连续缺勤',
    weekly_late: '周内迟到',
    monthly_absent: '月度缺勤',
  }
  return map[type] || type
}

// ─── ECharts 饼图初始化 ─────────────────────────────────────────
const initPieChart = () => {
  if (!pieChartRef.value) return
  if (pieChart) pieChart.dispose()
  pieChart = echarts.init(pieChartRef.value)

  const option: echarts.EChartsCoreOption = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'horizontal',
      bottom: 0,
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#606266' },
    },
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold',
            formatter: '{b}\n{c}',
          },
        },
        data: dashboardData.value.pie.map((slice) => ({
          name: slice.name,
          value: slice.value,
          itemStyle: { color: slice.color },
        })),
      },
    ],
  }
  pieChart.setOption(option, true)
}

// ─── 数据拉取 (含 demo 降级) ────────────────────────────────────
const fetchData = async () => {
  if (!navigator.onLine) {
    isOffline.value = true
    return
  }
  isOffline.value = false

  try {
    const data = await getAttendanceDashboard({ period: 'today' })
    dashboardData.value = data
  } catch {
    // 后端不可用 → demo 数据降级
    dashboardData.value = getDemoAttendanceDashboard()
  }

  try {
    const anomalies = await getAttendanceAnomalies(7)
    anomalyData.value = anomalies
  } catch {
    anomalyData.value = getDemoAttendanceAnomalies()
  }

  await nextTick()
  initPieChart()
}

// ─── 生命周期 ────────────────────────────────────────────────────
onMounted(async () => {
  await fetchData()

  resizeObserver = new ResizeObserver(() => {
    pieChart?.resize()
  })
  if (pieChartRef.value) resizeObserver.observe(pieChartRef.value)

  // 60s 轮询刷新异常列表
  poller = setInterval(fetchData, 60_000)
})

onBeforeUnmount(() => {
  if (poller) clearInterval(poller)
  resizeObserver?.disconnect()
  pieChart?.dispose()
  pieChart = null
})
</script>

<style scoped>
.attendance-widget {
  display: flex;
  gap: 16px;
  min-height: 320px;
}

/* ═══ 左侧 ═══ */
.att-left {
  flex: 0 0 42%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.att-rate-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-radius: 10px;
  border: 1px solid #d1fae5;
  transition: opacity 0.3s;
}

.att-rate-card.rate-offline {
  opacity: 0.6;
  background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
  border-color: #fde68a;
}

.rate-ring {
  flex-shrink: 0;
}

.rate-inner {
  display: flex;
  align-items: baseline;
  justify-content: center;
}

.rate-num {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  font-family: 'DIN Alternate', sans-serif;
}

.rate-pct {
  font-size: 14px;
  color: #909399;
  margin-left: 2px;
}

.rate-label {
  font-size: 12px;
  color: #909399;
  display: block;
  text-align: center;
  margin-top: 2px;
}

.rate-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rate-period {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.rate-total {
  font-size: 12px;
  color: #909399;
}

/* ═══ 异常指标卡 ═══ */
.anomaly-cards {
  display: flex;
  gap: 10px;
}

.anomaly-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: transform 0.2s ease;
}

.anomaly-card:hover {
  transform: translateY(-2px);
}

.anomaly-late {
  background: rgba(245, 158, 11, 0.08);
  border-color: rgba(245, 158, 11, 0.2);
}

.anomaly-absent {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.2);
}

.anomaly-leave {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.2);
}

.anomaly-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.anomaly-late .anomaly-icon { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.anomaly-absent .anomaly-icon { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.anomaly-leave .anomaly-icon { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }

.anomaly-body {
  flex: 1;
  min-width: 0;
}

.anomaly-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
  font-family: 'DIN Alternate', sans-serif;
}

.anomaly-label {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.anomaly-trend {
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 1px;
}

.anomaly-late .anomaly-trend { color: #f59e0b; }
.anomaly-absent .anomaly-trend { color: #ef4444; }

/* ═══ 饼图 ═══ */
.pie-container {
  flex: 1;
  min-height: 120px;
  width: 100%;
}

/* ═══ 右侧 ═══ */
.att-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #ebeef5;
  padding-left: 16px;
  min-width: 0;
}

.alert-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.alert-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.alert-title .el-icon {
  color: #ef4444;
}

.alert-list {
  flex: 1;
  overflow-y: auto;
  max-height: 280px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  border-left: 3px solid transparent;
  background: #fafafa;
  animation: slideIn 0.4s ease both;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(12px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.alert-danger {
  border-left-color: #ef4444;
  background: rgba(239, 68, 68, 0.04);
}

.alert-warning {
  border-left-color: #f59e0b;
  background: rgba(245, 158, 11, 0.04);
}

.alert-row-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.alert-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}

.avatar-danger { background: #ef4444; }
.avatar-warning { background: #f59e0b; }

.alert-warnings {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.warning-text {
  display: flex;
  align-items: center;
  gap: 6px;
}

.warning-desc {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.alert-row-right {
  flex-shrink: 0;
  margin-left: 8px;
}
</style>
