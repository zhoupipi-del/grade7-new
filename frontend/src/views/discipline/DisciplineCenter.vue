<template>
  <div class="discipline-center">
    <!-- Page Header -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">惩戒流转中心</h2>
        <span class="page-subtitle">处分下达 · 观察期追踪 · 溯源回溯 · 申诉答辩</span>
      </div>
      <div class="header-right">
        <el-tag type="info" effect="plain" size="small">
          <el-icon><DataAnalysis /></el-icon>
          {{ records.length }} 条处分记录
        </el-tag>
      </div>
    </div>

    <el-row :gutter="16" class="main-content">
      <!-- ═══════════════════════════════════════ -->
      <!-- Left: Punishment Roster (处分下达与观察名册) -->
      <!-- ═══════════════════════════════════════ -->
      <el-col :span="9">
        <el-card class="roster-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><Stamp /></el-icon>
                处分下达与观察名册
              </span>
            </div>
          </template>

          <!-- Filter Radio Buttons -->
          <el-radio-group v-model="statusFilter" size="small" class="filter-group">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="观察中">观察中</el-radio-button>
            <el-radio-button value="申诉中">申诉中</el-radio-button>
            <el-radio-button value="已撤销">已撤销</el-radio-button>
          </el-radio-group>

          <!-- Roster Table -->
          <el-table
            :data="filteredRecords"
            highlight-current-row
            @current-change="handleSelectRecord"
            size="small"
            class="roster-table"
            v-loading="loading"
            element-loading-text="加载处分记录..."
          >
            <el-table-column prop="student_name" label="学生" width="80" />
            <el-table-column prop="class_name" label="班级" width="85" />
            <el-table-column label="处分" width="90">
              <template #default="{ row }">
                <el-tag :type="getPunishTagType(row.level)" size="small">
                  {{ row.level }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="观察状态" width="90">
              <template #default="{ row }">
                <el-tag
                  :type="getStatusTagType(row.probation_status)"
                  size="small"
                  effect="plain"
                >
                  {{ row.probation_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="剩余" width="60" align="center">
              <template #default="{ row }">
                <span
                  v-if="row.days_remaining > 0"
                  :class="{ 'days-warning': row.days_remaining <= 30 }"
                >
                  {{ row.days_remaining }}天
                </span>
                <span v-else class="days-expired">—</span>
              </template>
            </el-table-column>
            <el-table-column label="源头" width="70" align="center">
              <template #default="{ row }">
                <el-icon v-if="row.source_type === 'RDI_Radar'" class="source-rdi">
                  <Aim />
                </el-icon>
                <el-icon v-else class="source-approval">
                  <Document />
                </el-icon>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- ═══════════════════════════════════════ -->
      <!-- Right: Traceability + Timeline           -->
      <!-- ═══════════════════════════════════════ -->
      <el-col :span="15">
        <!-- Detail Card (when a record is selected) -->
        <el-card
          v-if="selectedRecord"
          class="detail-card"
          shadow="never"
          :key="selectedRecord.punishment_id"
        >
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><View /></el-icon>
                溯源追踪 · {{ selectedRecord.punishment_id }}
              </span>
              <el-button
                type="warning"
                size="small"
                plain
                @click="openAppealDialog"
                :disabled="selectedRecord.probation_status === '已撤销'"
              >
                <el-icon><EditPen /></el-icon>
                提交撤销申诉
              </el-button>
            </div>
          </template>

          <!-- Source Traceability Descriptions -->
          <el-descriptions
            :column="3"
            border
            size="small"
            class="trace-descriptions"
          >
            <el-descriptions-item label="学生姓名">
              {{ selectedRecord.student_name }}
            </el-descriptions-item>
            <el-descriptions-item label="所在班级">
              {{ selectedRecord.class_name }}
            </el-descriptions-item>
            <el-descriptions-item label="处分等级">
              <el-tag :type="getPunishTagType(selectedRecord.level)" size="small">
                {{ selectedRecord.level }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="惩戒源头">
              <el-tag
                :type="sourceTypeTag(selectedRecord.source_type)"
                size="small"
                effect="plain"
              >
                {{ sourceTypeLabel(selectedRecord.source_type) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="源头编号">
              <span class="source-ref">{{ selectedRecord.source_ref_id }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="下达日期">
              {{ selectedRecord.execution_date }}
            </el-descriptions-item>
            <el-descriptions-item label="处分事由" :span="3">
              <div class="reason-text">{{ selectedRecord.reason }}</div>
            </el-descriptions-item>
            <el-descriptions-item label="观察期">
              {{ selectedRecord.probation_days }} 天
              <span v-if="selectedRecord.days_remaining > 0" class="days-remaining">
                （剩余 {{ selectedRecord.days_remaining }} 天）
              </span>
              <span v-else class="days-expired-text">（已期满）</span>
            </el-descriptions-item>
            <el-descriptions-item label="当前状态">
              <el-tag
                :type="getStatusTagType(selectedRecord.probation_status)"
                size="small"
              >
                {{ selectedRecord.probation_status }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <!-- Probation Timeline Chain -->
          <div class="timeline-section">
            <h4 class="section-title">
              <el-icon><Clock /></el-icon>
              撤销处分申诉观察期时序链
            </h4>
            <Timeline>
              <TimelineEvent
                v-for="(milestone, index) in selectedRecord.timeline_chain"
                :key="index"
                :title="milestone.title"
                :time="milestone.time"
                :status="milestone.status"
              >
                {{ milestone.description }}
              </TimelineEvent>
            </Timeline>
          </div>
        </el-card>

        <!-- Empty State (no record selected) -->
        <el-card v-else class="detail-card empty-state" shadow="never">
          <el-empty description="请从左侧名册选择一条处分记录，查看溯源追踪与时序链">
            <template #image>
              <el-icon class="empty-icon"><DocumentRemove /></el-icon>
            </template>
          </el-empty>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════════════════════════════════ -->
    <!-- Appeal Dialog                             -->
    <!-- ═══════════════════════════════════════ -->
    <el-dialog
      v-model="appealDialogVisible"
      title="提交撤销处分申诉"
      width="540px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-alert
        title="申诉须知"
        type="info"
        :closable="false"
        show-icon
        class="appeal-notice"
      >
        撤销处分申诉需在观察期内提交，德育处将在 5 个工作日内组织答辩委员会进行审核。
      </el-alert>

      <el-form :model="appealForm" label-width="90px" class="appeal-form">
        <el-form-item label="处分编号">
          <span class="form-static">{{ selectedRecord?.punishment_id }}</span>
        </el-form-item>
        <el-form-item label="学生姓名">
          <span class="form-static">{{ selectedRecord?.student_name }}</span>
        </el-form-item>
        <el-form-item label="处分等级">
          <span class="form-static">{{ selectedRecord?.level }}</span>
        </el-form-item>
        <el-form-item label="申诉理由" required>
          <el-input
            v-model="appealForm.reason"
            type="textarea"
            :rows="5"
            placeholder="请详细陈述撤销处分的理由，包括行为改善情况、家庭配合教育情况、心理评估结果等..."
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="appealDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="submitAppealHandler"
          :loading="appealSubmitting"
          :disabled="!appealForm.reason.trim()"
        >
          提交申诉
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import Timeline from '@/components/Timeline.vue'
import TimelineEvent from '@/components/TimelineEvent.vue'
import {
  fetchDisciplineWithFallback,
  submitAppealWithFallback,
  getPunishTagType,
  getStatusTagType,
  sourceTypeLabel,
  sourceTypeTag,
  type DisciplineRecord,
} from '@/api/discipline'

// ── State ──
const loading = ref(false)
const records = ref<DisciplineRecord[]>([])
const selectedRecord = ref<DisciplineRecord | null>(null)
const statusFilter = ref('')

// Appeal dialog state
const appealDialogVisible = ref(false)
const appealSubmitting = ref(false)
const appealForm = ref({
  reason: '',
})

// ── Computed ──
const filteredRecords = computed(() => {
  if (!statusFilter.value) return records.value
  return records.value.filter(r => r.probation_status === statusFilter.value)
})

// ── Methods ──
async function loadRecords() {
  loading.value = true
  try {
    records.value = await fetchDisciplineWithFallback()
    // Auto-select first record for immediate context
    if (records.value.length > 0 && !selectedRecord.value) {
      selectedRecord.value = records.value[0]
    }
  } catch {
    ElMessage.error('加载处分记录失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function handleSelectRecord(row: DisciplineRecord | null) {
  if (row) {
    selectedRecord.value = row
  }
}

function openAppealDialog() {
  appealForm.value.reason = ''
  appealDialogVisible.value = true
}

async function submitAppealHandler() {
  if (!selectedRecord.value) return
  if (!appealForm.value.reason.trim()) {
    ElMessage.warning('请填写申诉理由')
    return
  }

  appealSubmitting.value = true
  try {
    const result = await submitAppealWithFallback(
      selectedRecord.value.punishment_id,
      appealForm.value.reason.trim()
    )
    ElMessage.success(result.message)
    appealDialogVisible.value = false
  } catch {
    ElMessage.error('申诉提交失败，请稍后重试')
  } finally {
    appealSubmitting.value = false
  }
}

// ── Lifecycle ──
onMounted(() => {
  loadRecords()
})
</script>

<style scoped>
.discipline-center {
  padding: 0;
}

/* ── Page Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1f2c3f;
  margin: 0;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
}

/* ── Card ── */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.roster-card,
.detail-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.roster-card {
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
}

:deep(.roster-card .el-card__body) {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.detail-card {
  height: calc(100vh - 140px);
  overflow-y: auto;
}

/* ── Filter ── */
.filter-group {
  margin-bottom: 12px;
  width: 100%;
}

.filter-group :deep(.el-radio-button) {
  flex: 1;
}

.filter-group :deep(.el-radio-button__inner) {
  width: 100%;
}

/* ── Roster Table ── */
.roster-table {
  width: 100%;
}

.roster-table :deep(.el-table__body tr.current-row > td) {
  background-color: #ecf5ff !important;
}

.days-warning {
  color: #e6a23c;
  font-weight: 600;
}

.days-expired {
  color: #c0c4cc;
}

.source-rdi {
  color: #f56c6c;
  font-size: 16px;
}

.source-approval {
  color: #409eff;
  font-size: 16px;
}

/* ── Trace Descriptions ── */
.trace-descriptions {
  margin-bottom: 20px;
}

.trace-descriptions :deep(.el-descriptions__label) {
  width: 90px;
  font-weight: 600;
  background-color: #fafafa;
}

.reason-text {
  line-height: 1.6;
  color: #606266;
}

.source-ref {
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  color: #409eff;
  font-weight: 600;
}

.days-remaining {
  color: #e6a23c;
  font-weight: 500;
}

.days-expired-text {
  color: #909399;
}

/* ── Timeline Section ── */
.timeline-section {
  margin-top: 8px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

/* ── Empty State ── */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon {
  font-size: 64px;
  color: #dcdfe6;
}

/* ── Appeal Dialog ── */
.appeal-notice {
  margin-bottom: 16px;
}

.appeal-form {
  margin-top: 8px;
}

.form-static {
  font-weight: 600;
  color: #303133;
}

/* ── Responsive ── */
@media (max-width: 1200px) {
  .main-content :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }

  .roster-card {
    height: auto;
    max-height: 400px;
  }

  .detail-card {
    height: auto;
    margin-top: 16px;
  }
}
</style>
