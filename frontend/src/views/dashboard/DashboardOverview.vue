<template>
  <div class="dashboard-container" v-loading="pageLoading">
    <!-- ═══ 顶层：四象 KPI 指挥指标卡 ═══ -->
    <el-row :gutter="20" class="kpi-row">
      <el-col :span="6" v-for="metric in kpiMetrics" :key="metric.key">
        <el-card shadow="hover" class="kpi-card" :class="`kpi-${metric.tone}`">
          <div class="kpi-body">
            <div class="kpi-icon">
              <el-icon :size="28"><component :is="ICON_MAP[metric.icon]" /></el-icon>
            </div>
            <div class="kpi-content">
              <div class="kpi-value">{{ metric.value }}<span class="kpi-unit">{{ metric.unit }}</span></div>
              <div class="kpi-label">{{ metric.label }}</div>
            </div>
          </div>
          <div class="kpi-footer">
            <el-tag size="small" :type="metric.tone" effect="plain">{{ metric.schoolTag }}</el-tag>
            <span class="kpi-trend" :class="metric.trendDir">{{ metric.trend }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 中层：11:13 分屏 — 左实时告警流 + 右跨校区 RDI 雷达 ═══ -->
    <el-row :gutter="20" class="mid-row">
      <!-- 左：实时告警流 -->
      <el-col :span="11">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><Bell /></el-icon>
                实时风险告警流
              </span>
              <el-tag v-if="!isOffline" type="danger" effect="dark" size="small">
                <el-icon class="pulse-icon"><AlarmClock /></el-icon>
                实时 · 30s
              </el-tag>
              <el-tag v-else type="warning" effect="dark" size="small" class="animate-pulse">
                ⚠️ 离线模式
              </el-tag>
            </div>
          </template>
          <div class="alert-stream">
            <div
              v-for="alert in alertStream"
              :key="alert.id"
              class="alert-item"
              :class="`alert-${alert.level}`"
            >
              <div class="alert-main">
                <div class="alert-header">
                  <span class="alert-student">{{ alert.student_name }}</span>
                  <el-tag size="small" :type="alert.school === '本部校区' ? 'danger' : 'primary'" effect="plain">
                    {{ alert.school }}
                  </el-tag>
                  <el-tag size="small" :type="alert.level === 'danger' ? 'danger' : 'warning'" effect="dark">
                    {{ alert.level === 'danger' ? '高危' : '预警' }}
                  </el-tag>
                </div>
                <div class="alert-issue">{{ alert.issue }}</div>
                <div class="alert-meta">
                  <span class="alert-rdi">RDI: {{ alert.rdi.toFixed(2) }}σ</span>
                  <span class="alert-time">{{ alert.time }}</span>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右：跨校区 RDI 雷达对比 -->
      <el-col :span="13">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><Aim /></el-icon>
                跨校区 RDI 五维偏离度对比
              </span>
              <div class="legend-inline" v-if="!isOffline">
                <span class="legend-dot legend-benbu"></span>本部校区
                <span class="legend-dot legend-shiyan"></span>实验分校
              </div>
              <el-tag v-else type="warning" effect="dark" size="small" class="animate-pulse">
                ⚠️ 离线 · 缓存数据
              </el-tag>
            </div>
          </template>
          <div class="chart-relative-container">
            <div ref="radarChartRef" class="echart-dom radar-chart" :class="{ 'chart-dimmed': isOffline }"></div>
            <div v-if="isOffline && !hasCache" class="chart-offline-overlay">
              <el-empty description="数据流链路断开，正在尝试重连..." :image-size="80" />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 底层：全幅 EWMA 跨校区收敛趋势 ═══ -->
    <el-row :gutter="20" class="bottom-row">
      <el-col :span="24">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="card-header">
              <span class="panel-title">
                <el-icon><TrendCharts /></el-icon>
                EWMA 跨校区风险收敛趋势 (近 6 个观测窗)
              </span>
              <div class="legend-inline" v-if="!isOffline">
                <span class="legend-dot legend-benbu"></span>本部校区
                <span class="legend-dot legend-shiyan"></span>实验分校
              </div>
              <el-tag v-else type="warning" effect="dark" size="small" class="animate-pulse">
                ⚠️ 离线 · 缓存数据
              </el-tag>
            </div>
          </template>
          <div class="chart-relative-container">
            <div ref="trendChartRef" class="echart-dom trend-chart" :class="{ 'chart-dimmed': isOffline }"></div>
            <div v-if="isOffline && !hasCache" class="chart-offline-overlay">
              <el-empty description="数据流链路断开，正在尝试重连..." :image-size="80" />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 底层扩展：德学双优四象限散点图 (跨库聚合) ═══ -->
    <el-row :gutter="20" class="scatter-row">
      <el-col :span="24">
        <CorrelationScatter />
      </el-col>
    </el-row>

    <!-- ═══ Phase J 三大挂件行：流动红旗 + 考勤异常 + 德育动态流 ═══ -->
    <el-row :gutter="20" class="widget-row">
      <el-col :span="8">
        <RedFlagLeaderboard />
      </el-col>
      <el-col :span="8">
        <AttendanceWidget />
      </el-col>
      <el-col :span="8">
        <MoralLiveStream />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import {
  Bell, AlarmClock, Aim, TrendCharts,
  Warning, DataAnalysis, CircleCheck, Unlock,
} from '@element-plus/icons-vue'
import {
  fetchDashboardOverview,
  refreshAlertStream,
  campusColor,
  type KpiMetric,
  type AlertItem,
  type CampusRadarSeries,
  type CampusTrendSeries,
} from '@/api/dashboard'
import CorrelationScatter from './CorrelationScatter.vue'
import RedFlagLeaderboard from './RedFlagLeaderboard.vue'
import AttendanceWidget from './AttendanceWidget.vue'
import MoralLiveStream from './MoralLiveStream.vue'

// ─── 图标名称 → 组件映射 (API 返回字符串名, 模板用 <component :is>) ──
const ICON_MAP: Record<string, any> = {
  Warning,
  DataAnalysis,
  CircleCheck,
  Unlock,
}

// ─── 工具：hex → rgba（品牌色派生面积渐变，避免手写第二色源） ─────
const hexToRgba = (hex: string, alpha: number): string => {
  const v = hex.replace('#', '')
  const r = parseInt(v.substring(0, 2), 16)
  const g = parseInt(v.substring(2, 4), 16)
  const b = parseInt(v.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// ─── 响应式数据 (从 API 契约层获取) ─────────────────────────────
const kpiMetrics = ref<KpiMetric[]>([])
const alertStream = ref<AlertItem[]>([])
const radarSeries = ref<CampusRadarSeries[]>([])
const trendSeries = ref<CampusTrendSeries[]>([])

// ─── ECharts 实例与 DOM 引用 ────────────────────────────────────
const radarChartRef = ref<HTMLDivElement | null>(null)
const trendChartRef = ref<HTMLDivElement | null>(null)

let radarChart: ReturnType<typeof echarts.init> | null = null
let trendChart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null
let alertPoller: ReturnType<typeof setInterval> | null = null

const pageLoading = ref(true)

// ─── 离线降级状态 ───────────────────────────────────────────────
const isOffline = ref(!navigator.onLine)
const hasCache = ref(false)

const CACHE_KEY_TREND = 'wings3_dashboard_trend_snapshot'

interface ChartSnapshot {
  trendSeries: CampusTrendSeries[]
  radarSeries: CampusRadarSeries[]
  savedAt: number
}

// ─── 离线快照持久化 ─────────────────────────────────────────────
const saveChartCache = () => {
  try {
    const snapshot: ChartSnapshot = {
      trendSeries: trendSeries.value,
      radarSeries: radarSeries.value,
      savedAt: Date.now(),
    }
    localStorage.setItem(CACHE_KEY_TREND, JSON.stringify(snapshot))
    hasCache.value = true
  } catch {
    // localStorage 配额满或隐私模式 — 静默降级
  }
}

const tryLoadChartCache = (): boolean => {
  try {
    const cached = localStorage.getItem(CACHE_KEY_TREND)
    if (!cached) return false
    const snapshot = JSON.parse(cached) as ChartSnapshot
    if (!snapshot.trendSeries?.length && !snapshot.radarSeries?.length) return false

    // 用缓存数据原位渲染，实现无感过渡
    if (snapshot.radarSeries?.length) {
      radarSeries.value = snapshot.radarSeries
      initRadarChart()
    }
    if (snapshot.trendSeries?.length) {
      trendSeries.value = snapshot.trendSeries
      initTrendChart()
    }
    hasCache.value = true
    return true
  } catch {
    hasCache.value = false
    return false
  }
}

// ─── 浏览器网络状态监听 ─────────────────────────────────────────
const handleNetworkChange = () => {
  const wasOffline = isOffline.value
  isOffline.value = !navigator.onLine

  if (isOffline.value) {
    // 进入离线: 尝试从缓存恢复图表
    tryLoadChartCache()
  } else if (wasOffline) {
    // 从离线恢复在线: 立即拉取最新数据
    refreshDashboardData()
  }
}

// ─── 全量数据刷新 (首次加载 + 网络恢复时调用) ───────────────────
const refreshDashboardData = async () => {
  try {
    const data = await fetchDashboardOverview()
    kpiMetrics.value = data.kpiMetrics
    alertStream.value = data.alertStream
    radarSeries.value = data.radarSeries
    trendSeries.value = data.trendSeries

    // 成功获取后, 顺手做一层离线快照写入
    saveChartCache()
    isOffline.value = false

    await nextTick()
    initRadarChart()
    initTrendChart()
  } catch (err) {
    // 后端断开或超时, 启动前端降级兜底
    console.error('[DashboardOverview] refreshDashboardData error:', err)
    isOffline.value = true
    tryLoadChartCache()
  }
}

// ─── 告警流增量刷新 (30s 轮询, 基于 /risk_models/monitor-panel) ──
const startAlertPolling = () => {
  // 30s 间隔 — 避免频繁触发 RDI 后端计算
  alertPoller = setInterval(async () => {
    // 物理离线时跳过轮询, 节省资源
    if (!navigator.onLine) {
      isOffline.value = true
      return
    }

    const fresh = await refreshAlertStream()
    // null = 网络/解析失败 → 进入离线模式
    if (fresh === null) {
      isOffline.value = true
      tryLoadChartCache()
      return
    }

    // 轮询成功 — 恢复在线状态 (即使 fresh 为空数组也是成功)
    isOffline.value = false
    if (fresh.length === 0) return

    // 增量合并: 找出当前流中不存在的 id, 头部压栈
    const existingIds = new Set(alertStream.value.map(a => a.id))
    const newAlerts = fresh.filter(a => !existingIds.has(a.id))
    if (newAlerts.length > 0) {
      // 头部压入新高危, 保留最多 10 条
      alertStream.value = [...newAlerts, ...alertStream.value].slice(0, 10)
    }
  }, 30000)
}

const stopAlertPolling = () => {
  if (alertPoller !== null) {
    clearInterval(alertPoller)
    alertPoller = null
  }
}

// ─── 雷达图：五维偏离度跨校区对比 ───────────────────────────────
const initRadarChart = () => {
  if (!radarChartRef.value) return
  if (!radarChart) {
    radarChart = echarts.init(radarChartRef.value, 'wings')
  }

  const seriesData = radarSeries.value.map(s => {
    const color = campusColor(s.name)
    return {
      value: s.values,
      name: s.name,
      areaStyle: { color: hexToRgba(color, 0.22) },
      lineStyle: { color, width: 2.5 },
      itemStyle: { color },
      symbolSize: 6,
    }
  })

  const option: any = {
    tooltip: { trigger: 'item' },
    legend: { show: false },
    radar: {
      indicator: [
        { name: '学业偏离度', max: 5 },
        { name: '考勤破线度', max: 5 },
        { name: '行为抗拒度', max: 5 },
        { name: '家校传导系数', max: 5 },
        { name: '心理危机指数', max: 5 },
      ],
      splitArea: {
        areaStyle: {
          color: ['rgba(245, 247, 250, 0.6)', 'rgba(236, 240, 245, 0.6)'],
        },
      },
      axisName: { fontSize: 13, fontWeight: 500 },
      center: ['50%', '52%'],
      radius: '68%',
    },
    series: [{
      type: 'radar',
      data: seriesData,
    }],
  }
  radarChart.setOption(option, true)
}

// ─── 趋势图：EWMA 跨校区风险收敛 ────────────────────────────────
const initTrendChart = () => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value, 'wings')
  }

  // Use first series dates as x-axis, fallback to empty
  const dates = trendSeries.value[0]?.dates ?? []

  const series = trendSeries.value.map(s => {
    const color = campusColor(s.name)
    return {
      name: s.name,
      type: 'line',
      smooth: true,
      data: s.values,
      lineStyle: { color, width: 3 },
      itemStyle: { color },
      symbolSize: 8,
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: hexToRgba(color, 0.25) },
          { offset: 1, color: hexToRgba(color, 0) },
        ]),
      },
    }
  })

  const option: any = {
    tooltip: { trigger: 'axis' },
    legend: { show: false },
    grid: { left: '3%', right: '4%', bottom: '8%', top: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
    },
    yAxis: {
      type: 'value',
      name: 'RDI 指数',
      min: 0,
      max: 4,
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series,
  }
  trendChart.setOption(option, true)
}

