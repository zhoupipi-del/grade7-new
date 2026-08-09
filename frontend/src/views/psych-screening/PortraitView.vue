<template>
  <div class="portrait-page">
    <!-- 页头 -->
    <div class="page-hero">
      <div class="hero-left">
        <el-button :icon="ArrowLeft" size="small" text @click="$router.push('/psych-screening')" class="back-btn">
          返回总览
        </el-button>
        <div>
          <h1 class="hero-title">心理画像与交叉分析</h1>
          <p class="hero-sub">班级十维度雷达图 · 亲子评分交叉对比</p>
        </div>
      </div>
    </div>

    <!-- Tab -->
    <el-tabs v-model="activeTab" type="border-card" class="dark-tabs">
      <!-- Tab 1: 班级画像 -->
      <el-tab-pane name="portrait">
        <template #label>
          <span class="tab-label">
            <el-icon><DataAnalysis /></el-icon> 班级心理画像
          </span>
        </template>

        <div v-loading="portraitLoading" class="portrait-grid">
          <div
            v-for="(p, idx) in portraits"
            :key="p.id"
            class="portrait-card"
          >
            <div class="card-header">
              <div class="header-left">
                <span class="class-name">{{ p.class_name }}</span>
                <span class="badge-summary" :class="'summary-' + riskSummaryType(p.portrait_data?.risk_distribution)">
                  {{ riskSummary(p.portrait_data?.risk_distribution) }}
                </span>
              </div>
              <span class="student-count">{{ p.portrait_data?.total_students || 0 }}人参测</span>
            </div>

            <div :ref="el => setChartRef(p.id, el)" class="radar-area"></div>

            <div class="card-stats">
              <div class="mini-stat">
                <span class="ms-val" :style="{ color: scoreColor(p.portrait_data?.average_score) }">
                  {{ p.portrait_data?.average_score || '-' }}
                </span>
                <span class="ms-lbl">班级均分</span>
              </div>
              <div class="mini-stat">
                <span class="ms-val hl-red">{{ p.portrait_data?.risk_distribution?.high || 0 }}</span>
                <span class="ms-lbl">高危</span>
              </div>
              <div class="mini-stat">
                <span class="ms-val hl-yellow">{{ p.portrait_data?.risk_distribution?.medium || 0 }}</span>
                <span class="ms-lbl">中危</span>
              </div>
              <div class="mini-stat">
                <span class="ms-val hl-green">{{ p.portrait_data?.risk_distribution?.low || 0 }}</span>
                <span class="ms-lbl">低危</span>
              </div>
            </div>
          </div>

          <div v-if="!portraitLoading && portraits.length === 0" class="empty-placeholder">
            <el-icon :size="48" class="empty-icon"><DataAnalysis /></el-icon>
            <div class="empty-text">暂无班级画像数据</div>
            <div class="empty-sub">请先完成班级筛查并生成画像</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 交叉分析 -->
      <el-tab-pane name="cross">
        <template #label>
          <span class="tab-label">
            <el-icon><Connection /></el-icon> 亲子交叉分析
          </span>
        </template>

        <div v-loading="crossLoading">
          <!-- 概览 -->
          <div class="cross-summary" v-if="crossStats">
            <div class="summary-chip danger">
              <el-icon :size="28" class="summary-icon"><WarningFilled /></el-icon>
              <div>
                <span class="sc-val">{{ crossStats.overAnxious }}</span>
                <span class="sc-lbl">过度焦虑家长</span>
              </div>
            </div>
            <div class="summary-chip warning">
              <el-icon :size="28" class="summary-icon"><DataLine /></el-icon>
              <div>
                <span class="sc-val">{{ crossStats.scoreGap }}</span>
                <span class="sc-lbl">亲子评分背离</span>
              </div>
            </div>
            <div class="summary-chip info">
              <el-icon :size="28" class="summary-icon"><HomeFilled /></el-icon>
              <div>
                <span class="sc-val">{{ crossStats.highRisk }}</span>
                <span class="sc-lbl">高风险家庭</span>
              </div>
            </div>
          </div>

          <!-- 表格 -->
          <el-table :data="crossList" border v-loading="crossLoading" max-height="550" class="cross-table">
            <el-table-column type="index" width="50" label="#" />
            <el-table-column prop="student_name" label="学生" width="100" fixed />
            <el-table-column prop="class_name" label="班级" width="90" />
            <el-table-column label="分析类型" width="140">
              <template #default="{ row }">
                <span class="analysis-tag" :class="'analysis-' + row.analysis_type">
                  {{ analysisLabel(row.analysis_type) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="亲子对比详情" min-width="320">
              <template #default="{ row }">
                <div class="cross-cells" v-if="row.details_json && Object.keys(row.details_json).length">
                  <span class="cc-item" v-if="row.details_json.parent_avg">
                    期望焦虑 <strong>{{ row.details_json.parent_avg }}</strong>
                  </span>
                  <span class="cc-item" v-if="row.details_json.parent_edu">
                    教育焦虑 <strong>{{ row.details_json.parent_edu }}</strong>
                  </span>
                  <span class="cc-item" v-if="row.details_json.parent_comm">
                    沟通焦虑 <strong>{{ row.details_json.parent_comm }}</strong>
                  </span>
                  <span class="cc-item" v-if="row.details_json.parent_atmos">
                    家庭氛围 <strong>{{ row.details_json.parent_atmos }}</strong>
                  </span>
                  <span class="cc-item danger" v-if="row.details_json.abnormal_factors >= 4">
                    异常因子 <strong>{{ row.details_json.abnormal_factors }}</strong>
                  </span>
                </div>
                <span v-else class="cell-dash">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="分析时间" width="160" sortable>
              <template #default="{ row }">
                {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '-' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, computed, onBeforeUnmount } from 'vue'
import { ArrowLeft, DataAnalysis, Connection, WarningFilled, DataLine, HomeFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import request from '@/api/request'

const DIMENSION_ORDER = [
  '强迫症状', '偏执', '敌对', '人际敏感', '抑郁',
  '焦虑', '学习压力', '适应不良', '情绪不平衡', '心理不平衡'
]
const DIMENSION_MAX = 30

const activeTab = ref('portrait')
const portraitLoading = ref(false)
const crossLoading = ref(false)
const portraits = ref<any[]>([])
const crossList = ref<any[]>([])

const chartInstances = new Map<number, echarts.ECharts>()
const chartRefs = new Map<number, HTMLElement>()

function setChartRef(id: number, el: any) {
  if (el) chartRefs.set(id, el as HTMLElement)
}

function renderRadar(id: number, portraitData: any) {
  const el = chartRefs.get(id)
  if (!el) return

  const old = chartInstances.get(id)
  if (old) old.dispose()

  const chart = echarts.init(el, 'dark')
  chartInstances.set(id, chart)

  const dims = portraitData?.dimension_averages || {}
  const values = DIMENSION_ORDER.map(d => dims[d] || 0)

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(22,27,34,0.95)',
      borderColor: '#30363d',
      textStyle: { color: '#c9d1d9' },
      formatter: (params: any) => {
        const pct = ((params.value / DIMENSION_MAX) * 100).toFixed(1)
        return `${params.name}<br/>均分: <strong>${params.value?.toFixed(1)}</strong> / ${DIMENSION_MAX} (${pct}%)`
      }
    },
    radar: {
      center: ['50%', '52%'],
      radius: '62%',
      indicator: DIMENSION_ORDER.map(d => ({ name: d, max: DIMENSION_MAX })),
      axisName: { color: '#8b949e', fontSize: 10, borderRadius: 3, padding: [2, 4] },
      splitArea: {
        areaStyle: { color: ['rgba(48,54,61,0.2)', 'rgba(48,54,61,0.05)'] }
      },
      splitLine: { lineStyle: { color: '#30363d' } },
      axisLine: { lineStyle: { color: '#30363d' } }
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '班级均分',
        areaStyle: { color: 'rgba(88,166,255,0.15)' },
        lineStyle: { color: '#58a6ff', width: 2 },
        itemStyle: { color: '#58a6ff' },
      }],
      symbol: 'circle',
      symbolSize: 4,
    }]
  })
}

