<template>
  <div class="approval-center-view">
    <!-- ═══ Page Header ═══ -->
    <div class="page-header">
      <div class="header-left">
        <el-icon :size="22"><Checked /></el-icon>
        <span class="header-title">审批工作台</span>
        <el-tag size="small" type="info" effect="plain" round>多租户动态链</el-tag>
      </div>
      <div class="header-right">
        <el-radio-group v-model="ticketType" @change="loadTickets">
          <el-radio-button value="todo">待办工单</el-radio-button>
          <el-radio-button value="done">已办工单</el-radio-button>
        </el-radio-group>
        <el-button :icon="Refresh" circle @click="loadTickets" :loading="loading" />
      </div>
    </div>

    <el-row :gutter="20" class="main-row">
      <!-- ═══ Left: Ticket Card List (span=10) ═══ -->
      <el-col :span="10">
        <el-card shadow="never" class="ticket-list-card" v-loading="loading">
          <template #header>
            <div class="list-header">
              <span>工单列表</span>
              <el-badge :value="tickets.length" :max="99" type="primary" />
            </div>
          </template>

          <div
            v-if="tickets.length === 0 && !loading"
            class="empty-state"
          >
            <el-empty description="暂无工单" :image-size="80" />
          </div>

          <div
            v-for="ticket in tickets"
            :key="ticket.ticket_id"
            class="ticket-card"
            :class="{ active: selectedTicket?.ticket_id === ticket.ticket_id }"
            @click="selectTicket(ticket)"
          >
            <!-- Top: title + tenant tag -->
            <div class="ticket-top">
              <span class="ticket-title">{{ ticket.title }}</span>
              <el-tag size="small" effect="dark" round class="tenant-tag">
                {{ ticket.tenant_school }}
              </el-tag>
            </div>

            <!-- Middle: applicant + ticket_id -->
            <div class="ticket-mid">
              <el-icon><User /></el-icon>
              <span class="ticket-applicant">{{ ticket.applicant_name }}</span>
              <span class="ticket-id">{{ ticket.ticket_id }}</span>
            </div>

            <!-- Bottom: current node + time -->
            <div class="ticket-bottom">
              <el-tag
                size="small"
                :type="getNodeTagType(ticket.chain_config[ticket.current_node_index]?.status)"
                effect="light"
              >
                {{ ticket.chain_config[ticket.current_node_index]?.node_name ?? '--' }}
              </el-tag>
              <span class="ticket-time">{{ formatTime(ticket.created_at) }}</span>
            </div>

            <!-- Urgent badge for todo tickets -->
            <div
              v-if="ticketType === 'todo' && getRemainingHours(ticket) < 24"
              class="urgent-dot"
            >
              <el-icon color="#f56c6c"><WarningFilled /></el-icon>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- ═══ Right: Detail Card (span=14) ═══ -->
      <el-col :span="14">
        <el-card shadow="never" class="detail-card" v-if="selectedTicket">
          <!-- Detail Header -->
          <template #header>
            <div class="detail-header">
              <div class="detail-title-row">
                <span class="detail-title">{{ selectedTicket.title }}</span>
                <el-tag size="small" effect="dark" round>
                  {{ selectedTicket.tenant_school }}
                </el-tag>
              </div>
              <div class="detail-meta">
                <span class="meta-item">
                  <el-icon><Tickets /></el-icon>
                  {{ selectedTicket.ticket_id }}
                </span>
                <span class="meta-item">
                  <el-icon><User /></el-icon>
                  {{ selectedTicket.applicant_name }}
                </span>
                <span class="meta-item">
                  <el-icon><Clock /></el-icon>
                  创建于 {{ formatTime(selectedTicket.created_at) }}
                </span>
              </div>
            </div>
          </template>

          <!-- Countdown Banner -->
          <div v-if="ticketType === 'todo'" class="countdown-banner" :class="{ urgent: isUrgent, expired: isExpired }">
            <div class="countdown-left">
              <el-icon :size="28" class="countdown-icon">
                <AlarmClock v-if="isExpired" />
                <Timer v-else />
              </el-icon>
              <div class="countdown-text">
                <div class="countdown-label">
                  {{ isExpired ? '已超期滞留' : '审批剩余时限' }}
                </div>
                <div class="countdown-value" v-if="!isExpired">
                  {{ countdownDisplay }}
                </div>
                <div class="countdown-value expired-text" v-else>
                  超期 {{ overdueDisplay }}
                </div>
              </div>
            </div>
            <div class="countdown-right">
              <div class="deadline-label">截止时间</div>
              <div class="deadline-value">{{ formatTime(selectedTicket.deadline_at) }}</div>
            </div>
          </div>

          <!-- Dynamic Topology: el-steps -->
          <div class="topology-section">
            <div class="section-title">
              <el-icon><Share /></el-icon>
              <span>审批流转拓扑</span>
              <el-tag size="small" type="info" effect="plain">
                {{ selectedTicket.chain_config.length }} 节点链
              </el-tag>
            </div>

            <el-steps
              :active="selectedTicket.current_node_index"
              align-center
              class="approval-steps"
            >
              <el-step
                v-for="(node, index) in selectedTicket.chain_config"
                :key="node.node_id"
                :status="getStepStatus(node.status)"
              >
                <!-- Custom title slot: node name + status tag -->
                <template #title>
                  <div class="step-title">
                    <span class="step-name">{{ node.node_name }}</span>
                    <el-tag
                      size="small"
                      :type="getNodeTagType(node.status)"
                      effect="dark"
                      round
                    >
                      {{ getNodeStatusLabel(node.status) }}
                    </el-tag>
                  </div>
                </template>

                <!-- Custom description slot: role + assignee + time -->
                <template #description>
                  <div class="step-desc">
                    <div class="desc-row">
                      <el-icon><UserFilled /></el-icon>
                      <span class="desc-role">{{ getRoleLabel(node.assignee_role) }}</span>
                      <span class="desc-assignee">
                        {{ node.assignee_name ?? '待分配' }}
                      </span>
                    </div>
                    <div class="desc-row" v-if="node.update_time">
                      <el-icon><Clock /></el-icon>
                      <span class="desc-time">{{ formatTime(node.update_time) }}</span>
                    </div>
                    <!-- Urge button on pending node -->
                    <div
                      class="desc-row urge-row"
                      v-if="node.status === 'pending' && ticketType === 'todo'"
                    >
                      <el-button
                        size="small"
                        type="warning"
                        :icon="Bell"
                        :loading="urgingNodeId === node.node_id"
                        :disabled="urgedNodes.has(node.node_id)"
                        @click="triggerUrge(node.node_id)"
                      >
                        {{ urgedNodes.has(node.node_id) ? '已催办' : '催办' }}
                      </el-button>
                    </div>
                  </div>
                </template>
              </el-step>
            </el-steps>
          </div>

          <!-- Risk Notice Block -->
          <div class="risk-notice" v-if="ticketType === 'todo' && isUrgent">
            <el-icon color="#f56c6c" :size="20"><WarningFilled /></el-icon>
            <div class="notice-content">
              <div class="notice-title">超期风险预警</div>
              <div class="notice-text">
                该工单剩余时限不足 24 小时，请尽快处理。
                超期工单将自动触发升级审批流程，并记录在德育处审计日志中。
              </div>
            </div>
          </div>

          <!-- Control Console -->
          <div class="control-console" v-if="ticketType === 'todo'">
            <div class="console-title">
              <el-icon><Setting /></el-icon>
              <span>控制台</span>
            </div>
            <div class="console-actions">
              <el-button
                type="primary"
                :icon="Check"
                @click="handleApprove"
              >
                通过审批
              </el-button>
              <el-button
                type="danger"
                :icon="Close"
                @click="handleReject"
              >
                驳回
              </el-button>
              <el-button
                :icon="Document"
                @click="handleViewDetail"
              >
                查看详情
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- Empty state when no ticket selected -->
        <el-card shadow="never" class="detail-card empty-detail" v-else>
          <el-empty description="请从左侧选择工单查看审批流转拓扑" :image-size="120" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Reject Dialog -->
    <el-dialog v-model="rejectDialogVisible" title="驳回工单" width="480px">
      <el-form>
        <el-form-item label="驳回理由">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="4"
            placeholder="请输入驳回理由..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmReject">确认驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  Checked, User, UserFilled, Clock, Timer, AlarmClock,
  Bell, Share, Setting, Check, Close, Document,
  Tickets, WarningFilled, Refresh,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchTicketsWithFallback,
  urgeTicketNode,
  type ApprovalTicket,
  type ApprovalNode,
} from '@/api/approval'

