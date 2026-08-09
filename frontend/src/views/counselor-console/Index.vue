<template>
  <div class="counselor-console">
    <!-- ═══ 顶部英雄栏 ═══ -->
    <div class="page-hero">
      <div class="hero-left">
        <h1 class="hero-title">心理咨询工作台</h1>
        <p class="hero-sub">预约时段管理 · 预约审批 · 加密咨询写实 · 历史档案检索</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" size="large" round @click="loadAll" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- ═══ KPI 统计条 ═══ -->
    <div class="kpi-row" v-loading="statsLoading">
      <div class="kpi-card kpi-sessions">
        <div class="kpi-icon"><el-icon :size="24"><ChatDotRound /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ stats?.total_sessions ?? 0 }}</div>
          <div class="kpi-label">咨询总次数</div>
        </div>
      </div>
      <div class="kpi-card kpi-students">
        <div class="kpi-icon"><el-icon :size="24"><User /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ stats?.total_students ?? 0 }}</div>
          <div class="kpi-label">服务学生数</div>
        </div>
      </div>
      <div class="kpi-card kpi-pending">
        <div class="kpi-icon"><el-icon :size="24"><Clock /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ stats?.pending_appointments ?? 0 }}</div>
          <div class="kpi-label">待审预约</div>
        </div>
      </div>
      <div class="kpi-card kpi-upcoming">
        <div class="kpi-icon"><el-icon :size="24"><Calendar /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ stats?.upcoming_appointments ?? 0 }}</div>
          <div class="kpi-label">即将到来</div>
        </div>
      </div>
      <div class="kpi-card kpi-crisis">
        <div class="kpi-icon"><el-icon :size="24"><WarningFilled /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value" :class="{ 'crisis-pulse': (stats?.crisis_count ?? 0) > 0 }">
            {{ stats?.crisis_count ?? 0 }}
          </div>
          <div class="kpi-label">危机干预</div>
        </div>
      </div>
      <div class="kpi-card kpi-referral">
        <div class="kpi-icon"><el-icon :size="24"><Share /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ stats?.referral_count ?? 0 }}</div>
          <div class="kpi-label">转介转诊</div>
        </div>
      </div>
    </div>

    <!-- ═══ Tab 主区域 ═══ -->
    <el-tabs v-model="activeTab" class="console-tabs" @tab-change="onTabChange">

      <!-- ── Tab 1: 时段管理 ── -->
      <el-tab-pane label="时段管理" name="slots">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-date-picker
              v-model="slotDateFilter"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="default"
              @change="loadSlots"
            />
          </div>
          <div class="toolbar-right">
            <el-button type="primary" :icon="Plus" @click="showSlotDialog = true">
              开放新时段
            </el-button>
          </div>
        </div>

        <el-table
          :data="slots"
          v-loading="slotsLoading"
          stripe
          class="dark-table"
          empty-text="暂无开放时段，点击「开放新时段」创建"
        >
          <el-table-column prop="date" label="日期" width="120" />
          <el-table-column label="时间" width="140">
            <template #default="{ row }">
              <span class="time-range">{{ row.start_time }} ~ {{ row.end_time }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="location" label="地点" width="150" />
          <el-table-column label="容量" width="100">
            <template #default="{ row }">
              <span :class="{ 'capacity-full': row.current_booked >= row.max_capacity }">
                {{ row.current_booked }} / {{ row.max_capacity }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="slotStatusTag(row.status)" size="small" effect="dark">
                {{ slotStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="teacher_name" label="创建人" width="100" />
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'open'"
                size="small"
                :icon="Lock"
                @click="toggleSlotStatus(row.id, 'locked')"
              >锁定</el-button>
              <el-button
                v-if="row.status === 'locked'"
                size="small"
                type="success"
                :icon="Unlock"
                @click="toggleSlotStatus(row.id, 'open')"
              >解锁</el-button>
              <el-button
                v-if="row.status === 'open' || row.status === 'locked'"
                size="small"
                type="danger"
                :icon="Delete"
                @click="handleDeleteSlot(row.id)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── Tab 2: 预约审批 ── -->
      <el-tab-pane label="预约审批" name="appointments">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-select v-model="apptStatusFilter" placeholder="全部状态" clearable @change="loadAppointments" style="width: 140px">
              <el-option label="待确认" value="pending" />
              <el-option label="已确认" value="confirmed" />
              <el-option label="已完成" value="completed" />
              <el-option label="已取消" value="cancelled" />
              <el-option label="缺席" value="no_show" />
            </el-select>
            <el-select v-model="apptRiskFilter" placeholder="全部风险" clearable @change="loadAppointments" style="width: 140px; margin-left: 12px">
              <el-option label="正常" value="green" />
              <el-option label="关注" value="yellow" />
              <el-option label="预警" value="orange" />
              <el-option label="危机" value="red" />
            </el-select>
          </div>
        </div>

        <el-table
          :data="appointments"
          v-loading="apptLoading"
          stripe
          class="dark-table"
          empty-text="暂无预约记录"
        >
          <el-table-column prop="student_name" label="学生" width="100" />
          <el-table-column prop="slot_date" label="日期" width="120" />
          <el-table-column label="时间" width="120">
            <template #default="{ row }">{{ row.slot_time || '-' }}</template>
          </el-table-column>
          <el-table-column label="来源" width="110">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ sourceLabel(row.source) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="风险" width="90">
            <template #default="{ row }">
              <el-tag :type="riskFlagTag(row.risk_flag)" size="small" effect="dark">
                {{ riskFlagLabel(row.risk_flag) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="appointmentStatusTag(row.status)" size="small" effect="dark">
                {{ appointmentStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reason_summary" label="申请理由" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }: { row: any }">
              <el-button
                v-if="row.status === 'pending'"
                size="small"
                type="success"
                :icon="Check"
                @click="handleReviewAppt(row as Appointment, 'confirmed')"
              >确认</el-button>
              <el-button
                v-if="row.status === 'pending'"
                size="small"
                type="danger"
                :icon="Close"
                @click="handleReviewAppt(row as Appointment, 'cancelled')"
              >拒绝</el-button>
              <el-button
                v-if="row.status === 'confirmed'"
                size="small"
                type="primary"
                :icon="Edit"
                @click="handleCompleteAppt(row as Appointment)"
              >完成咨询</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── Tab 3: 加密写实 ── -->
      <el-tab-pane label="加密写实" name="write">
        <div class="write-panel">
          <div class="write-intro">
            <el-icon :size="40" class="lock-icon"><Lock /></el-icon>
            <h2 class="write-title">加密咨询日志</h2>
            <p class="write-desc">
              所有咨询记录使用 Fernet 对称加密落盘，数据库仅存密文。<br/>
              解密读取受角色门禁审计，每次解密自动记录操作日志。
            </p>
          </div>

          <el-form :model="recordForm" label-width="100px" class="write-form" label-position="top">
            <div class="form-row">
              <el-form-item label="关联预约 ID" required>
                <el-input-number v-model="recordForm.appointment_id" :min="1" controls-position="right" style="width: 100%" />
              </el-form-item>
              <el-form-item label="学生 ID" required>
                <el-input-number v-model="recordForm.student_id" :min="1" controls-position="right" style="width: 100%" />
              </el-form-item>
            </div>

            <div class="form-row">
              <el-form-item label="咨询类别">
                <el-select v-model="recordForm.consult_category" placeholder="选择类别" style="width: 100%">
                  <el-option label="情绪困扰" value="emotion" />
                  <el-option label="人际关系" value="interpersonal" />
                  <el-option label="学业压力" value="academic" />
                  <el-option label="家庭问题" value="family" />
                  <el-option label="自伤风险" value="self_harm" />
                  <el-option label="其他" value="other" />
                </el-select>
              </el-form-item>
              <el-form-item label="风险等级">
                <el-select v-model="recordForm.risk_level" style="width: 100%">
                  <el-option label="正常" value="green" />
                  <el-option label="关注" value="yellow" />
                  <el-option label="预警" value="orange" />
                  <el-option label="危机" value="red" />
                </el-select>
              </el-form-item>
            </div>

            <div class="form-row">
              <el-form-item label="咨询时长(分钟)">
                <el-input-number v-model="recordForm.session_duration_min" :min="1" :max="480" controls-position="right" style="width: 100%" />
              </el-form-item>
              <el-form-item label="随访日期">
                <el-date-picker
                  v-model="recordForm.followup_date"
                  type="date"
                  placeholder="选择日期"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  style="width: 100%"
                />
              </el-form-item>
            </div>

            <div class="form-row">
              <el-form-item label="危机标记">
                <el-switch v-model="recordForm.is_crisis" active-text="是" inactive-text="否" />
              </el-form-item>
              <el-form-item label="转介转诊">
                <el-switch v-model="recordForm.is_referred" active-text="是" inactive-text="否" />
              </el-form-item>
            </div>

            <el-form-item v-if="recordForm.is_referred" label="转介目标">
              <el-input v-model="recordForm.referral_target" placeholder="如：精神科门诊 / 校外心理咨询中心" />
            </el-form-item>

            <el-form-item label="咨询日志正文" required>
              <el-input
                v-model="recordForm.clog_plaintext"
                type="textarea"
                :rows="8"
                placeholder="请输入咨询纪要、观察记录、干预策略等。提交后服务层自动 Fernet 加密落盘，数据库不存明文。"
                show-word-limit
                :maxlength="5000"
              />
            </el-form-item>

            <div class="form-actions">
              <el-button
                type="primary"
                size="large"
                :icon="Lock"
                :loading="submitLoading"
                @click="submitRecord"
              >加密提交</el-button>
              <el-button size="large" @click="resetRecordForm">清空</el-button>
            </div>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- ── Tab 4: 咨询历史 ── -->
      <el-tab-pane label="咨询历史" name="history">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-input-number v-model="historyStudentId" :min="1" placeholder="学生 ID" style="width: 140px" />
            <el-button :icon="Search" @click="loadStudentHistory" style="margin-left: 12px">查询学生档案</el-button>
          </div>
          <div class="toolbar-right">
            <el-select v-model="historyRiskFilter" placeholder="全部风险" clearable @change="loadHistory" style="width: 140px">
              <el-option label="正常" value="green" />
              <el-option label="关注" value="yellow" />
              <el-option label="预警" value="orange" />
              <el-option label="危机" value="red" />
            </el-select>
          </div>
        </div>

        <el-table
          :data="historyRecords"
          v-loading="historyLoading"
          stripe
          class="dark-table"
          empty-text="暂无咨询记录"
          @row-click="showRecordDetail"
        >
          <el-table-column prop="id" label="#" width="60" />
          <el-table-column prop="student_name" label="学生" width="100" />
          <el-table-column prop="counselor_name" label="咨询师" width="100" />
          <el-table-column label="类别" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.consult_category" :type="consultCategoryTag(row.consult_category)" size="small" effect="plain">
                {{ consultCategoryLabel(row.consult_category) }}
              </el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="风险" width="90">
            <template #default="{ row }">
              <el-tag :type="riskFlagTag(row.risk_level)" size="small" effect="dark">
                {{ riskFlagLabel(row.risk_level) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="危机" width="70">
            <template #default="{ row }">
              <el-icon v-if="row.is_crisis" color="#f85149" :size="18"><WarningFilled /></el-icon>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="时长" width="80">
            <template #default="{ row }">{{ row.session_duration_min ? row.session_duration_min + 'min' : '-' }}</template>
          </el-table-column>
          <el-table-column prop="clog_display" label="日志摘要" min-width="250" show-overflow-tooltip />
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }: { row: any }">
              <el-button size="small" :icon="View" @click.stop="showRecordDetail(row as ConsultRecord)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══ 时段创建对话框 ═══ -->
    <el-dialog v-model="showSlotDialog" title="开放可预约时段" width="500px" class="dark-dialog">
      <el-form :model="slotForm" label-width="100px">
        <el-form-item label="日期" required>
          <el-date-picker
            v-model="slotForm.date"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="开始时间" required>
          <el-time-picker v-model="slotForm.start_time" format="HH:mm" value-format="HH:mm" placeholder="如 14:00" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间" required>
          <el-time-picker v-model="slotForm.end_time" format="HH:mm" value-format="HH:mm" placeholder="如 15:00" style="width: 100%" />
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="slotForm.location" placeholder="心理咨询室" />
        </el-form-item>
        <el-form-item label="最大容量">
          <el-input-number v-model="slotForm.max_capacity" :min="1" :max="5" />
        </el-form-item>
        <el-form-item label="周期模式">
          <el-select v-model="slotForm.week_pattern" style="width: 100%">
            <el-option label="每周" value="every" />
            <el-option label="单周" value="odd" />
            <el-option label="双周" value="even" />
          </el-select>
        </el-form-item>
        <el-form-item label="循环创建">
          <el-switch v-model="slotForm.is_recurring" active-text="是" inactive-text="否" />
          <span class="form-hint">开启后按周期模式自动生成后续时段</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSlotDialog = false">取消</el-button>
        <el-button type="primary" :loading="slotSubmitLoading" @click="submitSlot">创建时段</el-button>
      </template>
    </el-dialog>

    <!-- ═══ 咨询记录详情抽屉 ═══ -->
    <el-drawer
      v-model="showRecordDrawer"
      title="咨询记录详情"
      direction="rtl"
      size="50%"
      class="dark-drawer"
    >
      <template v-if="detailRecord">
        <div class="detail-header">
          <div class="detail-student">
            <el-icon :size="32"><User /></el-icon>
            <div>
              <div class="detail-name">{{ detailRecord.student_name || '学生#' + detailRecord.student_id }}</div>
              <div class="detail-meta">咨询师: {{ detailRecord.counselor_name || '-' }}</div>
            </div>
          </div>
          <div class="detail-tags">
            <el-tag :type="riskFlagTag(detailRecord.risk_level)" effect="dark" size="large">
              {{ riskFlagLabel(detailRecord.risk_level) }}
            </el-tag>
            <el-tag v-if="detailRecord.consult_category" :type="consultCategoryTag(detailRecord.consult_category)" effect="plain" size="large">
              {{ consultCategoryLabel(detailRecord.consult_category) }}
            </el-tag>
            <el-tag v-if="detailRecord.is_crisis" type="danger" effect="dark" size="large">危机</el-tag>
            <el-tag v-if="detailRecord.is_referred" type="warning" effect="dark" size="large">转介</el-tag>
          </div>
        </div>

        <div class="detail-info-grid">
          <div class="info-cell">
            <span class="info-label">咨询时长</span>
            <span class="info-value">{{ detailRecord.session_duration_min ? detailRecord.session_duration_min + ' 分钟' : '未记录' }}</span>
          </div>
          <div class="info-cell">
            <span class="info-label">随访日期</span>
            <span class="info-value">{{ detailRecord.followup_date || '无' }}</span>
          </div>
          <div class="info-cell">
            <span class="info-label">转介目标</span>
            <span class="info-value">{{ detailRecord.referral_target || '无' }}</span>
          </div>
          <div class="info-cell">
            <span class="info-label">创建时间</span>
            <span class="info-value">{{ detailRecord.created_at || '-' }}</span>
          </div>
        </div>

        <el-divider />

        <div class="detail-clog">
          <div class="clog-header">
            <el-icon :size="16"><Lock /></el-icon>
            <span>咨询日志（已解密）</span>
          </div>
          <div class="clog-body">{{ detailRecord.clog_display }}</div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh, Plus, Delete, Lock, Unlock, Check, Close, Edit,
  View, Search, Clock, Calendar, Share, ChatDotRound, User, WarningFilled,
} from '@element-plus/icons-vue'
import {
  getCounselorStats,
  getSlots, createSlot, updateSlotStatus, deleteSlot,
  getAppointments, updateAppointment,
  getConsultRecords, createConsultRecord, getConsultRecordDetail, getStudentConsultHistory,
  riskFlagLabel, riskFlagTag, riskFlagColor,
  appointmentStatusLabel, appointmentStatusTag,
  consultCategoryLabel, consultCategoryTag,
  slotStatusLabel, slotStatusTag,
  sourceLabel,
  type CounselorStats, type ConsultSlot, type Appointment, type ConsultRecord,
  type RiskFlag, type ConsultCategory, type AppointmentStatus, type SlotStatus,
  type SlotCreatePayload, type ConsultRecordCreatePayload,
} from '@/api/psychCounseling'

// ═══════════════════════════════════════════════════
// 全局状态
// ═══════════════════════════════════════════════════

const activeTab = ref('slots')
const loading = ref(false)
const statsLoading = ref(false)
const stats = ref<CounselorStats | null>(null)

// ── Tab 1: 时段管理 ──
const slots = ref<ConsultSlot[]>([])
const slotsLoading = ref(false)
const slotDateFilter = ref<[string, string] | null>(null)
const showSlotDialog = ref(false)
const slotSubmitLoading = ref(false)
const slotForm = reactive<SlotCreatePayload>({
  date: '',
  start_time: '',
  end_time: '',
  location: '心理咨询室',
  max_capacity: 1,
  week_pattern: 'every',
  is_recurring: false,
})

// ── Tab 2: 预约审批 ──
const appointments = ref<Appointment[]>([])
const apptLoading = ref(false)
const apptStatusFilter = ref<AppointmentStatus | ''>('')
const apptRiskFilter = ref<RiskFlag | ''>('')

// ── Tab 3: 加密写实 ──
const submitLoading = ref(false)
const recordForm = reactive<ConsultRecordCreatePayload>({
  appointment_id: 0,
  student_id: 0,
  clog_plaintext: '',
  risk_level: 'green',
  consult_category: undefined,
  is_crisis: false,
  is_referred: false,
  referral_target: '',
  followup_date: '',
  session_duration_min: 30,
})

// ── Tab 4: 咨询历史 ──
const historyRecords = ref<ConsultRecord[]>([])
const historyLoading = ref(false)
const historyStudentId = ref<number | undefined>(undefined)
const historyRiskFilter = ref<RiskFlag | ''>('')

// ── 详情抽屉 ──
const showRecordDrawer = ref(false)
const detailRecord = ref<ConsultRecord | null>(null)

// ═══════════════════════════════════════════════════
// 数据加载
// ═══════════════════════════════════════════════════

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getCounselorStats()
  } catch {
    // 静默降级 — 统计非关键
  } finally {
    statsLoading.value = false
  }
}

async function loadSlots() {
  slotsLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (slotDateFilter.value) {
      params.date_from = slotDateFilter.value[0]
      params.date_to = slotDateFilter.value[1]
    }
    const res = await getSlots(params as any)
    slots.value = res?.slots ?? []
  } catch {
    slots.value = []
  } finally {
    slotsLoading.value = false
  }
}

async function loadAppointments() {
  apptLoading.value = true
  try {
    const params: Record<string, any> = {}
    if (apptStatusFilter.value) params.status = apptStatusFilter.value
    if (apptRiskFilter.value) params.risk_flag = apptRiskFilter.value
    const res = await getAppointments(params)
    appointments.value = res?.appointments ?? []
  } catch {
    appointments.value = []
  } finally {
    apptLoading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const params: Record<string, any> = {}
    if (historyStudentId.value) params.student_id = historyStudentId.value
    if (historyRiskFilter.value) params.risk_level = historyRiskFilter.value
    const res = await getConsultRecords(params)
    historyRecords.value = res?.records ?? []
  } catch {
    historyRecords.value = []
  } finally {
    historyLoading.value = false
  }
}

async function loadStudentHistory() {
  if (!historyStudentId.value) {
    ElMessage.warning('请输入学生 ID')
    return
  }
  historyLoading.value = true
  try {
    const res = await getStudentConsultHistory(historyStudentId.value)
    historyRecords.value = res?.records ?? []
    if (historyRecords.value.length === 0) {
      ElMessage.info('该学生暂无咨询记录')
    }
  } catch {
    historyRecords.value = []
  } finally {
    historyLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  await Promise.allSettled([loadStats(), loadSlots(), loadAppointments(), loadHistory()])
  loading.value = false
}

function onTabChange(tab: string | number) {
  const name = String(tab)
  switch (name) {
    case 'slots': loadSlots(); break
    case 'appointments': loadAppointments(); break
    case 'write': break // 表单不需要加载数据
    case 'history': loadHistory(); break
  }
}

// ═══════════════════════════════════════════════════
// Tab 1: 时段操作
// ═══════════════════════════════════════════════════

async function submitSlot() {
  if (!slotForm.date || !slotForm.start_time || !slotForm.end_time) {
    ElMessage.warning('请填写日期和起止时间')
    return
  }
  slotSubmitLoading.value = true
  try {
    await createSlot({ ...slotForm })
    ElMessage.success('时段创建成功')
    showSlotDialog.value = false
    // 重置表单
    slotForm.date = ''
    slotForm.start_time = ''
    slotForm.end_time = ''
    slotForm.is_recurring = false
    await loadSlots()
    await loadStats()
  } catch {
    // 拦截器已提示
  } finally {
    slotSubmitLoading.value = false
  }
}

async function toggleSlotStatus(slotId: number, newStatus: SlotStatus) {
  try {
    await updateSlotStatus(slotId, { status: newStatus })
    ElMessage.success(`时段已${newStatus === 'locked' ? '锁定' : '解锁'}`)
    await loadSlots()
  } catch {
    // 拦截器已提示
  }
}

async function handleDeleteSlot(slotId: number) {
  try {
    await ElMessageBox.confirm('确定要删除此时段吗？已预约的时段无法删除。', '确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteSlot(slotId)
    ElMessage.success('时段已删除')
    await loadSlots()
  } catch {
    // 用户取消或删除失败
  }
}

// ═══════════════════════════════════════════════════
// Tab 2: 预约审批
// ═══════════════════════════════════════════════════

async function handleReviewAppt(row: Appointment, newStatus: AppointmentStatus) {
  const action = newStatus === 'confirmed' ? '确认' : '拒绝'
  try {
    let note = ''
    if (newStatus === 'cancelled') {
      const res = await ElMessageBox.prompt('请输入拒绝原因（可选）', '拒绝预约', {
        confirmButtonText: '确认拒绝',
        cancelButtonText: '取消',
      })
      note = res.value || ''
    }
    await updateAppointment(row.id, {
      status: newStatus,
      counselor_note: note || undefined,
    })
    ElMessage.success(`预约已${action}`)
    await loadAppointments()
    await loadStats()
  } catch {
    // 用户取消或操作失败
  }
}

async function handleCompleteAppt(row: Appointment) {
  try {
    await ElMessageBox.confirm(
      `确认学生「${row.student_name || row.student_id}」的咨询已完成？`,
      '完成咨询',
      { confirmButtonText: '确认完成', cancelButtonText: '取消', type: 'success' },
    )
    await updateAppointment(row.id, { status: 'completed' })
    ElMessage.success('咨询已完成，可前往「加密写实」提交记录')
    await loadAppointments()
    await loadStats()
  } catch {
    // 用户取消
  }
}

// ═══════════════════════════════════════════════════
// Tab 3: 加密写实
// ═══════════════════════════════════════════════════

async function submitRecord() {
  if (!recordForm.appointment_id || !recordForm.student_id) {
    ElMessage.warning('请填写关联预约 ID 和学生 ID')
    return
  }
  if (!recordForm.clog_plaintext.trim()) {
    ElMessage.warning('请输入咨询日志正文')
    return
  }
  submitLoading.value = true
  try {
    const payload: ConsultRecordCreatePayload = {
      appointment_id: recordForm.appointment_id,
      student_id: recordForm.student_id,
      clog_plaintext: recordForm.clog_plaintext,
      risk_level: recordForm.risk_level,
      consult_category: recordForm.consult_category,
      is_crisis: recordForm.is_crisis,
      is_referred: recordForm.is_referred,
      referral_target: recordForm.is_referred ? recordForm.referral_target : undefined,
      followup_date: recordForm.followup_date || undefined,
      session_duration_min: recordForm.session_duration_min,
    }
    await createConsultRecord(payload)
    ElMessage.success('加密咨询记录已提交，Fernet 密文已落盘')
    resetRecordForm()
    await loadStats()
  } catch {
    // 拦截器已提示
  } finally {
    submitLoading.value = false
  }
}

function resetRecordForm() {
  recordForm.appointment_id = 0
  recordForm.student_id = 0
  recordForm.clog_plaintext = ''
  recordForm.risk_level = 'green'
  recordForm.consult_category = undefined
  recordForm.is_crisis = false
  recordForm.is_referred = false
  recordForm.referral_target = ''
  recordForm.followup_date = ''
  recordForm.session_duration_min = 30
}

// ═══════════════════════════════════════════════════
// Tab 4: 咨询历史
// ═══════════════════════════════════════════════════

async function showRecordDetail(row: ConsultRecord) {
  showRecordDrawer.value = true
  detailRecord.value = row
  // 如果 clog_display 是脱敏摘要，尝试拉取完整解密
  try {
    const full = await getConsultRecordDetail(row.id)
    if (full?.clog_display && full.clog_display.length > row.clog_display.length) {
      detailRecord.value = full
    }
  } catch {
    // 已有摘要足够展示
  }
}

// ═══════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
/* ═══ GitHub Dark Theme ═══ */
.counselor-console {
  min-height: 100vh;
  background: #0d1117;
  color: #c9d1d9;
  padding: 24px;
}

/* ── 顶部英雄栏 ── */
.page-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.hero-title {
  font-size: 24px;
  font-weight: 700;
  color: #f0f6fc;
  margin: 0 0 6px 0;
}

.hero-sub {
  font-size: 13px;
  color: #8b949e;
  margin: 0;
}

/* ── KPI 统计条 ── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.kpi-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: border-color 0.2s;
}

.kpi-card:hover {
  border-color: #58a6ff;
}

.kpi-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #21262d;
}

.kpi-sessions .kpi-icon { color: #58a6ff; }
.kpi-students .kpi-icon { color: #3fb950; }
.kpi-pending .kpi-icon { color: #d29922; }
.kpi-upcoming .kpi-icon { color: #bc8cff; }
.kpi-crisis .kpi-icon { color: #f85149; }
.kpi-referral .kpi-icon { color: #db6d28; }

.kpi-body {
  flex: 1;
}

.kpi-value {
  font-size: 22px;
  font-weight: 700;
  color: #f0f6fc;
  line-height: 1.2;
}

.crisis-pulse {
  color: #f85149 !important;
  animation: crisis-pulse 2s ease-in-out infinite;
}

@keyframes crisis-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.kpi-label {
  font-size: 12px;
  color: #8b949e;
  margin-top: 2px;
}

/* ── Tabs ── */
.console-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.console-tabs :deep(.el-tabs__item) {
  color: #8b949e;
  font-size: 15px;
}

.console-tabs :deep(.el-tabs__item.is-active) {
  color: #58a6ff;
}

.console-tabs :deep(.el-tabs__active-bar) {
  background-color: #58a6ff;
}

.console-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: #30363d;
}

/* ── 工具栏 ── */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 暗色表格 ── */
.dark-table {
  background: #161b22 !important;
  color: #c9d1d9;
}

.dark-table :deep(.el-table__header-wrapper th) {
  background: #21262d !important;
  color: #8b949e;
  border-bottom: 1px solid #30363d;
}

.dark-table :deep(.el-table__body-wrapper) {
  background: #161b22;
}

.dark-table :deep(.el-table__body tr:hover > td) {
  background: #21262d !important;
}

.dark-table :deep(.el-table__body tr.el-table__row--striped td) {
  background: #1c2128;
}

.dark-table :deep(.el-table__empty-text) {
  color: #8b949e;
}

.dark-table :deep(.el-table border) {
  border-color: #30363d;
}

.dark-table :deep(td),
.dark-table :deep(th) {
  border-color: #30363d;
}

.time-range {
  font-family: 'SF Mono', 'Consolas', monospace;
  color: #58a6ff;
}

.capacity-full {
  color: #f85149;
  font-weight: 600;
}

/* ── 加密写实质感 ── */
.write-panel {
  max-width: 800px;
  margin: 0 auto;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 32px;
}

.write-intro {
  text-align: center;
  margin-bottom: 32px;
}

.lock-icon {
  color: #58a6ff;
  margin-bottom: 12px;
}

.write-title {
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
  margin: 0 0 8px 0;
}

.write-desc {
  font-size: 13px;
  color: #8b949e;
  line-height: 1.8;
  margin: 0;
}

.write-form {
  margin-top: 24px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #8b949e;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 24px;
}

/* ── 暗色对话框 ── */
.dark-dialog :deep(.el-dialog) {
  background: #161b22;
  border: 1px solid #30363d;
}

.dark-dialog :deep(.el-dialog__title) {
  color: #f0f6fc;
}

.dark-dialog :deep(.el-dialog__body) {
  color: #c9d1d9;
}

/* ── 暗色抽屉 ── */
.dark-drawer :deep(.el-drawer) {
  background: #0d1117;
  border-left: 1px solid #30363d;
}

.dark-drawer :deep(.el-drawer__header) {
  color: #f0f6fc;
}

.dark-drawer :deep(.el-drawer__body) {
  padding: 24px;
}

/* ── 记录详情 ── */
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.detail-student {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #58a6ff;
}

.detail-name {
  font-size: 18px;
  font-weight: 700;
  color: #f0f6fc;
}

.detail-meta {
  font-size: 13px;
  color: #8b949e;
  margin-top: 4px;
}

.detail-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.info-cell {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 12px 16px;
}

.info-label {
  display: block;
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 4px;
}

.info-value {
  font-size: 14px;
  color: #c9d1d9;
  font-weight: 500;
}

.detail-clog {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  overflow: hidden;
}

.clog-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #21262d;
  color: #58a6ff;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid #30363d;
}

.clog-body {
  padding: 20px;
  font-size: 14px;
  line-height: 1.8;
  color: #c9d1d9;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── 响应式 ── */
@media (max-width: 1200px) {
  .kpi-row {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
