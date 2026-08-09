<template>
  <div class="teacher-profile-container">
    <el-card class="profile-card">
      <template #header>
        <div class="card-header">
          <span class="header-title">
            🏅 教师教研全息画像
          </span>
          <el-select
            v-model="selectedTeacherId"
            filterable
            placeholder="选择教师查看教研画像..."
            :loading="loadingTeachers"
            size="default"
            style="width: 280px"
            @change="fetchTeacherProfile"
          >
            <el-option
              v-for="item in teacherList"
              :key="item.id"
              :label="`${item.real_name}${item.subject_code ? ' · ' + item.subject_code : ''}`"
              :value="item.id"
            />
          </el-select>
        </div>
      </template>

      <div v-loading="loadingProfile" element-loading-background="rgba(22, 27, 34, 0.8)">
        <div v-if="profile" class="profile-body">
          <!-- 左侧雷达图 -->
          <div class="radar-section">
            <div ref="radarChartRef" class="radar-chart"></div>
          </div>

          <!-- 右侧指标面板 -->
          <div class="metrics-section">
            <div class="metrics-grid">
              <div class="metric-box">
                <div class="metric-label">备课总数</div>
                <div class="metric-value info">{{ profile.metrics.plans_count }}<span class="unit"> 个</span></div>
                <div class="metric-sub">平均版本: {{ profile.metrics.avg_versions_per_plan }} 次/篇</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">协同批注</div>
                <div class="metric-value success">{{ profile.metrics.comments_count }}<span class="unit"> 条</span></div>
                <div class="metric-sub">社交连接密集度</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">监理质感 (主动)</div>
                <div class="metric-value warning">{{ profile.metrics.observations_count }}<span class="unit"> 节</span></div>
                <div class="metric-sub">弹幕打点: {{ profile.metrics.timeline_marks_count }} 次</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">监理质感 (质量)</div>
                <div class="metric-value" :class="qualityColor">
                  {{ profile.metrics.observed_count > 0 ? profile.metrics.observed_avg_score + '%' : '--' }}
                </div>
                <div class="metric-sub">
                  {{ profile.metrics.observed_count > 0
                    ? '被听课 ' + profile.metrics.observed_count + ' 次 · 评分矩阵 ' + profile.metrics.rubric_count + ' 份'
                    : '暂无被听课评分数据' }}
                </div>
              </div>
              <div class="metric-box">
                <div class="metric-label">AI偏方转化率</div>
                <div class="metric-value danger">{{ profile.scores.ai_integration }}<span class="unit">%</span></div>
                <div class="metric-sub">AI应用: {{ profile.metrics.ai_integration_count }} 篇</div>
              </div>
              <div class="metric-box" v-if="profile.metrics.scoring_count > 0">
                <div class="metric-label">评分客观度</div>
                <div class="metric-value" :class="objectivityColor">
                  {{ objectivityLabel }}
                </div>
                <div class="metric-sub">
                  均分 {{ profile.metrics.scoring_avg }}% · 全校 {{ profile.metrics.school_avg_score }}%
                </div>
              </div>
            </div>

            <!-- 🏅 勋章墙 -->
            <div class="badge-wall">
              <div class="badge-title">🏅 已获得教研勋章</div>
              <div class="badge-list">
                <el-tag
                  v-if="profile.scores.intensity > 70"
                  type="danger"
                  effect="dark"
                  size="large"
                >🔥 备课狂魔</el-tag>
                <el-tag
                  v-if="profile.scores.social > 60"
                  type="success"
                  effect="dark"
                  size="large"
                >💬 协同中枢</el-tag>
                <el-tag
                  v-if="profile.scores.rigor > 50"
                  type="warning"
                  effect="dark"
                  size="large"
                >🎯 金牌监工</el-tag>
                <el-tag
                  v-if="profile.metrics.observed_avg_score >= 85"
                  type="danger"
                  effect="dark"
                  size="large"
                >🏆 课堂王牌</el-tag>
                <el-tag
                  v-if="profile.metrics.ai_published_count > 1"
                  type="primary"
                  effect="dark"
                  size="large"
                >🤖 AI尝鲜者</el-tag>
                <span
                  v-if="profile.scores.intensity <= 70 && profile.scores.social <= 60 && profile.scores.rigor <= 50 && profile.metrics.observed_avg_score < 85 && profile.metrics.ai_published_count <= 1"
                  class="no-badge"
                >暂未达成勋章，加油备课听课哦！</span>
              </div>
            </div>
          </div>
        </div>

        <el-empty v-else description="选择一位教师，瞬间拉起他的全息教研轨迹画像" />
      </div>
    </el-card>

    <!-- 🔍 教学盲区关注度（独立诊断维度，不计入综合分） -->
    <el-card v-if="errorGap" class="blindspot-card">
      <template #header>
        <div class="card-header">
          <span class="header-title">🔍 教学盲区关注度 · 独立诊断维度</span>
          <el-tag :type="attributionTagType" effect="dark" size="small">
            {{ attributionLabel }}
          </el-tag>
        </div>
      </template>

      <div v-loading="loadingErrorGap" element-loading-background="rgba(22, 27, 34, 0.8)">
        <div v-if="errorGap.attribution === 'none'" class="blindspot-empty">
          ⚪ 该教师暂无任教班级 / 学科映射，盲区诊断暂不可计。
        </div>

        <div v-else class="blindspot-body">
          <div class="blindspot-score">
            <div class="score-value" :class="scoreColor">{{ errorGap.score }}</div>
            <div class="score-label">教学盲区关注度 / 100</div>
            <div class="score-sub">归因任教学生 {{ errorGap.attributed_students }} 人</div>
          </div>

          <div class="blindspot-detail">
            <div class="detail-block">
              <div class="block-title">📕 错题本</div>
              <div class="block-row"><span>归因错题</span><b>{{ errorGap.error_book.total }}</b></div>
              <div class="block-row"><span>未纠错</span><b class="warn">{{ errorGap.error_book.unresolved }}</b></div>
              <div class="type-tags">
                <el-tag
                  v-for="(cnt, type) in errorGap.error_book.by_error_type"
                  :key="type"
                  size="small"
                  type="info"
                  effect="plain"
                >{{ errorTypeLabel(type) }} {{ cnt }}</el-tag>
              </div>
            </div>

            <div class="detail-block">
              <div class="block-title">🧩 知识点断层</div>
              <div class="block-row"><span>断层总数</span><b>{{ errorGap.knowledge_gap.total }}</b></div>
              <div class="block-row"><span>危重 critical</span><b class="danger">{{ errorGap.knowledge_gap.critical }}</b></div>
              <div class="block-row"><span>活跃 active</span><b class="warn">{{ errorGap.knowledge_gap.active }}</b></div>
              <div class="block-row"><span>已消解 resolved</span><b class="ok">{{ errorGap.knowledge_gap.resolved }}</b></div>
            </div>
          </div>
        </div>

        <div v-if="errorGap.attribution !== 'none'" class="blindspot-foot">
          ⚠️ 本指标为教学诊断信号，<b>独立于</b>四维教研效能综合分，<b>不计入</b>全校排行榜。
        </div>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted, nextTick, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { getActiveTeachers, getTeacherProfile, getTeacherErrorGap } from '@/api/researchProfile'