function disposeCharts() {
  chartInstances.forEach(c => c.dispose())
  chartInstances.clear()
  chartRefs.clear()
}

function riskSummaryType(dist: any) {
  if (!dist) return 'success'
  if (dist.high > 0) return 'danger'
  if (dist.medium > 3) return 'warning'
  return 'success'
}
function riskSummary(dist: any) {
  if (!dist) return '无数据'
  const parts = []
  if (dist.high > 0) parts.push(`${dist.high}高危`)
  if (dist.medium > 0) parts.push(`${dist.medium}中危`)
  return parts.join(' / ') || '健康'
}
function scoreColor(score: number) {
  if (!score) return '#8b949e'
  if (score > 120) return '#f85149'
  if (score > 90) return '#d29922'
  return '#3fb950'
}
function analysisLabel(type: string) {
  const map: Record<string, string> = {
    over_anxious_parent: '过度焦虑家长',
    score_inconsistency: '亲子评分背离',
    pce_vs_mssmhs: 'PCE vs MSSMHS',
  }
  return map[type] || type
}
const crossStats = computed(() => {
  if (!crossList.value.length) return null
  return {
    overAnxious: crossList.value.filter(c => c.analysis_type === 'over_anxious_parent').length,
    scoreGap: crossList.value.filter(c => c.analysis_type === 'score_inconsistency').length,
    highRisk: crossList.value.filter(c => (c.details_json?.abnormal_factors || 0) >= 4).length,
  }
})

