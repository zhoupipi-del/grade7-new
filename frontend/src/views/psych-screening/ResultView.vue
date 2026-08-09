<template>
  <div class="result-view">
    <!-- 返回栏 -->
    <div class="back-bar">
      <el-button :icon="ArrowLeft" @click="$router.back()">返回</el-button>
      <h2 class="view-title">心理筛查结果</h2>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="loading-wrap">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 结果内容 -->
    <template v-if="!loading && survey">
      <!-- 头部信息卡 -->
      <el-card shadow="hover" class="result-card warm-card">
        <el-row :gutter="20" align="middle">
          <el-col :span="6">
            <div class="student-info">
              <el-avatar :size="56" icon="UserFilled" />
              <div>
                <div class="s-name">{{ survey.student_name }}</div>
                <div class="s-class">{{ survey.class_name }}</div>
              </div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric">
              <div class="metric-label">总分</div>
              <div class="metric-value" :style="{ color: scoreColor(survey.total_score) }">
                {{ survey.total_score }}
                <span class="metric-unit">/275</span>
              </div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric">
              <div class="metric-label">问卷类型</div>
              <div class="metric-value small">{{ survey.survey_type }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric">
              <div class="metric-label">完成时间</div>
              <div class="metric-value small">
                {{ survey.completed_at ? new Date(survey.completed_at).toLocaleString() : '-' }}
              </div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- 十维雷达图 -->
      <el-row :gutter="16" style="margin-top: 16px">
        <el-col :span="12">
          <el-card shadow="hover" class="warm-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">维度得分雷达</span>
                <el-tag type="warning" size="small">十因子</el-tag>
              </div>
            </template>
            <div ref="radarRef" style="height: 380px"></div>
          </el-card>
        </el-col>

        <!-- 维度明细表 -->
        <el-col :span="12">
          <el-card shadow="hover" class="warm-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">各维度详情</span>
                <el-tag type="warning" size="small">按原始分排序</el-tag>
              </div>
            </template>
            <div class="dim-table-scroll">
              <div
                v-for="d in sortedDimensions"
                :key="d.code"
                class="dim-row"
              >
                <div class="dim-info">
                  <span class="dim-name">{{ d.name }}</span>
                  <span class="dim-score">{{ d.score }}<small>/{{ d.max_score }}</small></span>
                </div>
                <el-progress
                  :percentage="d.percentage"
                  :color="barColor(d.percentage)"
                  :show-text="false"
                  :stroke-width="10"
                />
                <span class="dim-pct" :style="{ color: barColor(d.percentage) }">
                  {{ d.percentage.toFixed(0) }}%
                </span>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- AI 分析面板 -->
      <el-card v-if="aiResult" shadow="hover" class="warm-card" style="margin-top: 16px">
        <template #header>
          <div class="card-header">
            <span class="card-title">AI 心理白皮书诊断</span>
            <el-tag type="warning" size="small">DeepSeek</el-tag>
          </div>
        </template>
        <div class="ai-content">
          <div v-if="aiResult.prescription" class="v2-segments">
            <div class="seg seg-fact">
              <div class="seg-label">事实描述</div>
              <p>{{ aiResult.prescription.fact }}</p>
            </div>
            <div class="seg seg-analysis">
              <div class="seg-label">维度分析</div>
              <p>{{ aiResult.prescription.analysis }}</p>
            </div>
            <div class="seg seg-growth">
              <div class="seg-label">成长建议</div>
              <p>{{ aiResult.prescription.growth }}</p>
            </div>
          </div>
          <div v-else class="ai-plain">
            <p><strong>综合评估：</strong>{{ aiResult.analysis?.summary }}</p>
            <div v-if="aiResult.analysis?.risks?.length">
              <strong>风险提示：</strong>
              <ul>
                <li v-for="r in aiResult.analysis.risks" :key="r">{{ r }}</li>
              </ul>
            </div>
            <div v-if="aiResult.analysis?.suggestions?.length">
              <strong>建议措施：</strong>
              <ul>
                <li v-for="s in aiResult.analysis.suggestions" :key="s">{{ s }}</li>
              </ul>
            </div>
          </div>
        </div>
      </el-card>

      <!-- AI 分析按钮（如果还没加载） -->
      <div v-if="!aiResult && !aiLoading" style="margin-top: 16px; text-align: center">
        <el-button type="warning" :icon="MagicStick" :loading="aiLoading" @click="loadAI" size="large">
          生成 AI 心理白皮书
        </el-button>
      </div>
      <div v-if="aiLoading" style="margin-top: 16px; text-align: center">
        <el-icon :size="24" class="is-loading"><Loading /></el-icon>
        <span style="margin-left: 8px; color: #8b949e">AI 正在深度分析中，请稍候...</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, MagicStick, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { listSurveys, runAIAnalysis, type PsychSurvey, type AIAnalysisResult } from '@/api/psychScreening'

const route = useRoute()

const loading = ref(true)
const aiLoading = ref(false)
const survey = ref<PsychSurvey | null>(null)
const aiResult = ref<AIAnalysisResult | null>(null)
const radarRef = ref<HTMLElement | null>(null)
let radarInstance: echarts.ECharts | null = null

const sortedDimensions = computed(() => {
  if (!survey.value?.dimensions) return []
  return [...survey.value.dimensions].sort((a, b) => b.percentage - a.percentage)
})

function scoreColor(score: number) {
  if (score >= 160) return '#ff4444'
  if (score >= 120) return '#e6a23c'
  return '#67c23a'
}

function barColor(pct: number) {
  if (pct > 70) return '#f56c6c'
  if (pct > 50) return '#e6a23c'
  return '#ff9a56'
}

function renderRadar() {
  if (!radarRef.value || !survey.value?.dimensions?.length) return
  if (radarInstance) radarInstance.dispose()
  radarInstance = echarts.init(radarRef.value)

  const dims = survey.value.dimensions
  const indicators = dims.map(d => ({ name: d.name, max: 100 }))
  const data = dims.map(d => d.percentage)

  radarInstance.setOption({
    tooltip: { trigger: 'item' },
    legend: { data: ['得分率'], bottom: 0, textStyle: { color: '#c9d1d9' } },
    radar: {
      indicator: indicators,
      center: ['50%', '45%'],
      radius: '65%',
      axisName: { color: '#c9d1d9', fontSize: 12 },
      splitArea: {
        areaStyle: { color: ['rgba(255,154,86,0.05)', 'rgba(255,154,86,0.02)'] },
      },
    },
    series: [{
      type: 'radar',
      name: '得分率',
      data: [{ value: data, name: survey.value.student_name }],
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: '#ff9a56', width: 2 },
      areaStyle: { color: 'rgba(255,154,86,0.2)' },
      itemStyle: { color: '#ff9a56' },
    }],
  })
}