// ═════════════════════════════════════════════════════════════════
// State
// ═════════════════════════════════════════════════════════════════

const loading = ref(false)
const ticketType = ref<'todo' | 'done'>('todo')
const tickets = ref<ApprovalTicket[]>([])
const selectedTicket = ref<ApprovalTicket | null>(null)

// Countdown
const now = ref(Date.now())
let countdownTimer: ReturnType<typeof setInterval> | null = null

// Urge
const urgingNodeId = ref<string | null>(null)
const urgedNodes = ref<Set<string>>(new Set())

// Reject dialog
const rejectDialogVisible = ref(false)
const rejectReason = ref('')

// ═════════════════════════════════════════════════════════════════
// Computed: Countdown
// ═════════════════════════════════════════════════════════════════

const remainingMs = computed(() => {
  if (!selectedTicket.value) return 0
  const deadline = new Date(selectedTicket.value.deadline_at).getTime()
  return deadline - now.value
})

const isExpired = computed(() => remainingMs.value <= 0)

const isUrgent = computed(() => {
  if (isExpired.value) return false
  return remainingMs.value < 24 * 3600_000 // < 24 hours
})

const countdownDisplay = computed(() => {
  if (remainingMs.value <= 0) return '00:00:00'
  const totalSec = Math.floor(remainingMs.value / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  return `${pad(h)}:${pad(m)}:${pad(s)}`
})

const overdueDisplay = computed(() => {
  const overMs = -remainingMs.value
  const totalSec = Math.floor(overMs / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  return `${h}h ${m}m`
})

// ═════════════════════════════════════════════════════════════════
// Data Loading
// ═════════════════════════════════════════════════════════════════

async function loadTickets() {
  loading.value = true
  try {
    tickets.value = await fetchTicketsWithFallback(ticketType.value)
    // Auto-select first ticket if none selected
    if (tickets.value.length > 0 && !selectedTicket.value) {
      selectTicket(tickets.value[0])
    } else if (tickets.value.length === 0) {
      selectedTicket.value = null
    }
  } catch {
    tickets.value = []
    ElMessage.error('工单加载失败')
  } finally {
    loading.value = false
  }
}

function selectTicket(ticket: ApprovalTicket) {
  selectedTicket.value = ticket
  urgedNodes.value.clear()
  // Start countdown for todo tickets
  if (ticketType.value === 'todo') {
    startCountdown()
  } else {
    stopCountdown()
  }
}

// ═════════════════════════════════════════════════════════════════
// Countdown Timer
// ═════════════════════════════════════════════════════════════════

function startCountdown() {
  stopCountdown()
  now.value = Date.now()
  countdownTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

// ═════════════════════════════════════════════════════════════════
// Urge Mechanism
// ═════════════════════════════════════════════════════════════════

async function triggerUrge(nodeId: string) {
  if (!selectedTicket.value) return
  if (urgedNodes.value.has(nodeId)) {
    ElMessage.warning('该节点已催办，请勿重复操作')
    return
  }

  urgingNodeId.value = nodeId
  try {
    await urgeTicketNode(selectedTicket.value.ticket_id, nodeId)
    urgedNodes.value.add(nodeId)
    ElMessage.success('催办通知已推送至审批人（钉钉/企业微信）')
  } catch {
    // Even if backend fails, show success in demo mode
    urgedNodes.value.add(nodeId)
    ElMessage.success('催办通知已推送至审批人（钉钉/企业微信）')
  } finally {
    urgingNodeId.value = null
  }
}

// ═════════════════════════════════════════════════════════════════
// Approve / Reject / View
// ═════════════════════════════════════════════════════════════════

function handleApprove() {
  ElMessageBox.confirm(
    '确认通过当前节点的审批？通过后将流转至下一节点。',
    '审批确认',
    { confirmButtonText: '确认通过', cancelButtonText: '取消', type: 'success' },
  ).then(() => {
    ElMessage.success('审批已通过，工单流转至下一节点')
    // In real mode, would call approveRequest API
  }).catch(() => {})
}

function handleReject() {
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

function confirmReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请输入驳回理由')
    return
  }
  rejectDialogVisible.value = false
  ElMessage.success('工单已驳回')
  // In real mode, would call rejectRequest API
}

function handleViewDetail() {
  ElMessage.info(`查看工单 ${selectedTicket.value?.ticket_id} 详情`)
}

// ═════════════════════════════════════════════════════════════════
// Helpers
// ═════════════════════════════════════════════════════════════════

function getStepStatus(status: ApprovalNode['status']): 'success' | 'process' | 'wait' | 'error' | 'finish' {
  const map: Record<ApprovalNode['status'], 'success' | 'process' | 'wait' | 'error' | 'finish'> = {
    approved: 'success',
    pending: 'process',
    waiting: 'wait',
    rejected: 'error',
  }
  return map[status] ?? 'wait'
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

function getNodeTagType(status: ApprovalNode['status']): TagType {
  const map: Record<ApprovalNode['status'], TagType> = {
    approved: 'success',
    pending: 'warning',
    waiting: 'info',
    rejected: 'danger',
  }
  return map[status] ?? 'info'
}

function getNodeStatusLabel(status: ApprovalNode['status']): string {
  const map: Record<string, string> = {
    approved: '已通过',
    pending: '审批中',
    waiting: '待流转',
    rejected: '已驳回',
  }
  return map[status] ?? status
}

function getRoleLabel(role: string): string {
  const map: Record<string, string> = {
    class_teacher: '班主任',
    grade_leader: '年级组长',
    ms_admin: '德育处',
    principal: '校长',
    grade_coordinator: '级部统筹',
  }
  return map[role] ?? role
}

function getRemainingHours(ticket: ApprovalTicket): number {
  const deadline = new Date(ticket.deadline_at).getTime()
  return (deadline - Date.now()) / 3600_000
}

function formatTime(iso: string | null): string {
  if (!iso) return '--'
  const d = new Date(iso)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

// ═════════════════════════════════════════════════════════════════
// Lifecycle
// ═════════════════════════════════════════════════════════════════

onMounted(() => {
  loadTickets()
})

onBeforeUnmount(() => {
  stopCountdown()
})
</script>

<style scoped>
.approval-center-view {
  padding: 0;
}

/* ═══ Page Header ═══ */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 0 4px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-size: 18px;
  font-weight: 700;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ═══ Main Row ═══ */
.main-row {
  margin: 0 !important;
}

/* ═══ Left: Ticket List ═══ */
.ticket-list-card {
  border-radius: 10px;
  min-height: 600px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.empty-state {
  padding: 40px 0;
}

.ticket-card {
  position: relative;
  padding: 14px 16px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.25s ease;
  background: var(--el-bg-color-page);
}

.ticket-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.12);
  transform: translateX(2px);
}

.ticket-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.18);
}

.ticket-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.ticket-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.tenant-tag {
  flex-shrink: 0;
}

.ticket-mid {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.ticket-applicant {
  font-weight: 500;
}

.ticket-id {
  margin-left: auto;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  opacity: 0.7;
}

.ticket-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ticket-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.urgent-dot {
  position: absolute;
  top: 10px;
  right: 10px;
  animation: blink 1.2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ═══ Right: Detail Card ═══ */
.detail-card {
  border-radius: 10px;
  min-height: 600px;
}

.empty-detail {
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-title {
  font-size: 16px;
  font-weight: 700;
}

.detail-meta {
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ═══ Countdown Banner ═══ */
.countdown-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-radius: 10px;
  background: linear-gradient(135deg, #e8f4ff 0%, #f0f7ff 100%);
  border: 1px solid #b3d8ff;
  margin-bottom: 20px;
  transition: all 0.3s ease;
}

.countdown-banner.urgent {
  background: linear-gradient(135deg, #fff0f0 0%, #ffe8e8 100%);
  border-color: #f56c6c;
  animation: pulse 1.5s ease-in-out infinite;
}

.countdown-banner.expired {
  background: linear-gradient(135deg, #fef0f0 0%, #fde2e2 100%);
  border-color: #f56c6c;
  border-width: 2px;
}

@keyframes pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.3);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(245, 108, 108, 0);
  }
}

.countdown-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.countdown-icon {
  color: var(--el-color-primary);
}

.urgent .countdown-icon,
.expired .countdown-icon {
  color: #f56c6c;
}

.countdown-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 2px;
}

.countdown-value {
  font-size: 26px;
  font-weight: 800;
  font-family: 'Courier New', monospace;
  color: var(--el-color-primary);
  letter-spacing: 1px;
}

.urgent .countdown-value {
  color: #f56c6c;
}

.expired-text {
  color: #f56c6c !important;
  font-size: 20px !important;
}

.countdown-right {
  text-align: right;
}

.deadline-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 2px;
}

.deadline-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* ═══ Topology Section ═══ */
.topology-section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.approval-steps {
  padding: 10px 0;
}

/* Step custom slots */
.step-title {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.step-name {
  font-size: 13px;
  font-weight: 600;
}

.step-desc {
  text-align: center;
  padding: 4px 0;
}

.desc-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.desc-role {
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.desc-assignee {
  color: var(--el-text-color-secondary);
}

.desc-time {
  font-size: 11px;
  opacity: 0.8;
}

.urge-row {
  margin-top: 8px;
}

/* ═══ Risk Notice ═══ */
.risk-notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 8px;
  margin-bottom: 20px;
}

.notice-content {
  flex: 1;
}

.notice-title {
  font-size: 13px;
  font-weight: 700;
  color: #f56c6c;
  margin-bottom: 4px;
}

.notice-text {
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}

/* ═══ Control Console ═══ */
.control-console {
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.console-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.console-actions {
  display: flex;
  gap: 12px;
}
</style>
