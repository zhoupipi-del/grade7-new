<template>
  <div class="appointment-picker">
    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 顶格: 页面标题 + 孩子信息条                                    -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon><Clock /></el-icon>
          心理咨询预约中心
        </h2>
        <p class="page-subtitle">家校协同 · 关注孩子心理健康</p>
      </div>
      <div v-if="childInfo" class="header-right">
        <el-tag type="info" effect="dark" size="large">
          {{ childInfo.student_name }} · {{ childInfo.class_name }}
        </el-tag>
      </div>
    </div>

    <!-- 加载骨架 -->
    <div v-if="pageLoading" class="loading-container">
      <el-skeleton :rows="6" animated />
    </div>

    <!-- 主错误 -->
    <div v-else-if="initError" class="error-container">
      <el-empty :description="initError">
        <el-button type="primary" @click="initPage">重新加载</el-button>
      </el-empty>
    </div>

    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 双Tab主体                                                      -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <div v-else class="tab-container">
      <el-tabs v-model="activeTab" class="dark-tabs" @tab-change="handleTabChange">

        <!-- ── Tab 1: 可预约时段 ── -->
        <el-tab-pane label="可预约时段" name="slots">
          <template #label>
            <div class="tab-label">
              <el-icon><Calendar /></el-icon>
              <span>可预约时段</span>
              <el-badge v-if="openSlots.length > 0" :value="openSlots.length" class="tab-badge" />
            </div>
          </template>

          <!-- 时段卡片网格 -->
          <div v-if="slotsLoading" class="loading-container">
            <el-skeleton :rows="4" animated />
          </div>
          <div v-else-if="openSlots.length === 0" class="empty-state">
            <el-empty description="暂无可预约时段，请稍后再来查看" :image-size="80" />
            <el-button @click="fetchSlots">刷新时段</el-button>
          </div>
          <div v-else class="slots-grid">
            <div
              v-for="slot in openSlots"
              :key="slot.id"
              class="slot-card"
              :class="{ 'slot-full': slot.current_booked >= slot.max_capacity }"
              @click="openAppointmentDialog(slot)"
            >
              <div class="slot-card-header">
                <div class="slot-date">
                  <el-icon><Calendar /></el-icon>
                  <span>{{ slot.date }}</span>
                </div>
                <el-tag
                  :type="slot.current_booked >= slot.max_capacity ? 'danger' : 'success'"
                  effect="dark"
                  size="small"
                >
                  {{ slot.current_booked >= slot.max_capacity ? '已满' : '可预约' }}
                </el-tag>
              </div>
              <div class="slot-time">
                <el-icon><Clock /></el-icon>
                <span>{{ slot.start_time }} — {{ slot.end_time }}</span>
              </div>
              <div class="slot-meta">
                <div v-if="slot.teacher_name" class="slot-teacher">
                  <el-icon><User /></el-icon>
                  <span>{{ slot.teacher_name }}</span>
                </div>
                <div v-if="slot.location" class="slot-location">
                  <el-icon><LocationInformation /></el-icon>
                  <span>{{ slot.location }}</span>
                </div>
              </div>
              <div class="slot-capacity">
                <el-progress
                  :percentage="Math.round((slot.current_booked / slot.max_capacity) * 100)"
                  :color="slot.current_booked >= slot.max_capacity ? '#f85149' : '#3fb950'"
                  :show-text="false"
                  :stroke-width="6"
                />
                <span class="capacity-text">
                  {{ slot.current_booked }} / {{ slot.max_capacity }} 人
                </span>
              </div>
              <div class="slot-action">
                <el-button
                  type="primary"
                  size="small"
                  :disabled="slot.current_booked >= slot.max_capacity"
                  @click.stop="openAppointmentDialog(slot)"
                >
                  {{ slot.current_booked >= slot.max_capacity ? '名额已满' : '立即预约' }}
                </el-button>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- ── Tab 2: 我的预约 ── -->
        <el-tab-pane label="我的预约" name="appointments">
          <template #label>
            <div class="tab-label">
              <el-icon><Tickets /></el-icon>
              <span>我的预约</span>
              <el-badge v-if="pendingCount > 0" :value="pendingCount" class="tab-badge" type="warning" />
            </div>
          </template>

          <div v-if="apptsLoading" class="loading-container">
            <el-skeleton :rows="4" animated />
          </div>
          <div v-else-if="myAppointments.length === 0" class="empty-state">
            <el-empty description="您还没有预约记录" :image-size="80" />
            <el-button type="primary" @click="activeTab = 'slots'">去预约</el-button>
          </div>
          <div v-else class="appt-list">
            <div
              v-for="appt in myAppointments"
              :key="appt.id"
              class="appt-item"
              @click="openDetailDrawer(appt)"
            >
              <div class="appt-item-left">
                <div class="appt-date-block">
                  <div class="appt-date-day">{{ appt.slot_date || '待定' }}</div>
                  <div class="appt-date-time">{{ appt.slot_time || '--' }}</div>
                </div>
                <div class="appt-info">
                  <div class="appt-top-row">
                    <el-tag
                      :type="appointmentStatusTag(appt.status)"
                      effect="dark"
                      size="small"
                    >
                      {{ appointmentStatusLabel(appt.status) }}
                    </el-tag>
                    <el-tag
                      :type="riskFlagTag(appt.risk_flag)"
                      effect="plain"
                      size="small"
                    >
                      {{ riskFlagLabel(appt.risk_flag) }}
                    </el-tag>
                    <span class="appt-source">{{ sourceLabel(appt.source) }}</span>
                  </div>
                  <div v-if="appt.reason_summary" class="appt-reason">
                    {{ appt.reason_summary }}
                  </div>
                  <div class="appt-meta">
                    <span v-if="appt.slot_location">
                      <el-icon><LocationInformation /></el-icon>
                      {{ appt.slot_location }}
                    </span>
                    <span v-if="appt.created_at">
                      <el-icon><Clock /></el-icon>
                      {{ formatDateTime(appt.created_at) }}
                    </span>
                  </div>
                </div>
              </div>
              <el-icon class="appt-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-tab-pane>

      </el-tabs>
    </div>

    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 预约弹窗 Dialog                                                 -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <el-dialog
      v-model="dialogVisible"
      title="发起心理咨询预约"
      width="560px"
      class="dark-dialog"
      :close-on-click-modal="false"
    >
      <div v-if="selectedSlot" class="dialog-slot-info">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="日期">{{ selectedSlot.date }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ selectedSlot.start_time }} — {{ selectedSlot.end_time }}</el-descriptions-item>
          <el-descriptions-item label="心理老师">{{ selectedSlot.teacher_name || '待分配' }}</el-descriptions-item>
          <el-descriptions-item label="地点">{{ selectedSlot.location || '待通知' }}</el-descriptions-item>
          <el-descriptions-item label="剩余名额">
            <span :style="{ color: selectedSlot.max_capacity - selectedSlot.current_booked <= 1 ? '#f85149' : '#3fb950' }">
              {{ selectedSlot.max_capacity - selectedSlot.current_booked }} / {{ selectedSlot.max_capacity }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="预约学生">
            {{ childInfo?.student_name || '--' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <el-form ref="apptFormRef" :model="apptForm" :rules="apptRules" label-position="top" class="appt-form">
        <el-form-item label="预约原因简述" prop="reason_summary">
          <el-input
            v-model="apptForm.reason_summary"
            type="textarea"
            :rows="4"
            placeholder="请简要描述您希望咨询的问题（如情绪波动、人际交往困难、学业焦虑等），便于心理老师提前了解情况。"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="当前关注程度" prop="risk_flag">
          <el-radio-group v-model="apptForm.risk_flag">
            <el-radio-button value="green">正常 · 预防性咨询</el-radio-button>
            <el-radio-button value="yellow">关注 · 有些担忧</el-radio-button>
            <el-radio-button value="orange">预警 · 比较着急</el-radio-button>
            <el-radio-button value="red">危机 · 紧急求助</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAppointment">
          确认预约
        </el-button>
      </template>
    </el-dialog>

    <!-- ═══════════════════════════════════════════════════════ -->
    <!-- 预约详情抽屉 Drawer                                             -->
    <!-- ═══════════════════════════════════════════════════════ -->
    <el-drawer
      v-model="drawerVisible"
      title="预约详情"
      direction="rtl"
      size="480px"
      class="dark-drawer"
    >
      <template v-if="selectedAppt">
        <div class="drawer-content">
          <!-- 预约信息卡 -->
          <div class="drawer-section">
            <div class="drawer-section-title">
              <el-icon><Tickets /></el-icon>
              预约信息
            </div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="状态">
                <el-tag :type="appointmentStatusTag(selectedAppt.status)" effect="dark" size="small">
                  {{ appointmentStatusLabel(selectedAppt.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="风险标记">
                <el-tag :type="riskFlagTag(selectedAppt.risk_flag)" effect="plain" size="small">
                  {{ riskFlagLabel(selectedAppt.risk_flag) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="日期">{{ selectedAppt.slot_date || '待定' }}</el-descriptions-item>
              <el-descriptions-item label="时间">{{ selectedAppt.slot_time || '--' }}</el-descriptions-item>
              <el-descriptions-item label="地点">{{ selectedAppt.slot_location || '待通知' }}</el-descriptions-item>
              <el-descriptions-item label="来源">{{ sourceLabel(selectedAppt.source) }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDateTime(selectedAppt.created_at) }}</el-descriptions-item>
              <el-descriptions-item v-if="selectedAppt.confirmed_at" label="确认时间">
                {{ formatDateTime(selectedAppt.confirmed_at) }}
              </el-descriptions-item>
              <el-descriptions-item v-if="selectedAppt.completed_at" label="完成时间">
                {{ formatDateTime(selectedAppt.completed_at) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- 预约原因 -->
          <div v-if="selectedAppt.reason_summary" class="drawer-section">
            <div class="drawer-section-title">
              <el-icon><Document /></el-icon>
              预约原因
            </div>
            <div class="reason-box">
              {{ selectedAppt.reason_summary }}
            </div>
          </div>

          <!-- 心理老师备注 -->
          <div v-if="selectedAppt.counselor_note" class="drawer-section">
            <div class="drawer-section-title">
              <el-icon><ChatLineSquare /></el-icon>
              心理老师备注
            </div>
            <div class="note-box">
              {{ selectedAppt.counselor_note }}
            </div>
          </div>

          <!-- 状态时间轴 -->
          <div class="drawer-section">
            <div class="drawer-section-title">
              <el-icon><Clock /></el-icon>
              状态流转
            </div>
            <el-timeline class="status-timeline">
              <el-timeline-item
                v-if="selectedAppt.created_at"
                type="primary"
                :timestamp="formatDateTime(selectedAppt.created_at)"
                placement="top"
              >
                预约已提交（待心理老师确认）
              </el-timeline-item>
              <el-timeline-item
                v-if="selectedAppt.confirmed_at"
                type="success"
                :timestamp="formatDateTime(selectedAppt.confirmed_at)"
                placement="top"
              >
                心理老师已确认预约
              </el-timeline-item>
              <el-timeline-item
                v-if="selectedAppt.status === 'cancelled'"
                type="info"
                :timestamp="formatDateTime(selectedAppt.updated_at || selectedAppt.created_at)"
                placement="top"
              >
                预约已取消
              </el-timeline-item>
              <el-timeline-item
                v-if="selectedAppt.status === 'no_show'"
                type="danger"
                :timestamp="formatDateTime(selectedAppt.updated_at || selectedAppt.created_at)"
                placement="top"
              >
                未到诊（缺席）
              </el-timeline-item>
              <el-timeline-item
                v-if="selectedAppt.completed_at || selectedAppt.status === 'completed'"
                type="success"
                :timestamp="formatDateTime(selectedAppt.completed_at || selectedAppt.updated_at)"
                placement="top"
              >
                咨询已完成
              </el-timeline-item>
            </el-timeline>
          </div>

          <!-- 咨询记录(脱敏) -->
          <div v-if="consultRecords.length > 0" class="drawer-section">
            <div class="drawer-section-title">
              <el-icon><Notebook /></el-icon>
              咨询记录
              <el-tag size="small" type="info" effect="plain" class="ml-2">脱敏展示</el-tag>
            </div>
            <div
              v-for="record in consultRecords"
              :key="record.id"
              class="record-card"
            >
              <div class="record-header">
                <el-tag :type="riskFlagTag(record.risk_level)" effect="plain" size="small">
                  {{ riskFlagLabel(record.risk_level) }}
                </el-tag>
                <el-tag v-if="record.consult_category" :type="consultCategoryTag(record.consult_category)" size="small">
                  {{ consultCategoryLabel(record.consult_category) }}
                </el-tag>
                <span v-if="record.is_crisis" class="crisis-flag">危机干预</span>
                <span class="record-date">{{ formatDateTime(record.created_at) }}</span>
              </div>
              <div class="record-content">{{ record.clog_display }}</div>
              <div v-if="record.followup_date" class="record-followup">
                <el-icon><Bell /></el-icon>
                建议复诊: {{ record.followup_date }}
              </div>
            </div>
          </div>

          <!-- 咨询预约须知 -->
          <div class="drawer-section tips-section">
            <div class="tips-title">
              <el-icon><WarningFilled /></el-icon>
              温馨提示
            </div>
            <ul class="tips-list">
              <li>预约提交后，心理老师将在1-2个工作日内确认</li>
              <li>请按时到诊，如需取消请联系班主任或心理辅导室</li>
              <li>咨询记录内容仅心理老师可见，家长端为脱敏摘要</li>
              <li>如有紧急心理危机，请立即拨打心理援助热线: 400-161-9995</li>
            </ul>
          </div>
        </div>
      </template>
    </el-drawer>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  Clock, Calendar, User, LocationInformation, Tickets,
  ArrowRight, Document, ChatLineSquare, Notebook, Bell, WarningFilled,
} from '@element-plus/icons-vue'
import {
  getSlots,
  createAppointment,
  getMyAppointments,
  getConsultRecords,
  appointmentStatusLabel,
  appointmentStatusTag,
  riskFlagLabel,
  riskFlagTag,
  consultCategoryLabel,
  consultCategoryTag,
  sourceLabel,
  type ConsultSlot,
  type Appointment,
  type ConsultRecord,
  type RiskFlag,
} from '@/api/psychCounseling'
import { getChildOverview, type ChildOverview } from '@/api/parent_portal'

// ═══════════════════════════════════════════════════
// 状态
// ═══════════════════════════════════════════════════

const pageLoading = ref(true)
const initError = ref<string | null>(null)
const childInfo = ref<ChildOverview | null>(null)

const activeTab = ref<'slots' | 'appointments'>('slots')

// Tab1: 时段
const slotsLoading = ref(false)
const openSlots = ref<ConsultSlot[]>([])

// Tab2: 我的预约
const apptsLoading = ref(false)
const myAppointments = ref<Appointment[]>([])

// 预约弹窗
const dialogVisible = ref(false)
const selectedSlot = ref<ConsultSlot | null>(null)
const submitting = ref(false)
const apptFormRef = ref<FormInstance>()
const apptForm = ref({
  reason_summary: '',
  risk_flag: 'green' as RiskFlag,
})
const apptRules: FormRules = {
  reason_summary: [
    { required: true, message: '请简要描述预约原因', trigger: 'blur' },
    { min: 10, message: '请至少输入10个字', trigger: 'blur' },
  ],
  risk_flag: [
    { required: true, message: '请选择关注程度', trigger: 'change' },
  ],
}

// 详情抽屉
const drawerVisible = ref(false)
const selectedAppt = ref<Appointment | null>(null)
const consultRecords = ref<ConsultRecord[]>([])

// ═══════════════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════════════

const pendingCount = computed(() =>
  myAppointments.value.filter(a => a.status === 'pending').length
)

// ═══════════════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════════════

async function initPage() {
  pageLoading.value = true
  initError.value = null
  try {
    // 并行: 获取孩子信息 + 开放时段
    const [child, slots] = await Promise.all([
      getChildOverview(),
      getSlots({ status: 'open' }),
    ])
    childInfo.value = child
    openSlots.value = slots.slots || []
  } catch (err: any) {
    initError.value = err?.message || '初始化失败，请稍后重试'
  } finally {
    pageLoading.value = false
  }
}

// ═══════════════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════════════

function handleTabChange(tab: string | number) {
  const tabName = String(tab)
  if (tabName === 'appointments' && myAppointments.value.length === 0) {
    fetchMyAppointments()
  }
}

// ═══════════════════════════════════════════════════
// 时段列表
// ═══════════════════════════════════════════════════

async function fetchSlots() {
  slotsLoading.value = true
  try {
    const res = await getSlots({ status: 'open' })
    openSlots.value = res.slots || []
    if (openSlots.value.length === 0) {
      ElMessage.info('当前暂无可预约时段')
    }
  } catch {
    ElMessage.error('时段列表加载失败')
  } finally {
    slotsLoading.value = false
  }
}

// ═══════════════════════════════════════════════════
// 我的预约
// ═══════════════════════════════════════════════════

async function fetchMyAppointments() {
  apptsLoading.value = true
  try {
    const res = await getMyAppointments()
    myAppointments.value = res.appointments || []
  } catch {
    ElMessage.error('预约记录加载失败')
  } finally {
    apptsLoading.value = false
  }
}

// ═══════════════════════════════════════════════════
// 预约弹窗
// ═══════════════════════════════════════════════════

function openAppointmentDialog(slot: ConsultSlot) {
  if (slot.current_booked >= slot.max_capacity) {
    ElMessage.warning('该时段名额已满')
    return
  }
  selectedSlot.value = slot
  apptForm.value = {
    reason_summary: '',
    risk_flag: 'green',
  }
  dialogVisible.value = true
}

async function submitAppointment() {
  if (!apptFormRef.value || !selectedSlot.value || !childInfo.value) return

  await apptFormRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      await createAppointment({
        student_id: childInfo.value!.student_id,
        slot_id: selectedSlot.value!.id,
        source: 'parent',
        reason_summary: apptForm.value.reason_summary,
        risk_flag: apptForm.value.risk_flag,
      })
      ElMessage.success('预约提交成功！心理老师将尽快确认')
      dialogVisible.value = false

      // 刷新时段（名额已变）+ 预约列表
      await fetchSlots()
      if (activeTab.value === 'appointments') {
        await fetchMyAppointments()
      } else {
        // 自动切换到"我的预约"
        activeTab.value = 'appointments'
        await fetchMyAppointments()
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '预约提交失败'
      ElMessage.error(msg)
    } finally {
      submitting.value = false
    }
  })
}

// ═══════════════════════════════════════════════════
// 详情抽屉
// ═══════════════════════════════════════════════════

async function openDetailDrawer(appt: Appointment) {
  selectedAppt.value = appt
  consultRecords.value = []
  drawerVisible.value = true

  // 尝试加载该学生的咨询记录（后端会自动脱敏返回给家长）
  if (childInfo.value?.student_id) {
    try {
      const res = await getConsultRecords({
        student_id: childInfo.value.student_id,
      })
      consultRecords.value = res.records || []
    } catch {
      // 静默失败 — 咨询记录是附加信息
    }
  }
}

// ═══════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════

function formatDateTime(dt: string | null): string {
  if (!dt) return '--'
  try {
    const d = new Date(dt)
    return d.toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return dt
  }
}

// ═══════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════

onMounted(() => {
  initPage()
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════ */
/* GitHub Dark Theme                                      */
/* ═══════════════════════════════════════════════════ */
.appointment-picker {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 0 20px 0;
}

/* ── 页面标题 ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  flex-direction: column;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  font-weight: 600;
  color: #e6edf3;
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 13px;
  color: #8b949e;
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
}

/* ── 加载 / 错误 ── */
.loading-container {
  padding: 32px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
}

.error-container {
  padding: 60px 40px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  text-align: center;
}

.error-container :deep(.el-empty__description) {
  color: #f85149;
}

/* ── Tab 容器 ── */
.tab-container {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px 20px;
}

.dark-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.dark-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: #30363d;
}

.dark-tabs :deep(.el-tabs__item) {
  color: #8b949e;
  font-size: 15px;
}

.dark-tabs :deep(.el-tabs__item.is-active) {
  color: #58a6ff;
}

.dark-tabs :deep(.el-tabs__active-bar) {
  background-color: #58a6ff;
}

.dark-tabs :deep(.el-tabs__item:hover) {
  color: #79c0ff;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tab-badge :deep(.el-badge__content) {
  font-size: 11px;
}

/* ── 空状态 ── */
.empty-state {
  padding: 40px 20px;
  text-align: center;
}

.empty-state :deep(.el-empty__description) {
  color: #8b949e;
}

/* ── 时段卡片网格 ── */
.slots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.slot-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.slot-card:hover {
  border-color: #58a6ff;
  box-shadow: 0 0 0 1px rgba(88, 166, 255, 0.2);
}

.slot-card.slot-full {
  opacity: 0.6;
  cursor: not-allowed;
}

.slot-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.slot-date {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 16px;
  font-weight: 600;
  color: #e6edf3;
}

.slot-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #79c0ff;
}

.slot-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.slot-teacher,
.slot-location {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #8b949e;
}

.slot-capacity {
  display: flex;
  align-items: center;
  gap: 8px;
}

.slot-capacity :deep(.el-progress) {
  flex: 1;
}

.capacity-text {
  font-size: 12px;
  color: #8b949e;
  white-space: nowrap;
}

.slot-action {
  display: flex;
  justify-content: flex-end;
}

/* ── 我的预约列表 ── */
.appt-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.appt-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.appt-item:hover {
  border-color: #58a6ff;
  background: #1a2332;
}

.appt-item-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
  min-width: 0;
}

.appt-date-block {
  text-align: center;
  min-width: 80px;
  padding: 8px 12px;
  background: #21262d;
  border-radius: 6px;
}

.appt-date-day {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.appt-date-time {
  font-size: 12px;
  color: #8b949e;
  margin-top: 2px;
}

.appt-info {
  flex: 1;
  min-width: 0;
}

.appt-top-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.appt-source {
  font-size: 12px;
  color: #8b949e;
}

.appt-reason {
  font-size: 13px;
  color: #c9d1d9;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.appt-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #8b949e;
}

.appt-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.appt-arrow {
  color: #484f58;
  font-size: 16px;
}

/* ═══════════════════════════════════════════════════ */
/* 预约弹窗 — Dark Dialog                                */
/* ═══════════════════════════════════════════════════ */
.dark-dialog :deep(.el-dialog) {
  background: #161b22;
  border: 1px solid #30363d;
}

.dark-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid #30363d;
}

.dark-dialog :deep(.el-dialog__title) {
  color: #e6edf3;
}

.dark-dialog :deep(.el-dialog__body) {
  color: #c9d1d9;
}

.dark-dialog :deep(.el-dialog__footer) {
  border-top: 1px solid #30363d;
}

.dialog-slot-info {
  margin-bottom: 20px;
}

.dark-dialog :deep(.el-descriptions__label) {
  color: #8b949e;
  background: #21262d !important;
}

.dark-dialog :deep(.el-descriptions__content) {
  color: #e6edf3;
  background: #161b22 !important;
}

.dark-dialog :deep(.el-descriptions__cell) {
  border-color: #30363d !important;
}

.appt-form :deep(.el-form-item__label) {
  color: #c9d1d9;
}

.dark-dialog :deep(.el-textarea__inner) {
  background: #0d1117;
  border-color: #30363d;
  color: #e6edf3;
}

.dark-dialog :deep(.el-textarea__inner:focus) {
  border-color: #58a6ff;
}

.dark-dialog :deep(.el-input__count) {
  background: #21262d;
  color: #8b949e;
}

.dark-dialog :deep(.el-radio-button__inner) {
  background: #21262d;
  border-color: #30363d;
  color: #8b949e;
}

.dark-dialog :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #fff;
  box-shadow: -1px 0 0 0 #1f6feb;
}

/* ═══════════════════════════════════════════════════ */
/* 详情抽屉 — Dark Drawer                                */
/* ═══════════════════════════════════════════════════ */
.dark-drawer :deep(.el-drawer) {
  background: #0d1117;
}

.dark-drawer :deep(.el-drawer__header) {
  color: #e6edf3;
  border-bottom: 1px solid #30363d;
  margin-bottom: 0;
  padding: 16px 20px;
}

.dark-drawer :deep(.el-drawer__body) {
  padding: 20px;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.drawer-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #58a6ff;
}

.ml-2 {
  margin-left: 8px;
}

.dark-drawer :deep(.el-descriptions__label) {
  color: #8b949e;
  background: #161b22 !important;
  width: 100px;
}

.dark-drawer :deep(.el-descriptions__content) {
  color: #e6edf3;
  background: #0d1117 !important;
}

.dark-drawer :deep(.el-descriptions__cell) {
  border-color: #30363d !important;
}

.dark-drawer :deep(.el-descriptions--small .el-descriptions__label) {
  width: 90px;
}

/* ── 原因 / 备注框 ── */
.reason-box,
.note-box {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 12px 16px;
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.6;
}

.note-box {
  border-left: 3px solid #d29922;
}

/* ── 状态时间轴 ── */
.status-timeline {
  padding: 4px 0 0 0;
}

.dark-drawer :deep(.el-timeline-item__timestamp) {
  color: #8b949e;
  font-size: 12px;
}

.dark-drawer :deep(.el-timeline-item__content) {
  color: #c9d1d9;
  font-size: 13px;
}

/* ── 咨询记录卡片 ── */
.record-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 12px 16px;
}

.record-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.crisis-flag {
  font-size: 12px;
  color: #f85149;
  font-weight: 600;
  background: rgba(248, 81, 73, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.record-date {
  font-size: 12px;
  color: #8b949e;
  margin-left: auto;
}

.record-content {
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.6;
  padding: 8px 0;
}

.record-followup {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #d29922;
  padding-top: 8px;
  border-top: 1px solid #30363d;
}

/* ── 温馨提示 ── */
.tips-section {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 16px;
}

.tips-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #d29922;
  margin-bottom: 10px;
}

.tips-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #8b949e;
  line-height: 1.8;
}

.tips-list li {
  margin-bottom: 4px;
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .slots-grid {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .appt-item-left {
    flex-direction: column;
    align-items: flex-start;
  }

  .appt-date-block {
    min-width: auto;
    width: 100%;
  }

  .dark-dialog :deep(.el-dialog) {
    width: 95% !important;
  }

  .dark-drawer :deep(.el-drawer) {
    width: 100% !important;
  }
}
</style>
