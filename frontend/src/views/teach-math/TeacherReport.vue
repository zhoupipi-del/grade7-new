<template>
  <div class="teacher-report-container" v-loading="loading">
    <!-- 顶部筛选控制栏 -->
    <div class="filter-header-zone">
      <div class="title-section">
        <span class="decorator-line"></span>
        <h2>数学学情智能化审题诊断看盘</h2>
      </div>
      <div class="controls-section">
        <el-select
          v-model="currentClass"
          placeholder="选择班级"
          size="default"
          @change="handleFilterChange"
          style="width: 200px"
        >
          <el-option
            v-for="item in classOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-radio-group
          v-model="timeRange"
          size="default"
          @change="handleFilterChange"
          class="ml-3"
        >
          <el-radio-button value="7d">近7天</el-radio-button>
          <el-radio-button value="30d">近30天</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 核心 KPI 看板行 -->
    <el-row :gutter="16" class="kpi-row-zone">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-meta">活跃分析学生</div>
          <div class="kpi-value text-primary">
            {{ kpiData.active_students }}<span class="unit">人</span>
          </div>
          <div class="kpi-footer">
            班级覆盖率 <span class="highlight">{{ calculateCoverage() }}%</span>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-meta">高频审题翻译次数</div>
          <div class="kpi-value text-success">
            {{ kpiData.total_translations }}<span class="unit">次</span>
          </div>
          <div class="kpi-footer">核心语义拆解高阶触发</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-meta">人均求助频次</div>
          <div class="kpi-value text-warning">
            {{ kpiData.avg_queries_per_student.toFixed(1) }}<span class="unit">次/人</span>
          </div>
          <div class="kpi-footer">高依赖度解题警惕线: 15次</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-meta">阅读理解 RDI 预警</div>
          <div class="kpi-value text-danger">
            {{ kpiData.risk_students_count }}<span class="unit">人</span>
          </div>
          <div class="kpi-footer">触发关键语义脱节拦截</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 动态图表复合分析区 -->
    <el-row :gutter="16" class="chart-row-zone">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="chart-container-card">
          <template #header>
            <div class="card-header">
              <span>审题需求演进与趋势波动（DeepSeek 引擎调用统计）</span>
            </div>
          </template>
          <div v-if="!hasTrendData" class="empty-chart-placeholder">
            <el-empty description="暂无趋势数据，请先引导学生使用审题助手" :image-size="80" />
          </div>
          <div ref="trendChartRef" class="echart-wrapper" v-show="hasTrendData"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="chart-container-card">
          <template #header>
            <div class="card-header">
              <span>班级前沿审题盲区排行（共性阅读障碍归因）</span>
            </div>
          </template>
          <div v-if="!hasBlindSpots" class="empty-chart-placeholder">
            <el-empty description="暂无盲区数据" :image-size="80" />
          </div>
          <div ref="blindSpotChartRef" class="echart-wrapper" v-show="hasBlindSpots"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 下钻明细：学生解题独立性与风险评估矩阵 -->
    <el-card shadow="never" class="table-container-card">
      <template #header>
        <div class="card-header flex justify-between items-center">
          <span>班级学生个体审题特征与 RDI 阻断指数</span>
          <el-tag type="info" size="small">点击表头可按提问频次或独立性指数排序</el-tag>
        </div>
      </template>

      <el-table
        :data="studentList"
        style="width: 100%"
        max-height="450"
        border
        stripe
        :default-sort="{ prop: 'query_count', order: 'descending' }"
      >
        <el-table-column
          prop="student_name"
          label="学生姓名"
          width="120"
          align="center"
          fixed
        />
        <el-table-column
          prop="query_count"
          label="审题提问次数"
          width="140"
          align="center"
          sortable
        />
        <el-table-column
          prop="top_blind_spot"
          label="首要思维盲区（核心干预点）"
          min-width="220"
        >
          <template #default="scope">
            <span class="blind-spot-text">{{
              scope.row.top_blind_spot || '暂无明显语意卡顿'
            }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="independence_score"
          label="独立解题指数"
          width="180"
          sortable
        >
          <template #default="scope">
            <div class="progress-cell">
              <el-progress
                :percentage="scope.row.independence_score"
                :status="getProgressStatus(scope.row.independence_score)"
                :stroke-width="8"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="rdi_status"
          label="阅读依赖 RDI 评级"
          width="150"
          align="center"
        >
          <template #default="scope">
            <el-tag
              :type="getTagType(scope.row.rdi_status)"
              effect="dark"
              disable-transitions
            >
              {{ getStatusLabel(scope.row.rdi_status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!hasStudents" class="empty-table-placeholder">
        <el-empty description="暂无学生审题记录" :image-size="60" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts/core'
import { getClasses } from '@/api/classes'
import {
  getClassReportKPI,
  getBlindSpots,
  getStudentUsageList,
  type MathReportKPI,
  type BlindSpotItem,
  type StudentUsageItem,
} from '@/api/teachMath'

// ── 筛选响应式状态 ──
const loading = ref<boolean>(false)
const currentClass = ref<number>(1) // 默认第一个班
const timeRange = ref<string>('7d')

// 班级选项 — 从真实API动态获取
const classOptions = ref<Array<{ value: number; label: string }>>([])

async function fetchClassOptions() {
  try {
    const res: any = await getClasses()
    const list = res?.items ?? (Array.isArray(res) ? res : [])
    classOptions.value = list.map((c: any) => ({
      value: c.id,
      label: c.name,
    }))
    if (classOptions.value.length > 0) {
      currentClass.value = classOptions.value[0].value
    }
  } catch {
    classOptions.value = []
  }
}

// ── 核心数据集 ──
const kpiData = ref<MathReportKPI>({
  active_students: 0,
  total_translations: 0,
  avg_queries_per_student: 0,
  risk_students_count: 0,
  trend_data: [],
})
const blindSpots = ref<BlindSpotItem[]>([])
const studentList = ref<StudentUsageItem[]>([])

// ── 计算属性 ──
const hasTrendData = computed(() => kpiData.value.trend_data.length > 0)
const hasBlindSpots = computed(() => blindSpots.value.length > 0)
const hasStudents = computed(() => studentList.value.length > 0)

// ── 图表 DOM 引用 ──
const trendChartRef = ref<HTMLDivElement | null>(null)
const blindSpotChartRef = ref<HTMLDivElement | null>(null)
let trendChartInstance: echarts.ECharts | null = null
let blindSpotChartInstance: echarts.ECharts | null = null

// ── 辅助函数 ──
const calculateCoverage = (): string => {
  // 班级人数近似值（从 KPI 的 active_students 与总数比例计算）
  const classSizeMap: Record<number, number> = {
    1: 98, 2: 95, 3: 96, 4: 98, 5: 104, 6: 93, 7: 96, 8: 101,
  }
  const total = classSizeMap[currentClass.value] || 50
  if (!kpiData.value.active_students) return '0.0'
  return ((kpiData.value.active_students / total) * 100).toFixed(1)
}

const getProgressStatus = (score: number) => {
  if (score >= 80) return 'success'
  if (score >= 50) return ''
  return 'exception'
}

const getTagType = (status: 'safe' | 'warning' | 'danger'): 'success' | 'warning' | 'danger' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    safe: 'success',
    warning: 'warning',
    danger: 'danger',
  }
  return map[status] || 'info'
}

const getStatusLabel = (status: 'safe' | 'warning' | 'danger') => {
  const map: Record<string, string> = {
    safe: '自主安全',
    warning: '轻度依赖',
    danger: '高度滞后',
  }
  return map[status] || '未激活'
}

// ── 盲区配色映射 (匹配后端 _classify_error_type 输出) ──
const ERROR_TYPE_COLORS: Record<string, string> = {
  '等量关系建模困难': '#E6A23C',  // amber
  '函数概念混淆': '#F56C6C',      // red
  '几何直观不足': '#409EFF',      // blue
  '代数运算薄弱': '#909399',      // gray
  '情境转译障碍': '#F56C6C',      // red
  '数据解读偏差': '#67C23A',      // green
  '审题理解障碍': '#E6A23C',      // amber
}

// ── ECharts 初始化 ──
const initTrendChart = () => {
  if (!trendChartRef.value || !hasTrendData.value) return
  if (!trendChartInstance) {
    trendChartInstance = echarts.init(trendChartRef.value)
  }

  const xAxisData = kpiData.value.trend_data.map((d) => d.date)
  const seriesData = kpiData.value.trend_data.map((d) => d.count)

  trendChartInstance.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: { lineStyle: { color: '#909399' } },
      axisLabel: { color: '#606266' },
    },
    yAxis: {
      type: 'value',
      name: '调用频次',
      nameTextStyle: { color: '#909399' },
      splitLine: { lineStyle: { type: 'dashed', color: '#E4E7ED' } },
      axisLabel: { color: '#606266' },
    },
    series: [
      {
        name: '翻译解析请求',
        type: 'line',
        smooth: true,
        data: seriesData,
        itemStyle: { color: '#409EFF' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64,158,255,0.3)' },
            { offset: 1, color: 'rgba(64,158,255,0.01)' },
          ]),
        },
      },
    ],
  })
}