import type { ActiveTeacher, TeacherResearchProfile, TeacherErrorGap } from '@/api/researchProfile'
import { ElMessage } from 'element-plus'

const loadingTeachers = ref(false)
const loadingProfile = ref(false)
const teacherList = ref<ActiveTeacher[]>([])
const selectedTeacherId = ref<number | null>(null)
const profile = ref<TeacherResearchProfile | null>(null)
const loadingErrorGap = ref(false)
const errorGap = ref<TeacherErrorGap | null>(null)

const radarChartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

const fetchTeachers = async () => {
  loadingTeachers.value = true
  try {
    const data = await getActiveTeachers()
    teacherList.value = data
    if (data.length > 0 && !selectedTeacherId.value) {
      selectedTeacherId.value = data[0].id
      await fetchTeacherProfile()
    }
  } catch {
    ElMessage.error('无法加载教研活跃教师列表')
  } finally {
    loadingTeachers.value = false
  }
}

const fetchTeacherProfile = async () => {
  if (!selectedTeacherId.value) return
  loadingProfile.value = true
  loadingErrorGap.value = true
  try {
    const [profileRes, gapRes] = await Promise.allSettled([
      getTeacherProfile(selectedTeacherId.value),
      getTeacherErrorGap(selectedTeacherId.value),
    ])
    if (profileRes.status === 'fulfilled') {
      profile.value = profileRes.value
      await nextTick()
      renderRadarChart()
    } else {
      ElMessage.error('拉取教师全息教研画像失败')
    }
    // 教学盲区诊断为附加独立维度，失败不阻塞主画像
    if (gapRes.status === 'fulfilled') {
      errorGap.value = gapRes.value
    } else {
      errorGap.value = null
    }
  } finally {
    loadingProfile.value = false
    loadingErrorGap.value = false
  }
}

