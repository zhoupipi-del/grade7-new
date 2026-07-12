<template>
  <div class="ai-prescription-container">
    <!-- ═══ Layer 1: Patient Header Card ═══ -->
    <el-card shadow="never" class="patient-header-card" v-loading="loading" element-loading-text="AI 处方引擎分析中...">
      <div class="patient-profile">
        <!-- Avatar -->
        <div class="patient-avatar" :style="{ background: avatarGradient }">
          {{ avatarText }}
        </div>

        <!-- Info -->
        <div class="patient-info">
          <div class="patient-name-row">
            <span class="patient-name">{{ prescription?.student_name ?? '--' }}</span>
            <el-tag size="small" effect="plain" round>{{ prescription?.class_name ?? '--' }}</el-tag>
            <el-tag size="small" :type="riskTagType" effect="dark" round>
              <el-icon :size="12" style="margin-right: 4px"><WarningFilled /></el-icon>
              {{ riskLabel }}
            </el-tag>
          </div>
          <div class="patient-summary-box">
            <el-icon class="summary-icon"><Notebook /></el-icon>
            <span class="summary-text">{{ prescription?.analysis_summary ?? 'AI 分析摘要加载中...' }}</span>
          </div>
        </div>

        <!-- RDI Score Badge -->
        <div class="rdi-badge">
          <div class="rdi-value" :style="{ color: rdiColor }">{{ prescription?.rdi_score?.toFixed(2) ?? '--' }}</div>
          <div class="rdi-label">RDI 偏离指数</div>
          <div class="rdi-bar">
            <div class="rdi-bar-fill" :style="{ width: rdiBarWidth, background: rdiColor }"></div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ═══ Layer 2: Control Banner ═══ -->
    <div class="control-banner">
      <div class="banner-left">
        <el-icon :size="16"><Timer /></el-icon>
        <span class="banner-time">生成时间：{{ formattedTime }}</span>
        <el-divider direction="vertical" />
        <el-icon :size="16" :color="breakerActive ? '#67c23a' : '#e6a23c'"><Clock /></el-icon>
        <span :class="['banner-deadline', { 'deadline-active': breakerActive }]">
          {{ breakerActive ? `干预进行中 · 剩余 ${breakerCountdown}` : '72 小时干预窗口未启动' }}
        </span>
      </div>
      <div class="banner-right">
        <el-button :icon="Printer" @click="handlePrint">打印处方</el-button>
        <el-button
          type="primary"
          :icon="Check"
          :disabled="breakerActive"
          @click="handleImplement"
        >
          {{ breakerActive ? '已确认接单' : '确认接单并投入干预' }}
        </el-button>
      </div>
    </div>

    <!-- ═══ Layer 3 V2: Three-Segment Display (Fact→Analysis→Growth) ═══ -->
    <template v-if="hasV2Segments">
      <!-- ══ Segment 1: Fact — Clinical Facts (Blue Calm) ══ -->
      <div class="segment-card segment-fact">
        <div class="segment-header">
          <div class="segment-icon-wrapper icon-fact">
            <el-icon :size="20"><DataAnalysis /></el-icon>
          </div>
          <div class="segment-title-area">
            <span class="segment-title">临床事实</span>
            <span class="segment-subtitle">Fact · σ值精确 · 临床严谨</span>
          </div>
          <el-tag size="small" type="primary" effect="plain" round>冷静蓝</el-tag>
        </div>
        <div class="segment-body" v-html="renderedFact"></div>
      </div>

      <!-- ══ Segment 2: Analysis — Cross-Diagnosis (Orange) ══ -->
      <div class="segment-card segment-analysis">
        <div class="segment-header">
          <div class="segment-icon-wrapper icon-analysis">
            <el-icon :size="20"><Connection /></el-icon>
          </div>
          <div class="segment-title-area">
            <span class="segment-title">交叉归因</span>
            <span class="segment-subtitle">Analysis · 学业×行为×心理 · 诊断叙事</span>
          </div>
          <el-tag size="small" type="warning" effect="plain" round>诊断橙</el-tag>
        </div>
        <div class="segment-body" v-html="renderedAnalysis"></div>
      </div>

      <!-- ══ Segment 3: Growth — Three-Tier Intervention (Green) ══ -->
      <div class="segment-card segment-growth">
        <div class="segment-header">
          <div class="segment-icon-wrapper icon-growth">
            <el-icon :size="20"><TrendCharts /></el-icon>
          </div>
          <div class="segment-title-area">
            <span class="segment-title">三层递进干预</span>
            <span class="segment-subtitle">Growth · 即时24h → 短期72h → 持续4周 · 实操话术</span>
          </div>
          <el-tag size="small" type="success" effect="plain" round>实操绿</el-tag>
        </div>
        <div class="segment-body" v-html="renderedGrowth"></div>
      </div>
    </template>

    <!-- ═══ V1 Fallback: Measures Grid (backward compat) ═══ -->
    <template v-if="!hasV2Segments && prescription?.measures?.length">
      <el-row :gutter="20" class="measures-grid">
        <el-col
          v-for="measure in prescription.measures"
          :key="measure.id"
          :xs="24"
          :sm="12"
          :md="12"
          :lg="12"
        >
          <el-card shadow="hover" class="measure-card" :class="`card-${measure.tag_type}`">
            <div class="measure-header">
              <div class="measure-icon-wrapper" :class="`icon-${measure.tag_type}`">
                <el-icon :size="24"><WarningFilled /></el-icon>
              </div>
              <div class="measure-title-area">
                <span class="measure-category">{{ measure.category }}</span>
                <el-tag size="small" :type="measure.tag_type" effect="light" round>
                  {{ measure.timeline }}
                </el-tag>
              </div>
            </div>
            <div class="measure-section">
              <div class="section-label">
                <span class="section-icon">⚠️</span>
                <span>症结透视</span>
              </div>
              <div class="section-content issue-content">{{ measure.core_issue }}</div>
            </div>
            <div class="measure-section">
              <div class="section-label">
                <span class="section-icon">🚀</span>
                <span>临床执行步骤</span>
              </div>
              <ol class="action-list">
                <li v-for="(step, idx) in measure.action_plan" :key="idx">{{ step }}</li>
              </ol>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- Empty State -->
    <el-card shadow="never" v-if="!loading && !hasV2Segments && !prescription?.measures?.length" class="empty-card">
      <el-result icon="warning" title="暂无处方数据" sub-title="请从 RDI 风险雷达选择学生后生成 AI 处方">
        <template #extra>
          <el-button type="primary" @click="goBack">返回风险雷达</el-button>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Timer, Clock, Printer, Check, Notebook,
  WarningFilled, DataAnalysis, Connection, TrendCharts,
} from '@element-plus/icons-vue'
import {
  getAIPrescriptionV2, activateBreaker, isBreakerActive, getBreakerRemaining,
  renderSegmentMarkdown, type AIPrescriptionPayloadV2, type RiskLevel,
} from '@/api/prescription'

