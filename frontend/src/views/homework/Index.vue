<template>
  <div class="homework-console">
    <h2 class="page-title">作业管理</h2>

    <el-row :gutter="16" class="kpi-row">
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ dash.total_assignments }}</div>
          <div class="kpi-label">作业总数</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#67c23a">{{ dash.active_assignments }}</div>
          <div class="kpi-label">进行中</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ dash.total_submissions }}</div>
          <div class="kpi-label">提交总数</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#e6a23c">{{ dash.pending_grading }}</div>
          <div class="kpi-label">待批改</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ dash.avg_score !== null ? dash.avg_score.toFixed(1) : '-' }}</div>
          <div class="kpi-label">平均分</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#f56c6c">{{ dash.error_hotspots?.length || 0 }}</div>
          <div class="kpi-label">错题类型</div>
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab" class="main-tabs">
      <!-- Tab 1: 作业列表 -->
      <el-tab-pane label="作业列表" name="list">
        <div class="filter-bar">
          <el-select v-model="filters.status" placeholder="状态" clearable style="width:120px" @change="loadAssignments">
            <el-option label="进行中" value="published" />
            <el-option label="已关闭" value="closed" />
          </el-select>
          <el-select v-model="filters.homework_type" placeholder="类型" clearable style="width:130px" @change="loadAssignments">
            <el-option label="日常作业" value="daily" />
            <el-option label="周作业" value="weekly" />
            <el-option label="单元作业" value="unit" />
            <el-option label="假期作业" value="holiday" />
            <el-option label="项目作业" value="project" />
          </el-select>
          <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">发布作业</el-button>
          <el-button :icon="Refresh" @click="loadAssignments">刷新</el-button>
        </div>

        <el-table :data="assignments" v-loading="loading.assignments" stripe @row-click="openAssignmentDetail" style="width:100%">
          <el-table-column prop="title" label="作业标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="subject_name" label="学科" width="80" />
          <el-table-column prop="class_name" label="班级" width="100" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag :type="hwTypeTag(row.homework_type) as any" size="small">{{ hwTypeLabel(row.homework_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="提交/批改" width="120" align="center">
            <template #default="{ row }">
              <span>{{ row.graded_count }}/{{ row.submission_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'published' ? 'success' : 'info'" size="small">{{ row.status === 'published' ? '进行中' : '已关闭' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assigned_date" label="布置时间" width="160">
            <template #default="{ row }">{{ formatDate(row.assigned_date) }}</template>
          </el-table-column>
          <el-table-column prop="due_date" label="截止时间" width="160">
            <template #default="{ row }">{{ formatDate(row.due_date) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.status === 'published'" type="warning" size="small" link @click.stop="closeAssignment(row)">关闭</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="filters.page"
          :page-size="filters.page_size"
          :total="assignmentTotal"
          layout="total, prev, pager, next"
          style="margin-top:16px;justify-content:flex-end;display:flex"
          @current-change="loadAssignments"
        />
      </el-tab-pane>

      <!-- Tab 2: 批改工作台 -->
      <el-tab-pane label="批改工作台" name="grading">
        <div class="filter-bar">
          <el-select v-model="gradingAssignmentId" placeholder="选择作业" filterable style="width:300px" @change="loadSubmissions">
            <el-option v-for="a in assignments" :key="a.id" :label="`${a.title} (${a.class_name || '-'})`" :value="a.id" />
          </el-select>
          <el-button :icon="Refresh" @click="loadSubmissions">刷新</el-button>
        </div>

        <el-table :data="submissions" v-loading="loading.submissions" stripe style="width:100%">
          <el-table-column prop="student_name" label="学生" width="120" />
          <el-table-column prop="status" label="提交状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="subStatusTag(row.status) as any" size="small">{{ subStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="submitted_at" label="提交时间" width="160">
            <template #default="{ row }">{{ row.submitted_at ? formatDate(row.submitted_at) : '-' }}</template>
          </el-table-column>
          <el-table-column prop="late_minutes" label="迟交(分)" width="90" align="center">
            <template #default="{ row }">{{ row.late_minutes > 0 ? row.late_minutes : '-' }}</template>
          </el-table-column>
          <el-table-column label="批改状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.grading" type="success" size="small">{{ row.grading.score }}分</el-tag>
              <el-tag v-else type="warning" size="small">待批改</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center">
            <template #default="{ row }">
              <el-button type="primary" size="small" link @click="openGradeDrawer(row)">批改</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 3: 错题热点 -->
      <el-tab-pane label="错题热点" name="hotspots">
        <el-card shadow="never">
          <template #header><span>错题类型分布（来源：错题断层漏斗引擎）</span></template>
          <div v-if="dash.error_hotspots && dash.error_hotspots.length > 0">
            <div v-for="item in dash.error_hotspots" :key="item.error_type" class="hotspot-item">
              <span class="hotspot-label">{{ errorTypeLabel(item.error_type) }}</span>
              <el-progress :percentage="hotspotPercent(item.count)" :color="errorTypeColor(item.error_type)" :stroke-width="20" :text-inside="true" />
              <span class="hotspot-count">{{ item.count }} 题</span>
            </div>
          </div>
          <el-empty v-else description="暂无错题数据" />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 发布作业弹窗 -->
    <el-dialog v-model="showCreateDialog" title="发布作业" width="600px" @close="resetCreateForm">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="请输入作业标题" />
        </el-form-item>
        <el-form-item label="学科" required>
          <el-select v-model="createForm.subject_id" placeholder="选择学科" style="width:100%">
            <el-option label="语文" :value="1" />
            <el-option label="数学" :value="2" />
            <el-option label="英语" :value="3" />
            <el-option label="政治" :value="4" />
            <el-option label="历史" :value="5" />
            <el-option label="地理" :value="6" />
            <el-option label="生物" :value="7" />
            <el-option label="物理" :value="8" />
          </el-select>
        </el-form-item>
        <el-form-item label="班级">
          <el-input v-model.number="createForm.class_id" placeholder="班级ID（留空则全年级）" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="createForm.homework_type" style="width:100%">
            <el-option label="日常作业" value="daily" />
            <el-option label="周作业" value="weekly" />
            <el-option label="单元作业" value="unit" />
            <el-option label="假期作业" value="holiday" />
            <el-option label="项目作业" value="project" />
          </el-select>
        </el-form-item>
        <el-form-item label="布置时间" required>
          <el-date-picker v-model="createForm.assigned_date" type="datetime" placeholder="选择布置时间" style="width:100%" />
        </el-form-item>
        <el-form-item label="截止时间" required>
          <el-date-picker v-model="createForm.due_date" type="datetime" placeholder="选择截止时间" style="width:100%" />
        </el-form-item>
        <el-form-item label="总分">
          <el-input-number v-model="createForm.total_score" :min="1" :max="200" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="作业内容描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="loading.create" @click="handleCreate">发布</el-button>
      </template>
    </el-dialog>

    <!-- 作业详情抽屉 -->
    <el-drawer v-model="showDetailDrawer" :title="detailAssignment?.title || '作业详情'" size="50%">
      <template v-if="detailAssignment">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="学科">{{ detailAssignment.subject_name }}</el-descriptions-item>
          <el-descriptions-item label="班级">{{ detailAssignment.class_name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ hwTypeLabel(detailAssignment.homework_type) }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detailAssignment.status === 'published' ? '进行中' : '已关闭' }}</el-descriptions-item>
          <el-descriptions-item label="布置时间">{{ formatDate(detailAssignment.assigned_date) }}</el-descriptions-item>
          <el-descriptions-item label="截止时间">{{ formatDate(detailAssignment.due_date) }}</el-descriptions-item>
          <el-descriptions-item label="总分">{{ detailAssignment.total_score }}</el-descriptions-item>
          <el-descriptions-item label="提交/批改">{{ detailAssignment.graded_count }}/{{ detailAssignment.submission_count }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ detailAssignment.description || '-' }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>

    <!-- 批改抽屉 -->
    <el-drawer v-model="showGradeDrawer" title="批改作业" size="55%">
      <template v-if="gradeTarget">
        <el-descriptions :column="2" border style="margin-bottom:20px">
          <el-descriptions-item label="学生">{{ gradeTarget.student_name }}</el-descriptions-item>
          <el-descriptions-item label="提交状态">
            <el-tag :type="subStatusTag(gradeTarget.status) as any" size="small">{{ subStatusLabel(gradeTarget.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="提交内容" :span="2">{{ gradeTarget.content || '(无文字内容)' }}</el-descriptions-item>
        </el-descriptions>

        <el-form :model="gradeForm" label-width="80px">
          <el-form-item label="得分" required>
            <el-input-number v-model="gradeForm.score" :min="0" :max="gradeForm.max_score" :precision="1" />
            <span style="margin-left:8px;color:#909399">/ {{ gradeForm.max_score }} 分</span>
          </el-form-item>
          <el-form-item label="满分">
            <el-input-number v-model="gradeForm.max_score" :min="1" :max="200" />
          </el-form-item>
          <el-form-item label="评语">
            <el-input v-model="gradeForm.feedback" type="textarea" :rows="2" placeholder="教师评语" />
          </el-form-item>
        </el-form>

        <el-divider content-position="left">错题标记（自动同步至错题断层漏斗）</el-divider>

        <div v-for="(item, idx) in gradeForm.error_items" :key="idx" class="error-item-block">
          <div class="error-item-header">
            <span>错题 #{{ idx + 1 }}</span>
            <el-button type="danger" size="small" link @click="gradeForm.error_items.splice(idx, 1)">删除</el-button>
          </div>
          <el-form label-width="80px" size="small">
            <el-form-item label="题目内容">
              <el-input v-model="item.question_content" type="textarea" :rows="2" placeholder="错题内容" />
            </el-form-item>
            <el-form-item label="学生答案">
              <el-input v-model="item.student_answer" placeholder="学生作答" />
            </el-form-item>
            <el-form-item label="正确答案">
              <el-input v-model="item.correct_answer" placeholder="正确答案" />
            </el-form-item>
            <el-form-item label="错误类型">
              <el-select v-model="item.error_type" style="width:100%">
                <el-option label="概念性错误" value="conceptual" />
                <el-option label="程序性错误" value="procedural" />
                <el-option label="粗心错误" value="careless" />
                <el-option label="遗漏错误" value="omission" />
                <el-option label="未知错误" value="unknown" />
              </el-select>
            </el-form-item>
            <el-form-item label="难度">
              <el-select v-model="item.difficulty" style="width:100%" clearable>
                <el-option label="简单" value="easy" />
                <el-option label="中等" value="medium" />
                <el-option label="困难" value="hard" />
              </el-select>
            </el-form-item>
            <el-form-item label="知识点">
              <el-select v-model="item.knowledge_point_ids" multiple filterable style="width:100%" placeholder="关联知识点">
                <el-option v-for="kp in knowledgePoints" :key="kp.id" :label="kp.name" :value="kp.id" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>

        <el-button type="primary" plain :icon="Plus" style="width:100%;margin-top:8px" @click="addErrorItem">添加错题</el-button>

        <div style="margin-top:24px;text-align:right">
          <el-button @click="showGradeDrawer = false">取消</el-button>
          <el-button type="primary" :loading="loading.grade" @click="handleGrade">提交批改</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import * as hwApi from '@/api/homeworkMgmt'
import type { AssignmentResponse, SubmissionResponse, DashboardResponse } from '@/api/homeworkMgmt'
import * as efApi from '@/api/errorFunnel'
import type { KnowledgePointResponse } from '@/api/errorFunnel'

const userStore = useUserStore()
const isTeacher = computed(() => {
  const role = userStore.currentRole
  return role === 'MS_ADMIN' || role === 'GRADE_LEADER' || role === 'CLASS_TEACHER'
})

const activeTab = ref('list')

/* ── 看板 ── */
const dash = ref<DashboardResponse>({
  total_assignments: 0, active_assignments: 0, total_submissions: 0, pending_grading: 0,
  avg_score: null, avg_completion_rate: null, by_type: {}, recent_assignments: [], error_hotspots: [],
})

async function loadDashboard() {
  try {
    dash.value = await hwApi.getDashboard()
  } catch (e: any) {
    console.error('Dashboard load failed', e)
  }
}

/* ── 作业列表 ── */
const assignments = ref<AssignmentResponse[]>([])
const assignmentTotal = ref(0)
const loading = reactive({ assignments: false, submissions: false, create: false, grade: false })
const filters = reactive({
  status: '' as string, homework_type: '' as string,
  page: 1, page_size: 20,
})

async function loadAssignments() {
  loading.assignments = true
  try {
    const params: any = { page: filters.page, page_size: filters.page_size }
    if (filters.status) params.status = filters.status
    if (filters.homework_type) params.homework_type = filters.homework_type
    const res = await hwApi.listAssignments(params)
    assignments.value = res.items
    assignmentTotal.value = res.total
  } catch (e: any) {
    ElMessage.error('加载作业列表失败')
  } finally {
    loading.assignments = false
  }
}

/* ── 发布作业 ── */
const showCreateDialog = ref(false)
const createForm = reactive({
  title: '', subject_id: 2, class_id: null as number | null,
  homework_type: 'daily' as const, assigned_date: '', due_date: '',
  total_score: 100, description: '',
})

function resetCreateForm() {
  createForm.title = ''
  createForm.class_id = null
  createForm.homework_type = 'daily'
  createForm.assigned_date = ''
  createForm.due_date = ''
  createForm.total_score = 100
  createForm.description = ''
}

async function handleCreate() {
  if (!createForm.title || !createForm.assigned_date || !createForm.due_date) {
    ElMessage.warning('请填写标题、布置时间和截止时间')
    return
  }
  loading.create = true
  try {
    await hwApi.createAssignment({
      title: createForm.title,
      subject_id: createForm.subject_id,
      class_id: createForm.class_id || undefined,
      homework_type: createForm.homework_type,
      assigned_date: typeof createForm.assigned_date === 'string' ? createForm.assigned_date : new Date(createForm.assigned_date).toISOString(),
      due_date: typeof createForm.due_date === 'string' ? createForm.due_date : new Date(createForm.due_date).toISOString(),
      total_score: createForm.total_score,
      description: createForm.description || undefined,
    })
    ElMessage.success('作业发布成功')
    showCreateDialog.value = false
    resetCreateForm()
    await loadAssignments()
    await loadDashboard()
  } catch (e: any) {
    ElMessage.error('发布失败: ' + (e.message || '未知错误'))
  } finally {
    loading.create = false
  }
}

/* ── 关闭作业 ── */
async function closeAssignment(row: any) {
  try {
    await ElMessageBox.confirm(`确定关闭作业"${row.title}"吗？`, '确认', { type: 'warning' })
    await hwApi.closeAssignment(row.id)
    ElMessage.success('作业已关闭')
    await loadAssignments()
    await loadDashboard()
  } catch { /* cancelled */ }
}

/* ── 作业详情抽屉 ── */
const showDetailDrawer = ref(false)
const detailAssignment = ref<AssignmentResponse | null>(null)

async function openAssignmentDetail(row: any) {
  detailAssignment.value = row
  showDetailDrawer.value = true
}

/* ── 批改工作台 ── */
const gradingAssignmentId = ref<number | null>(null)
const submissions = ref<SubmissionResponse[]>([])

async function loadSubmissions() {
  if (!gradingAssignmentId.value) return
  loading.submissions = true
  try {
    const res = await hwApi.getSubmissions(gradingAssignmentId.value)
    submissions.value = res.items
  } catch (e: any) {
    ElMessage.error('加载提交列表失败')
  } finally {
    loading.submissions = false
  }
}

/* ── 批改抽屉 ── */
const showGradeDrawer = ref(false)
const gradeTarget = ref<SubmissionResponse | null>(null)
const gradeForm = reactive({
  score: 0, max_score: 100, feedback: '',
  error_items: [] as hwApi.ErrorItemPayload[],
})
const knowledgePoints = ref<KnowledgePointResponse[]>([])

async function openGradeDrawer(row: any) {
  gradeTarget.value = row
  gradeForm.score = row.grading?.score ?? 0
  gradeForm.max_score = row.grading?.max_score ?? 100
  gradeForm.feedback = row.grading?.feedback ?? ''
  gradeForm.error_items = []
  showGradeDrawer.value = true
  if (knowledgePoints.value.length === 0) {
    try { knowledgePoints.value = await efApi.listKnowledgePoints() } catch { /* ignore */ }
  }
}

function addErrorItem() {
  gradeForm.error_items.push({
    question_content: '', student_answer: '', correct_answer: '',
    error_type: 'conceptual', difficulty: 'medium', knowledge_point_ids: [],
  })
}

async function handleGrade() {
  if (!gradeTarget.value) return
  loading.grade = true
  try {
    await hwApi.gradeSubmission(gradeTarget.value.id, {
      score: gradeForm.score,
      max_score: gradeForm.max_score,
      feedback: gradeForm.feedback || undefined,
      error_items: gradeForm.error_items.length > 0 ? gradeForm.error_items : undefined,
    })
    ElMessage.success('批改成功，错题已同步至断层漏斗')
    showGradeDrawer.value = false
    await loadSubmissions()
    await loadDashboard()
  } catch (e: any) {
    ElMessage.error('批改失败: ' + (e.message || '未知错误'))
  } finally {
    loading.grade = false
  }
}

/* ── 工具函数 ── */
function formatDate(dt: string | null): string {
  if (!dt) return '-'
  return new Date(dt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const hwTypeLabel = hwApi.homeworkTypeLabel
const hwTypeTag = hwApi.homeworkTypeTag
const subStatusLabel = hwApi.submissionStatusLabel
const subStatusTag = hwApi.submissionStatusTag
const errorTypeLabel = (t: string) => hwApi.errorTypeLabel(t as any)
function errorTypeColor(t: string): string {
  const map: Record<string, string> = { conceptual: '#f56c6c', procedural: '#e6a23c', careless: '#909399', omission: '#e6a23c', unknown: '#909399' }
  return map[t] || '#909399'
}
function hotspotPercent(count: number): number {
  const total = dash.value.error_hotspots?.reduce((s, i) => s + i.count, 0) || 1
  return Math.round((count / total) * 100)
}

onMounted(() => {
  loadDashboard()
  loadAssignments()
})
</script>

<style scoped>
.homework-console { padding: 20px; }
.page-title { margin: 0 0 16px 0; font-size: 18px; font-weight: 500; color: #303133; }
.kpi-row { margin-bottom: 16px; }
.kpi-card { text-align: center; padding: 8px 0; }
.kpi-value { font-size: 28px; font-weight: 600; color: #409eff; line-height: 1.4; }
.kpi-label { font-size: 13px; color: #909399; }
.main-tabs { margin-top: 8px; }
.filter-bar { display: flex; gap: 12px; margin-bottom: 16px; align-items: center; }
.hotspot-item { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.hotspot-label { width: 100px; font-size: 13px; color: #606266; flex-shrink: 0; }
.hotspot-count { width: 60px; font-size: 13px; color: #909399; text-align: right; flex-shrink: 0; }
.error-item-block { border: 1px solid #ebeef5; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.error-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 13px; font-weight: 500; color: #303133; }
</style>