const initBlindSpotChart = () => {
  if (!blindSpotChartRef.value || !hasBlindSpots.value) return
  if (!blindSpotChartInstance) {
    blindSpotChartInstance = echarts.init(blindSpotChartRef.value)
  }

  // 逆序排列使最高频排在上方
  const sortedSpots = [...blindSpots.value].sort((a, b) => a.frequency - b.frequency)
  const yAxisData = sortedSpots.map((s) => s.term)
  const seriesData = sortedSpots.map((s) => s.frequency)

  blindSpotChartInstance.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const item = sortedSpots[params.dataIndex]
        return `${params.name}<br/>检索求助 <b>${params.value}</b> 次<br/>归因: ${item?.error_type || '未知'}`
      },
    },
    grid: { left: '3%', right: '8%', bottom: '3%', top: '5%', containLabel: true },
    xAxis: {
      type: 'value',
      splitLine: { show: false },
      axisLabel: { color: '#606266' },
    },
    yAxis: {
      type: 'category',
      data: yAxisData,
      axisLabel: { color: '#303133', fontSize: 12 },
    },
    series: [
      {
        name: '盲区触发频次',
        type: 'bar',
        data: seriesData,
        barWidth: '55%',
        itemStyle: {
          color: (params: any) => {
            const item = sortedSpots[params.dataIndex]
            if (!item) return '#409EFF'
            return ERROR_TYPE_COLORS[item.error_type] || '#409EFF'
          },
          borderRadius: [0, 4, 4, 0],
        },
      },
    ],
  })
}