const route = useRoute()
const router = useRouter()

// ─── State ──────────────────────────────────────────────────────
const loading = ref(true)
const prescription = ref<AIPrescriptionPayloadV2 | null>(null)
const breakerActive = ref(false)
const breakerRemainingMs = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// ─── Computed ───────────────────────────────────────────────────
const warningId = computed(() => {
  const raw = route.query.warning_id as string
  return raw ? parseInt(raw, 10) : 0
})
const studentId = computed(() => {
  const raw = route.query.student_id as string
  return raw ? parseInt(raw, 10) : 0
})

const avatarText = computed(() => {
  const name = prescription.value?.student_name ?? ''
  return name.length >= 2 ? name.slice(-2) : name
})

const avatarGradient = computed(() => {
  const name = prescription.value?.student_name ?? ''
  const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const hue = hash % 360
  return `linear-gradient(135deg, hsl(${hue}, 65%, 55%), hsl(${(hue + 40) % 360}, 65%, 45%))`
})

const formattedTime = computed(() => {
  const ts = prescription.value?.generated_at
  if (!ts) return '--'
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

const rdiColor = computed(() => {
  const score = prescription.value?.rdi_score ?? 0
  if (score >= 5.0) return '#f56c6c'
  if (score >= 4.0) return '#e6a23c'
  return '#67c23a'
})

const rdiBarWidth = computed(() => {
  const score = prescription.value?.rdi_score ?? 0
  const pct = Math.min((score / 8) * 100, 100)
  return `${pct}%`
})

const breakerCountdown = computed(() => {
  const ms = breakerRemainingMs.value
  if (ms <= 0) return '0h'
  const h = Math.floor(ms / (1000 * 60 * 60))
  const m = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60))
  return `${h}h ${m}m`
})

// V2 segment flags
const hasV2Segments = computed(() => {
  const p = prescription.value
  return p && (!!p.fact || !!p.analysis || !!p.growth)
})

// V2 rendered segments (Markdown → HTML)
const renderedFact = computed(() => renderSegmentMarkdown(prescription.value?.fact ?? ''))
const renderedAnalysis = computed(() => renderSegmentMarkdown(prescription.value?.analysis ?? ''))
const renderedGrowth = computed(() => renderSegmentMarkdown(prescription.value?.growth ?? ''))

