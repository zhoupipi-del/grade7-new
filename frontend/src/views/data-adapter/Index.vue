<template>
  <div class="da-console">
    <!-- Header -->
    <div class="da-header">
      <div>
        <h1 class="da-title">新高考统一数据并网适配层</h1>
        <p class="da-subtitle">支持 3+1+2 走班选科大盘级联清洗、排名归一化与等级赋分自动机</p>
      </div>
      <div class="da-phase-badge">
        <span class="da-phase-dot" :class="phaseClass"></span>
        当前学段: {{ phaseLabel }}
      </div>
    </div>

    <!-- Exam ID Input (senior only) -->
    <div v-if="isSenior" class="da-exam-bar">
      <label class="da-exam-label">关联大考 ID:</label>
      <input
        v-model.number="examId"
        type="number"
        class="da-exam-input"
        placeholder="必填"
      />
      <span class="da-exam-hint">高中学段上传需关联考试ID以触发赋分管道</span>
    </div>

    <!-- Upload Drop Zone -->
    <div
      class="da-dropzone"
      :class="{ 'da-dropzone--active': isDragging, 'da-dropzone--done': resultData }"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="handleFileDrop"
      @click="triggerFileInput"
    >
      <input
        type="file"
        ref="fileInput"
        class="da-file-input"
        accept=".xlsx,.xls,.csv"
        @change="handleFileSelect"
      />

      <!-- Idle state -->
      <div v-if="!uploading && !resultData" class="da-dropzone-idle">
        <div class="da-dropzone-icon">📊</div>
        <p class="da-dropzone-text">点击或将原始成绩 Excel/CSV 拖拽到此处上传</p>
        <p class="da-dropzone-hint">支持原始分、缺考标记，系统自动执行走班选科过滤与线性插值赋分</p>
      </div>

      <!-- Uploading state -->
      <div v-if="uploading" class="da-dropzone-loading">
        <div class="da-spinner"></div>
        <p class="da-dropzone-loading-text">大盘缓冲中 → 正在横向拆表 → 激活赋分自动机引擎...</p>
      </div>

      <!-- Success state -->
      <div v-if="!uploading && resultData" class="da-dropzone-success">
        <div class="da-dropzone-icon da-dropzone-icon--ok">🎉</div>
        <p class="da-dropzone-success-text">并网全链路级联落盘成功！</p>
        <p class="da-dropzone-success-meta">
          学校ID: {{ userStore.schoolId }} | 当前流道: {{ resultData.phase }}
          | 总行: {{ resultData.total_rows }} | 成功: {{ resultData.success_rows }}
          <span v-if="resultData.skipped_rows"> | 跳过: {{ resultData.skipped_rows }}</span>
        </p>
        <button class="da-reset-btn" @click.stop="resetConsole">清除重置并网控制台</button>
      </div>
    </div>

    <!-- Pipeline Summary -->
    <div v-if="resultData && resultData.pipeline_summary" class="da-pipeline">
      <h3 class="da-pipeline-title">📈 9学科并网吞吐流水线实时战报</h3>

      <div class="da-subject-grid">
        <div
          v-for="(metrics, subject) in resultData.pipeline_summary"
          :key="subject"
          class="da-subject-card"
          :class="getSubjectCardClass(subject as string)"
        >
          <div class="da-subject-tag">{{ getSubjectCategory(subject as string) }}</div>
          <div class="da-subject-name">{{ getSubjectChineseName(subject as string) }}</div>
          <div class="da-subject-code">{{ subject }}</div>
          <div class="da-subject-metric">
            <span class="da-subject-num">{{ metrics.active }}</span>
            <span class="da-subject-unit">/ {{ metrics.total }} 人</span>
          </div>
          <div class="da-progress-track">
            <div
              class="da-progress-fill"
              :class="getSubjectCardClass(subject as string)"
              :style="{ width: metrics.total > 0 ? (metrics.active / metrics.total * 100) + '%' : '0%' }"
            ></div>
          </div>
          <div class="da-subject-stats">
            <span v-if="isSubjectScaled(subject as string)" class="da-stat-scaled">已赋分</span>
            <span v-if="!isSubjectScaled(subject as string) && metrics.active" class="da-stat-rank">仅排名</span>
            <span v-if="metrics.active < metrics.total" class="da-stat-skip">缺考 {{ metrics.total - metrics.active }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Clean Stats (no pipeline) -->
    <div v-if="resultData && !resultData.pipeline_summary" class="da-clean-stats">
      <div class="da-stat-row">
        <div class="da-stat-box">
          <div class="da-stat-val">{{ resultData.total_rows }}</div>
          <div class="da-stat-lbl">总行数</div>
        </div>
        <div class="da-stat-box da-stat-box--ok">
          <div class="da-stat-val">{{ resultData.success_rows }}</div>
          <div class="da-stat-lbl">成功</div>
        </div>
        <div v-if="resultData.failed_rows" class="da-stat-box da-stat-box--err">
          <div class="da-stat-val">{{ resultData.failed_rows }}</div>
          <div class="da-stat-lbl">失败</div>
        </div>
        <div v-if="resultData.skipped_rows" class="da-stat-box da-stat-box--skip">
          <div class="da-stat-val">{{ resultData.skipped_rows }}</div>
          <div class="da-stat-lbl">跳过</div>
        </div>
      </div>
    </div>

    <!-- Errors -->
    <div v-if="resultData && resultData.errors && resultData.errors.length" class="da-errors">
      <h4 class="da-errors-title">⚠️ 清洗坏账明细 ({{ resultData.errors.length }}条)</h4>
      <div class="da-errors-list">
        <div v-for="(err, i) in resultData.errors" :key="i" class="da-error-item">
          <span class="da-error-row">行{{ err.row }}</span>
          <span class="da-error-col">{{ err.column }}</span>
          <span class="da-error-type">{{ err.error_type }}</span>
          <span class="da-error-msg">{{ err.message }}</span>
        </div>
      </div>
    </div>

    <!-- Z-Score Heatmap Matrix -->
    <ZScoreHeatmap :exam-id="examId" />

    <!-- RDI 风险预警流水盘 + AI 处方抽屉 -->
    <RiskAlertsPanel :exam-id="examId" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import { uploadScores, type UploadScoresResponse } from '@/api/dataAdapter'
import ZScoreHeatmap from './components/ZScoreHeatmap.vue'
import RiskAlertsPanel from './components/RiskAlertsPanel.vue'

const userStore = useUserStore()

const examId = ref<number>(1)
const isDragging = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const resultData = ref<UploadScoresResponse | null>(null)

const isSenior = computed(() => userStore.currentPhase === 'senior')
const phaseLabel = computed(() => {
  const phase = userStore.currentPhase
  const map: Record<string, string> = {
    senior: '硬核高中 (Senior)',
    junior: '标准初中 (Junior)',
    primary: '小学 (Primary)',
    integrated: '完中 (Integrated)',
  }
  return map[phase] || phase
})
const phaseClass = computed(() => {
  const phase = userStore.currentPhase
  return `da-phase-dot--${phase}`
})

const SUBJECT_NAMES: Record<string, string> = {
  chinese: '核心语文',
  math: '核心数学',
  english: '核心英语',
  physics: '首选物理',
  history: '首选历史',
  chemistry: '再选化学',
  biology: '再选生物',
  politics: '再选政治',
  geography: '再选地理',
}

const SCALED_SUBJECTS = new Set(['chemistry', 'biology', 'politics', 'geography'])
const REQUIRED_SUBJECTS = new Set(['chinese', 'math', 'english'])
const PREFERRED_SUBJECTS = new Set(['physics', 'history'])

function getSubjectChineseName(code: string): string {
  return SUBJECT_NAMES[code] || code
}

function getSubjectCategory(code: string): string {
  if (REQUIRED_SUBJECTS.has(code)) return '必考'
  if (PREFERRED_SUBJECTS.has(code)) return '首选'
  if (SCALED_SUBJECTS.has(code)) return '再选·赋分'
  return '其他'
}

function getSubjectCardClass(code: string): string {
  if (REQUIRED_SUBJECTS.has(code)) return 'da-subject--required'
  if (PREFERRED_SUBJECTS.has(code)) return 'da-subject--preferred'
  if (SCALED_SUBJECTS.has(code)) return 'da-subject--scaled'
  return ''
}

function isSubjectScaled(code: string): boolean {
  return SCALED_SUBJECTS.has(code)
}

function triggerFileInput() {
  if (!uploading.value) fileInput.value?.click()
}

function handleFileSelect(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files && files.length > 0) {
    uploadFilePipeline(files[0])
  }
}