const renderRadarChart = () => {
  if (!radarChartRef.value || !profile.value) return
  if (chartInstance) chartInstance.dispose()

  chartInstance = echarts.init(radarChartRef.value, 'dark')
  chartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    radar: {
      indicator: [
        { name: '备课狂热度', max: 100 },
        { name: '教研社交活性', max: 100 },
        { name: '监理课堂质感', max: 100 },
        { name: 'AI偏方应用率', max: 100 },
      ],
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: '#8b949e', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(48, 54, 61, 0.6)' } },
      splitArea: {
        show: true,
        areaStyle: { color: ['rgba(48,54,61,0.1)', 'rgba(48,54,61,0.2)'] },
      },
      axisLine: { lineStyle: { color: 'rgba(48, 54, 61, 0.6)' } },
    },
    series: [{
      name: '教研效能',
      type: 'radar',
      data: [{
        value: [
          profile.value.scores.intensity,
          profile.value.scores.social,
          profile.value.scores.rigor,
          profile.value.scores.ai_integration,
        ],
        name: '效能指数',
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f56c6c' },
        areaStyle: {
          color: new echarts.graphic.RadialGradient(0.5, 0.5, 1, [
            { offset: 0, color: 'rgba(245, 108, 108, 0.1)' },
            { offset: 1, color: 'rgba(245, 108, 108, 0.5)' },
          ]),
        },
        itemStyle: { color: '#f56c6c' },
      }],
    }],
  })
}

const handleResize = () => chartInstance?.resize()

// V3.2 质量维度计算属性
const qualityColor = computed(() => {
  if (!profile.value || profile.value.metrics.observed_count === 0) return 'muted'
  const q = profile.value.metrics.observed_avg_score
  if (q >= 85) return 'success'
  if (q >= 60) return 'warning'
  return 'danger'
})

const objectivityColor = computed(() => {
  if (!profile.value || profile.value.metrics.scoring_count === 0) return 'muted'
  const dev = Math.abs(
    profile.value.metrics.scoring_avg - profile.value.metrics.school_avg_score
  )
  if (dev <= 3) return 'success'
  if (dev <= 10) return 'warning'
  return 'danger'
})

const objectivityLabel = computed(() => {
  if (!profile.value || profile.value.metrics.scoring_count === 0) return '--'
  const dev = Math.abs(
    profile.value.metrics.scoring_avg - profile.value.metrics.school_avg_score
  )
  if (dev <= 3) return '✓ 客观'
  if (dev <= 10) return '△ 轻微偏差'
  return '✗ 偏差较大'
})

// 🔍 教学盲区关注度（独立诊断维度，不计入四维综合分）
const attributionLabel = computed(() => {
  const a = errorGap.value?.attribution
  if (a === 'precise') return '🎯 精确归因（课表时空实例）'
  if (a === 'fallback') return '🧭 回退归因（学科 / 年级组）'
  return '⚪ 无任教映射'
})

const attributionTagType = computed<'success' | 'warning' | 'info'>(() => {
  const a = errorGap.value?.attribution
  if (a === 'precise') return 'success'
  if (a === 'fallback') return 'warning'
  return 'info'
})