// Risk level display
const riskLevel = computed<RiskLevel>(() => prescription.value?.risk_level ?? 'MEDIUM')

const riskTagType = computed(() => {
  switch (riskLevel.value) {
    case 'CRITICAL': return 'danger'
    case 'HIGH': return 'danger'
    case 'MEDIUM': return 'warning'
    case 'LOW': return 'success'
    default: return 'info'
  }
})

const riskLabel = computed(() => {
  switch (riskLevel.value) {
    case 'CRITICAL': return '一票否决 ⚠️'
    case 'HIGH': return 'RED 级干预'
    case 'MEDIUM': return 'WARNING 级'
    case 'LOW': return '观察级'
    default: return '待评估'
  }
})

// ─── Data Loading ───────────────────────────────────────────────
async function loadPrescription() {
  loading.value = true
  try {
    const wid = warningId.value || 1
    const sid = studentId.value
    prescription.value = await getAIPrescriptionV2(wid, sid || undefined)

    // Check breaker state
    if (isBreakerActive(wid)) {
      breakerActive.value = true
      breakerRemainingMs.value = getBreakerRemaining(wid)
      startCountdown()
    }
  } catch (err) {
    console.error('[AI Prescription] Load failed:', err)
    ElMessage.error('AI 处方加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

// ─── Actions ────────────────────────────────────────────────────
function handlePrint() {
  window.print()
}

async function handleImplement() {
  try {
    await ElMessageBox.confirm(
      '确认接单后，72 小时干预窗口将立即启动。系统将追踪您的执行进度，到期前自动提醒。',
      '确认接单并投入干预',
      {
        confirmButtonText: '确认接单',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    const wid = warningId.value || prescription.value?.warning_id || 1
    activateBreaker(wid)
    breakerActive.value = true
    breakerRemainingMs.value = getBreakerRemaining(wid)
    startCountdown()

    ElMessage.success('已确认接单 — 72 小时干预窗口已启动，系统将自动追踪执行进度')
  } catch {
    // User cancelled
  }
}

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    breakerRemainingMs.value -= 1000
    if (breakerRemainingMs.value <= 0) {
      breakerActive.value = false
      breakerRemainingMs.value = 0
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      ElMessage.info('72 小时干预窗口已到期 — 请提交干预效果评估')
    }
  }, 1000)
}

function goBack() {
  router.push('/rdi-radar')
}

// ─── Lifecycle ──────────────────────────────────────────────────
onMounted(() => {
  loadPrescription()
})

onUnmounted(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<style scoped>
/* ═══ Container ═══ */
.ai-prescription-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ═══ Layer 1: Patient Header ═══ */
.patient-header-card {
  border-radius: 10px;
  border: 1px solid var(--el-border-color-light);
}
.patient-profile {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}
.patient-avatar {
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}
.patient-info {
  flex: 1;
  min-width: 0;
}
.patient-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.patient-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}
.patient-summary-box {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 14px;
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  line-height: 1.7;
}
.summary-icon {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--el-color-primary);
}
.summary-text {
  font-size: 13.5px;
  color: var(--el-text-color-regular);
}
.rdi-badge {
  flex-shrink: 0;
  text-align: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, var(--el-fill-color-lighter), var(--el-fill-color));
  border-radius: 10px;
  min-width: 120px;
}
.rdi-value {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 4px;
}
.rdi-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.rdi-bar {
  width: 100%;
  height: 6px;
  background: var(--el-fill-color-dark);
  border-radius: 3px;
  overflow: hidden;
}
.rdi-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}

/* ═══ Layer 2: Control Banner ═══ */
.control-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.banner-left {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.banner-time {
  white-space: nowrap;
}
.banner-deadline {
  font-weight: 500;
  color: var(--el-color-warning);
}
.banner-deadline.deadline-active {
  color: var(--el-color-success);
}
.banner-right {
  display: flex;
  gap: 10px;
}

/* ═══ Layer 3 V2: Segment Cards ═══ */
.segment-card {
  border-radius: 10px;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  overflow: hidden;
  transition: box-shadow 0.3s ease;
}
.segment-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

/* Fact — Blue Calm */
.segment-fact {
  border-left: 4px solid #409eff;
}
.segment-fact .segment-header {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.08), rgba(64, 158, 255, 0.02));
}

/* Analysis — Orange Diagnosis */
.segment-analysis {
  border-left: 4px solid #e6a23c;
}
.segment-analysis .segment-header {
  background: linear-gradient(135deg, rgba(230, 162, 60, 0.08), rgba(230, 162, 60, 0.02));
}

/* Growth — Green Action */
.segment-growth {
  border-left: 4px solid #67c23a;
}
.segment-growth .segment-header {
  background: linear-gradient(135deg, rgba(103, 194, 58, 0.08), rgba(103, 194, 58, 0.02));
}

