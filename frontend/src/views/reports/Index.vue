<template>
  <div class="reports-workbench">
    <!-- ═══════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ═══════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Files /></el-icon>
          报告导出工作台
        </h2>
        <span class="page-subtitle">Celery 异步引擎 · 班级德育报告 / 学生个人报告 · PDF 生成</span>
      </div>
      <div class="header-right">
        <el-tag type="info" effect="plain" size="small">
          学期: {{ semester }} · 活跃任务: {{ activeTaskCount }}
        </el-tag>
      </div>
    </div>

    <!-- ═══════════════════════════════════════ -->
    <!-- Main Content: Export Form + Task List   -->
    <!-- ═══════════════════════════════════════ -->
    <el-row :gutter="16" class="workbench-body">
      <!-- Left: Export Form -->
      <el-col :span="8">
        <div class="export-panel">
          <!-- ── 单班导出 ────────────────── -->
          <el-card shadow="never" class="export-card">
            <template #header>
              <span class="card-title-text">
                <el-icon><Document /></el-icon> 班级德育报告
              </span>
            </template>

            <el-form label-width="80px" size="default">
              <el-form-item label="报告类型">
                <el-radio-group v-model="singleForm.report_type">
                  <el-radio-button
                    v-for="rt in REPORT_TYPES"
                    :key="rt.value"
                    :value="rt.value"
                  >
                    {{ rt.label }}
                  </el-radio-button>
                </el-radio-group>
              </el-form-item>

              <el-form-item label="目标班级">
                <el-select
                  v-model="singleForm.class_id"
                  placeholder="选择班级"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="c in classOptions"
                    :key="c.id"
                    :label="c.name"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>

              <el-form-item
                v-if="singleForm.report_type === 'student_individual'"
                label="目标学生"
              >
                <el-select
                  v-model="singleForm.student_id"
                  placeholder="(可选) 选择学生，留空生成全班"
                  filterable
                  clearable
                  style="width: 100%"
                >
                  <el-option
                    v-for="s in studentOptions"
                    :key="s.id"
                    :label="`${s.name} (${s.student_no})`"
                    :value="s.id"
                  />
                </el-select>
              </el-form-item>

              <el-form-item>
                <el-button
                  type="primary"
                  :icon="VideoPlay"
                  :loading="singleExporting"
                  :disabled="!singleForm.class_id"
                  @click="triggerSingleExport"
                  style="width: 100%"
                >
                  开始生成报告
                </el-button>
              </el-form-item>
            </el-form>

            <el-divider />

            <div class="export-info">
              <el-icon><Clock /></el-icon>
              <span>报告通过 Celery 异步生成，预计耗时 5-15 秒，完成后可下载 PDF</span>
            </div>
          </el-card>

          <!-- ── 年级批量导出 ────────────────── -->
          <el-card shadow="never" class="export-card" v-if="isBatchRole">
            <template #header>
              <span class="card-title-text">
                <el-icon><Collection /></el-icon> 年级批量导出
              </span>
            </template>

            <el-form label-width="80px" size="default">
              <el-form-item label="目标年级">
                <el-select
                  v-model="batchForm.grade_id"
                  placeholder="选择年级"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="g in gradeOptions"
                    :key="g.id"
                    :label="g.name"
                    :value="g.id"
                  />
                </el-select>
              </el-form-item>

              <el-form-item>
                <el-button
                  type="success"
                  :icon="VideoPlay"
                  :loading="batchExporting"
                  :disabled="!batchForm.grade_id"
                  @click="triggerBatchExport"
                  style="width: 100%"
                >
                  批量生成全年级报告
                </el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </div>
      </el-col>

      <!-- Right: Task List -->
      <el-col :span="16">
        <el-card shadow="never" class="task-list-card">
          <template #header>
            <div class="card-header-row">
              <span class="card-title-text">
                <el-icon><List /></el-icon> 导出任务列表
              </span>
              <div class="header-actions">
                <el-button
                  size="small"
                  :icon="Refresh"
                  :loading="pollingActive"
                  @click="refreshAllTasks"
                >
                  刷新状态
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="completedTasks.length === 0"
                  @click="clearCompleted"
                >
                  清除已完成
                </el-button>
              </div>
            </div>
          </template>

          <!-- 活跃任务进度卡片 -->
          <div v-if="activeTasks.length > 0" class="progress-section">
            <div
              v-for="task in activeTasks"
              :key="task.id"
              class="progress-card"
            >
              <div class="progress-header">
                <span class="progress-title">
                  <el-tag
                    :type="taskStateTagType(task.state)"
                    size="small"
                    effect="dark"
                  >
                    {{ taskStateLabel(task.state) }}
                  </el-tag>
                  <span class="progress-class">{{ task.className }}</span>
                  <span class="progress-type">{{ task.reportType === 'class_moral' ? '班级报告' : '学生报告' }}</span>
                </span>
                <span class="progress-pct">{{ task.progress }}%</span>
              </div>
              <el-progress
                :percentage="task.progress"
                :status="task.state === 'SUCCESS' ? 'success' : task.state === 'FAILURE' ? 'exception' : undefined"
                :stroke-width="8"
                :text-inside="false"
              />
              <div class="progress-footer">
                <span class="progress-text">{{ task.statusText }}</span>
                <span class="progress-time">{{ formatElapsed(task.createdAt) }}</span>
              </div>
            </div>
          </div>

          <!-- 已完成任务列表 -->
          <div v-if="completedTasks.length > 0" class="completed-section">
            <div class="section-label">已完成报告</div>
            <el-table
              :data="completedTasks"
              size="small"
              stripe
              class="completed-table"
            >
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag
                    :type="row.state === 'SUCCESS' ? 'success' : 'danger'"
                    size="small"
                    effect="dark"
                  >
                    {{ row.state === 'SUCCESS' ? '完成' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="班级" width="110">
                <template #default="{ row }">{{ row.className }}</template>
              </el-table-column>
              <el-table-column label="类型" width="90">
                <template #default="{ row }">
                  {{ row.reportType === 'class_moral' ? '班级报告' : '学生报告' }}
                </template>
              </el-table-column>
              <el-table-column label="文件名" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.result?.filename" class="filename-text">
                    {{ row.result.filename }}
                  </span>
                  <span v-else class="error-text">{{ row.error || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="大小" width="80" align="center">
                <template #default="{ row }">
                  {{ formatFileSize(row.result?.file_size_kb) }}
                </template>
              </el-table-column>
              <el-table-column label="生成时间" width="110">
                <template #default="{ row }">
                  {{ row.result?.generated_at ? formatTime(row.result.generated_at) : '—' }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" align="center" fixed="right">
                <template #default="{ row }">
                  <el-button
                    v-if="row.state === 'SUCCESS' && row.result?.download_url"
                    type="primary"
                    size="small"
                    link
                    :icon="Download"
                    @click="downloadReport(row as unknown as TaskTracker)"
                  >
                    下载
                  </el-button>
                  <el-button
                    v-else
                    size="small"
                    type="danger"
                    link
                    :icon="Delete"
                    @click="removeTask((row as unknown as TaskTracker).id)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 空状态 -->
          <el-empty
            v-if="allTasks.length === 0"
            description="暂无导出任务，请在左侧选择班级并点击「开始生成报告」"
            :image-size="80"
          >
            <el-button type="primary" @click="demoTask">演示模式 (离线 Demo)</el-button>
          </el-empty>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  VideoPlay,
  Clock,
  Files,
  Collection,
  List,
  Refresh,
  Download,
  Delete,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import {
  exportMoralReport,
  exportGradeReport,
  getTaskStatus,
  taskStateTagType,
  taskStateLabel,
  formatFileSize,
  REPORT_TYPES,
  POLL_INTERVAL,
  MAX_POLL_COUNT,
  getDemoClasses,
  getDemoGrades,
  getDemoTaskTracker,
  getDemoTaskStatus,
  simulateTaskProgress,
  type TaskTracker,
  type ClassOption,
  type GradeOption,
} from '@/api/reports'

// --- Store ---
const userStore = useUserStore()
const isBatchRole = computed(() =>
  ['MS_ADMIN', 'GRADE_LEADER'].includes(userStore.currentRole || ''),
)
const semester = '2025-2026-2'

// --- Export Form State ---
const singleForm = ref({
  report_type: 'class_moral',
  class_id: null as number | null,
  student_id: null as number | null,
})
const singleExporting = ref(false)

const batchForm = ref({
  grade_id: null as number | null,
})
const batchExporting = ref(false)

// --- Options ---
const classOptions = ref<ClassOption[]>([])
const gradeOptions = ref<GradeOption[]>([])
const studentOptions = ref<{ id: number; name: string; student_no: string }[]>([])

// --- Task State ---
const tasks = ref<TaskTracker[]>([])
const pollingActive = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null
const pollCount = ref(0)

// --- Computed ---
const activeTasks = computed(() =>
  tasks.value.filter((t) => t.state === 'PENDING' || t.state === 'PROGRESS'),
)

const completedTasks = computed(() =>
  tasks.value.filter((t) => t.state === 'SUCCESS' || t.state === 'FAILURE'),
)

const allTasks = computed(() => [...activeTasks.value, ...completedTasks.value])

const activeTaskCount = computed(() => activeTasks.value.length)

// ═══════════════════════════════════════════════════
// Export Triggers
// ═══════════════════════════════════════════════════

async function triggerSingleExport() {
  if (!singleForm.value.class_id) {
    ElMessage.warning('请选择目标班级')
    return
  }

  singleExporting.value = true
  try {
    const res = await exportMoralReport({
      class_id: singleForm.value.class_id,
      semester,
      report_type: singleForm.value.report_type,
      student_id: singleForm.value.student_id || undefined,
    })

    const className =
      classOptions.value.find((c) => c.id === singleForm.value.class_id)?.name ||
      `班级#${singleForm.value.class_id}`

    // Add pending task
    tasks.value.unshift({
      id: res.task_id,
      classId: singleForm.value.class_id,
      className,
      reportType: singleForm.value.report_type,
      state: 'PENDING',
      progress: 0,
      statusText: '任务已提交，排队中...',
      createdAt: new Date(),
    })

    ElMessage.success(`任务已提交 (${res.task_id.slice(0, 8)}...)`)

    // Start polling
    startPolling()
  } catch {
    ElMessage.error('提交任务失败，请重试')
  } finally {
    singleExporting.value = false
  }
}

async function triggerBatchExport() {
  if (!batchForm.value.grade_id) {
    ElMessage.warning('请选择目标年级')
    return
  }

  batchExporting.value = true
  try {
    const res = await exportGradeReport({
      grade_id: batchForm.value.grade_id,
      semester,
    })

    // Add pending tasks for each class
    for (let i = 0; i < res.task_ids.length; i++) {
      const cidx = i + 1 // class index
      tasks.value.unshift({
        id: res.task_ids[i],
        classId: cidx,
        className: `七(${cidx})班`,
        reportType: 'class_moral',
        state: 'PENDING',
        progress: 0,
        statusText: `批量任务 ${i + 1}/${res.task_ids.length}，排队中...`,
        createdAt: new Date(),
      })
    }

    ElMessage.success(`全年级 ${res.total_classes} 个班级的报告任务已提交`)
    startPolling()
  } catch {
    ElMessage.error('批量提交失败，请重试')
  } finally {
    batchExporting.value = false
  }
}

// ═══════════════════════════════════════════════════
// Polling Engine
// ═══════════════════════════════════════════════════

function startPolling() {
  if (pollTimer) return // already polling

  pollingActive.value = true
  pollCount.value = 0

  pollTimer = setInterval(async () => {
    pollCount.value++

    const pending = tasks.value.filter(
      (t) => t.state === 'PENDING' || t.state === 'PROGRESS',
    )

    if (pending.length === 0 || pollCount.value >= MAX_POLL_COUNT) {
      stopPolling()
      return
    }

    // Poll each pending task
    const updates = await Promise.allSettled(
      pending.map((t) => getTaskStatus(t.id).catch(() => null)),
    )

    let allDone = true

    updates.forEach((result, idx) => {
      const task = pending[idx]
      const status = result.status === 'fulfilled' ? result.value : null

      if (!status) {
        // Network error — keep polling
        allDone = false
        return
      }

      // Update task in-place
      task.state = status.state
      task.progress = status.progress || 0
      task.statusText = status.status_text || taskStateLabel(status.state)

      if (status.state === 'SUCCESS' && status.result) {
        task.result = status.result
      }
      if (status.state === 'FAILURE') {
        task.error = status.error || '未知错误'
      }

      if (status.state === 'PENDING' || status.state === 'PROGRESS') {
        allDone = false
      }
    })

    if (allDone) {
      stopPolling()
    }
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  pollingActive.value = false
}

async function refreshAllTasks() {
  const pending = tasks.value.filter(
    (t) => t.state === 'PENDING' || t.state === 'PROGRESS',
  )

  if (pending.length === 0) {
    ElMessage.info('没有需要刷新的活跃任务')
    return
  }

  pollingActive.value = true
  const updates = await Promise.allSettled(
    pending.map((t) => getTaskStatus(t.id).catch(() => null)),
  )

  updates.forEach((result, idx) => {
    const task = pending[idx]
    const status = result.status === 'fulfilled' ? result.value : null
    if (!status) return

    task.state = status.state
    task.progress = status.progress || 0
    task.statusText = status.status_text || taskStateLabel(status.state)
    if (status.state === 'SUCCESS' && status.result) {
      task.result = status.result
    }
    if (status.state === 'FAILURE') {
      task.error = status.error || '未知错误'
    }
  })

  pollingActive.value = false
  ElMessage.success(`已刷新 ${pending.length} 个任务状态`)
}

// ═══════════════════════════════════════════════════
// Task Management
// ═══════════════════════════════════════════════════

function downloadReport(task: TaskTracker) {
  if (!task.result?.download_url) {
    ElMessage.warning('下载链接不可用')
    return
  }
  // Open download in new tab
  window.open(task.result.download_url, '_blank')
  ElMessage.success(`开始下载: ${task.result.filename}`)
}

function removeTask(taskId: string) {
  tasks.value = tasks.value.filter((t) => t.id !== taskId)
}

async function clearCompleted() {
  try {
    await ElMessageBox.confirm(
      `确定清除全部 ${completedTasks.value.length} 条已完成任务吗？`,
      '确认清除',
      {
        type: 'warning',
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )
    tasks.value = tasks.value.filter(
      (t) => t.state === 'PENDING' || t.state === 'PROGRESS',
    )
    ElMessage.success('已完成任务已清除')
  } catch {
    // cancelled
  }
}

// ═══════════════════════════════════════════════════
// Demo Mode (离线降级)
// ═══════════════════════════════════════════════════

function demoTask() {
  const classId = singleForm.value.class_id || 1
  const className =
    classOptions.value.find((c) => c.id === classId)?.name || '七(1)班'
  const demoTaskId = `demo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

  // Create initial pending tracker
  const initialTracker: TaskTracker = {
    id: demoTaskId,
    classId,
    className,
    reportType: singleForm.value.report_type,
    state: 'PENDING',
    progress: 0,
    statusText: '任务已提交 (Demo)',
    createdAt: new Date(),
  }
  tasks.value.unshift(initialTracker)

  // Start simulated progress
  simulateTaskProgress(
    demoTaskId,
    classId,
    (tracker) => {
      // Update existing task in-place
      const idx = tasks.value.findIndex((t) => t.id === demoTaskId)
      if (idx >= 0) {
        tasks.value[idx] = { ...tasks.value[idx], ...tracker }
      }
    },
    (tracker) => {
      const idx = tasks.value.findIndex((t) => t.id === demoTaskId)
      if (idx >= 0) {
        tasks.value[idx] = { ...tasks.value[idx], ...tracker }
      }
      ElMessage.success('Demo: 报告已生成，可点击下载')
    },
  )
}

// ═══════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════

function formatElapsed(date: Date): string {
  const elapsed = Math.floor((Date.now() - date.getTime()) / 1000)
  if (elapsed < 60) return `${elapsed}秒前`
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}分钟前`
  return `${Math.floor(elapsed / 3600)}小时前`
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ═══════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════

onMounted(() => {
  // Load class/grade options
  try {
    // Use demo data for now — production would fetch from API
    classOptions.value = getDemoClasses()
    gradeOptions.value = getDemoGrades()
  } catch {
    classOptions.value = getDemoClasses()
    gradeOptions.value = getDemoGrades()
  }

  // Default: select first class
  if (classOptions.value.length > 0) {
    singleForm.value.class_id = classOptions.value[0].id
  }
  if (gradeOptions.value.length > 0) {
    batchForm.value.grade_id = gradeOptions.value[0].id
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.reports-workbench {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
  display: block;
}

.workbench-body {
  flex: 1;
  overflow: hidden;
}

/* ── Export Panel ── */
.export-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.export-card {
  /* no extra styling needed */
}

.card-title-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.export-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}

/* ── Task List ── */
.task-list-card {
  height: calc(100vh - 200px);
  display: flex;
  flex-direction: column;
}

.task-list-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* ── Progress Section ── */
.progress-section {
  margin-bottom: 16px;
}

.progress-card {
  padding: 12px;
  margin-bottom: 10px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #303133;
}

.progress-class {
  font-weight: 600;
}

.progress-type {
  color: #909399;
  font-size: 12px;
}

.progress-pct {
  font-size: 14px;
  font-weight: 700;
  color: #409eff;
}

.progress-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.progress-text {
  font-size: 12px;
  color: #909399;
}

.progress-time {
  font-size: 12px;
  color: #c0c4cc;
}

/* ── Completed Section ── */
.completed-section {
  flex: 1;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7ed;
}

.completed-table {
  margin-bottom: 0;
}

.filename-text {
  font-size: 13px;
  color: #409eff;
  cursor: pointer;
}

.filename-text:hover {
  text-decoration: underline;
}

.error-text {
  font-size: 13px;
  color: #f56c6c;
}

/* ── Misc ── */
:deep(.el-radio-group) {
  width: 100%;
}

:deep(.el-radio-button) {
  flex: 1;
}

:deep(.el-radio-button__inner) {
  width: 100%;
  text-align: center;
}
</style>