// ── 数据流拉取（含离线快照）──
const CACHE_PREFIX = 'wings_cache_teacher_report'

const loadAllDashboardData = async () => {
  loading.value = true
  const cacheKeySuffix = `${currentClass.value}_${timeRange.value}`

  try {
    const [kpiRes, spotsRes, studentsRes] = await Promise.all([
      getClassReportKPI(currentClass.value, timeRange.value),
      getBlindSpots(currentClass.value, timeRange.value),
      getStudentUsageList(currentClass.value),
    ])

    kpiData.value = { ...kpiRes }
    blindSpots.value = [...spotsRes]
    studentList.value = [...studentsRes]

    // 写入离线快照
    try {
      localStorage.setItem(`${CACHE_PREFIX}_kpi_${cacheKeySuffix}`, JSON.stringify(kpiRes))
      localStorage.setItem(`${CACHE_PREFIX}_spots_${cacheKeySuffix}`, JSON.stringify(spotsRes))
      localStorage.setItem(`${CACHE_PREFIX}_students_${cacheKeySuffix}`, JSON.stringify(studentsRes))
    } catch {
      // localStorage 满或不可用，静默降级
    }
  } catch {
    console.warn('[TeacherReport] 后端不可达，激活本地数据容灾快照')

    const cachedKPI = localStorage.getItem(`${CACHE_PREFIX}_kpi_${cacheKeySuffix}`)
    const cachedSpots = localStorage.getItem(`${CACHE_PREFIX}_spots_${cacheKeySuffix}`)
    const cachedStudents = localStorage.getItem(`${CACHE_PREFIX}_students_${cacheKeySuffix}`)

    if (cachedKPI) {
      try { kpiData.value = JSON.parse(cachedKPI) } catch { /* corrupt cache, skip */ }
    }
    if (cachedSpots) {
      try { blindSpots.value = JSON.parse(cachedSpots) } catch { /* corrupt cache, skip */ }
    }
    if (cachedStudents) {
      try { studentList.value = JSON.parse(cachedStudents) } catch { /* corrupt cache, skip */ }
    }
  } finally {
    loading.value = false
    await nextTick()
    // 销毁旧实例再重建，避免数据切换时残留
    disposeCharts()
    initTrendChart()
    initBlindSpotChart()
  }
}

