<template>
  <div class="rdi-dashboard-container">
    <!-- ═══ 顶部：统计概览卡 ═══ -->
    <el-row :gutter="12" class="summary-row">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card stat-total">
          <div class="stat-value">{{ metrics?.summary.total_students ?? '--' }}</div>
          <div class="stat-label">活跃预警学生</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card stat-risk">
          <div class="stat-value">{{ metrics?.summary.at_risk_count ?? '--' }}</div>
          <div class="stat-label">风险学生总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card stat-intervention">
          <div class="stat-value">{{ metrics?.summary.by_risk_level.intervention ?? '--' }}</div>
          <div class="stat-label">需干预</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card stat-veto">
          <div class="stat-value">{{ metrics?.sigma_funnel.veto ?? '--' }}</div>
          <div class="stat-label">3σ 一票否决</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 三栏主区域 ═══ -->
    <el-row :gutter="12" class="main-row">
      <!-- ═══ 左栏：四维雷达图 ═══ -->
      <el-col :span="8">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span class="panel-title">四维风险雷达</span>
              <el-tooltip content="psych 轴外凸 = 心理危机集群" placement="top">
                <el-icon class="info-icon"><InfoFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <div ref="radarChartRef" class="chart-dom radar-chart"></div>
          <div class="radar-legend">
            <span class="legend-item"><i class="dot avg-dot"></i> 均值</span>
            <span class="legend-item"><i class="dot max-dot"></i> 最大值</span>
          </div>
        </el-card>
      </el-col>

      <!-- ═══ 中栏：危机事件流 ═══ -->
      <el-col :span="8">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span class="panel-title">危机事件流</span>
              <el-tag size="small" type="danger" effect="dark">{{ eventStream.length }} 条</el-tag>
            </div>
          </template>
          <div class="event-stream" v-loading="loading">
            <div
              v-for="event in eventStream"
              :key="event.student_id"
              class="event-item"
              :class="`border-${event.risk_color}`"
              @click="handleEventClick(event)"
            >
              <div class="event-left">
                <div class="event-avatar" :class="`bg-${event.risk_color}`">
                  {{ event.student_name.charAt(0) }}
                </div>
              </div>
              <div class="event-body">
                <div class="event-top-row">
                  <span class="event-name">{{ event.student_name }}</span>
                  <span class="event-class">{{ event.class_name }}</span>
                </div>
                <div class="event-mid-row">
                  <span class="event-rdi">RDI {{ event.rdi_score.toFixed(2) }}</span>
                  <el-tag
                    size="small"
                    :type="colorToTagType(event.risk_color)"
                    effect="dark"
                    class="trigger-tag"
                  >
                    {{ formatTrigger(event.trigger_factor) }}
                  </el-tag>
                </div>
                <div class="event-bottom-row" v-if="event.psych_veto_triggered">
                  <span class="veto-badge">3σ VETO: {{ event.veto_dimension }}</span>
                </div>
              </div>
            </div>
            <el-empty v-if="!loading && eventStream.length === 0" description="当前无活跃预警" />
          </div>
        </el-card>
      </el-col>

      <!-- ═══ 右栏：σ区间漏斗 ═══ -->
      <el-col :span="8">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span class="panel-title">σ 区间分布漏斗</span>
            </div>
          </template>
          <div ref="funnelChartRef" class="chart-dom funnel-chart"></div>
          <div class="funnel-legend">
            <div class="legend-row">
              <span class="legend-item"><i class="dot green-dot"></i> Normal (&lt;1σ)</span>
              <span class="legend-count">{{ metrics?.sigma_funnel.normal ?? 0 }}</span>
            </div>
            <div class="legend-row">
              <span class="legend-item"><i class="dot yellow-dot"></i> Watch (1-2σ)</span>
              <span class="legend-count">{{ metrics?.sigma_funnel.watch ?? 0 }}</span>
            </div>
            <div class="legend-row">
              <span class="legend-item"><i class="dot orange-dot"></i> Warning (2-3σ)</span>
              <span class="legend-count">{{ metrics?.sigma_funnel.warning ?? 0 }}</span>
            </div>
            <div class="legend-row">
              <span class="legend-item"><i class="dot red-dot"></i> Veto (≥3σ)</span>
              <span class="legend-count">{{ metrics?.sigma_funnel.veto ?? 0 }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 底部：班级热力图 + TOP风险学生 ═══ -->
    <el-row :gutter="12" class="bottom-row">
      <el-col :span="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span class="panel-title">班级×σ区间交叉热力</span>
            </div>
          </template>
          <el-table
            :data="metrics?.class_heatmap ?? []"
            size="small"
            stripe
            style="width: 100%"
            :max-height="280"
          >
            <el-table-column prop="class_name" label="班级" width="100" fixed />
            <el-table-column prop="total" label="总计" width="70" />
            <el-table-column label="Normal (<1σ)" width="110">
              <template #default="{ row }">
                <span :class="{ 'hot-cell': row.normal > 0 }">{{ row.normal }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Watch (1-2σ)" width="110">
              <template #default="{ row }">
                <span :class="{ 'warm-cell': row.watch > 0 }">{{ row.watch }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Warning (2-3σ)" width="120">
              <template #default="{ row }">
                <span :class="{ 'hot-cell': row.warning > 0 }">{{ row.warning }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Veto (≥3σ)" width="100">
              <template #default="{ row }">
                <span :class="{ 'veto-cell': row.veto > 0 }">{{ row.veto }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span class="panel-title">TOP 风险学生 (四维分解)</span>
            </div>
          </template>
          <el-table
            :data="metrics?.top_risk_students ?? []"
            size="small"
            stripe
            style="width: 100%"
            :max-height="280"
          >
            <el-table-column prop="student_name" label="姓名" width="80" fixed />
            <el-table-column prop="class_name" label="班级" width="80" />
            <el-table-column prop="rdi_score" label="RDI" width="65" sortable>
              <template #default="{ row }">
                <span class="rdi-text">{{ row.rdi_score.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="B" width="50" title="行为偏离">
              <template #default="{ row }">
                <span :class="deviationClass(row.behavior_deviation)">{{ row.behavior_deviation.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="A" width="50" title="考勤偏离">
              <template #default="{ row }">
                <span :class="deviationClass(row.attendance_deviation)">{{ row.attendance_deviation.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="S" width="50" title="学业偏离">
              <template #default="{ row }">
                <span :class="deviationClass(row.score_deviation)">{{ row.score_deviation.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="P" width="50" title="心理偏离">
              <template #default="{ row }">
                <span :class="deviationClass(row.psych_deviation, row.psych_veto_triggered)">{{ row.psych_deviation.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="top_dimension" label="主因" width="70">
              <template #default="{ row }">
                <el-tag size="small" :type="dimensionTagType(row.top_dimension)">
                  {{ row.top_dimension }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import '@/utils/echarts'
import {
  getDashboardMetrics,
  type DashboardMetricsOut,
  type DashboardEventItem,
} from '@/api/rdi'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const metrics = ref<DashboardMetricsOut | null>(null)

// ECharts DOM refs
const radarChartRef = ref<HTMLDivElement | null>(null)
const funnelChartRef = ref<HTMLDivElement | null>(null)

// ECharts instances
let radarChart: ReturnType<typeof echarts.init> | null = null
let funnelChart: ReturnType<typeof echarts.init> | null = null

// ─── Computed-like getters ─────────────────────────────────────
const eventStream = ref<DashboardEventItem[]>([])

// ─── 加载看板数据 ───────────────────────────────────────────────
const loadDashboard = async () => {
  loading.value = true
  try {
    const params: { class_id?: number; grade_id?: number } = {}
    if (userStore.currentRole === 'CLASS_TEACHER' && userStore.userInfo?.class_id) {
      params.class_id = userStore.userInfo.class_id
    }
    const data = await getDashboardMetrics(params)
    metrics.value = data
    eventStream.value = data.event_stream ?? []

    await nextTick()
    renderRadarChart(data)
    renderFunnelChart(data)
  } catch (err) {
    console.error('[RDI Dashboard] load failed', err)
    ElMessage.error('无法加载风险看板数据')
  } finally {
    loading.value = false
  }
}

// ─── 四维雷达图 ─────────────────────────────────────────────────
const DIMENSION_LABELS: Record<string, string> = {
  behavior: '行为偏离 (Behavior)',
  attendance: '考勤偏离 (Attendance)',
  score: '学业偏离 (Academic)',
  psych: '心理偏离 (Psych)',
}

const renderRadarChart = (data: DashboardMetricsOut) => {
  if (!radarChartRef.value) return
  if (!radarChart) {
    radarChart = echarts.init(radarChartRef.value)
  }

  const dims = data.radar.dimensions
  const indicators = dims.map((d) => ({
    name: DIMENSION_LABELS[d] || d,
    max: Math.max(...data.radar.max, 5) * 1.2,
  }))

  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const vals = params.value
        let html = '<div style="font-weight:600;margin-bottom:4px">四维风险分解</div>'
        dims.forEach((d, i) => {
          html += `<div>${DIMENSION_LABELS[d] || d}: ${vals[i]?.toFixed(2)}σ</div>`
        })
        return html
      },
    },
    radar: {
      indicator: indicators,
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      splitLine: { lineStyle: { color: '#e4e7ed' } },
      axisName: { color: '#606266', fontSize: 11 },
      center: ['50%', '52%'],
      radius: '68%',
    },
    series: [
      {
        name: '最大值',
        type: 'radar',
        data: [
          {
            value: data.radar.max,
            name: '最大值 (Max)',
            areaStyle: { color: 'rgba(245, 108, 108, 0.12)' },
            lineStyle: { color: '#f56c6c', width: 2, type: 'dashed' },
            itemStyle: { color: '#f56c6c' },
            symbolSize: 6,
          },
        ],
      },
      {
        name: '均值',
        type: 'radar',
        data: [
          {
            value: data.radar.avg,
            name: '均值 (Avg)',
            areaStyle: { color: 'rgba(64, 158, 255, 0.2)' },
            lineStyle: { color: '#409eff', width: 2 },
            itemStyle: { color: '#409eff' },
            symbolSize: 6,
          },
        ],
      },
    ],
  }
  radarChart.setOption(option, true)
}

// ─── σ区间漏斗图 ────────────────────────────────────────────────
const renderFunnelChart = (data: DashboardMetricsOut) => {
  if (!funnelChartRef.value) return
  if (!funnelChart) {
    funnelChart = echarts.init(funnelChartRef.value)
  }

  const f = data.sigma_funnel
  const funnelData = [
    { value: f.normal, name: 'Normal (<1σ)', itemStyle: { color: '#67c23a' } },
    { value: f.watch, name: 'Watch (1-2σ)', itemStyle: { color: '#e6a23c' } },
    { value: f.warning, name: 'Warning (2-3σ)', itemStyle: { color: '#f56c6c' } },
    { value: f.veto, name: 'Veto (≥3σ)', itemStyle: { color: '#1a1a2e' } },
  ].filter((d) => d.value > 0)

  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} 人',
    },
    series: [
      {
        type: 'funnel',
        left: '10%',
        right: '10%',
        top: '5%',
        bottom: '5%',
        width: '80%',
        min: 0,
        max: Math.max(f.normal, f.watch, f.warning, f.veto, 1),
        minSize: '20%',
        maxSize: '100%',
        sort: 'descending',
        gap: 4,
        label: {
          show: true,
          position: 'inside',
          fontSize: 13,
          fontWeight: 'bold',
          color: '#fff',
        },
        labelLine: { show: false },
        itemStyle: {
          borderColor: '#fff',
          borderWidth: 1,
        },
        emphasis: {
          label: { fontSize: 15 },
        },
        data: funnelData.length > 0 ? funnelData : [{ value: 0, name: '无数据', itemStyle: { color: '#c0c4cc' } }],
      },
    ],
  }
  funnelChart.setOption(option, true)
}

// ─── 工具函数 ───────────────────────────────────────────────────
const colorToTagType = (color: string): 'success' | 'warning' | 'danger' | 'info' => {
  switch (color) {
    case 'black': return 'info'
    case 'red': return 'danger'
    case 'orange': return 'warning'
    case 'yellow': return 'warning'
    case 'green': return 'success'
    default: return 'info'
  }
}

const formatTrigger = (trigger: string): string => {
  if (trigger.startsWith('psych_veto:')) return `3σ ${trigger.split(':')[1]}`
  if (trigger === 'high_rdi') return '高RDI'
  if (trigger === 'escalating') return '升级中'
  if (trigger === 'moderate_rdi') return '中等RDI'
  if (trigger === 'baseline') return '基线'
  return trigger
}

const dimensionTagType = (dim: string): 'success' | 'warning' | 'danger' | 'info' => {
  switch (dim) {
    case 'psych': return 'danger'
    case 'behavior': return 'warning'
    case 'score': return 'info'
    case 'attendance': return 'success'
    default: return 'info'
  }
}

const deviationClass = (value: number, isVeto = false): string => {
  if (isVeto || value >= 3) return 'dev-veto'
  if (value >= 2) return 'dev-high'
  if (value >= 1) return 'dev-mid'
  return 'dev-low'
}

// ─── 事件流点击 → 跳转 AI 处方 ──────────────────────────────────
const handleEventClick = (event: DashboardEventItem) => {
  router.push(`/ai-prescription?student_id=${event.student_id}`)
}

// ─── 自适应缩放 ─────────────────────────────────────────────────
const handleResize = () => {
  radarChart?.resize()
  funnelChart?.resize()
}

// ─── 生命周期 ───────────────────────────────────────────────────
onMounted(() => {
  loadDashboard()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  radarChart?.dispose()
  funnelChart?.dispose()
  radarChart = null
  funnelChart = null
})
</script>

<style scoped>
.rdi-dashboard-container {
  background: #f0f2f5;
  min-height: calc(100vh - 100px);
  padding-bottom: 8px;
}

/* ── 顶部统计卡 ── */
.summary-row {
  margin-bottom: 12px;
}
.stat-card {
  text-align: center;
  padding: 8px 0;
  border-radius: 8px;
  border: none;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  font-family: 'Courier New', monospace;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}
.stat-total .stat-value { color: #409eff; }
.stat-risk .stat-value { color: #e6a23c; }
.stat-intervention .stat-value { color: #f56c6c; }
.stat-veto .stat-value { color: #1a1a2e; }

/* ── 面板卡片 ── */
.panel-card {
  border-radius: 8px;
  height: 100%;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-title {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}
.info-icon {
  color: #909399;
  cursor: help;
}

/* ── 主区域行 ── */
.main-row {
  margin-bottom: 12px;
}

/* ── 图表 DOM ── */
.chart-dom {
  width: 100%;
}
.radar-chart {
  height: 320px;
}
.funnel-chart {
  height: 280px;
}

/* ── 雷达图图例 ── */
.radar-legend {
  display: flex;
  justify-content: center;
  gap: 20px;
  padding-top: 4px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #606266;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.avg-dot { background: #409eff; }
.max-dot { background: #f56c6c; opacity: 0.6; }
.green-dot { background: #67c23a; }
.yellow-dot { background: #e6a23c; }
.orange-dot { background: #f56c6c; }
.red-dot { background: #1a1a2e; }

/* ── 漏斗图例 ── */
.funnel-legend {
  padding: 8px 12px;
}
.legend-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
}
.legend-count {
  font-weight: 700;
  font-family: 'Courier New', monospace;
  color: #303133;
}

/* ── 危机事件流 ── */
.event-stream {
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}
.event-stream::-webkit-scrollbar {
  width: 4px;
}
.event-stream::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 2px;
}
.event-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  border-left: 3px solid transparent;
}
.event-item:hover {
  background: #f5f7fa;
}
.event-item.border-black { border-left-color: #1a1a2e; }
.event-item.border-red { border-left-color: #f56c6c; }
.event-item.border-orange { border-left-color: #e6a23c; }
.event-item.border-yellow { border-left-color: #f0c040; }
.event-item.border-green { border-left-color: #67c23a; }

.event-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  flex-shrink: 0;
}
.event-avatar.bg-black { background: #1a1a2e; }
.event-avatar.bg-red { background: #f56c6c; }
.event-avatar.bg-orange { background: #e6a23c; }
.event-avatar.bg-yellow { background: #f0c040; }
.event-avatar.bg-green { background: #67c23a; }

.event-body {
  flex: 1;
  min-width: 0;
}
.event-top-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
}
.event-name {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}
.event-class {
  font-size: 12px;
  color: #909399;
}
.event-mid-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.event-rdi {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #606266;
}
.trigger-tag {
  font-size: 11px;
}
.event-bottom-row {
  margin-top: 4px;
}
.veto-badge {
  display: inline-block;
  background: #1a1a2e;
  color: #fff;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* ── 底部行 ── */
.bottom-row {
  margin-bottom: 0;
}

/* ── 热力表格单元格 ── */
:deep(.hot-cell) {
  color: #e6a23c;
  font-weight: 600;
}
:deep(.warm-cell) {
  color: #f0c040;
  font-weight: 600;
}
:deep(.veto-cell) {
  color: #f56c6c;
  font-weight: 700;
  background: rgba(245, 108, 108, 0.08);
  padding: 2px 6px;
  border-radius: 3px;
}
:deep(.rdi-text) {
  font-family: 'Courier New', monospace;
  font-weight: 700;
  color: #f56c6c;
}

/* ── 偏离度色彩 ── */
:deep(.dev-veto) {
  color: #1a1a2e;
  font-weight: 700;
  background: rgba(26, 26, 46, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
}
:deep(.dev-high) {
  color: #f56c6c;
  font-weight: 600;
}
:deep(.dev-mid) {
  color: #e6a23c;
}
:deep(.dev-low) {
  color: #67c23a;
}
</style>
