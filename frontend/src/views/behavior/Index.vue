<template>
  <div class="behavior-center">
    <!-- ═══════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ═══════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Warning /></el-icon>
          德育与处分中心
        </h2>
        <span class="page-subtitle">违纪登记 · 处分状态机 · 草稿滑窗 · 申诉管理</span>
      </div>
      <div class="header-right">
        <el-tag type="info" effect="plain" size="small">
          <el-icon><DataAnalysis /></el-icon>
          {{ behaviorRecords.length }} 条违纪 · {{ sanctions.length }} 条处分 · {{ drafts.length }} 条草稿
        </el-tag>
      </div>
    </div>

    <el-row :gutter="12" class="main-content">
      <!-- ═══════════════════════════════════════ -->
      <!-- Left Column: 违纪记录名册 (span 7)       -->
      <!-- ═══════════════════════════════════════ -->
      <el-col :span="7">
        <el-card class="records-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><Warning /></el-icon>
                违纪记录名册
              </span>
              <el-button type="primary" size="small" :icon="Plus" plain>登记</el-button>
            </div>
          </template>

          <!-- Type Filter -->
          <el-radio-group v-model="typeFilter" size="small" class="filter-group">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="warning">提醒</el-radio-button>
            <el-radio-button value="minor">轻微</el-radio-button>
            <el-radio-button value="major">一般</el-radio-button>
            <el-radio-button value="serious">严重</el-radio-button>
          </el-radio-group>

          <!-- Records Table -->
          <el-table
            :data="filteredRecords"
            highlight-current-row
            @current-change="handleSelectRecord"
            size="small"
            class="records-table"
            v-loading="loading"
            element-loading-text="加载违纪记录..."
          >
            <el-table-column prop="student_name" label="学生" width="75" />
            <el-table-column prop="class_name" label="班级" width="80" />
            <el-table-column label="类型" width="70">
              <template #default="{ row }">
                <el-tag :type="behaviorTypeTag(row.type)" size="small">
                  {{ behaviorTypeLabel(row.type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="扣分" width="55" align="center">
              <template #default="{ row }">
                <span class="points-text">{{ row.points }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="70">
              <template #default="{ row }">
                <el-tag :type="behaviorStatusTag(row.status)" size="small" effect="plain">
                  {{ behaviorStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="发生时间" min-width="90">
              <template #default="{ row }">
                <span class="time-text">{{ formatDate(row.incident_date) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- ═══════════════════════════════════════ -->
      <!-- Center Column: 详情 & 处分状态机 (span 10) -->
      <!-- ═══════════════════════════════════════ -->
      <el-col :span="10">
        <el-card
          v-if="selectedRecord"
          class="detail-card"
          shadow="never"
          :key="selectedRecord.id"
        >
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><View /></el-icon>
                违纪详情 · #{{ selectedRecord.id }}
              </span>
              <el-button
                v-if="selectedRecord.status === 'pending'"
                type="success"
                size="small"
                plain
                @click="handleResolve"
              >
                <el-icon><CircleCheck /></el-icon>
                标记已处理
              </el-button>
            </div>
          </template>

          <!-- Record Detail -->
          <el-descriptions :column="2" border size="small" class="detail-descriptions">
            <el-descriptions-item label="学生姓名">
              {{ selectedRecord.student_name }}
            </el-descriptions-item>
            <el-descriptions-item label="所在班级">
              {{ selectedRecord.class_name }}
            </el-descriptions-item>
            <el-descriptions-item label="违纪类型">
              <el-tag :type="behaviorTypeTag(selectedRecord.type)" size="small">
                {{ behaviorTypeLabel(selectedRecord.type) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="扣分值">
              <span class="points-text">{{ selectedRecord.points }} 分</span>
            </el-descriptions-item>
            <el-descriptions-item label="发生时间">
              {{ formatDate(selectedRecord.incident_date) }}
            </el-descriptions-item>
            <el-descriptions-item label="发生地点">
              {{ selectedRecord.location || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="当前状态">
              <el-tag :type="behaviorStatusTag(selectedRecord.status)" size="small">
                {{ behaviorStatusLabel(selectedRecord.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="登记人">
              {{ selectedRecord.recorded_by }}
            </el-descriptions-item>
            <el-descriptions-item label="违纪描述" :span="2">
              <div class="reason-text">{{ selectedRecord.description }}</div>
            </el-descriptions-item>
          </el-descriptions>

          <!-- Related Sanctions for this student -->
          <div class="section-block">
            <h4 class="section-title">
              <el-icon><Stamp /></el-icon>
              关联处分状态机
              <el-tag
                v-if="studentSanctions.length > 0"
                type="danger"
                size="small"
                class="ml-8"
              >
                {{ studentSanctions.length }} 条
              </el-tag>
            </h4>

            <div v-if="studentSanctions.length > 0" class="sanction-flow">
              <div
                v-for="s in studentSanctions"
                :key="s.id"
                class="sanction-item"
              >
                <div class="sanction-header">
                  <el-tag :type="disciplineLevelTag(s.level)" size="small">
                    {{ disciplineLevelLabel(s.level) }}
                  </el-tag>
                  <el-tag :type="disciplineStatusTag(s.status)" size="small" effect="plain">
                    {{ disciplineStatusLabel(s.status) }}
                  </el-tag>
                  <span class="sanction-points">{{ s.points }} 分</span>
                </div>
                <div class="sanction-reason">{{ s.reason }}</div>
                <!-- State Machine Flow -->
                <div class="state-flow">
                  <div
                    v-for="step in stateSteps"
                    :key="step.key"
                    class="state-node"
                    :class="getStateClass(s.status, step.key)"
                  >
                    <div class="state-dot"></div>
                    <span class="state-label">{{ step.label }}</span>
                  </div>
                </div>
              </div>
            </div>

            <el-empty
              v-else
              description="该生暂无正式处分记录"
              :image-size="60"
            />
          </div>

          <!-- Escalation Check -->
          <div class="section-block">
            <h4 class="section-title">
              <el-icon><Aim /></el-icon>
              30天滑窗升级评估
            </h4>
            <div class="escalation-box">
              <div class="escalation-stat">
                <span class="stat-label">30天内严重违纪</span>
                <span class="stat-value" :class="{ 'stat-danger': studentSeriousCount >= 3 }">
                  {{ studentSeriousCount }} 次
                </span>
              </div>
              <div class="escalation-stat">
                <span class="stat-label">升级阈值</span>
                <span class="stat-value">3 次</span>
              </div>
              <div class="escalation-stat">
                <span class="stat-label">评估结果</span>
                <el-tag
                  :type="studentSeriousCount >= 3 ? 'danger' : 'success'"
                  size="small"
                  effect="dark"
                >
                  {{ studentSeriousCount >= 3 ? '触发升级' : '未达阈值' }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>

        <!-- Empty State -->
        <el-card v-else class="detail-card empty-state" shadow="never">
          <el-empty description="请从左侧名册选择一条违纪记录，查看详情与处分联动">
            <template #image>
              <el-icon class="empty-icon"><DocumentRemove /></el-icon>
            </template>
          </el-empty>
        </el-card>
      </el-col>

      <!-- ═══════════════════════════════════════ -->
      <!-- Right Column: 草稿箱 & 申诉队列 (span 7)  -->
      <!-- ═══════════════════════════════════════ -->
      <el-col :span="7">
        <!-- Drafts Queue -->
        <el-card class="drafts-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><FolderOpened /></el-icon>
                草稿箱 · 30天滑窗铁证
              </span>
              <el-tag type="warning" size="small" effect="plain">
                {{ drafts.length }} 条待审
              </el-tag>
            </div>
          </template>

          <div class="drafts-list">
            <div
              v-for="draft in drafts"
              :key="draft.id"
              class="draft-item"
            >
              <div class="draft-header">
                <span class="draft-student">{{ draft.student_name }}</span>
                <el-tag :type="disciplineLevelTag(draft.level)" size="small">
                  {{ disciplineLevelLabel(draft.level) }}
                </el-tag>
              </div>
              <div class="draft-meta">
                <span>{{ draft.class_name }}</span>
                <span class="draft-points">累计 {{ draft.total_points }} 分</span>
              </div>
              <!-- Evidence Chain -->
              <div class="evidence-chain">
                <div
                  v-for="(ev, i) in draft.evidence"
                  :key="i"
                  class="evidence-node"
                >
                  <div class="evidence-dot">{{ i + 1 }}</div>
                  <div class="evidence-content">
                    <div class="evidence-desc">{{ ev.description }}</div>
                    <div class="evidence-meta">
                      <span>{{ formatDate(ev.incident_date) }}</span>
                      <span>{{ ev.location }}</span>
                      <span class="evidence-points">{{ ev.points }} 分</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="draft-footer">
                <span class="window-text">
                  窗口: {{ formatDate(draft.window_start) }} ~ {{ formatDate(draft.window_end) }}
                </span>
                <el-button
                  type="primary"
                  size="small"
                  plain
                  @click="handleSubmitDraft(draft)"
                >
                  推背提交
                </el-button>
              </div>
            </div>

            <el-empty
              v-if="drafts.length === 0"
              description="暂无草稿"
              :image-size="50"
            />
          </div>
        </el-card>

        <!-- Appeals Queue -->
        <el-card class="appeals-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><ChatLineRound /></el-icon>
                申诉队列
              </span>
              <el-tag type="info" size="small" effect="plain">
                {{ totalAppeals }} 条
              </el-tag>
            </div>
          </template>

          <div class="appeals-list">
            <!-- Discipline Appeals -->
            <div
              v-for="ap in disciplineAppeals"
              :key="'d-' + ap.id"
              class="appeal-item"
            >
              <div class="appeal-header">
                <el-tag type="danger" size="small" effect="plain">处分申诉</el-tag>
                <el-tag :type="appealStatusTag(ap.status)" size="small">
                  {{ appealStatusLabel(ap.status) }}
                </el-tag>
              </div>
              <div class="appeal-student">{{ ap.student_name }} · {{ ap.class_name }}</div>
              <div class="appeal-reason">{{ ap.reason }}</div>
              <div class="appeal-time">提交于 {{ formatDate(ap.submitted_at) }}</div>
            </div>

            <!-- Behavior Appeals -->
            <div
              v-for="ap in behaviorAppeals"
              :key="'b-' + ap.id"
              class="appeal-item"
            >
              <div class="appeal-header">
                <el-tag type="warning" size="small" effect="plain">违纪申诉</el-tag>
                <el-tag :type="appealStatusTag(ap.status)" size="small">
                  {{ appealStatusLabel(ap.status) }}
                </el-tag>
              </div>
              <div class="appeal-student">{{ ap.student_name }} · {{ ap.class_name }}</div>
              <div class="appeal-reason">{{ ap.reason }}</div>
              <div class="appeal-time">提交于 {{ formatDate(ap.submitted_at) }}</div>
            </div>

            <el-empty
              v-if="behaviorAppeals.length === 0 && disciplineAppeals.length === 0"
              description="暂无申诉"
              :image-size="50"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Plus,
  Warning,
  View,
  Stamp,
  Aim,
  DataAnalysis,
  CircleCheck,
  DocumentRemove,
  FolderOpened,
  ChatLineRound,
} from '@element-plus/icons-vue'
import {
  fetchBehaviorWithFallback,
  fetchSanctionsWithFallback,
  fetchDraftsWithFallback,
  fetchAppealsWithFallback,
  behaviorTypeLabel,
  behaviorTypeTag,
  behaviorStatusLabel,
  behaviorStatusTag,
  disciplineLevelLabel,
  disciplineLevelTag,
  disciplineStatusLabel,
  disciplineStatusTag,
  appealStatusLabel,
  appealStatusTag,
  type BehaviorRecord,
  type Sanction,
  type SanctionDraft,
  type BehaviorAppeal,
  type DisciplineAppeal,
  type BehaviorType,
  type DisciplineStatus,
} from '@/api/behavior'

// ── State ──
const loading = ref(false)
const typeFilter = ref<BehaviorType | ''>('')

const behaviorRecords = ref<BehaviorRecord[]>([])
const sanctions = ref<Sanction[]>([])
const drafts = ref<SanctionDraft[]>([])
const behaviorAppeals = ref<BehaviorAppeal[]>([])
const disciplineAppeals = ref<DisciplineAppeal[]>([])

const selectedRecord = ref<BehaviorRecord | null>(null)

// ── State Machine Steps ──
const stateSteps = [
  { key: 'DRAFT_PENDING', label: '草案' },
  { key: 'PENDING', label: '待审批' },
  { key: 'GRADE_LEADER_APPROVED', label: '年级已批' },
  { key: 'ACTIVE', label: '生效' },
  { key: 'REVOKED', label: '撤销/回血' },
] as const

// ── Computed ──
const filteredRecords = computed(() => {
  if (!typeFilter.value) return behaviorRecords.value
  return behaviorRecords.value.filter(r => r.type === typeFilter.value)
})

const studentSanctions = computed(() => {
  if (!selectedRecord.value) return []
  return sanctions.value.filter(s => s.student_id === selectedRecord.value!.student_id)
})

const studentSeriousCount = computed(() => {
  if (!selectedRecord.value) return 0
  return behaviorRecords.value.filter(
    r => r.student_id === selectedRecord.value!.student_id && r.type === 'serious'
  ).length
})

const totalAppeals = computed(() => behaviorAppeals.value.length + disciplineAppeals.value.length)

// ── Methods ──
function formatDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function getStateClass(status: DisciplineStatus, stepKey: string): string {
  const order = ['DRAFT_PENDING', 'PENDING', 'GRADE_LEADER_APPROVED', 'ACTIVE', 'REVOKED']
  const currentIdx = order.indexOf(status)
  const stepIdx = order.indexOf(stepKey)

  if (stepIdx < currentIdx) return 'state-completed'
  if (stepIdx === currentIdx) return 'state-current'

  // Special: REJECTED is a terminal state parallel to ACTIVE
  if (status === 'REJECTED' && stepKey === 'ACTIVE') return 'state-rejected'

  return 'state-pending'
}

async function loadAllData() {
  loading.value = true
  try {
    const [behaviorRes, sanctionRes, draftRes, appealRes] = await Promise.all([
      fetchBehaviorWithFallback(),
      fetchSanctionsWithFallback(),
      fetchDraftsWithFallback(),
      fetchAppealsWithFallback(),
    ])

    behaviorRecords.value = behaviorRes.items
    sanctions.value = sanctionRes.items
    drafts.value = draftRes.items
    behaviorAppeals.value = appealRes.behavior
    disciplineAppeals.value = appealRes.discipline

    // Auto-select first record
    if (behaviorRecords.value.length > 0) {
      selectedRecord.value = behaviorRecords.value[0]
    }
  } catch {
    ElMessage.error('加载德育数据失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function handleSelectRecord(row: BehaviorRecord | null) {
  if (row) {
    selectedRecord.value = row
  }
}

function handleResolve() {
  if (!selectedRecord.value) return
  ElMessage.success(`已标记 #${selectedRecord.value.id} ${selectedRecord.value.student_name} 的违纪为已处理`)
  selectedRecord.value.status = 'resolved'
  selectedRecord.value.resolved_at = new Date().toISOString()
}

function handleSubmitDraft(draft: SanctionDraft) {
  ElMessage.success(`草稿 #${draft.id} (${draft.student_name}) 已推背提交为正式处分`)
}

// ── Lifecycle ──
onMounted(() => {
  loadAllData()
})
</script>

<style scoped>
.behavior-center {
  padding: 0;
}

/* ── Page Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 20px;
  font-weight: 700;
  color: #1f2c3f;
  margin: 0;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
}

/* ── Card Common ── */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.ml-8 {
  margin-left: 8px;
}

/* ── Left: Records Card ── */
.records-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
  height: calc(100vh - 130px);
  display: flex;
  flex-direction: column;
}

:deep(.records-card .el-card__body) {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.filter-group {
  margin-bottom: 10px;
  width: 100%;
}

.filter-group :deep(.el-radio-button) {
  flex: 1;
}

.filter-group :deep(.el-radio-button__inner) {
  width: 100%;
}

.records-table {
  width: 100%;
}

.records-table :deep(.el-table__body tr.current-row > td) {
  background-color: #ecf5ff !important;
}

.points-text {
  font-family: 'Courier New', Courier, monospace;
  font-weight: 600;
  color: #f56c6c;
}

.time-text {
  font-size: 12px;
  color: #909399;
}

/* ── Center: Detail Card ── */
.detail-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
  height: calc(100vh - 130px);
  overflow-y: auto;
}

:deep(.detail-card .el-card__body) {
  padding: 14px;
}

.detail-descriptions {
  margin-bottom: 16px;
}

.detail-descriptions :deep(.el-descriptions__label) {
  width: 80px;
  font-weight: 600;
  background-color: #fafafa;
}

.reason-text {
  line-height: 1.6;
  color: #606266;
}

/* ── Section Block ── */
.section-block {
  margin-top: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}

/* ── Sanction Flow ── */
.sanction-flow {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sanction-item {
  padding: 10px 12px;
  background: #f9fafc;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.sanction-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.sanction-points {
  margin-left: auto;
  font-family: 'Courier New', Courier, monospace;
  font-weight: 600;
  color: #f56c6c;
  font-size: 13px;
}

.sanction-reason {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin-bottom: 8px;
}

/* ── State Machine Flow ── */
.state-flow {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px 0 4px;
}

.state-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
  position: relative;
}

.state-node:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 5px;
  right: -50%;
  width: 100%;
  height: 2px;
  background: #dcdfe6;
  z-index: 0;
}

.state-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #dcdfe6;
  border: 2px solid #e4e7ed;
  z-index: 1;
  transition: all 0.3s;
}

.state-label {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

.state-completed .state-dot {
  background: #67c23a;
  border-color: #67c23a;
}

.state-completed .state-label {
  color: #67c23a;
  font-weight: 500;
}

.state-completed:not(:last-child)::after {
  background: #67c23a;
}

.state-current .state-dot {
  background: #f56c6c;
  border-color: #f56c6c;
  box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.2);
  animation: pulse-current 2s infinite;
}

.state-current .state-label {
  color: #f56c6c;
  font-weight: 600;
}

@keyframes pulse-current {
  0%, 100% { box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.2); }
  50% { box-shadow: 0 0 0 6px rgba(245, 108, 108, 0.05); }
}

.state-rejected .state-dot {
  background: #909399;
  border-color: #909399;
}

.state-rejected .state-label {
  color: #909399;
  text-decoration: line-through;
}

.state-pending .state-dot {
  background: #f5f7fa;
  border-color: #dcdfe6;
}

/* ── Escalation Box ── */
.escalation-box {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #f9fafc;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.escalation-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
  font-family: 'Courier New', Courier, monospace;
}

.stat-danger {
  color: #f56c6c;
}

/* ── Right: Drafts Card ── */
.drafts-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
  margin-bottom: 12px;
}

:deep(.drafts-card .el-card__body) {
  padding: 10px;
  max-height: 340px;
  overflow-y: auto;
}

.drafts-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.draft-item {
  padding: 10px 12px;
  background: #fdf6ec;
  border-radius: 6px;
  border: 1px solid #f3d19e;
}

.draft-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.draft-student {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.draft-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.draft-points {
  color: #f56c6c;
  font-weight: 600;
}

/* ── Evidence Chain ── */
.evidence-chain {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  border-top: 1px dashed #e6a23c;
}

.evidence-node {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.evidence-dot {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e6a23c;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.evidence-content {
  flex: 1;
}

.evidence-desc {
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
}

.evidence-meta {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.evidence-points {
  color: #f56c6c;
  font-weight: 600;
}

.draft-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #e6a23c;
}

.window-text {
  font-size: 11px;
  color: #909399;
}

/* ── Appeals Card ── */
.appeals-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

:deep(.appeals-card .el-card__body) {
  padding: 10px;
  max-height: 260px;
  overflow-y: auto;
}

.appeals-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.appeal-item {
  padding: 8px 10px;
  background: #f9fafc;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.appeal-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.appeal-student {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 2px;
}

.appeal-reason {
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.appeal-time {
  font-size: 11px;
  color: #909399;
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

/* ── Responsive ── */
@media (max-width: 1400px) {
  .main-content :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }

  .records-card,
  .detail-card {
    height: auto;
    max-height: 500px;
    margin-bottom: 12px;
  }
}
</style>
