<template>
  <div class="psych-dashboard">
    <!-- 顶部标题栏 -->
    <div class="page-hero">
      <div class="hero-left">
        <h1 class="hero-title">心理关怀 · 筛查仪表盘</h1>
        <p class="hero-sub">MSSMHS-55 中学生心理健康量表 · PCE-55 家长评价量表</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Plus" type="primary" size="large" round @click="goFill">
          开始新筛查
        </el-button>
        <el-button :icon="RefreshRight" size="large" round @click="loadAll" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- KPI 四维指标卡 -->
    <div class="kpi-row">
      <div class="kpi-card kpi-total">
        <div class="kpi-icon"><el-icon :size="28"><Document /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ dashData?.overview?.total_surveys || 0 }}</div>
          <div class="kpi-label">筛查总人次</div>
        </div>
        <div class="kpi-detail">MSSMHS {{ dashData?.overview?.mssmhs_count || 0 }} · PCE {{ dashData?.overview?.pce_count || 0 }}</div>
      </div>
      <div class="kpi-card kpi-low">
        <div class="kpi-icon"><el-icon :size="28"><CircleCheck /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ dashData?.overview?.low_risk_count || 0 }}</div>
          <div class="kpi-label">低风险</div>
        </div>
        <div class="kpi-detail">心理健康状态良好</div>
      </div>
      <div class="kpi-card kpi-medium">
        <div class="kpi-icon"><el-icon :size="28"><WarningFilled /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ dashData?.overview?.medium_risk_count || 0 }}</div>
          <div class="kpi-label">中风险</div>
        </div>
        <div class="kpi-detail">需班主任持续关注</div>
      </div>
      <div class="kpi-card kpi-high">
        <div class="kpi-icon"><el-icon :size="28"><CircleCloseFilled /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ dashData?.overview?.high_risk_count || 0 }}</div>
          <div class="kpi-label">高风险</div>
        </div>
        <div class="kpi-detail">需立即启动干预</div>
      </div>
    </div>

    <!-- 图表双栏 -->
    <div class="chart-row">
      <!-- 左：风险漏斗 -->
      <div class="chart-panel">
        <div class="panel-header">
          <span class="panel-title">风险等级分布</span>
          <el-tag type="danger" size="small" effect="dark">预警漏斗</el-tag>
        </div>
        <div ref="pieRef" class="chart-body"></div>
      </div>
      <!-- 右：十维偏差度 -->
      <div class="chart-panel">
        <div class="panel-header">
          <span class="panel-title">各维度偏差度排行</span>
          <el-tag type="warning" size="small" effect="dark">MSSMHS-55</el-tag>
        </div>
        <div class="dimension-bars" v-if="dimensionRanking.length">
          <div v-for="d in dimensionRanking" :key="d.code" class="dim-item">
            <div class="dim-header">
              <span class="dim-name">{{ d.name }}</span>
              <span class="dim-pct" :style="{ color: barColor(d.deviation_pct) }">
                {{ d.deviation_pct.toFixed(1) }}%
              </span>
            </div>
            <div class="dim-track">
              <div class="dim-fill" :style="{ width: d.deviation_pct + '%', background: barGradient(d.deviation_pct) }"></div>
            </div>
          </div>
        </div>
        <div v-else class="empty-placeholder">
          <el-icon :size="48" class="empty-icon"><Histogram /></el-icon>
          <div class="empty-text">暂无显著维度偏差</div>
          <div class="empty-sub">所有维度得分处于正常区间</div>
        </div>
      </div>
    </div>

    <!-- 干预摘要 -->
    <div class="intervention-strip" @click="$router.push('/psych-screening/intervention')">
      <div class="strip-left">
        <el-icon :size="22"><Bell /></el-icon>
        <span class="strip-title">干预追踪</span>
      </div>
      <div class="strip-cards">
        <div class="strip-card">
          <span class="sc-val">{{ dashData?.intervention_summary?.total || 0 }}</span>
          <span class="sc-lbl">干预总数</span>
        </div>
        <div class="strip-card pending">
          <span class="sc-val">{{ dashData?.intervention_summary?.pending || 0 }}</span>
          <span class="sc-lbl">待处理</span>
        </div>
        <div class="strip-card progress">
          <span class="sc-val">{{ dashData?.intervention_summary?.in_progress || 0 }}</span>
          <span class="sc-lbl">进行中</span>
        </div>
        <div class="strip-card done">
          <span class="sc-val">{{ dashData?.intervention_summary?.completed || 0 }}</span>
          <span class="sc-lbl">已完成</span>
        </div>
      </div>
      <el-icon class="strip-arrow"><ArrowRight /></el-icon>
    </div>

    <!-- 问卷列表 -->
    <div class="survey-section">
      <div class="section-bar">
        <span class="section-title">筛查问卷列表</span>
        <div class="section-filters">
          <el-select v-model="filterSurveyType" placeholder="类型" clearable size="small" style="width: 130px">
            <el-option label="MSSMHS-55 (学生)" value="MSSMHS-55" />
            <el-option label="PCE-55 (家长)" value="PCE-55" />
          </el-select>
          <el-select v-model="filterGradeId" placeholder="年级" clearable size="small" style="width: 110px; margin-left: 8px">
            <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
          <el-button type="primary" size="small" style="margin-left: 8px" @click="loadSurveys" :loading="listLoading">查询</el-button>
        </div>
        <div class="survey-stats">
          共 <strong>{{ surveyTotal }}</strong> 份
          <span class="dot-divider">·</span>
          <span class="c-high">高风险 {{ surveyStatCounts?.high || 0 }}</span>
          <span class="dot-divider">·</span>
          <span class="c-medium">中风险 {{ surveyStatCounts?.medium || 0 }}</span>
          <span class="dot-divider">·</span>
          <span class="c-low">低风险 {{ surveyStatCounts?.low || 0 }}</span>
        </div>
      </div>

      <el-table :data="surveys" border v-loading="listLoading" max-height="480" class="survey-table">
        <el-table-column type="index" width="55" label="#" />
        <el-table-column prop="student_name" label="学生姓名" width="100" sortable />
        <el-table-column prop="class_name" label="班级" width="90" sortable />
        <el-table-column prop="survey_type" label="问卷类型" width="130">
          <template #default="{ row }">
            <span class="type-tag" :class="row.survey_type === 'MSSMHS-55' ? 'type-mss' : 'type-pce'">
              {{ row.survey_type }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="总分" width="80" align="center" sortable prop="total_score">
          <template #default="{ row }">
            <span class="score-badge" :class="scoreClass(row.total_score)">
              {{ row.total_score }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="85" align="center">
          <template #default="{ row }">
            <span class="risk-tag" :class="riskClass(row.total_score)">
              {{ riskLabel(row.total_score) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="效度" width="75" align="center">
          <template #default="{ row }">
            <span class="validity-tag" :class="row.verify_status === 'VERIFIED' ? 'valid-ok' : 'valid-pending'">
              {{ row.verify_status === 'VERIFIED' ? '有效' : '待核' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="完成时间" width="155" sortable prop="completed_at">
          <template #default="{ row }">
            {{ row.completed_at ? new Date(row.completed_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="viewResult(row)" class="action-link">查看结果</el-button>
            <el-button type="warning" size="small" link @click="viewResult(row)" class="action-link">AI分析</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="survey-pagination" v-if="surveyTotal > 20">
        <el-pagination
          v-model:current-page="surveyPage"
          :page-size="20"
          :total="surveyTotal"
          layout="total, prev, pager, next"
          small
          @current-change="loadSurveys"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, RefreshRight, Document, CircleCheck, WarningFilled, CircleCloseFilled, Bell, ArrowRight, Histogram } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboard, listSurveys, type PsychDashboardStats } from '@/api/psychScreening'
import { getGrades } from '@/api/classes'

const router = useRouter()

const loading = ref(false)
const listLoading = ref(false)
const dashData = ref<PsychDashboardStats | null>(null)
const dimensionRanking = ref<Array<{ code: string; name: string; deviation_pct: number }>>([])
const grades = ref<Array<{ id: number; name: string }>>([])
const surveys = ref<any[]>([])
const surveyTotal = ref(0)
const surveyStatCounts = ref<{ high: number; medium: number; low: number } | null>(null)
const surveyPage = ref(1)
const filterSurveyType = ref('')
const filterGradeId = ref<number | ''>('')

const pieRef = ref<HTMLElement | null>(null)
let pieInstance: echarts.ECharts | null = null

function barColor(pct: number) {
  if (pct > 70) return '#f85149'
  if (pct > 50) return '#d29922'
  return '#58a6ff'
}
function barGradient(pct: number) {
  if (pct > 70) return 'linear-gradient(90deg, #f85149, #da3633)'
  if (pct > 50) return 'linear-gradient(90deg, #d29922, #e3b341)'
  return 'linear-gradient(90deg, #58a6ff, #79c0ff)'
}
function scoreClass(score: number) {
  if (score >= 160) return 'score-high'
  if (score >= 120) return 'score-medium'
  return 'score-low'
}
function riskClass(score: number) {
  if (score >= 160) return 'risk-high'
  if (score >= 120) return 'risk-medium'
  return 'risk-low'
}
function riskLabel(score: number) {
  if (score >= 160) return '高风险'
  if (score >= 120) return '中风险'
  return '低风险'
}

function renderPie() {
  if (!pieRef.value) return
  if (pieInstance) pieInstance.dispose()
  pieInstance = echarts.init(pieRef.value, 'dark')

  const data = dashData.value?.risk_distribution || []
  pieInstance.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} 人 ({d}%)',
      backgroundColor: 'rgba(22,27,34,0.95)',
      borderColor: '#30363d',
      textStyle: { color: '#c9d1d9' }
    },
    legend: {
      bottom: 0,
      textStyle: { color: '#8b949e', fontSize: 12 }
    },
    color: ['#3fb950', '#d29922', '#f85149'],
    series: [{
      type: 'pie',
      radius: ['50%', '75%'],
      center: ['50%', '48%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#0d1117', borderWidth: 3 },
      label: { show: false },
      emphasis: {
        label: { show: true, fontSize: 16, fontWeight: 'bold', color: '#f0f6fc' },
        scaleSize: 10,
      },
      data,
    }],
  })
}

async function loadAll() {
  loading.value = true
  try {
    const [dashRes, gradeRes] = await Promise.all([
      getDashboard().catch(() => null),
      getGrades().catch(() => ({ data: [] })),
    ])
    if (dashRes) {
      dashData.value = dashRes as unknown as PsychDashboardStats
      dimensionRanking.value = (dashRes as any)?.dimension_ranking || []
    }
    grades.value = (gradeRes as any)?.data || gradeRes || []
  } catch (e) {
    console.error('Dashboard load error:', e)
  } finally {
    loading.value = false
    await nextTick()
    renderPie()
  }
}

async function loadSurveys() {
  listLoading.value = true
  try {
    const params: any = { limit: 20, offset: (surveyPage.value - 1) * 20 }
    if (filterSurveyType.value) params.survey_type = filterSurveyType.value
    if (filterGradeId.value) params.grade_id = filterGradeId.value
    const res: any = await listSurveys(params)
    surveys.value = res?.surveys || []
    surveyTotal.value = res?.total || 0
    surveyStatCounts.value = res?.stats || null
  } catch (e) {
    console.error('Surveys load error:', e)
  } finally {
    listLoading.value = false
  }
}

function goFill() {
  router.push('/psych-screening/fill')
}
function viewResult(survey: any) {
  router.push({ path: '/psych-screening/result', query: { survey_id: survey.id } })
}

onMounted(() => {
  loadAll()
  loadSurveys()
})
</script>

<style scoped>
.psych-dashboard {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

/* 顶部 */
.page-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
.hero-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #f0f6fc;
  letter-spacing: -0.5px;
}
.hero-sub {
  margin: 4px 0 0;
  color: #8b949e;
  font-size: 13px;
}
.hero-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

/* KPI 卡片 */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.kpi-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 20px;
  position: relative;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: default;
}
.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.kpi-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  border-radius: 4px 0 0 4px;
}
.kpi-total::before { background: linear-gradient(180deg, #58a6ff, #1f6feb); }
.kpi-low::before { background: linear-gradient(180deg, #3fb950, #2ea043); }
.kpi-medium::before { background: linear-gradient(180deg, #d29922, #e3b341); }
.kpi-high::before { background: linear-gradient(180deg, #f85149, #da3633); }
.kpi-icon {
  position: absolute;
  top: 16px;
  right: 16px;
  opacity: 0.12;
}
.kpi-total .kpi-icon { color: #58a6ff; }
.kpi-low .kpi-icon { color: #3fb950; }
.kpi-medium .kpi-icon { color: #d29922; }
.kpi-high .kpi-icon { color: #f85149; }
.kpi-body { margin-bottom: 8px; }
.kpi-value {
  font-size: 32px;
  font-weight: 800;
  color: #f0f6fc;
  line-height: 1;
}
.kpi-total .kpi-value { color: #58a6ff; }
.kpi-low .kpi-value { color: #3fb950; }
.kpi-medium .kpi-value { color: #d29922; }
.kpi-high .kpi-value { color: #f85149; }
.kpi-label {
  font-size: 13px;
  color: #8b949e;
  margin-top: 4px;
  font-weight: 500;
}
.kpi-detail {
  font-size: 11px;
  color: #484f58;
}

/* 图表双栏 */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}
.chart-panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  overflow: hidden;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #21262d;
}
.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
}
.chart-body {
  height: 320px;
}

/* 维度排行 */
.dimension-bars {
  padding: 12px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.dim-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.dim-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.dim-name { color: #c9d1d9; }
.dim-pct { font-weight: 700; }
.dim-track {
  height: 8px;
  background: #21262d;
  border-radius: 4px;
  overflow: hidden;
}
.dim-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 空状态 */
.empty-placeholder {
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

/* 干预条 */
.intervention-strip {
  display: flex;
  align-items: center;
  gap: 20px;
  background: linear-gradient(135deg, #1a1f2e 0%, #161b22 100%);
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 16px 24px;
  margin-bottom: 24px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.intervention-strip:hover {
  border-color: #d29922;
  box-shadow: 0 0 0 1px rgba(210,153,34,0.15);
}
.strip-left {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #d29922;
  flex-shrink: 0;
}
.strip-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
}
.strip-cards {
  display: flex;
  gap: 16px;
  flex: 1;
}
.strip-card {
  text-align: center;
  padding: 6px 16px;
  border-radius: 8px;
  background: rgba(13,17,23,0.6);
  border: 1px solid #21262d;
  min-width: 70px;
}
.strip-card.pending { border-color: rgba(210,153,34,0.4); }
.strip-card.progress { border-color: rgba(88,166,255,0.4); }
.strip-card.done { border-color: rgba(63,185,80,0.4); }
.sc-val {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
}
.sc-lbl {
  display: block;
  font-size: 11px;
  color: #8b949e;
  margin-top: 2px;
}
.strip-arrow {
  color: #484f58;
  font-size: 20px;
}

/* 问卷列表 */
.survey-section {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  overflow: hidden;
}
.section-bar {
  display: flex;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #21262d;
  gap: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
  flex-shrink: 0;
}
.section-filters { display: flex; align-items: center; }
.survey-stats {
  margin-left: auto;
  font-size: 12px;
  color: #8b949e;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}
.survey-stats strong { color: #c9d1d9; }
.dot-divider { color: #30363d; }
.c-high { color: #f85149; font-weight: 600; }
.c-medium { color: #d29922; font-weight: 600; }
.c-low { color: #3fb950; font-weight: 600; }

.survey-table { background: transparent; }
.survey-pagination {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #21262d;
}

/* 分数徽章 */
.score-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 700;
  font-size: 14px;
}
.score-high { background: rgba(248,81,73,0.15); color: #f85149; }
.score-medium { background: rgba(210,153,34,0.15); color: #d29922; }
.score-low { background: rgba(63,185,80,0.15); color: #3fb950; }

/* 类型标签 */
.type-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.type-mss { background: rgba(88,166,255,0.12); color: #58a6ff; border: 1px solid rgba(88,166,255,0.2); }
.type-pce { background: rgba(63,185,80,0.12); color: #3fb950; border: 1px solid rgba(63,185,80,0.2); }

/* 风险标签 */
.risk-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
.risk-high { background: rgba(248,81,73,0.15); color: #f85149; border: 1px solid rgba(248,81,73,0.25); }
.risk-medium { background: rgba(210,153,34,0.15); color: #d29922; border: 1px solid rgba(210,153,34,0.25); }
.risk-low { background: rgba(63,185,80,0.15); color: #3fb950; border: 1px solid rgba(63,185,80,0.25); }

/* 效度标签 */
.validity-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.valid-ok { background: rgba(63,185,80,0.12); color: #3fb950; border: 1px solid rgba(63,185,80,0.2); }
.valid-pending { background: rgba(139,148,158,0.12); color: #8b949e; border: 1px solid rgba(139,148,158,0.2); }

.action-link { color: #58a6ff; }

/* Element Plus 暗色覆盖 - 核心修复 */
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
  text-transform: uppercase;
  letter-spacing: 0.5px;
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
:deep(.el-button--primary.is-link) { color: #58a6ff; }
:deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-text-color: #c9d1d9;
}
</style>