async function loadPortraits() {
  portraitLoading.value = true
  try {
    const res: any = await request.get('/psych_screening/class-portraits')
    portraits.value = Array.isArray(res) ? res : (res?.data || [])
    await nextTick()
    portraits.value.forEach(p => {
      if (p.portrait_data) renderRadar(p.id, p.portrait_data)
    })
  } catch (e) {
    console.error('Portraits load error:', e)
  } finally {
    portraitLoading.value = false
  }
}

async function loadCrossAnalyses() {
  crossLoading.value = true
  try {
    const res: any = await request.get('/psych_screening/cross-analyses')
    crossList.value = Array.isArray(res) ? res : (res?.data || [])
  } catch (e) {
    console.error('Cross analysis load error:', e)
  } finally {
    crossLoading.value = false
  }
}

onMounted(() => {
  loadPortraits()
  loadCrossAnalyses()
  window.addEventListener('resize', () => chartInstances.forEach(c => c.resize()))
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', () => chartInstances.forEach(c => c.resize()))
  disposeCharts()
})
</script>

<style scoped>
.portrait-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

/* 页头 */
.page-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.hero-left {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.back-btn { color: #8b949e; }
.hero-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #f0f6fc;
}
.hero-sub {
  margin: 2px 0 0;
  color: #8b949e;
  font-size: 13px;
}

/* Tabs */
.dark-tabs { overflow: hidden; }
.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

/* 画像网格 */
.portrait-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
  padding: 16px 0;
}
.portrait-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.portrait-card:hover {
  border-color: #58a6ff;
  box-shadow: 0 0 0 1px rgba(88,166,255,0.1);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #21262d;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.class-name {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
}
.student-count {
  font-size: 12px;
  color: #8b949e;
}
.radar-area {
  width: 100%;
  height: 300px;
}
.card-stats {
  display: flex;
  justify-content: space-around;
  padding: 10px 16px 14px;
  border-top: 1px solid #21262d;
}
.mini-stat { text-align: center; }
.ms-val {
  display: block;
  font-size: 18px;
  font-weight: 700;
}
.ms-val.hl-red { color: #f85149; }
.ms-val.hl-yellow { color: #d29922; }
.ms-val.hl-green { color: #3fb950; }
.ms-lbl {
  display: block;
  font-size: 11px;
  color: #8b949e;
  margin-top: 2px;
}

/* 自定义徽章 */
.badge-summary {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.badge-summary.summary-success { background: rgba(63,185,80,0.12); color: #3fb950; border: 1px solid rgba(63,185,80,0.2); }
.badge-summary.summary-warning { background: rgba(210,153,34,0.12); color: #d29922; border: 1px solid rgba(210,153,34,0.2); }
.badge-summary.summary-danger { background: rgba(248,81,73,0.12); color: #f85149; border: 1px solid rgba(248,81,73,0.2); }

/* 交叉分析 */
.cross-summary {
  display: flex;
  gap: 14px;
  margin-bottom: 16px;
}
.summary-chip {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 10px;
  background: #161b22;
  border: 1px solid #30363d;
}
.summary-chip.danger { border-color: rgba(248,81,73,0.3); background: rgba(248,81,73,0.05); }
.summary-chip.warning { border-color: rgba(210,153,34,0.3); background: rgba(210,153,34,0.05); }
.summary-chip.info { border-color: rgba(88,166,255,0.3); background: rgba(88,166,255,0.05); }
.summary-icon { color: #484f58; }
.summary-chip.danger .summary-icon { color: #f85149; }
.summary-chip.warning .summary-icon { color: #d29922; }
.summary-chip.info .summary-icon { color: #58a6ff; }
.sc-val {
  display: block;
  font-size: 22px;
  font-weight: 800;
  color: #f0f6fc;
}
.sc-lbl {
  display: block;
  font-size: 11px;
  color: #8b949e;
}
.cross-table { background: transparent; }
.cross-cells {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}
.cc-item {
  font-size: 12px;
  color: #8b949e;
  background: rgba(13,17,23,0.6);
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid #21262d;
}
.cc-item strong { color: #c9d1d9; }
.cc-item.danger { border-color: rgba(248,81,73,0.3); color: #f85149; }
.cc-item.danger strong { color: #f85149; }
.cell-dash { color: #484f58; }

.analysis-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.analysis-tag.analysis-over_anxious_parent { background: rgba(248,81,73,0.12); color: #f85149; border: 1px solid rgba(248,81,73,0.2); }
.analysis-tag.analysis-score_inconsistency { background: rgba(210,153,34,0.12); color: #d29922; border: 1px solid rgba(210,153,34,0.2); }
.analysis-tag.analysis-pce_vs_mssmhs { background: rgba(88,166,255,0.12); color: #58a6ff; border: 1px solid rgba(88,166,255,0.2); }

/* 空状态 */
.empty-placeholder {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #484f58;
}
.empty-icon {
  color: #30363d;
  margin-bottom: 12px;
}
.empty-text {
  font-size: 15px;
  font-weight: 500;
  color: #6e7681;
  margin-bottom: 4px;
}
.empty-sub {
  font-size: 12px;
  color: #484f58;
}

/* 暗色覆盖 */
:deep(.el-tabs--border-card) {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 12px;
}
:deep(.el-tabs--border-card > .el-tabs__header) {
  background: #161b22;
  border-bottom: 1px solid #30363d;
  border-radius: 12px 12px 0 0;
}
:deep(.el-tabs--border-card > .el-tabs__header .el-tabs__item) {
  color: #8b949e;
  border: none;
  transition: color 0.2s;
}
:deep(.el-tabs--border-card > .el-tabs__header .el-tabs__item.is-active) {
  color: #58a6ff;
  background: #0d1117;
}
:deep(.el-tabs__content) { padding: 0; }

:deep(.el-table) {
  --el-table-bg-color: #0d1117;
  --el-table-tr-bg-color: #0d1117;
  --el-table-header-bg-color: #161b22;
  --el-table-border-color: #21262d;
  --el-table-text-color: #c9d1d9;
  --el-table-header-text-color: #8b949e;
  --el-table-row-hover-bg-color: #1c2129;
}
:deep(.el-table th) {
  font-weight: 600;
  font-size: 12px;
}
:deep(.el-table__body-wrapper .el-table__row) {
  background-color: #0d1117 !important;
}
:deep(.el-table__body-wrapper .el-table__row:hover > td) {
  background-color: #1c2129 !important;
}
:deep(.el-table td) {
  border-bottom: 1px solid #21262d;
  color: #c9d1d9;
}
</style>