/* Segment Header */
.segment-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.segment-icon-wrapper {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.icon-fact {
  background: linear-gradient(135deg, #409eff, #79bbff);
}
.icon-analysis {
  background: linear-gradient(135deg, #e6a23c, #f0c78a);
}
.icon-growth {
  background: linear-gradient(135deg, #67c23a, #95d475);
}
.segment-title-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.segment-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}
.segment-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  letter-spacing: 0.5px;
}

/* Segment Body — Markdown Content */
.segment-body {
  padding: 20px 24px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
  font-size: 14px;
}

/* Markdown Rendered Content Styles */
.segment-body .seg-content {
  /* root container */
}
.segment-body .seg-p {
  margin-bottom: 12px;
}
.segment-body .seg-h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin: 16px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.segment-body .seg-h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 12px 0 6px;
}
.segment-body strong {
  color: var(--el-text-color-primary);
  font-weight: 600;
}
.segment-body .seg-ul {
  margin: 8px 0;
  padding-left: 0;
  list-style: none;
}
.segment-body .seg-li {
  position: relative;
  padding-left: 18px;
  margin-bottom: 6px;
  line-height: 1.7;
}
.segment-body .seg-li::before {
  content: '•';
  position: absolute;
  left: 4px;
  color: var(--el-text-color-secondary);
  font-weight: 700;
}

/* Growth-specific tier highlight */
.segment-growth .seg-li::before {
  content: '▸';
  color: #67c23a;
}

/* ═══ V1 Fallback: Measures Grid ═══ */
.measures-grid {
  margin-top: 4px;
}
.measure-card {
  border-radius: 10px;
  border: 1px solid var(--el-border-color-light);
  margin-bottom: 16px;
  transition: box-shadow 0.3s ease, transform 0.2s ease;
}
.measure-card:hover {
  transform: translateY(-2px);
}
.card-danger {
  border-left: 3px solid var(--el-color-danger);
}
.card-warning {
  border-left: 3px solid var(--el-color-warning);
}
.card-success {
  border-left: 3px solid var(--el-color-success);
}
.card-info {
  border-left: 3px solid var(--el-color-info);
}

/* Measure Header */
.measure-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}
.measure-icon-wrapper {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.icon-danger {
  background: linear-gradient(135deg, #f56c6c, #f89898);
}
.icon-warning {
  background: linear-gradient(135deg, #e6a23c, #f0c78a);
}
.icon-success {
  background: linear-gradient(135deg, #67c23a, #95d475);
}
.icon-info {
  background: linear-gradient(135deg, #909399, #b1b3b8);
}
.measure-title-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.measure-category {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

/* Measure Sections */
.measure-section {
  margin-bottom: 14px;
}
.section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.section-icon {
  font-size: 14px;
}
.section-content {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.issue-content {
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  border-left: 2px solid var(--el-border-color);
}
.action-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
.action-list li {
  margin-bottom: 4px;
}

/* ═══ Empty State ═══ */
.empty-card {
  border-radius: 10px;
}

/* ═══ Responsive ═══ */
@media (max-width: 768px) {
  .patient-profile {
    flex-direction: column;
  }
  .rdi-badge {
    width: 100%;
  }
  .control-banner {
    flex-direction: column;
    gap: 10px;
    align-items: stretch;
  }
  .banner-left {
    flex-wrap: wrap;
  }
  .banner-right {
    justify-content: flex-end;
  }
  .segment-header {
    flex-wrap: wrap;
    gap: 10px;
  }
  .segment-body {
    padding: 16px;
  }
}

/* ═══ Print Styles — Clean Paper Prescription ═══ */
@media print {
  .control-banner,
  .layout-aside,
  .layout-header,
  .el-aside,
  .el-header {
    display: none !important;
  }
  .ai-prescription-container {
    gap: 8px;
  }
  .patient-header-card,
  .segment-card,
  .measure-card,
  .empty-card {
    border: 1px solid #ccc !important;
    box-shadow: none !important;
    break-inside: avoid;
  }
  .patient-summary-box {
    border: 1px dashed #999;
  }
  .rdi-badge {
    border: 1px solid #ccc;
  }
  .segment-fact {
    border-left: 4px solid #409eff;
  }
  .segment-analysis {
    border-left: 4px solid #e6a23c;
  }
  .segment-growth {
    border-left: 4px solid #67c23a;
  }
  body {
    background: #fff !important;
    color: #000 !important;
  }
  .summary-text,
  .segment-body,
  .action-list,
  .patient-name,
  .measure-category,
  .segment-title {
    color: #000 !important;
  }
}
</style>
