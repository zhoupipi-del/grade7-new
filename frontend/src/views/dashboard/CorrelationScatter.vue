<template>
  <div class="scatter-container">
    <!-- ═══ 头部：标题 + 学期选择 + 在线状态 ═══ -->
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <span class="panel-title">
            <el-icon><DataLine /></el-icon>
            德学双优四象限矩阵
            <span class="title-sub">德育分 × 学业分 跨库聚合</span>
          </span>
          <div class="header-actions">
            <el-select
              v-model="currentSemester"
              size="small"
              placeholder="选择学期"
              style="width: 160px"
              @change="onSemesterChange"
            >
              <el-option
                v-for="sem in semesterOptions"
                :key="sem.value"
                :label="sem.label"
                :value="sem.value"
              />
            </el-select>
            <el-tag v-if="!isOffline" type="success" effect="plain" size="small">
              <el-icon class="pulse-dot"><CircleCheck /></el-icon>
              在线 · 实时
            </el-tag>
            <el-tag v-else type="warning" effect="dark" size="small" class="animate-pulse">
              ⚠️ 离线 · 缓存
            </el-tag>
          </div>
        </div>
      </template>

      <!-- ═══ 四象限统计卡片行 ═══ -->
      <el-row :gutter="12" class="quadrant-stats-row">
        <el-col :span="6" v-for="q in quadrantStats" :key="q.code">
          <div class="quadrant-stat-card" :style="{ borderLeftColor: q.color }">
            <div class="qstat-header">
              <span class="qstat-code" :style="{ color: q.color }">{{ q.code }}</span>
              <span class="qstat-label">{{ q.label }}</span>
            </div>
            <div class="qstat-body">
              <div class="qstat-count">
                <span class="qstat-num">{{ q.count }}</span>
                <span class="qstat-unit">人</span>
              </div>
              <div class="qstat-pct">{{ q.percentage }}%</div>
            </div>
            <div class="qstat-priority" v-if="q.priority <= 2">
              <el-tag size="small" :type="q.priority === 1 ? 'danger' : 'warning'" effect="dark">
                {{ q.priority === 1 ? '优先干预' : '行为矫正' }}
              </el-tag>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- ═══ ECharts 散点图主体 ═══ -->
      <div class="chart-relative-container" v-loading="loading">
        <div ref="scatterChartRef" class="echart-dom scatter-chart" :class="{ 'chart-dimmed': isOffline }"></div>
        <div v-if="isOffline && !hasCache" class="chart-offline-overlay">
          <el-empty description="数据流链路断开，正在尝试重连..." :image-size="80" />
        </div>
        <div v-if="!loading && !isOffline && points.length === 0" class="chart-empty-overlay">
          <el-empty description="当前学期暂无德学双优数据" :image-size="80" />
        </div>
      </div>

      <!-- ═══ 图例说明 ═══ -->
      <div class="legend-footer">
        <div class="legend-item">
          <span class="legend-line legend-x"></span>
          <span class="legend-text">X轴 · 德育量化总分（来自 Wings3 StudentScore）</span>
        </div>
        <div class="legend-item">
          <span class="legend-line legend-y"></span>
          <span class="legend-text">Y轴 · 学业平均分（跨库拉取自 grade7_new.scores）</span>
        </div>
        <div class="legend-item">
          <span class="legend-dash"></span>
          <span class="legend-text">虚线 = 中位数（象限分割线，后端预计算）</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { DataLine, CircleCheck } from '@element-plus/icons-vue'
import {
  getCorrelationScatter,
  QUADRANT_LABELS,
  QUADRANT_PRIORITY,
  type ScatterPoint,
  type ScatterMedians,
  type QuadrantType,
  type CorrelationScatterResponse,
} from '@/api/dashboard'

// ─── 学期选项（与后端 semester 参数对齐） ────────────────────────
const semesterOptions = [
  { label: '2025-2026 第二学期', value: '2025-2026-2' },
  { label: '2025-2026 第一学期', value: '2025-2026-1' },
]
const currentSemester = ref('2025-2026-2')