const scoreColor = computed(() => {
  const s = errorGap.value?.score ?? 0
  if (s >= 60) return 'danger'
  if (s >= 30) return 'warning'
  return 'success'
})

const errorTypeLabel = (type: string): string => {
  const map: Record<string, string> = {
    conceptual: '概念',
    procedural: '程序',
    careless: '粗心',
    omission: '疏漏',
    unknown: '未知',
  }
  return map[type] ?? type
}

onMounted(() => {
  fetchTeachers()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<style scoped>
.teacher-profile-container { width: 100%; }

.profile-card {
  background-color: var(--bg-secondary, #161b22) !important;
  border: 1px solid var(--border-color, #30363d) !important;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #e6edf3);
}

.profile-body {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.radar-section {
  flex: 1;
  min-width: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.radar-chart {
  width: 100%;
  height: 340px;
  min-width: 300px;
}

.metrics-section {
  flex: 1;
  min-width: 280px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.metric-box {
  background-color: var(--bg-tertiary, #0d1117);
  border: 1px solid var(--border-color, #30363d);
  border-radius: 8px;
  padding: 14px;
  text-align: center;
  transition: transform 0.15s, box-shadow 0.15s;
}

.metric-box:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.metric-label {
  font-size: 12px;
  color: var(--text-tertiary, #8b949e);
  margin-bottom: 4px;
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.3;
}

.metric-value .unit {
  font-size: 14px;
  font-weight: 400;
}

.metric-value.info { color: #58a6ff; }
.metric-value.success { color: #3fb950; }
.metric-value.warning { color: #d29922; }
.metric-value.danger { color: #f85149; }
.metric-value.muted { color: #484f58; }

.metric-sub {
  font-size: 11px;
  color: var(--text-tertiary, #484f58);
  margin-top: 4px;
}

.badge-wall {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--border-color, #30363d);
}

.badge-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary, #c9d1d9);
  margin-bottom: 10px;
}

.badge-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.no-badge {
  font-size: 12px;
  color: var(--text-tertiary, #484f58);
}

.blindspot-card {
  margin-top: 16px;
  background-color: var(--bg-secondary, #161b22) !important;
  border: 1px solid var(--border-color, #30363d) !important;
}

.blindspot-empty {
  font-size: 13px;
  color: var(--text-tertiary, #8b949e);
  text-align: center;
  padding: 20px 0;
}

.blindspot-body {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  align-items: center;
}

.blindspot-score {
  flex: 0 0 200px;
  text-align: center;
  padding: 16px;
  border-radius: 10px;
  background: var(--bg-tertiary, #0d1117);
  border: 1px solid var(--border-color, #30363d);
}

.score-value {
  font-size: 48px;
  font-weight: 800;
  line-height: 1.1;
}

.score-value.danger { color: #f85149; }
.score-value.warning { color: #d29922; }
.score-value.success { color: #3fb950; }

.score-label {
  font-size: 13px;
  color: var(--text-secondary, #c9d1d9);
  margin-top: 6px;
}

.score-sub {
  font-size: 12px;
  color: var(--text-tertiary, #8b949e);
  margin-top: 4px;
}

.blindspot-detail {
  flex: 1;
  min-width: 280px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.detail-block {
  background: var(--bg-tertiary, #0d1117);
  border: 1px solid var(--border-color, #30363d);
  border-radius: 8px;
  padding: 14px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #c9d1d9);
  margin-bottom: 10px;
}

.block-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-tertiary, #8b949e);
  padding: 3px 0;
}

.block-row b { color: var(--text-primary, #e6edf3); font-weight: 700; }
.block-row b.warn { color: #d29922; }
.block-row b.danger { color: #f85149; }
.block-row b.ok { color: #3fb950; }

.type-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.blindspot-foot {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color, #30363d);
  font-size: 12px;
  color: var(--text-tertiary, #8b949e);
}

.blindspot-foot b { color: var(--text-secondary, #c9d1d9); }
</style>
