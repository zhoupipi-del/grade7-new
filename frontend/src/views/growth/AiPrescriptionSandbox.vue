<template>
  <div class="sandbox-overlay" v-if="visible" @click.self="handleDismiss">
    <div class="sandbox-panel">
      <!-- ── Header: 红色预警标识 ── -->
      <div class="sandbox-header">
        <div class="alert-badge">
          <span class="pulse-dot"></span>
          <el-icon :size="20"><WarningFilled /></el-icon>
          <span class="alert-type">{{ alertData?.alert_type || '复合预警' }}</span>
        </div>
        <h3 class="alert-title">{{ alertData?.title || '沸点拦截' }}</h3>
        <div class="alert-meta">
          <span>学生ID: {{ alertData?.student_id || alertId }}</span>
          <span>{{ formatDateTime(alertData?.created_at || '') }}</span>
        </div>
        <el-button class="close-btn" :icon="Close" circle size="small" @click="handleDismiss" />
      </div>

      <!-- ── Loading State ── -->
      <div v-if="loading.detail" class="sandbox-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在获取预警详情...</p>
      </div>

      <!-- ── Main Content ── -->
      <div v-else-if="alertData" class="sandbox-body">
        <!-- Reason Meta -->
        <div v-if="alertData.reason_meta" class="reason-section">
          <div class="section-label"><el-icon><InfoFilled /></el-icon> 触发原因</div>
          <div class="reason-cards">
            <template v-for="(val, key) in alertData.reason_meta" :key="key">
              <div v-if="typeof val === 'object' || typeof val === 'string'" class="reason-card">
                <span class="reason-key">{{ formatReasonKey(String(key)) }}</span>
                <span class="reason-val">{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
              </div>
            </template>
          </div>
        </div>

        <!-- AI Prescription: Typewriter -->
        <div class="prescription-section">
          <div class="section-label"><el-icon><MagicStick /></el-icon> AI 处方 (V3 三轨驱动)</div>
          <div class="prescription-box" ref="prescriptionBoxRef">
            <div class="typewriter-content" v-html="typewriterHtml"></div>
            <span v-if="isTyping" class="typewriter-cursor">▌</span>
            <div v-if="isTyping" class="typing-progress">
              <el-progress :percentage="typingProgress" :stroke-width="2" color="#f56c6c" :show-text="false" />
            </div>
          </div>
          <div v-if="!isTyping && !alertData.ai_prescription" class="no-prescription">
            <el-icon :size="24"><Warning /></el-icon>
            <p>该预警尚未生成AI处方</p>
          </div>
        </div>

        <!-- Human-in-the-Loop Fine-tuning -->
        <div v-if="!alertData.is_resolved && !isTyping" class="fine-tuning-section">
          <div class="section-label"><el-icon><EditPen /></el-icon> 人工微调沙箱</div>
          <el-input
            v-model="finalPrescription"
            type="textarea"
            :rows="6"
            placeholder="在AI处方基础上进行微调，或直接输入最终处置方案（至少10字）..."
            maxlength="2000"
            show-word-limit
            :disabled="loading.resolve"
          />
          <div class="tuning-actions">
            <el-input
              v-model="resolutionNote"
              placeholder="处置备注（可选，最多500字）"
              maxlength="500"
              show-word-limit
              :disabled="loading.resolve"
              style="flex: 1"
            />
            <el-button
              type="danger"
              @click="handleResolve"
              :loading="loading.resolve"
              :disabled="finalPrescription.trim().length < 10"
            >
              <el-icon><Stamp /></el-icon> 签署归档
            </el-button>
          </div>
        </div>

        <!-- Resolved State -->
        <div v-if="alertData.is_resolved" class="resolved-badge">
          <el-icon :size="20"><CircleCheckFilled /></el-icon>
          <span>已归档 — {{ formatDateTime(alertData.resolved_at || '') }}</span>
        </div>
        <div v-if="alertData.is_resolved && alertData.final_prescription" class="final-prescription-box">
          <div class="section-label">最终处方</div>
          <div class="prescription-text" v-html="formatAiPrescription(alertData.final_prescription)"></div>
        </div>
      </div>

      <!-- ── Error State ── -->
      <div v-else class="sandbox-error">
        <el-icon :size="32"><WarningFilled /></el-icon>
        <p>{{ errorMsg || '无法获取预警详情' }}</p>
        <el-button size="small" @click="fetchAlertDetail">重新加载</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AiPrescriptionSandbox — CEP 复合预警 AI处方微调沙箱
 *
 * 核心能力:
 * 1. SSE推送触发 → 红色预警弹窗
 * 2. 打字机动画渲染V3 AI处方 (~15ms/字符)
 * 3. Human-in-the-Loop 人工微调textarea
 * 4. 一键签署归档 POST /growth/alerts/{id}/resolve
 * 5. 暗色主题对齐 (#0d1117/#161b22/#30363d)
 */

import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import {
  WarningFilled, Close, Loading, MagicStick, EditPen,
  Stamp, CircleCheckFilled, InfoFilled, Warning,
} from '@element-plus/icons-vue'
import {
  getCompositeAlert, resolveCompositeAlert,
  type CompositeAlertDetail, type AlertResolveRequest,
} from '@/api/growth'

// ── Props & Emits ──────────────────────────

interface Props {
  visible: boolean
  alertId: number | null
  /** SSE推送的原始payload (可选, 用于初始显示) */
  ssePayload?: Record<string, any> | null
}

const props = withDefaults(defineProps<Props>(), {
  alertId: null,
  ssePayload: null,
})

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'resolved', alertId: number): void
}>()