// ─── 响应式数据 ─────────────────────────────────────────────────
const points = ref<ScatterPoint[]>([])
const medians = ref<ScatterMedians>({ moral_median: 0, math_median: 0 })
const quadrantsMeta = ref<Record<string, string>>({})

const loading = ref(true)

// ─── 离线降级状态 ───────────────────────────────────────────────
const isOffline = ref(!navigator.onLine)
const hasCache = ref(false)
const CACHE_KEY_SCATTER = 'wings3_dashboard_scatter_snapshot'

interface ScatterSnapshot {
  points: ScatterPoint[]
  medians: ScatterMedians
  quadrantsMeta: Record<string, string>
  semester: string
  savedAt: number
}

// ─── ECharts 实例 ───────────────────────────────────────────────
const scatterChartRef = ref<HTMLDivElement | null>(null)
let scatterChart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

// ─── 四象限统计卡片计算属性 ─────────────────────────────────────
interface QuadrantStat {
  code: QuadrantType
  label: string
  color: string
  priority: number
  count: number
  percentage: string
}

const quadrantStats = computed<QuadrantStat[]>(() => {
  const total = points.value.length
  const codes: QuadrantType[] = ['Q3', 'Q2', 'Q4', 'Q1'] // 按优先级排序展示
  return codes.map(code => {
    const count = points.value.filter(p => p.quadrant === code).length
    const pct = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0'
    return {
      code,
      label: QUADRANT_LABELS[code].name,
      color: QUADRANT_LABELS[code].color,
      priority: QUADRANT_PRIORITY[code],
      count,
      percentage: pct,
    }
  })
})

// ─── 离线快照持久化 ─────────────────────────────────────────────
const saveScatterCache = () => {
  try {
    const snapshot: ScatterSnapshot = {
      points: points.value,
      medians: medians.value,
      quadrantsMeta: quadrantsMeta.value,
      semester: currentSemester.value,
      savedAt: Date.now(),
    }
    localStorage.setItem(CACHE_KEY_SCATTER, JSON.stringify(snapshot))
    hasCache.value = true
  } catch {
    // localStorage 配额满或隐私模式 — 静默降级
  }
}

const tryLoadScatterCache = (): boolean => {
  try {
    const cached = localStorage.getItem(CACHE_KEY_SCATTER)
    if (!cached) return false
    const snapshot = JSON.parse(cached) as ScatterSnapshot
    if (!snapshot.points?.length) return false

    points.value = snapshot.points
    medians.value = snapshot.medians
    quadrantsMeta.value = snapshot.quadrantsMeta
    // 如果缓存的学期与当前不同，不强制覆盖当前学期选择
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
    // 进入离线: 尝试从缓存恢复
    const restored = tryLoadScatterCache()
    if (restored) {
      nextTick(() => initScatterChart())
    }
  } else if (wasOffline) {
    // 从离线恢复在线: 立即拉取最新数据
    fetchScatterData()
  }
}

// ─── 数据拉取 ───────────────────────────────────────────────────
const fetchScatterData = async () => {
  loading.value = true
  try {
    const resp = await getCorrelationScatter(currentSemester.value)
    const data: CorrelationScatterResponse = resp.data
    points.value = data.points
    medians.value = data.medians
    quadrantsMeta.value = data.quadrants

    saveScatterCache()
    isOffline.value = false

    await nextTick()
    initScatterChart()
  } catch {
    // 后端断开或超时, 启动前端降级兜底
    isOffline.value = true
    const restored = tryLoadScatterCache()
    if (restored) {
      await nextTick()
      initScatterChart()
    }
  } finally {
    loading.value = false
  }
}

// ─── 学期切换 ───────────────────────────────────────────────────
const onSemesterChange = () => {
  fetchScatterData()
}