function handleFileDrop(e: DragEvent) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    uploadFilePipeline(files[0])
  }
}

async function uploadFilePipeline(file: File) {
  if (isSenior.value && !examId.value) {
    ElMessage.warning('高中学段上传必须填写关联大考 ID')
    return
  }

  uploading.value = true
  resultData.value = null

  try {
    const data = await uploadScores(file, isSenior.value ? examId.value : undefined)
    resultData.value = data
    ElMessage.success(`并网成功: ${data.success_rows} 行落盘`)
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message || '并网管道发生未知中断'
    ElMessage.error(`适配层拒绝接入: ${detail}`)
  } finally {
    uploading.value = false
  }
}

function resetConsole() {
  resultData.value = null
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<style scoped>
.da-console {
  padding: 24px;
  max-width: 1152px;
  margin: 0 auto;
}

/* Header */
.da-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #30363d;
  padding-bottom: 16px;
  margin-bottom: 24px;
}

.da-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, #58a6ff, #2dd4bf);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.da-subtitle {
  font-size: 13px;
  color: #8b949e;
  margin: 4px 0 0;
}

.da-phase-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  background: #1c2330;
  border: 1px solid #30363d;
  color: #2dd4bf;
  white-space: nowrap;
}

.da-phase-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2dd4bf;
}