// ── Reactive State ────────────────────────

const alertData = ref<CompositeAlertDetail | null>(null)
const loading = ref({ detail: false, resolve: false })
const errorMsg = ref('')

// Typewriter State
const typewriterHtml = ref('')
const isTyping = ref(false)
const typingProgress = ref(0)
const prescriptionBoxRef = ref<HTMLDivElement | null>(null)
let typewriterTimer: ReturnType<typeof setTimeout> | null = null
let typewriterAbort = false

// Human-in-the-Loop State
const finalPrescription = ref('')
const resolutionNote = ref('')

// ── Watch: dialog visible → fetch detail ──

watch(() => props.visible, (newVal) => {
  if (newVal && props.alertId) {
    fetchAlertDetail()
  }
  if (!newVal) {
    // Cleanup typewriter
    abortTypewriter()
    alertData.value = null
    typewriterHtml.value = ''
    finalPrescription.value = ''
    resolutionNote.value = ''
  }
})

// ── Data Fetching ─────────────────────────

async function fetchAlertDetail() {
  if (!props.alertId) return
  loading.value.detail = true
  errorMsg.value = ''
  try {
    alertData.value = await getCompositeAlert(props.alertId)
    // If has AI prescription → start typewriter
    if (alertData.value?.ai_prescription && !alertData.value.is_resolved) {
      finalPrescription.value = alertData.value.ai_prescription
      startTypewriter(alertData.value.ai_prescription)
    } else if (alertData.value?.final_prescription) {
      // Already resolved → show final directly
      typewriterHtml.value = formatAiPrescription(alertData.value.final_prescription)
    }
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail || '获取预警详情失败'
  } finally {
    loading.value.detail = false
  }
}

// ── Typewriter Engine ─────────────────────

function startTypewriter(rawText: string) {
  abortTypewriter()
  typewriterAbort = false
  isTyping.value = true
  typingProgress.value = 0
  typewriterHtml.value = ''

  const formatted = formatAiPrescription(rawText)
  // Split formatted HTML into character chunks for typewriter effect
  // We'll render the full formatted text progressively
  const totalLen = formatted.length
  let currentIdx = 0

  const TYPE_SPEED = 15  // ms per character chunk
  const CHUNK_SIZE = 3   // characters per tick for smoother feel

  function tick() {
    if (typewriterAbort) {
      isTyping.value = false
      return
    }
    currentIdx = Math.min(currentIdx + CHUNK_SIZE, totalLen)
    typewriterHtml.value = formatted.substring(0, currentIdx)
    typingProgress.value = Math.round((currentIdx / totalLen) * 100)

    if (currentIdx >= totalLen) {
      isTyping.value = false
      typewriterHtml.value = formatted
      return
    }
    typewriterTimer = setTimeout(tick, TYPE_SPEED)
  }
  tick()
}