// ─── ECharts 散点图初始化 ───────────────────────────────────────
const initScatterChart = () => {
  if (!scatterChartRef.value) return
  if (!scatterChart) {
    scatterChart = echarts.init(scatterChartRef.value)
  }

  const mMed = medians.value.moral_median
  const aMed = medians.value.math_median

  // 按象限分组数据点
  const quadrantCodes: QuadrantType[] = ['Q1', 'Q2', 'Q3', 'Q4']
  const series = quadrantCodes.map(code => {
    const color = QUADRANT_LABELS[code].color
    const qPoints = points.value.filter(p => p.quadrant === code)
    return {
      name: `${code} · ${QUADRANT_LABELS[code].name}`,
      type: 'scatter',
      data: qPoints.map(p => ({
        value: [p.x_moral_score, p.y_math_score],
        student_id: p.student_id,
        student_name: p.student_name,
        quadrant: p.quadrant,
        quadrant_label: QUADRANT_LABELS[p.quadrant].name,
        quadrant_desc: QUADRANT_LABELS[p.quadrant].desc,
        top_blind_spots: p.top_blind_spots,
      })),
      symbolSize: 14,
      itemStyle: {
        color,
        borderColor: 'rgba(255, 255, 255, 0.8)',
        borderWidth: 1.5,
        shadowBlur: 6,
        shadowColor: `${color}66`,
      },
      emphasis: {
        scale: 1.4,
        itemStyle: {
          borderWidth: 2,
          shadowBlur: 12,
        },
      },
      // 中位数分割线 — 仅在 Q1 系列上挂载 markLine（避免重复）
      markLine: code === 'Q1' ? {
        silent: true,
        symbol: 'none',
        lineStyle: {
          type: 'dashed',
          color: '#909399',
          width: 1.5,
        },
        label: {
          show: true,
          position: 'end',
          formatter: (params: any) => {
            if (params.name === 'moralMed') return `德育中位 ${mMed.toFixed(1)}`
            if (params.name === 'mathMed') return `学业中位 ${aMed.toFixed(1)}`
            return ''
          },
          color: '#606266',
          fontSize: 11,
        },
        data: [
          { name: 'moralMed', xAxis: mMed },
          { name: 'mathMed', yAxis: aMed },
        ],
      } : undefined,
      // 象限背景淡色区域 — 仅在 Q3 系列上挂载 markArea（高危区高亮）
      markArea: code === 'Q3' ? {
        silent: true,
        itemStyle: {
          color: 'rgba(239, 68, 68, 0.06)',
          borderColor: 'rgba(239, 68, 68, 0.2)',
          borderWidth: 1,
        },
        data: [[
          { coord: [0, 0] },
          { coord: [mMed, aMed] },
        ]],
      } : undefined,
    }
  })

  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const d = params.data
        if (!d || !d.student_name) return ''
        const blindSpots = d.top_blind_spots?.length
          ? d.top_blind_spots.map((s: string) => `· ${s}`).join('<br/>')
          : '<span style="color:#c0c4cc">无显著盲点</span>'
        const quadrantColor = QUADRANT_LABELS[d.quadrant as QuadrantType].color
        return `
          <div style="font-weight:600;font-size:14px;color:#303133;margin-bottom:6px;">
            ${d.student_name}
          </div>
          <div style="font-size:12px;color:#606266;line-height:1.8;">
            <div>德育量化分：<b style="color:#3b82f6">${d.value[0].toFixed(1)}</b></div>
            <div>学业平均分：<b style="color:#10b981">${d.value[1].toFixed(1)}</b></div>
            <div style="margin-top:4px;">
              <span style="display:inline-block;padding:1px 6px;border-radius:3px;background:${quadrantColor};color:#fff;font-size:11px;">
                ${d.quadrant}
              </span>
              <span style="color:#909399;margin-left:4px;">${d.quadrant_label}</span>
            </div>
            <div style="margin-top:4px;font-size:11px;color:#909399;font-style:italic;">
              ${d.quadrant_desc || ''}
            </div>
            <div style="margin-top:6px;padding-top:6px;border-top:1px dashed #ebeef5;">
              <div style="color:#909399;font-size:11px;margin-bottom:2px;">德育盲点指标：</div>
              ${blindSpots}
            </div>
          </div>
        `
      },
    },
    legend: {
      show: true,
      bottom: 0,
      textStyle: { color: '#606266', fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12,
      icon: 'circle',
    },
    grid: {
      left: '4%',
      right: '4%',
      bottom: '12%',
      top: '8%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      name: '德育量化总分',
      nameLocation: 'middle',
      nameGap: 32,
      nameTextStyle: { color: '#303133', fontSize: 13, fontWeight: 600 },
      min: 0,
      max: 100,
      splitLine: { lineStyle: { type: 'dashed', color: '#ebeef5' } },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#606266' },
    },
    yAxis: {
      type: 'value',
      name: '学业平均分',
      nameLocation: 'middle',
      nameGap: 42,
      nameTextStyle: { color: '#303133', fontSize: 13, fontWeight: 600 },
      min: 0,
      max: 100,
      splitLine: { lineStyle: { type: 'dashed', color: '#ebeef5' } },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#606266' },
    },
    series,
  }

  scatterChart.setOption(option, true)
}