async function loadSurvey(surveyId: number) {
  loading.value = true
  try {
    const res = await listSurveys({ limit: 1, offset: 0 })
    // 用 ID 筛选
    const all = (res as any)?.surveys || []
    if (surveyId && all.length) {
      survey.value = all.find((s: PsychSurvey) => s.id === surveyId) || all[0]
    } else {
      survey.value = all[0] || null
    }
    await nextTick()
    renderRadar()
  } catch (e) {
    console.error('Load survey result error:', e)
  } finally {
    loading.value = false
  }
}

async function loadAI() {
  if (!survey.value) return
  aiLoading.value = true
  try {
    const res = await runAIAnalysis({ survey_id: survey.value.id })
    aiResult.value = res as AIAnalysisResult
  } catch (e: any) {
    ElMessage.error(e?.message || 'AI 分析失败')
  } finally {
    aiLoading.value = false
  }
}

onMounted(() => {
  const surveyId = Number(route.query.survey_id)
  loadSurvey(surveyId)

  // 如果 URL 带了 ai=1，自动触发 AI 分析
  if (route.query.ai === '1') {
    setTimeout(loadAI, 500)
  }
})
</script>

<style scoped>
.result-view {
  padding: 20px;
  color: #c9d1d9;
}

.back-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.view-title {
  font-size: 18px;
  font-weight: 600;
  color: #f0f6fc;
  margin: 0;
}

.loading-wrap {
  padding: 40px;
}

.warm-card {
  background: #161b22 !important;
  border: 1px solid #30363d !important;
}
.warm-card :deep(.el-card__header) {
  border-bottom: 1px solid #30363d;
  padding: 14px 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
}

.student-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.s-name { font-size: 18px; font-weight: 600; color: #f0f6fc; }
.s-class { font-size: 13px; color: #8b949e; }

.metric { text-align: center; }
.metric-label { font-size: 13px; color: #8b949e; margin-bottom: 4px; }
.metric-value { font-size: 36px; font-weight: 700; }
.metric-value.small { font-size: 16px; color: #f0f6fc; }
.metric-unit { font-size: 14px; font-weight: 400; color: #8b949e; }

.dim-table-scroll { max-height: 380px; overflow-y: auto; }
.dim-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #21262d;
}
.dim-info {
  width: 120px;
  flex-shrink: 0;
}
.dim-name { font-size: 13px; color: #c9d1d9; display: block; }
.dim-score { font-size: 12px; color: #8b949e; display: block; }
.dim-pct { font-size: 12px; font-weight: 600; width: 36px; text-align: right; }

.ai-content { padding: 4px 0; }
.v2-segments { display: flex; flex-direction: column; gap: 16px; }
.seg {
  padding: 16px 20px;
  border-radius: 8px;
  border-left: 4px solid;
}
.seg-label { font-weight: 700; font-size: 14px; margin-bottom: 8px; }
.seg p { margin: 0; font-size: 14px; line-height: 1.7; }
.seg-fact {
  background: rgba(64,158,255,0.1);
  border-color: #409eff;
}
.seg-fact .seg-label { color: #409eff; }
.seg-analysis {
  background: rgba(230,162,60,0.1);
  border-color: #e6a23c;
}
.seg-analysis .seg-label { color: #e6a23c; }
.seg-growth {
  background: rgba(103,194,58,0.1);
  border-color: #67c23a;
}
.seg-growth .seg-label { color: #67c23a; }

.ai-plain { padding: 16px; font-size: 14px; line-height: 1.8; }
.ai-plain ul { margin: 8px 0; padding-left: 20px; }
.ai-plain li { margin-bottom: 4px; }
</style>