function abortTypewriter() {
  typewriterAbort = true
  if (typewriterTimer) {
    clearTimeout(typewriterTimer)
    typewriterTimer = null
  }
  isTyping.value = false
}

// ── Resolve (Sign & Archive) ──────────────

async function handleResolve() {
  if (!props.alertId || !alertData.value) return
  if (finalPrescription.value.trim().length < 10) {
    ElMessage.warning('最终处方至少10个字')
    return
  }
  loading.value.resolve = true
  try {
    const body: AlertResolveRequest = {
      final_prescription: finalPrescription.value.trim(),
    }
    if (resolutionNote.value.trim()) {
      body.resolution_note = resolutionNote.value.trim()
    }
    const res = await resolveCompositeAlert(props.alertId, body)
    ElMessage.success('处方已签署归档')
    // Update local state
    alertData.value.is_resolved = res.is_resolved
    alertData.value.resolved_at = res.resolved_at
    alertData.value.resolved_by = res.resolved_by
    alertData.value.final_prescription = res.final_prescription
    alertData.value.resolution_note = res.resolution_note
    emit('resolved', props.alertId)
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    if (err?.response?.status === 409) {
      ElMessage.warning('该预警已被其他人签署归档')
      fetchAlertDetail()  // Refresh to get latest state
    } else {
      ElMessage.error(detail || '签署归档失败')
    }
  } finally {
    loading.value.resolve = false
  }
}

// ── Dismiss ───────────────────────────────

function handleDismiss() {
  abortTypewriter()
  emit('update:visible', false)
}

// ── Helpers ───────────────────────────────

