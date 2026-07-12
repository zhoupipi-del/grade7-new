<template>
  <div class="radar-container">
    <!-- ═══ 筛选栏 ═══ -->
    <div class="filter-bar">
      <span class="filter-label">学生ID：</span>
      <el-input v-model="studentIdInput" placeholder="输入学生ID" size="small" style="width: 120px" @keyup.enter="fetchRadar" />
      <el-button size="small" type="primary" @click="fetchRadar" :loading="loading">计算雷达</el-button>
      <el-button size="small" @click="fetchLedger" :loading="ledgerLoading">德育工单</el-button>
      <el-tag v-if="radarData" :type="healthTagType" effect="dark" size="default" style="margin-left: 12px">
        {{ healthLabel }}
      </el-tag>
    </div>

    <!-- ═══ 雷达图 + 扣分明细 ═══ -->
    <el-row :gutter="16" v-if="radarData" style="margin-top: 16px">
      <el-col :span="14">
        <el-card shadow="hover" class="dark-card">
          <template #header>
            <span class="card-title">全息五维成长雷达</span>
          </template>
          <div ref="radarChartRef" class="radar-canvas"></div>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="hover" class="dark-card">
          <template #header>
            <span class="card-title">维度扣分明细</span>
          </template>
          <div class="penalty-list">
            <div v-for="dim in dimensionList" :key="dim.key" class="penalty-row">
              <div class="penalty-header">
                <span class="penalty-label" :style="{ color: dim.color }">{{ dim.label }}</span>
                <span class="penalty-score" :style="{ color: scoreColor(radarData.scores[dim.key]) }">
                  {{ radarData.scores[dim.key].toFixed(1) }}
                </span>
              </div>
              <div class="penalty-bar-track">
                <div class="penalty-bar-fill" :style="{
                  width: radarData.scores[dim.key] + '%',
                  background: scoreColor(radarData.scores[dim.key])
                }"></div>
              </div>
              <div class="penalty-detail">
                原始扣分: {{ radarData.penalties[dim.key]?.toFixed(2) || 0 }}
                <el-tag v-if="isAlert(dim.key)" type="danger" size="small" effect="dark" style="margin-left: 6px">
                  {{ alertAction(dim.key) }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 数据来源摘要 ═══ -->
    <el-card v-if="radarData" shadow="hover" class="dark-card" style="margin-top: 16px">
      <template #header>
        <span class="card-title">13路数据采集摘要</span>
      </template>
      <el-row :gutter="12">
        <el-col :span="4" v-for="(item, key) in (sourceSummary as Record<string, { label: string; value: any }>)" :key="key">
          <div class="source-item">
            <div class="source-label">{{ item?.label }}</div>
            <div class="source-value">{{ item?.value }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- ═══ 德育工单列表 ═══ -->
    <el-card v-if="ledgerData" shadow="hover" class="dark-card" style="margin-top: 16px">
      <template #header>
        <div class="ledger-header">
          <span class="card-title">德育量化工单 ({{ ledgerData.total }})</span>
          <el-checkbox v-model="unresolvedOnly" @change="fetchLedger" size="small">仅未解除</el-checkbox>
        </div>
      </template>
      <el-table :data="ledgerData.items" stripe size="small" :max-height="360">
        <el-table-column prop="id" label="工单ID" width="70" />
        <el-table-column prop="student_id" label="学生" width="70" />
        <el-table-column prop="dimension_name" label="维度" width="100">
          <template #default="{ row }">
            <el-tag :type="dimensionTagType(row.dimension_name)" size="small">{{ dimensionLabelMap[row.dimension_name] || row.dimension_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_score" label="触发分" width="80">
          <template #default="{ row }">
            <span :style="{ color: scoreColor(row.trigger_score) }">{{ row.trigger_score.toFixed(1) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="action_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.action_type === 'RED_ZONE' ? 'danger' : 'warning'" size="small" effect="dark">
              {{ row.action_type === 'RED_ZONE' ? '红线' : '警戒' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column prop="is_resolved" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_resolved ? 'success' : 'danger'" size="small">{{ row.is_resolved ? '已解除' : '挂牌中' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="挂牌时间" width="150">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" v-if="canResolve">
          <template #default="{ row }">
            <el-button v-if="!row.is_resolved" type="primary" size="small" link @click="showResolveDialog(row as any as MoralLedgerEntry)">解除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 空状态 ═══ -->
    <el-empty v-if="!radarData && !loading" description="输入学生ID，点击「计算雷达」查看五维全息画像" :image-size="100" style="padding: 60px 0" />

    <!-- ═══ 解除工单对话框 ═══ -->
    <el-dialog v-model="resolveDialog" title="解除德育工单" width="480px">
      <el-form>
        <el-form-item label="工单ID">
          <span>{{ resolveTarget?.id }}</span>
        </el-form-item>
        <el-form-item label="触发维度">
          <el-tag :type="dimensionTagType(resolveTarget?.dimension_name || '')" size="small">
            {{ dimensionLabelMap[resolveTarget?.dimension_name || ''] || resolveTarget?.dimension_name }}
          </el-tag>
        </el-form-item>
        <el-form-item label="触发分数">
          <span :style="{ color: scoreColor(resolveTarget?.trigger_score || 100) }">
            {{ resolveTarget?.trigger_score?.toFixed(1) }}
          </span>
        </el-form-item>
        <el-form-item label="干预说明">
          <el-input v-model="resolveNote" type="textarea" :rows="3" placeholder="记录干预措施（如：已谈话/已补差/已辅导）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resolveDialog = false">取消</el-button>
        <el-button type="primary" @click="doResolve" :loading="resolving">确认解除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, shallowRef, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import '@/utils/echarts'
import { ElMessage } from 'element-plus'
import {
  getFiveDimensionRadar,
  listMoralLedger,
  resolveMoralLedger,
  type RadarResponse,
  type MoralLedgerResponse,
  type MoralLedgerEntry,
} from '@/api/growth'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isParent = computed(() => userStore.currentRole === 'PARENT')
const canResolve = computed(() => ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER'].includes(userStore.currentRole || ''))

// ── 数据 ──
const studentIdInput = ref('')
const loading = ref(false)
const radarData = ref<RadarResponse | null>(null)

const ledgerLoading = ref(false)
const ledgerData = ref<MoralLedgerResponse | null>(null)
const unresolvedOnly = ref(false)

// ── 解除工单 ──
const resolveDialog = ref(false)
const resolveTarget = ref<MoralLedgerEntry | null>(null)
const resolveNote = ref('')
const resolving = ref(false)

// ── ECharts ──
const radarChartRef = ref<HTMLDivElement | null>(null)
const chartInstance = shallowRef<echarts.ECharts | null>(null)

// ── 维度配置 ──
const dimensionList = [
  { key: 'moral', label: '道德品行', color: '#f56c6c' },
  { key: 'academic', label: '学业发展', color: '#409eff' },
  { key: 'psych', label: '身心健康', color: '#8b5cf6' },
  { key: 'habit', label: '行为习惯', color: '#e6a23c' },
  { key: 'practice', label: '综合实践', color: '#67c23a' },
] as const

const dimensionLabelMap: Record<string, string> = {
  moral: '道德品行',
  academic: '学业发展',
  psych: '身心健康',
  habit: '行为习惯',
  practice: '综合实践',
}

// ── 健康状态 ──
const minScore = computed(() => {
  if (!radarData.value) return 100
  return Math.min(...Object.values(radarData.value.scores))
})

const healthTagType = computed((): 'success' | 'info' | 'danger' => {
  if (minScore.value >= 85) return 'success'
  if (minScore.value >= 60) return 'info'
  return 'danger'
})

const healthLabel = computed(() => {
  if (minScore.value >= 85) return '全息卓越'
  if (minScore.value >= 60) return '平稳成长'
  return '高危熔断 / 德育督导中'
})

// ── 来源摘要 ──
const sourceSummary = computed(() => {
  if (!radarData.value) return {}
  const s = radarData.value.sources
  return {
    attendance: { label: '考勤异常', value: s.attendance?.total ?? 0 },
    behavior: { label: '违纪/处分', value: (s.behavior?.violation_count ?? 0) + (s.behavior?.punishment_count ?? 0) },
    academic: { label: '考试均分', value: s.academic?.exam_avg ?? 'N/A' },
    homework: { label: '作业缺交', value: s.homework?.missing_count ?? 0 },
    psych: { label: '心理风险', value: s.psych?.risk_level ?? 'green' },
    timeline: { label: '时光轴事件', value: s.timeline?.total ?? 0 },
    snapshot: { label: '最新快照', value: s.snapshot?.period_label ?? '无' },
    activity: { label: '活动参与', value: s.activity_count ?? 0 },
  }
})

// ── 工具函数 ──
function scoreColor(score: number): string {
  if (score >= 85) return '#67c23a'
  if (score >= 70) return '#409eff'
  if (score >= 60) return '#e6a23c'
  return '#f56c6c'
}

function dimensionTagType(dim: string): 'danger' | 'primary' | 'warning' | 'success' | 'info' {
  const map: Record<string, 'danger' | 'primary' | 'warning' | 'success' | 'info'> = {
    moral: 'danger',
    academic: 'primary',
    psych: 'warning',
    habit: 'warning',
    practice: 'success',
  }
  return map[dim] || 'info'
}

function isAlert(dim: string): boolean {
  return radarData.value?.alerts?.some(a => a.dimension === dim) ?? false
}

function alertAction(dim: string): string {
  const a = radarData.value?.alerts?.find(a => a.dimension === dim)
  return a?.action_type === 'RED_ZONE' ? '红线告警' : '警戒挂牌'
}

function formatTime(t: string | null): string {
  if (!t) return '—'
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

// ── API 调用 ──
async function fetchRadar() {
  const sid = parseInt(studentIdInput.value)
  if (!sid) {
    ElMessage.warning('请输入学生ID')
    return
  }
  loading.value = true
  try {
    radarData.value = await getFiveDimensionRadar(sid)
    await nextTick()
    renderChart()
    if (radarData.value.alerts.length > 0) {
      ElMessage.warning(`检测到 ${radarData.value.alerts.length} 个维度触发德育工单`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '雷达数据获取失败')
  } finally {
    loading.value = false
  }
}

async function fetchLedger() {
  ledgerLoading.value = true
  try {
    const params: any = { unresolved_only: unresolvedOnly.value, page: 1, page_size: 50 }
    if (studentIdInput.value) params.student_id = parseInt(studentIdInput.value)
    ledgerData.value = await listMoralLedger(params)
  } catch (e: any) {
    ElMessage.error(e?.message || '工单列表获取失败')
  } finally {
    ledgerLoading.value = false
  }
}

function showResolveDialog(row: MoralLedgerEntry) {
  resolveTarget.value = row
  resolveNote.value = ''
  resolveDialog.value = true
}

async function doResolve() {
  if (!resolveTarget.value) return
  resolving.value = true
  try {
    await resolveMoralLedger(resolveTarget.value.id, resolveNote.value)
    ElMessage.success('工单已解除')
    resolveDialog.value = false
    await fetchLedger()
    if (studentIdInput.value) await fetchRadar()
  } catch (e: any) {
    ElMessage.error(e?.message || '解除失败')
  } finally {
    resolving.value = false
  }
}

// ── ECharts 渲染 ──
function renderChart() {
  if (!radarChartRef.value || !radarData.value) return

  if (!chartInstance.value) {
    chartInstance.value = echarts.init(radarChartRef.value)
  }

  const scores = radarData.value.scores
  const option = {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(22, 27, 34, 0.95)',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 12 },
    },
    radar: {
      indicator: [
        { name: '道德品行', max: 100 },
        { name: '学业发展', max: 100 },
        { name: '身心健康', max: 100 },
        { name: '行为习惯', max: 100 },
        { name: '综合实践', max: 100 },
      ],
      shape: 'polygon',
      splitNumber: 5,
      center: ['50%', '52%'],
      radius: '68%',
      axisName: {
        color: '#8b949e',
        fontWeight: 'bold' as const,
        fontSize: 13,
      },
      splitLine: {
        lineStyle: {
          color: ['rgba(48, 54, 61, 0.6)', 'rgba(48, 54, 61, 0.5)', 'rgba(48, 54, 61, 0.4)', 'rgba(48, 54, 61, 0.3)', 'rgba(88, 166, 255, 0.4)'],
          width: 1,
        },
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(13, 17, 23, 0.3)', 'rgba(22, 27, 34, 0.3)', 'rgba(13, 17, 23, 0.2)', 'rgba(22, 27, 34, 0.2)', 'rgba(13, 17, 23, 0.1)'],
        },
      },
      axisLine: { lineStyle: { color: 'rgba(48, 54, 61, 0.6)' } },
    },
    series: [
      {
        name: '五维雷达',
        type: 'radar',
        data: [
          {
            value: [scores.moral, scores.academic, scores.psych, scores.habit, scores.practice],
            name: '当前水位',
            itemStyle: { color: '#58a6ff' },
            areaStyle: {
              color: new echarts.graphic.RadialGradient(0.5, 0.5, 0.8, [
                { offset: 0, color: 'rgba(88, 166, 255, 0.05)' },
                { offset: 1, color: 'rgba(88, 166, 255, 0.35)' },
              ]),
            },
            lineStyle: { width: 2, color: '#58a6ff' },
          },
        ],
        animationDuration: 1200,
        animationEasing: 'cubicOut',
      },
    ],
  }

  chartInstance.value.setOption(option, true)
}

function handleResize() {
  chartInstance.value?.resize()
}

watch(() => radarData.value, () => {
  nextTick(() => renderChart())
}, { deep: true })

onMounted(() => {
  window.addEventListener('resize', handleResize)
  // 家长自动加载
  if (isParent.value) {
    const boundId = (userStore.userInfo as any)?.bound_student_id
    if (boundId) {
      studentIdInput.value = String(boundId)
      fetchRadar()
    }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance.value?.dispose()
  chartInstance.value = null
})
</script>

<style scoped>
.radar-container {
  padding: 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #161b22;
  border-radius: 8px;
  border: 1px solid #30363d;
}

.filter-label {
  color: #8b949e;
  font-size: 13px;
  white-space: nowrap;
}

.dark-card {
  background: #161b22 !important;
  border: 1px solid #30363d !important;
}

.dark-card :deep(.el-card__header) {
  background: #0d1117;
  border-bottom: 1px solid #30363d;
}

.dark-card :deep(.el-card__body) {
  background: #161b22;
}

.card-title {
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
}

.radar-canvas {
  width: 100%;
  height: 360px;
}

/* ── 扣分明细 ── */
.penalty-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.penalty-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.penalty-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.penalty-label {
  font-size: 13px;
  font-weight: 600;
}

.penalty-score {
  font-size: 18px;
  font-weight: bold;
}

.penalty-bar-track {
  height: 6px;
  background: rgba(48, 54, 61, 0.5);
  border-radius: 3px;
  overflow: hidden;
}

.penalty-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.8s ease;
}

.penalty-detail {
  font-size: 11px;
  color: #8b949e;
  display: flex;
  align-items: center;
}

/* ── 来源摘要 ── */
.source-item {
  text-align: center;
  padding: 10px;
  background: rgba(13, 17, 23, 0.5);
  border-radius: 6px;
  border: 1px solid rgba(48, 54, 61, 0.5);
}

.source-label {
  font-size: 11px;
  color: #8b949e;
  margin-bottom: 4px;
}

.source-value {
  font-size: 16px;
  font-weight: bold;
  color: #58a6ff;
}

/* ── 工单 ── */
.ledger-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
