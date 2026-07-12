<template>
  <div class="zscore-container">
    <div class="panel-header">
      <div class="header-title">
        <span class="icon">📊</span>
        <h3>全校行政班级 × 学科 Z-Score 强弱热力分布矩阵</h3>
      </div>
      <button @click="fetchMatrixData" :disabled="loading" class="refresh-btn">
        {{ loading ? '矩阵重构中...' : '同步最新大盘' }}
      </button>
    </div>

    <div class="chart-wrapper">
      <div v-if="loading" class="chart-loader">
        <div class="spinner"></div>
        <p>正在横向拉取班级轴... 正在纵向级联标准差...</p>
      </div>

      <div v-show="!loading && hasData" ref="heatmapChartRef" class="main-heatmap"></div>

      <div v-if="!loading && !hasData" class="empty-state">
        <p>暂无有效的多班并网成绩数据，请先前往数据接入端导入 Excel</p>
      </div>
    </div>

    <!-- Global Subject Stats -->
    <div v-if="hasData && globalStats" class="stats-panel">
      <h4 class="stats-title">全校大盘学科统计 (μ / σ)</h4>
      <div class="stats-grid">
        <div v-for="(stats, subject) in globalStats" :key="subject" class="stat-chip">
          <span class="stat-chip-name">{{ subjectMap[subject as string] || subject }}</span>
          <span class="stat-chip-val">μ={{ stats.mean }} σ={{ stats.std }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { getZscoreMatrix } from '@/api/dataAdapter'

const props = defineProps<{
  examId: number
}>()

const loading = ref<boolean>(false)
const hasData = ref<boolean>(false)
const globalStats = ref<Record<string, { mean: number; std: number }> | null>(null)
const heatmapChartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

const subjectMap: Record<string, string> = {
  chinese: '语文', math: '数学', english: '英语',
  physics: '物理', history: '历史', chemistry: '化学',
  biology: '生物', politics: '政治', geography: '地理',
}

const fetchMatrixData = async () => {
  if (!props.examId) return
  loading.value = true
  try {
    const res = await getZscoreMatrix(props.examId)
    if (res && res.status === 'success') {
      const payload = res.data
      globalStats.value = payload.global_subject_stats || null
      if (payload.classes && payload.classes.length > 0) {
        hasData.value = true
        await nextTick()
        renderHeatmap(payload)
      } else {
        hasData.value = false
      }
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message || '未知中断'
    ElMessage.error(`Z-Score 矩阵加载溃缩: ${detail}`)
  } finally {
    loading.value = false
  }
}

const renderHeatmap = (data: {
  classes: string[]
  subjects: string[]
  matrix_data: [number, number, number][]
}) => {
  if (!heatmapChartRef.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(heatmapChartRef.value)
  }

  const formattedSubjects = data.subjects.map((sub: string) => subjectMap[sub] || sub)

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 13 },
      formatter: function (params: any) {
        const classStr = data.classes[params.value[0]]
        const subStr = formattedSubjects[params.value[1]]
        const zValue = params.value[2]
        let evaluation = '与全校持平'
        if (zValue > 0) evaluation = `领先全校平均线 ${zValue} 个标准差`
        if (zValue < 0) evaluation = `落后全校平均线 ${Math.abs(zValue)} 个标准差`

        return `
          <div style="font-weight:600;margin-bottom:4px;">${classStr}</div>
          <div style="color:#8b949e;">学科: <span style="color:#e6edf3">${subStr}</span></div>
          <div style="color:#8b949e;">平均Z分: <span style="color:${zValue >= 0 ? '#2dd4bf' : '#f85149'};font-weight:bold">${zValue}</span></div>
          <div style="font-size:11px;color:#8b949e;margin-top:4px;border-top:1px solid #30363d;padding-top:4px;">${evaluation}</div>
        `
      },
    },
    grid: {
      top: '8%',
      left: '4%',
      right: '4%',
      bottom: '18%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: data.classes,
      splitArea: {
        show: true,
        areaStyle: { color: ['rgba(22,27,34,0.3)', 'rgba(13,17,23,0.3)'] },
      },
      axisLabel: { color: '#8b949e', rotate: 25, fontSize: 12 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    yAxis: {
      type: 'category',
      data: formattedSubjects,
      splitArea: { show: true },
      axisLabel: { color: '#c9d1d9', fontWeight: 'bold', fontSize: 12 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    visualMap: {
      min: -2,
      max: 2,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '2%',
      inRange: {
        color: ['#f85149', '#3d1414', '#161b22', '#1a3a5c', '#2dd4bf'],
      },
      textStyle: { color: '#8b949e', fontSize: 11 },
      text: ['强势 (Z≥+2)', '薄弱 (Z≤-2)'],
      itemWidth: 15,
      itemHeight: 140,
    },
    series: [
      {
        name: 'Class Z-Score',
        type: 'heatmap',
        data: data.matrix_data,
        label: {
          show: true,
          color: '#e6edf3',
          fontSize: 12,
          fontWeight: 'bold',
          formatter: function (p: any) {
            const v = p.value[2]
            return v === 0 ? '0.0' : String(v)
          },
        },
        itemStyle: {
          borderColor: '#0d1117',
          borderWidth: 2,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
            borderColor: '#58a6ff',
            borderWidth: 2,
          },
        },
      },
    ],
  }

  chartInstance.setOption(option, true)
}

const handleResize = () => {
  chartInstance?.resize()
}

watch(
  () => props.examId,
  (newId) => {
    if (newId) fetchMatrixData()
  }
)

onMounted(() => {
  fetchMatrixData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.zscore-container {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 24px;
  margin-top: 24px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #30363d;
  padding-bottom: 16px;
  margin-bottom: 20px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title .icon {
  font-size: 20px;
}

.header-title h3 {
  font-size: 17px;
  font-weight: 600;
  color: #e6edf3;
  margin: 0;
}

.refresh-btn {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: #30363d;
  border-color: #8b949e;
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chart-wrapper {
  position: relative;
  min-height: 400px;
  background: #0d1117;
  border-radius: 8px;
  border: 1px solid #30363d;
  overflow: hidden;
}

.main-heatmap {
  width: 100%;
  height: 450px;
}

.chart-loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: absolute;
  inset: 0;
  background: rgba(13, 17, 23, 0.8);
  gap: 16px;
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(88, 166, 255, 0.2);
  border-bottom-color: #58a6ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.chart-loader p {
  color: #58a6ff;
  font-size: 13px;
  animation: pulse 1.5s infinite ease-in-out;
  margin: 0;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: #8b949e;
  font-size: 14px;
}

.empty-state p {
  margin: 0;
}

/* Stats Panel */
.stats-panel {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #30363d;
}

.stats-title {
  font-size: 13px;
  font-weight: 600;
  color: #2dd4bf;
  margin: 0 0 12px;
}

.stats-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  background: #0d1117;
  border: 1px solid #30363d;
}

.stat-chip-name {
  font-size: 12px;
  font-weight: 600;
  color: #e6edf3;
}

.stat-chip-val {
  font-size: 11px;
  font-family: monospace;
  color: #8b949e;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
}
</style>