function formatAiPrescription(text: string): string {
  return text.replace(/\n/g, '<br/>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

function formatDateTime(dateStr: string): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatReasonKey(key: string): string {
  const map: Record<string, string> = {
    // ── CRITICAL_COMPOSITE 通用字段 ──
    attendance_absent_count: '缺勤次数',
    behavior_violation_count: '违纪次数',
    score_gap_count: '学业断层',
    psych_risk_score: '心理风险',
    rdi_score: 'RDI综合指数',
    trigger_dimensions: '触发维度',
    // ── 公用元字段 ──
    module: '来源模块',
    alert_source: '告警来源',
    school_id: '学校ID',
    student_id: '学生ID',
    student_name: '学生姓名',
    class_id: '班级ID',
    class_name: '班级',
    triggered_at: '触发时间',
    // ── PSYCH_RISK_ESCALATION ──
    prev_risk: '既往风险等级',
    new_risk: '当前风险等级',
    total_score: '筛查总分',
    survey_id: '问卷ID',
    risk_jump: '风险跃迁',
    // ── HABIT_CARD_SILENCE ──
    teacher_id: '教师ID',
    teacher_name: '教师姓名',
    card_id: '卡牌ID',
    card_name: '卡牌名称',
    silence_days: '沉默天数',
    threshold_days: '沉默阈值(天)',
  }
  return map[key] || key
}

// ── Cleanup ───────────────────────────────

onBeforeUnmount(() => {
  abortTypewriter()
})
</script>

<style scoped>
/* ── Overlay ── */
.sandbox-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 2000;
  animation: fadeInOverlay 0.3s ease;
}
@keyframes fadeInOverlay {
  from { opacity: 0; } to { opacity: 1; }
}

/* ── Panel ── */
.sandbox-panel {
  width: 720px; max-width: 90vw; max-height: 85vh;
  background: #161b22;
  border: 2px solid #f56c6c;
  border-radius: 16px;
  overflow-y: auto;
  box-shadow: 0 8px 40px rgba(245, 108, 108, 0.3);
  animation: slideInPanel 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes slideInPanel {
  from { transform: scale(0.85) translateY(30px); opacity: 0; }
  to { transform: scale(1) translateY(0); opacity: 1; }
}

/* ── Header ── */
.sandbox-header {
  padding: 20px 24px 16px;
  background: linear-gradient(135deg, #f56c6c22 0%, #f56c6c08 100%);
  border-bottom: 1px solid #30363d;
  position: relative;
}
.alert-badge {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px;
}
.pulse-dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: #f56c6c;
  animation: pulseGlow 2s ease-in-out infinite;
  box-shadow: 0 0 8px #f56c6c;
}
@keyframes pulseGlow {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}
.alert-type {
  font-size: 12px; font-weight: 700; color: #f56c6c;
  background: #f56c6c22; padding: 2px 8px; border-radius: 4px;
}
.alert-title {
  font-size: 18px; font-weight: 700; color: #e6edf3;
  margin: 0 0 6px;
}
.alert-meta {
  display: flex; gap: 16px; font-size: 12px; color: #6e7681;
}
.close-btn {
  position: absolute; top: 16px; right: 16px;
  background: transparent !important; border-color: #30363d !important;
  color: #6e7681 !important;
}

/* ── Loading ── */
.sandbox-loading {
  display: flex; flex-direction: column; align-items: center;
  padding: 60px 20px; color: #6e7681; gap: 16px;
}
.sandbox-loading p { margin: 0; }

/* ── Error ── */
.sandbox-error {
  display: flex; flex-direction: column; align-items: center;
  padding: 40px 20px; color: #f56c6c; gap: 12px;
}
.sandbox-error p { margin: 0; font-size: 14px; }

/* ── Body ── */
.sandbox-body {
  padding: 20px 24px;
}

/* ── Section Label ── */
.section-label {
  font-size: 13px; font-weight: 600; color: #8b949e;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 12px;
}

/* ── Reason Cards ── */
.reason-section { margin-bottom: 20px; }
.reason-cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}
.reason-card {
  background: #21262d; border-radius: 8px; padding: 8px 12px;
  border-left: 3px solid #e6a23c;
}
.reason-key { font-size: 12px; color: #6e7681; display: block; margin-bottom: 2px; }
.reason-val { font-size: 13px; color: #e6edf3; font-weight: 600; }

/* ── Prescription Section ── */
.prescription-section { margin-bottom: 20px; }
.prescription-box {
  background: #21262d; border-radius: 10px; padding: 16px 20px;
  min-height: 120px; position: relative;
  border: 1px solid #30363d;
}
.typewriter-content {
  font-size: 14px; line-height: 1.8; color: #8b949e;
}
.typewriter-content :deep(strong) { color: #e6edf3; }
.typewriter-cursor {
  display: inline-block; color: #f56c6c; font-weight: 700;
  animation: cursorBlink 0.8s ease-in-out infinite;
}
@keyframes cursorBlink {
  0%, 100% { opacity: 1; } 50% { opacity: 0; }
}
.typing-progress {
  margin-top: 8px;
}
.no-prescription {
  display: flex; flex-direction: column; align-items: center;
  padding: 24px; color: #6e7681; gap: 8px;
}
.no-prescription p { margin: 0; font-size: 13px; }

/* ── Fine-tuning Section ── */
.fine-tuning-section {
  margin-bottom: 20px;
  background: #0d1117; border-radius: 12px; padding: 16px 20px;
  border: 1px solid #30363d;
}
.tuning-actions {
  display: flex; gap: 8px; margin-top: 12px; align-items: flex-start;
}

/* ── Resolved Badge ── */
.resolved-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; margin-bottom: 16px;
  background: #67c23a22; border-radius: 8px;
  color: #67c23a; font-weight: 600; font-size: 14px;
}
.final-prescription-box {
  background: #21262d; border-radius: 10px; padding: 16px 20px;
  border: 1px solid #67c23a44;
}
.prescription-text {
  font-size: 14px; line-height: 1.8; color: #8b949e;
}
.prescription-text :deep(strong) { color: #e6edf3; }

/* ── Element Plus Dark Overrides ── */
:deep(.el-textarea__inner) {
  background: #161b22 !important; color: #e6edf3 !important;
  box-shadow: 0 0 0 1px #30363d inset !important;
  border-radius: 8px;
}
:deep(.el-textarea__inner::placeholder) { color: #6e7681 !important; }
:deep(.el-input__wrapper) {
  background: #161b22 !important; box-shadow: 0 0 0 1px #30363d inset !important;
}
:deep(.el-input__inner) { color: #e6edf3 !important; }
:deep(.el-input__inner::placeholder) { color: #6e7681 !important; }
:deep(.el-button.is-circle) {
  background: transparent !important; border-color: #30363d !important;
  color: #6e7681 !important;
}
</style>