// ─── 生命周期：挂载 ─────────────────────────────────────────────
onMounted(async () => {
  pageLoading.value = true

  // 注册浏览器网络状态监听
  window.addEventListener('online', handleNetworkChange)
  window.addEventListener('offline', handleNetworkChange)

  try {
    // 全量数据拉取 (内含离线降级 + 缓存恢复)
    await refreshDashboardData()

    // ResizeObserver 自动跟随容器尺寸
    resizeObserver = new ResizeObserver(() => {
      radarChart?.resize()
      trendChart?.resize()
    })
    if (radarChartRef.value) resizeObserver.observe(radarChartRef.value)
    if (trendChartRef.value) resizeObserver.observe(trendChartRef.value)

    // 启动告警流增量轮询 (30s)
    startAlertPolling()
  } catch (err) {
    console.error('[DashboardOverview] onMounted error:', err)
  } finally {
    // 无论成功失败, loading 必须关闭 — 否则页面永远转圈
    pageLoading.value = false
  }
})

// ─── 生命周期：卸载清理 ─────────────────────────────────────────
onBeforeUnmount(() => {
  stopAlertPolling()
  // 移除网络状态监听
  window.removeEventListener('online', handleNetworkChange)
  window.removeEventListener('offline', handleNetworkChange)
  resizeObserver?.disconnect()
  resizeObserver = null
  radarChart?.dispose()
  trendChart?.dispose()
  radarChart = null
  trendChart = null
})
</script>