.da-phase-dot--senior { background: #f85149; }
.da-phase-dot--junior { background: #d29922; }
.da-phase-dot--primary { background: #3fb950; }
.da-phase-dot--integrated { background: #58a6ff; }

/* Exam ID Bar */
.da-exam-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: #161b22;
  border: 1px solid #30363d;
  margin-bottom: 20px;
}

.da-exam-label {
  font-size: 14px;
  font-weight: 500;
  color: #8b949e;
  white-space: nowrap;
}

.da-exam-input {
  width: 100px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 6px 12px;
  text-align: center;
  color: #58a6ff;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.da-exam-input:focus {
  border-color: #58a6ff;
}

.da-exam-hint {
  font-size: 12px;
  color: #6e7681;
}

/* Drop Zone */
.da-dropzone {
  border: 2px dashed #30363d;
  border-radius: 12px;
  padding: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #161b22;
  min-height: 180px;
}

.da-dropzone:hover {
  border-color: #8b949e;
}

.da-dropzone--active {
  border-color: #58a6ff;
  background: #1c2330;
}

.da-dropzone--done {
  cursor: default;
  border-color: #3fb950;
  background: #0d1f0d;
}

.da-file-input {
  display: none;
}

.da-dropzone-idle,
.da-dropzone-loading,
.da-dropzone-success {
  text-align: center;
}

.da-dropzone-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.da-dropzone-icon--ok {
  filter: hue-rotate(60deg);
}

.da-dropzone-text {
  font-size: 15px;
  font-weight: 500;
  color: #e6edf3;
  margin: 0 0 6px;
}

.da-dropzone-hint {
  font-size: 12px;
  color: #6e7681;
  margin: 0;
}

.da-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #30363d;
  border-bottom-color: #58a6ff;
  border-radius: 50%;
  margin: 0 auto 16px;
  animation: da-spin 0.8s linear infinite;
}

@keyframes da-spin {
  to { transform: rotate(360deg); }
}

.da-dropzone-loading-text {
  font-size: 14px;
  color: #58a6ff;
  animation: da-pulse 1.5s ease-in-out infinite;
}

@keyframes da-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.da-dropzone-success-text {
  font-size: 16px;
  font-weight: 700;
  color: #3fb950;
  margin: 0 0 6px;
}

.da-dropzone-success-meta {
  font-size: 12px;
  color: #8b949e;
  margin: 0;
}

.da-reset-btn {
  margin-top: 10px;
  font-size: 12px;
  color: #58a6ff;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
}

.da-reset-btn:hover {
  color: #79c0ff;
}

/* Pipeline Summary */
.da-pipeline {
  margin-top: 24px;
}

.da-pipeline-title {
  font-size: 17px;
  font-weight: 600;
  color: #e6edf3;
  margin: 0 0 16px;
}

.da-subject-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.da-subject-card {
  position: relative;
  padding: 16px;
  border-radius: 10px;
  background: #161b22;
  border: 1px solid #30363d;
  overflow: hidden;
  transition: border-color 0.2s;
}

.da-subject-card:hover {
  border-color: #8b949e;
}

.da-subject-tag {
  position: absolute;
  top: 10px;
  right: 12px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: 4px;
  background: #21262d;
  color: #6e7681;
}

.da-subject--required .da-subject-tag { background: #0d2818; color: #3fb950; }
.da-subject--preferred .da-subject-tag { background: #0c2233; color: #58a6ff; }
.da-subject--scaled .da-subject-tag { background: #1a1538; color: #a371f7; }

.da-subject-name {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.da-subject-code {
  font-size: 11px;
  font-family: monospace;
  color: #6e7681;
  margin-bottom: 8px;
}

.da-subject-metric {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.da-subject-num {
  font-size: 24px;
  font-weight: 700;
  color: #e6edf3;
}

.da-subject-unit {
  font-size: 12px;
  color: #6e7681;
}

.da-progress-track {
  width: 100%;
  height: 4px;
  background: #0d1117;
  border-radius: 2px;
  margin-top: 12px;
  overflow: hidden;
}

.da-progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
  background: linear-gradient(90deg, #2dd4bf, #58a6ff);
}

.da-subject--required .da-progress-fill { background: linear-gradient(90deg, #3fb950, #2dd4bf); }
.da-subject--preferred .da-progress-fill { background: linear-gradient(90deg, #58a6ff, #79c0ff); }
.da-subject--scaled .da-progress-fill { background: linear-gradient(90deg, #a371f7, #d2a8ff); }

.da-subject-stats {
  display: flex;
  gap: 10px;
  margin-top: 8px;
  font-size: 11px;
}

.da-stat-fail { color: #f85149; }
.da-stat-skip { color: #d29922; }
.da-stat-scaled { color: #a371f7; font-weight: 600; }
.da-stat-rank { color: #8b949e; }

/* Clean Stats (no pipeline) */
.da-clean-stats {
  margin-top: 24px;
}

.da-stat-row {
  display: flex;
  gap: 16px;
}

.da-stat-box {
  flex: 1;
  padding: 20px;
  border-radius: 10px;
  background: #161b22;
  border: 1px solid #30363d;
  text-align: center;
}

.da-stat-box--ok { border-color: #238636; }
.da-stat-box--err { border-color: #da3633; }
.da-stat-box--skip { border-color: #9e6a03; }

.da-stat-val {
  font-size: 28px;
  font-weight: 700;
  color: #e6edf3;
}

.da-stat-box--ok .da-stat-val { color: #3fb950; }
.da-stat-box--err .da-stat-val { color: #f85149; }
.da-stat-box--skip .da-stat-val { color: #d29922; }

.da-stat-lbl {
  font-size: 12px;
  color: #8b949e;
  margin-top: 4px;
}

/* Errors */
.da-errors {
  margin-top: 24px;
  padding: 16px;
  border-radius: 10px;
  background: #161b22;
  border: 1px solid #da3633;
}

.da-errors-title {
  font-size: 14px;
  font-weight: 600;
  color: #f85149;
  margin: 0 0 12px;
}

.da-errors-list {
  max-height: 200px;
  overflow-y: auto;
}

.da-error-item {
  font-size: 12px;
  font-family: monospace;
  color: #f85149;
  padding: 4px 0;
  border-bottom: 1px solid #21262d;
  display: flex;
  gap: 12px;
  align-items: center;
}

.da-error-item:last-child {
  border-bottom: none;
}

.da-error-row {
  color: #d29922;
  font-weight: 600;
  min-width: 40px;
}

.da-error-col {
  color: #58a6ff;
  min-width: 60px;
}

.da-error-type {
  color: #6e7681;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: #21262d;
}

.da-error-msg {
  color: #f85149;
  flex: 1;
}

/* Responsive */
@media (max-width: 768px) {
  .da-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .da-subject-grid {
    grid-template-columns: 1fr;
  }
  .da-stat-row {
    flex-direction: column;
  }
}
</style>