// ─── 生命周期：挂载 ─────────────────────────────────────────────
onMounted(async () => {
  // 注册浏览器网络状态监听
  window.addEventListener('online', handleNetworkChange)
  window.addEventListener('offline', handleNetworkChange)

  // 首次数据拉取
  await fetchScatterData()

  // ResizeObserver 自动跟随容器尺寸
  resizeObserver = new ResizeObserver(() => {
    scatterChart?.resize()
  })
  if (scatterChartRef.value) resizeObserver.observe(scatterChartRef.value)
})

// ─── 生命周期：卸载清理 ─────────────────────────────────────────
onBeforeUnmount(() => {
  window.removeEventListener('online', handleNetworkChange)
  window.removeEventListener('offline', handleNetworkChange)
  resizeObserver?.disconnect()
  resizeObserver = null
  scatterChart?.dispose()
  scatterChart = null
})
</script>

<style scoped>
.scatter-container {
  width: 100%;
}

/* ═══ 面板卡 ═══ */
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
  color: #409eff;
}

.title-sub {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  margin-left: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ═══ 四象限统计卡片 ═══ */
.quadrant-stats-row {
  margin-bottom: 18px;
}

.quadrant-stat-card {
  background: #fafbfc;
  border-radius: 6px;
  border-left: 4px solid #dcdfe6;
  padding: 14px 16px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.quadrant-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}

.qstat-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}

.qstat-code {
  font-size: 18px;
  font-weight: 700;
  font-family: 'DIN Alternate', 'Helvetica Neue', sans-serif;
}

.qstat-label {
  font-size: 12px;
  color: #606266;
  line-height: 1.3;
}

.qstat-body {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.qstat-count {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.qstat-num {
  font-size: 26px;
  font-weight: 700;
  color: #303133;
  font-family: 'DIN Alternate', 'Helvetica Neue', sans-serif;
  line-height: 1;
}

.qstat-unit {
  font-size: 12px;
  color: #909399;
}

.qstat-pct {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  font-family: 'Courier New', monospace;
}

.qstat-priority {
  margin-top: 8px;
}

/* ═══ ECharts 容器 ═══ */
.echart-dom {
  width: 100%;
}

.scatter-chart {
  height: 460px;
}

.chart-relative-container {
  position: relative;
  width: 100%;
}

/* 离线状态下让底层图表产生脱色模糊效果 */
.chart-dimmed {
  filter: grayscale(40%) opacity(60%);
  transition: filter 0.5s ease;
}

/* 离线占位图层 */
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

/* 空数据占位 */
.chart-empty-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.9);
  z-index: 5;
}

/* ═══ 图例说明 ═══ */
.legend-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  padding: 12px 4px 0;
  margin-top: 8px;
  border-top: 1px dashed #ebeef5;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
}

.legend-line {
  display: inline-block;
  width: 18px;
  height: 3px;
  border-radius: 2px;
}

.legend-x {
  background: linear-gradient(90deg, #3b82f6, #10b981);
}

.legend-y {
  background: linear-gradient(90deg, #10b981, #f59e0b);
}

.legend-dash {
  display: inline-block;
  width: 18px;
  height: 0;
  border-top: 2px dashed #909399;
}

.legend-text {
  color: #909399;
}

/* ═══ 脉动动画 ═══ */
.pulse-dot {
  margin-right: 2px;
  animation: pulse-online 2s ease-in-out infinite;
}

@keyframes pulse-online {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.animate-pulse {
  animation: offline-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes offline-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