<style scoped>
.dashboard-container {
  background-color: #f0f2f5;
  min-height: calc(100vh - 100px);
  padding: 4px;
}

/* ═══ KPI 指标卡 ═══ */
.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  border-radius: 8px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
}

.kpi-body {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kpi-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-danger .kpi-icon { background: rgba(245, 108, 108, 0.12); color: #f56c6c; }
.kpi-warning .kpi-icon { background: rgba(230, 162, 60, 0.12); color: #e6a23c; }
.kpi-success .kpi-icon { background: rgba(103, 194, 58, 0.12); color: #67c23a; }
.kpi-primary .kpi-icon { background: rgba(30, 96, 145, 0.12); color: #1e6091; }

.kpi-content {
  flex: 1;
  min-width: 0;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
  font-family: 'DIN Alternate', 'Helvetica Neue', sans-serif;
}

.kpi-unit {
  font-size: 14px;
  font-weight: 500;
  color: #909399;
  margin-left: 4px;
}

.kpi-label {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
}

.kpi-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #ebeef5;
}

.kpi-trend {
  font-size: 12px;
  font-weight: 600;
}

.kpi-trend.up { color: #f56c6c; }
.kpi-trend.down { color: #67c23a; }
.kpi-trend.flat { color: #909399; }

/* ═══ 面板卡通用 ═══ */
.mid-row,
.bottom-row,
.scatter-row,
.widget-row {
  margin-bottom: 20px;
}

.panel-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-weight: 600;
  color: #303133;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.panel-title .el-icon {
  color: #1e6091;
}

.legend-inline {
  font-size: 12px;
  color: #606266;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 2px;
}

.legend-benbu { background: #1e6091; }
.legend-shiyan { background: #2a9d8f; }

/* ═══ 告警流 ═══ */
.alert-stream {
  max-height: 380px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.alert-item {
  padding: 12px 14px;
  border-radius: 6px;
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  transition: transform 0.15s ease;
}

.alert-item:hover {
  transform: translateX(2px);
}

.alert-danger {
  border-left-color: #f56c6c;
  background: #fef0f0;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.alert-student {
  font-weight: 600;
  color: #303133;
  font-size: 15px;
}

.alert-issue {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
  line-height: 1.5;
}

.alert-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

.alert-rdi {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  color: #f56c6c;
}

/* ═══ ECharts 容器 ═══ */
.echart-dom {
  width: 100%;
}

.radar-chart {
  height: 400px;
}

.trend-chart {
  height: 320px;
}

/* ═══ 离线降级视觉 ═══ */
.chart-relative-container {
  position: relative;
  width: 100%;
}

/* 离线状态下让底层图表产生脱色模糊效果，突出上方警告 */
.chart-dimmed {
  filter: grayscale(40%) opacity(60%);
  transition: filter 0.5s ease;
}

/* 离线占位图层 — 仅在无缓存时显示 */
.chart-offline-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.7);
  z-index: 10;
}

/* 脉动动画 — 提升断网重连时的视觉感知 */
.animate-pulse {
  animation: offline-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes offline-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ═══ 实时脉冲动画 ═══ */
.pulse-icon {
  margin-right: 2px;
  animation: pulse-alarm 1.5s ease-in-out infinite;
}

@keyframes pulse-alarm {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ═══ 滚动条美化 ═══ */
.alert-stream::-webkit-scrollbar {
  width: 6px;
}

.alert-stream::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 3px;
}

.alert-stream::-webkit-scrollbar-thumb:hover {
  background: #c0c4cc;
}
</style>
