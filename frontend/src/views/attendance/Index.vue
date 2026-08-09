<template>
  <div class="attendance-center">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon><Calendar /></el-icon>
          考勤管理
        </h2>
        <span class="page-subtitle">RDI 四维之一 · 出勤率监控 · 异常预警 · 请假审批</span>
      </div>
      <div class="header-right">
        <el-select v-model="selectedGradeId" placeholder="选择年级" style="width: 140px" @change="onGradeChange">
          <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
        <el-select v-model="selectedClassId" placeholder="选择班级" style="width: 160px" clearable @change="fetchData">
          <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </div>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- Tab 1: Dashboard -->
      <el-tab-pane label="仪表盘" name="dashboard">
        <div v-loading="loading.dashboard">
          <!-- Overview Cards -->
          <el-row :gutter="16" class="stat-cards" v-if="dashboardData">
            <el-col :span="4">
              <div class="stat-card total">
                <div class="stat-value">{{ dashboardData.summary?.total_students || 0 }}</div>
                <div class="stat-label">应到</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat-card present">
                <div class="stat-value">{{ dashboardData.summary?.present || 0 }}</div>
                <div class="stat-label">实到</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat-card absent">
                <div class="stat-value">{{ dashboardData.summary?.absent || 0 }}</div>
                <div class="stat-label">缺勤</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat-card late">
                <div class="stat-value">{{ dashboardData.summary?.late || 0 }}</div>
                <div class="stat-label">迟到</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat-card leave">
                <div class="stat-value">{{ dashboardData.summary?.leave || 0 }}</div>
                <div class="stat-label">请假</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat-card rate">
                <div class="stat-value">{{ ((dashboardData.summary?.attendance_rate || 0) * 100).toFixed(1) }}%</div>
                <div class="stat-label">出勤率</div>
              </div>
            </el-col>
          </el-row>

          <!-- Trend Chart placeholder -->
          <el-card shadow="never" class="trend-card" v-if="dashboardData?.trend?.length">
            <template #header>出勤趋势</template>
            <div class="trend-bars">
              <div v-for="item in dashboardData.trend" :key="item.date" class="trend-bar-group">
                <div class="trend-bar present" :style="{ height: barHeight(item.present) + 'px' }" :title="`实到: ${item.present}`" />
                <div class="trend-bar absent" :style="{ height: barHeight(item.absent) + 'px' }" :title="`缺勤: ${item.absent}`" />
                <div class="trend-bar late" :style="{ height: barHeight(item.late) + 'px' }" :title="`迟到: ${item.late}`" />
                <span class="trend-date">{{ item.date.slice(5) }}</span>
              </div>
            </div>
            <div class="trend-legend">
              <span class="legend-item"><i class="dot present"></i>实到</span>
              <span class="legend-item"><i class="dot absent"></i>缺勤</span>
              <span class="legend-item"><i class="dot late"></i>迟到</span>
            </div>
          </el-card>

          <el-empty v-if="!loading.dashboard && !dashboardData" description="暂无数据，请选择年级和班级" />
        </div>
      </el-tab-pane>

      <!-- Tab 2: Class Attendance Records -->
      <el-tab-pane label="班级考勤" name="records">
        <div class="records-toolbar">
          <el-date-picker
            v-model="recordDate"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @change="fetchClassRecords"
          />
          <el-button type="primary" :icon="Refresh" @click="fetchClassRecords">刷新</el-button>
        </div>
        <el-table :data="classRecords" v-loading="loading.records" stripe style="width: 100%">
          <el-table-column prop="student_name" label="学生" width="120" />
          <el-table-column prop="class_name" label="班级" width="120" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ STATUS_LABELS[row.status as AttendanceStatus] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="record_date" label="日期" width="120" />
          <el-table-column prop="note" label="备注" min-width="200" show-overflow-tooltip />
        </el-table>
        <el-empty v-if="!loading.records && classRecords.length === 0" description="选择班级和日期查看考勤记录" />
      </el-tab-pane>

      <!-- Tab 3: Anomaly Alerts -->
      <el-tab-pane label="异常预警" name="anomalies">
        <div class="anomalies-toolbar">
          <span class="toolbar-label">监测天数：</span>
          <el-select v-model="anomalyDays" style="width: 100px" @change="fetchAnomalies">
            <el-option :value="3" label="3天" />
            <el-option :value="7" label="7天" />
            <el-option :value="14" label="14天" />
            <el-option :value="30" label="30天" />
          </el-select>
          <el-button type="primary" :icon="Refresh" @click="fetchAnomalies">刷新</el-button>
        </div>
        <el-table :data="anomalies" v-loading="loading.anomalies" stripe style="width: 100%">
          <el-table-column prop="student_name" label="学生" width="120" />
          <el-table-column prop="class_name" label="班级" width="120" />
          <el-table-column prop="alert_type" label="预警类型" width="160">
            <template #default="{ row }">
              <el-tag :type="row.severity === 'danger' ? 'danger' : 'warning'" size="small">
                {{ alertTypeLabel(row.alert_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" min-width="300" show-overflow-tooltip />
        </el-table>
        <el-empty v-if="!loading.anomalies && anomalies.length === 0" description="近期无异常考勤记录" />
      </el-tab-pane>

      <!-- Tab 4: Leave Management -->
      <el-tab-pane label="请假管理" name="leaves">
        <div class="leaves-toolbar">
          <el-select v-model="leaveStatusFilter" placeholder="状态筛选" clearable style="width: 140px" @change="fetchLeaves">
            <el-option value="pending" label="待审批" />
            <el-option value="class_approved" label="班主任已批" />
            <el-option value="grade_approved" label="年级已批" />
            <el-option value="rejected" label="已拒绝" />
          </el-select>
          <el-button type="primary" :icon="Refresh" @click="fetchLeaves">刷新</el-button>
        </div>
        <el-table :data="leaves" v-loading="loading.leaves" stripe style="width: 100%">
          <el-table-column prop="student_name" label="学生" width="100" />
          <el-table-column prop="class_name" label="班级" width="100" />
          <el-table-column prop="start_date" label="起始" width="120" />
          <el-table-column prop="end_date" label="结束" width="120" />
          <el-table-column prop="reason" label="请假原因" min-width="200" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="leaveStatusType(row.status)" size="small">
                {{ leaveStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button type="success" size="small" @click="handleApproveLeave(row.id, 'approve')">通过</el-button>
                <el-button type="danger" size="small" @click="handleApproveLeave(row.id, 'reject')">拒绝</el-button>
              </template>
              <span v-else class="text-muted">已处理</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading.leaves && leaves.length === 0" description="暂无请假记录" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Calendar, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import { getGrades, getClasses } from '@/api/classes'
import {
  getDashboard, getClassAttendance, getAnomalies, listLeaves, approveLeave,
  STATUS_LABELS,
  type AttendanceStatus, type DashboardData, type AnomalyAlert, type LeaveRecord,
} from '@/api/attendance'

const userStore = useUserStore()
const isAdmin = ref(userStore.currentRole === 'MS_ADMIN')

// ── 筛选条件 ──
const grades = ref<any[]>([])
const classes = ref<any[]>([])
const selectedGradeId = ref<number | null>(null)
const selectedClassId = ref<number | null>(null)

// ── Tab 状态 ──
const activeTab = ref('dashboard')

// ── 数据 ──
const dashboardData = ref<DashboardData | null>(null)
const classRecords = ref<any[]>([])
const anomalies = ref<AnomalyAlert[]>([])
const leaves = ref<LeaveRecord[]>([])

// ── 加载状态 ──
const loading = ref({
  dashboard: false,
  records: false,
  anomalies: false,
  leaves: false,
})

// ── 日期/筛选 ──
const recordDate = ref(new Date().toISOString().slice(0, 10))
const anomalyDays = ref(7)
const leaveStatusFilter = ref('')

// ═══════════════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════════════

onMounted(async () => {
  await fetchGrades()
})

async function fetchGrades() {
  try {
    const res: any = await getGrades()
    grades.value = res?.items || res || []
    if (grades.value.length > 0) {
      // 年级组长自动选中自己的年级
      const userGradeId = (userStore.userInfo as any)?.grade_id
      if (userGradeId) {
        selectedGradeId.value = userGradeId
      } else {
        selectedGradeId.value = grades.value[0].id
      }
      await onGradeChange()
    }
  } catch {
    // silent
  }
}

async function onGradeChange() {
  selectedClassId.value = null
  if (!selectedGradeId.value) return
  try {
    const res: any = await getClasses({ grade_id: selectedGradeId.value })
    classes.value = res?.items || res || []
  } catch {
    classes.value = []
  }
  fetchData()
}

function fetchData() {
  if (activeTab.value === 'dashboard') fetchDashboard()
  else if (activeTab.value === 'records') fetchClassRecords()
  else if (activeTab.value === 'anomalies') fetchAnomalies()
  else if (activeTab.value === 'leaves') fetchLeaves()
}

function onTabChange() {
  fetchData()
}

// ═══════════════════════════════════════════════════
// Dashboard
// ═══════════════════════════════════════════════════

async function fetchDashboard() {
  loading.value.dashboard = true
  try {
    const params: any = { period: 'week' }
    if (selectedGradeId.value) params.grade_id = selectedGradeId.value
    if (selectedClassId.value) params.class_id = selectedClassId.value
    const res: any = await getDashboard(params)
    dashboardData.value = res
  } catch {
    dashboardData.value = null
  } finally {
    loading.value.dashboard = false
  }
}

const maxTrendValue = ref(1)
function barHeight(val: number): number {
  if (!dashboardData.value?.trend) return 0
  const max = Math.max(...dashboardData.value.trend.map((t: any) => Math.max(t.present || 0, t.absent || 0, t.late || 0)), 1)
  return Math.max(2, (val / max) * 120)
}

// ═══════════════════════════════════════════════════
// Class Records
// ═══════════════════════════════════════════════════

async function fetchClassRecords() {
  if (!selectedClassId.value) {
    ElMessage.warning('请先选择班级')
    return
  }
  loading.value.records = true
  try {
    const res: any = await getClassAttendance(selectedClassId.value, { record_date: recordDate.value })
    classRecords.value = res?.records || []
  } catch {
    classRecords.value = []
  } finally {
    loading.value.records = false
  }
}

// ═══════════════════════════════════════════════════
// Anomalies
// ═══════════════════════════════════════════════════

async function fetchAnomalies() {
  loading.value.anomalies = true
  try {
    const res: any = await getAnomalies(anomalyDays.value)
    anomalies.value = res?.alerts || []
  } catch {
    anomalies.value = []
  } finally {
    loading.value.anomalies = false
  }
}

function alertTypeLabel(type: string): string {
  const map: Record<string, string> = {
    consecutive_absent: '连续缺勤',
    weekly_late: '本周迟到频繁',
    monthly_absent: '本月缺勤过多',
  }
  return map[type] || type
}

// ═══════════════════════════════════════════════════
// Leaves
// ═══════════════════════════════════════════════════

async function fetchLeaves() {
  loading.value.leaves = true
  try {
    const params: any = { limit: 50 }
    if (leaveStatusFilter.value) params.status = leaveStatusFilter.value
    if (selectedGradeId.value) params.grade_id = selectedGradeId.value
    if (selectedClassId.value) params.class_id = selectedClassId.value
    const res: any = await listLeaves(params)
    leaves.value = res?.items || res || []
  } catch {
    leaves.value = []
  } finally {
    loading.value.leaves = false
  }
}

async function handleApproveLeave(leaveId: number, action: 'approve' | 'reject') {
  try {
    await approveLeave({ leave_id: leaveId, action })
    ElMessage.success(action === 'approve' ? '已通过' : '已拒绝')
    fetchLeaves()
  } catch {
    // error handled by interceptor
  }
}

// ═══════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════

function statusTagType(status: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    present: 'success',
    absent: 'danger',
    late: 'warning',
    leave: 'primary',
    early_leave: 'info',
  }
  return map[status] || 'info'
}

function leaveStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待审批',
    class_approved: '班主任已批',
    grade_approved: '年级已批',
    rejected: '已拒绝',
  }
  return map[status] || status
}

function leaveStatusType(status: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    pending: 'warning',
    class_approved: 'primary',
    grade_approved: 'success',
    rejected: 'danger',
  }
  return map[status] || 'info'
}
</script>

<style scoped>
.attendance-center {
  padding: 0 0 20px 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  margin: 0;
  color: #303133;
}

.page-subtitle {
  font-size: 12px;
  color: #909399;
  margin-left: 12px;
}

.header-right {
  display: flex;
  gap: 8px;
}

.stat-cards {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 20px 8px;
  border-radius: 8px;
  color: #fff;
  transition: transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.stat-card.total { background: linear-gradient(135deg, #667eea, #764ba2); }
.stat-card.present { background: linear-gradient(135deg, #11998e, #38ef7d); }
.stat-card.absent { background: linear-gradient(135deg, #eb3349, #f45c43); }
.stat-card.late { background: linear-gradient(135deg, #f7b733, #fc4a1a); }
.stat-card.leave { background: linear-gradient(135deg, #45b6ea, #4facfe); }
.stat-card.rate { background: linear-gradient(135deg, #a18cd1, #fbc2eb); }

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  opacity: 0.9;
  margin-top: 4px;
}

.trend-card {
  margin-top: 4px;
}

.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 160px;
  padding: 10px 0;
  overflow-x: auto;
}

.trend-bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 36px;
}

.trend-bar {
  width: 10px;
  border-radius: 3px 3px 0 0;
  transition: height 0.3s;
}

.trend-bar.present { background: #67c23a; }
.trend-bar.absent { background: #f56c6c; }
.trend-bar.late { background: #e6a23c; }

.trend-date {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

.trend-legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  justify-content: center;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #606266;
}

.legend-item .dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.dot.present { background: #67c23a; }
.dot.absent { background: #f56c6c; }
.dot.late { background: #e6a23c; }

.records-toolbar,
.anomalies-toolbar,
.leaves-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.toolbar-label {
  font-size: 14px;
  color: #606266;
}

.text-muted {
  color: #c0c4cc;
  font-size: 13px;
}
</style>