const disposeCharts = () => {
  if (trendChartInstance) {
    trendChartInstance.dispose()
    trendChartInstance = null
  }
  if (blindSpotChartInstance) {
    blindSpotChartInstance.dispose()
    blindSpotChartInstance = null
  }
}

const handleFilterChange = () => {
  loadAllDashboardData()
}

// ── 侦听器: 班级/时间范围变化时自动刷新 ──
watch([currentClass, timeRange], () => {
  loadAllDashboardData()
})

// ── 窗口自适应 ──
const handleResize = () => {
  trendChartInstance?.resize()
  blindSpotChartInstance?.resize()
}

onMounted(async () => {
  await fetchClassOptions()
  loadAllDashboardData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  disposeCharts()
})
</script>

<style scoped>
.teacher-report-container {
  padding: 18px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 84px);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;
}

/* ── 顶部筛选栏 ── */
.filter-header-zone {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ffffff;
  padding: 14px 20px;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  margin-bottom: 16px;
}

.title-section {
  display: flex;
  align-items: center;
  gap: 10px;
}

.decorator-line {
  width: 4px;
  height: 18px;
  background-color: #409eff;
  border-radius: 2px;
}

.title-section h2 {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.controls-section {
  display: flex;
  align-items: center;
}

.ml-3 {
  margin-left: 12px;
}

/* ── KPI 卡片 ── */
.kpi-row-zone {
  margin-bottom: 16px;
}

.kpi-card {
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.kpi-meta {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.kpi-value {
  font-size: 26px;
  font-weight: 700;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', sans-serif;
  line-height: 1.2;
  margin-bottom: 6px;
}

.kpi-value .unit {
  font-size: 12px;
  font-weight: normal;
  color: #606266;
  margin-left: 4px;
}

.kpi-footer {
  font-size: 11px;
  color: #909399;
  border-top: 1px solid #f2f6fc;
  padding-top: 6px;
  margin-top: 4px;
}

.highlight {
  font-weight: 600;
  color: #303133;
}

.text-primary { color: #409eff; }
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }

/* ── 图表区 ── */
.chart-row-zone {
  margin-bottom: 16px;
}

.chart-container-card {
  border-radius: 8px;
}

.chart-container-card :deep(.el-card__body) {
  padding: 8px 16px 16px;
}

.card-header {
  font-size: 13px;
  font-weight: 600;
  color: #434447;
  display: flex;
  align-items: center;
}
.card-header.flex { display: flex; }
.card-header.justify-between { justify-content: space-between; }
.card-header.items-center { align-items: center; }

.echart-wrapper {
  width: 100%;
  height: 280px;
}

.empty-chart-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 280px;
}

/* ── 学生明细表 ── */
.table-container-card {
  border-radius: 8px;
}

.empty-table-placeholder {
  padding: 40px 0;
}

.blind-spot-text {
  font-weight: 500;
  color: #e6a23c;
  background-color: #fdf6ec;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.progress-cell {
  padding-right: 10px;
}

/* ── 滚动条微调 ── */
.teacher-report-container :deep(.el-table__body-wrapper::-webkit-scrollbar) {
  width: 6px;
  height: 6px;
}
.teacher-report-container :deep(.el-table__body-wrapper::-webkit-scrollbar-thumb) {
  background-color: #dcdfe6;
  border-radius: 3px;
}
</style>
