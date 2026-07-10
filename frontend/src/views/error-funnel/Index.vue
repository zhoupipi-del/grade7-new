<template>
  <div class="error-funnel-console">
    <h2 class="page-title">错题断层漏斗</h2>

    <el-row :gutter="16" class="kpi-row">
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ dash.total_errors }}</div>
          <div class="kpi-label">错题总数</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#e6a23c">{{ dash.unresolved_errors }}</div>
          <div class="kpi-label">未解决</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ dash.total_gaps }}</div>
          <div class="kpi-label">断层总数</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#f56c6c">{{ dash.critical_gaps }}</div>
          <div class="kpi-label">临界</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#e6a23c">{{ dash.warning_gaps }}</div>
          <div class="kpi-label">预警</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#909399">{{ dash.watch_gaps }}</div>
          <div class="kpi-label">关注</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#67c23a">{{ dash.resolved_gaps }}</div>
          <div class="kpi-label">已解决</div>
        </el-card>
      </el-col>
      <el-col :span="3">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value" style="color:#409eff">{{ dash.ai_prescriptions_generated }}</div>
          <div class="kpi-label">AI处方</div>
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab" class="main-tabs">
      <!-- Tab 1: 漏斗看板 -->
      <el-tab-pane label="漏斗看板" name="dashboard">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><span>错题类型分布</span></template>
              <div v-if="Object.keys(dash.error_type_distribution).length > 0">
                <div v-for="(count, type) in dash.error_type_distribution" :key="type" class="dist-item">
                  <span class="dist-label">{{ errorTypeLabel(type as any) }}</span>
                  <el-progress :percentage="distPercent(count as number)" :color="errorTypeColor(type as string)" :stroke-width="18" :text-inside="true" />
                  <span class="dist-count">{{ count }} 题</span>
                </div>
              </div>
              <el-empty v-else description="暂无数据" :image-size="60" />
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><span>知识点错题热力 TOP</span></template>
              <div v-if="dash.top_error_knowledge_points.length > 0">
                <div v-for="(kp, idx) in dash.top_error_knowledge_points" :key="idx" class="kp-hot-item">
                  <span class="kp-rank">{{ idx + 1 }}</span>
                  <span class="kp-name">{{ kp.name }}</span>
                  <el-tag type="danger" size="small">{{ kp.error_count }}错</el-tag>
                </div>
              </div>
              <el-empty v-else description="暂无数据" :image-size="60" />
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never" style="margin-top:16px">
          <template #header><span>最近错题</span></template>
          <el-table :data="dash.recent_errors" stripe size="small" style="width:100%">
            <el-table-column prop="student_id" label="学生ID" width="80" />
            <el-table-column prop="question_content" label="题目内容" min-width="200" show-overflow-tooltip />
            <el-table-column label="错误类型" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="errorTypeTag(row.error_type) as any" size="small">{{ errorTypeLabel(row.error_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source_desc" label="来源" min-width="150" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="140">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- Tab 2: 错题本 -->
      <el-tab-pane label="错题本" name="errors">
        <div class="filter-bar">
          <el-select v-model="errFilters.error_type" placeholder="错误类型" clearable style="width:140px" @change="loadErrors">
            <el-option label="概念性错误" value="conceptual" />
            <el-option label="程序性错误" value="procedural" />
            <el-option label="粗心错误" value="careless" />
            <el-option label="遗漏错误" value="omission" />
          </el-select>
          <el-select v-model="errFilters.source_type" placeholder="来源" clearable style="width:120px" @change="loadErrors">
            <el-option label="作业" value="homework" />
            <el-option label="考试" value="exam" />
            <el-option label="手动" value="manual" />
          </el-select>
          <el-select v-model="errFilters.is_resolved" placeholder="状态" clearable style="width:100px" @change="loadErrors">
            <el-option label="未解决" :value="false" />
            <el-option label="已解决" :value="true" />
          </el-select>
          <el-button :icon="Refresh" @click="loadErrors">刷新</el-button>
        </div>

        <el-table :data="errors" v-loading="loading.errors" stripe style="width:100%">
          <el-table-column prop="student_name" label="学生" width="100" />
          <el-table-column prop="subject_name" label="学科" width="70" />
          <el-table-column prop="question_content" label="题目内容" min-width="200" show-overflow-tooltip />
          <el-table-column label="错误类型" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="errorTypeTag(row.error_type) as any" size="small">{{ errorTypeLabel(row.error_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="sourceTypeTag(row.source_type) as any" size="small">{{ sourceTypeLabel(row.source_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="知识点" min-width="120">
            <template #default="{ row }">
              <span v-if="row.knowledge_point_names">{{ row.knowledge_point_names.join(', ') }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="难度" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.difficulty" :type="difficultyTag(row.difficulty) as any" size="small">{{ difficultyLabel(row.difficulty) }}</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_resolved ? 'success' : 'warning'" size="small">{{ row.is_resolved ? '已解决' : '未解决' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="140">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!row.is_resolved" type="success" size="small" link @click="resolveError(row)">解决</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="errFilters.page"
          :page-size="errFilters.page_size"
          :total="errorTotal"
          layout="total, prev, pager, next"
          style="margin-top:16px;justify-content:flex-end;display:flex"
          @current-change="loadErrors"
        />
      </el-tab-pane>

      <!-- Tab 3: 断层雷达 -->
      <el-tab-pane label="断层雷达" name="gaps">
        <div class="filter-bar">
          <el-select v-model="gapFilters.gap_level" placeholder="断层等级" clearable style="width:120px" @change="loadGaps">
            <el-option label="关注" value="watch" />
            <el-option label="预警" value="warning" />
            <el-option label="临界" value="critical" />
          </el-select>
          <el-select v-model="gapFilters.gap_status" placeholder="状态" clearable style="width:100px" @change="loadGaps">
            <el-option label="活跃" value="active" />
            <el-option label="已解决" value="resolved" />
          </el-select>
          <el-button :icon="Refresh" @click="loadGaps">刷新</el-button>
        </div>

        <el-table :data="gaps" v-loading="loading.gaps" stripe style="width:100%" @row-click="openGapDetail">
          <el-table-column prop="student_name" label="学生" width="100" />
          <el-table-column prop="subject_name" label="学科" width="70" />
          <el-table-column prop="knowledge_point_name" label="知识点" min-width="150" show-overflow-tooltip />
          <el-table-column label="断层等级" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="gapLevelTag(row.gap_level) as any" size="small" :effect="row.gap_level === 'critical' ? 'dark' : 'light'">
                {{ gapLevelLabel(row.gap_level) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error_count" label="错题数" width="80" align="center" />
          <el-table-column prop="consecutive_errors" label="连续错题" width="90" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.consecutive_errors >= 3 ? '#f56c6c' : row.consecutive_errors >= 2 ? '#e6a23c' : '#909399', fontWeight: row.consecutive_errors >= 2 ? 600 : 400 }">
                {{ row.consecutive_errors }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.gap_status === 'active' ? 'danger' : 'success'" size="small">{{ gapStatusLabel(row.gap_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="AI处方" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.ai_prescription" type="success" size="small">已生成</el-tag>
              <el-tag v-else type="info" size="small">-</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" width="140">
            <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="center" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" link @click.stop="generatePrescription(row)" :loading="loading.prescription === row.id">
                {{ row.ai_prescription ? '重新生成' : 'AI处方' }}
              </el-button>
              <el-button v-if="row.gap_status === 'active'" type="success" size="small" link @click.stop="resolveGap(row)">解决</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="gapFilters.page"
          :page-size="gapFilters.page_size"
          :total="gapTotal"
          layout="total, prev, pager, next"
          style="margin-top:16px;justify-content:flex-end;display:flex"
          @current-change="loadGaps"
        />
      </el-tab-pane>

      <!-- Tab 4: 知识点管理 -->
      <el-tab-pane label="知识点管理" name="knowledge">
        <div class="filter-bar">
          <el-button type="primary" :icon="Plus" @click="showKpDialog = true">新增知识点</el-button>
          <el-button :icon="Refresh" @click="loadKnowledgePoints">刷新</el-button>
        </div>

        <el-table :data="knowledgePoints" v-loading="loading.kp" stripe style="width:100%">
          <el-table-column prop="name" label="知识点名称" min-width="180" />
          <el-table-column prop="code" label="编码" width="120" />
          <el-table-column prop="subject_name" label="学科" width="80" />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="sort_order" label="排序" width="60" align="center" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 断层详情 + AI处方抽屉 -->
    <el-drawer v-model="showGapDrawer" title="断层详情" size="55%">
      <template v-if="detailGap">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="学生">{{ detailGap.student_name }}</el-descriptions-item>
          <el-descriptions-item label="学科">{{ detailGap.subject_name }}</el-descriptions-item>
          <el-descriptions-item label="知识点">{{ detailGap.knowledge_point_name }}</el-descriptions-item>
          <el-descriptions-item label="断层等级">
            <el-tag :type="gapLevelTag(detailGap.gap_level) as any" size="small">{{ gapLevelLabel(detailGap.gap_level) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="错题总数">{{ detailGap.error_count }}</el-descriptions-item>
          <el-descriptions-item label="连续错题">{{ detailGap.consecutive_errors }}</el-descriptions-item>
          <el-descriptions-item label="最近错题来源" :span="2">{{ detailGap.last_error_source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="最近错题时间" :span="2">{{ formatDate(detailGap.last_error_date) }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">AI 处方</el-divider>

        <template v-if="detailGap.ai_prescription">
          <el-alert type="success" :closable="false" style="margin-bottom:16px">
            <template #title>
              <span>AI处方已生成 ({{ formatDate(detailGap.ai_prescription_generated_at) }})</span>
            </template>
          </el-alert>
          <div class="prescription-content" v-html="formatPrescription(detailGap.ai_prescription)"></div>
        </template>
        <template v-else>
          <el-empty description="暂无AI处方，点击下方按钮生成" :image-size="80">
            <el-button type="primary" :loading="loading.prescription === detailGap.id" @click="generatePrescription(detailGap)">
              生成AI处方
            </el-button>
          </el-empty>
        </template>
      </template>
    </el-drawer>

    <!-- 新增知识点弹窗 -->
    <el-dialog v-model="showKpDialog" title="新增知识点" width="500px" @close="resetKpForm">
      <el-form :model="kpForm" label-width="80px">
        <el-form-item label="学科" required>
          <el-select v-model="kpForm.subject_id" placeholder="选择学科" style="width:100%">
            <el-option label="语文" :value="1" />
            <el-option label="数学" :value="2" />
            <el-option label="英语" :value="3" />
            <el-option label="物理" :value="8" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="kpForm.name" placeholder="知识点名称" />
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="kpForm.code" placeholder="知识点编码（可选）" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="kpForm.description" type="textarea" :rows="2" placeholder="知识点描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showKpDialog = false">取消</el-button>
        <el-button type="primary" :loading="loading.createKp" @click="handleCreateKp">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import * as efApi from '@/api/errorFunnel'
import type {
  DashboardResponse, ErrorItemResponse, KnowledgeGapResponse, KnowledgePointResponse,
} from '@/api/errorFunnel'

const activeTab = ref('dashboard')

/* ── 看板 ── */
const dash = ref<DashboardResponse>({
  total_errors: 0, unresolved_errors: 0, total_gaps: 0, critical_gaps: 0,
  warning_gaps: 0, watch_gaps: 0, resolved_gaps: 0, ai_prescriptions_generated: 0,
  top_error_knowledge_points: [], top_error_students: [], error_type_distribution: {}, recent_errors: [],
})

async function loadDashboard() {
  try { dash.value = await efApi.getDashboard() } catch { /* ignore */ }
}

/* ── 错题本 ── */
const errors = ref<ErrorItemResponse[]>([])
const errorTotal = ref(0)
const loading = reactive({ errors: false, gaps: false, kp: false, prescription: null as number | null, createKp: false })
const errFilters = reactive({
  error_type: '' as string, source_type: '' as string, is_resolved: null as boolean | null,
  page: 1, page_size: 20,
})

async function loadErrors() {
  loading.errors = true
  try {
    const params: any = { page: errFilters.page, page_size: errFilters.page_size }
    if (errFilters.error_type) params.error_type = errFilters.error_type
    if (errFilters.source_type) params.source_type = errFilters.source_type
    if (errFilters.is_resolved !== null) params.is_resolved = errFilters.is_resolved
    const res = await efApi.listErrors(params)
    errors.value = res.items
    errorTotal.value = res.total
  } catch { ElMessage.error('加载错题列表失败') }
  finally { loading.errors = false }
}

async function resolveError(row: any) {
  try {
    await efApi.resolveError(row.id)
    ElMessage.success('已标记为已解决')
    await loadErrors()
    await loadDashboard()
  } catch { ElMessage.error('操作失败') }
}

/* ── 断层雷达 ── */
const gaps = ref<KnowledgeGapResponse[]>([])
const gapTotal = ref(0)
const gapFilters = reactive({
  gap_level: '' as string, gap_status: '' as string,
  page: 1, page_size: 20,
})

async function loadGaps() {
  loading.gaps = true
  try {
    const params: any = { page: gapFilters.page, page_size: gapFilters.page_size }
    if (gapFilters.gap_level) params.gap_level = gapFilters.gap_level
    if (gapFilters.gap_status) params.gap_status = gapFilters.gap_status
    const res = await efApi.listGaps(params)
    gaps.value = res.items
    gapTotal.value = res.total
  } catch { ElMessage.error('加载断层列表失败') }
  finally { loading.gaps = false }
}

/* ── 断层详情抽屉 ── */
const showGapDrawer = ref(false)
const detailGap = ref<KnowledgeGapResponse | null>(null)

function openGapDetail(row: any) {
  detailGap.value = row
  showGapDrawer.value = true
}

/* ── AI处方生成 ── */
async function generatePrescription(row: any) {
  loading.prescription = row.id
  try {
    const res = await efApi.generatePrescription(row.id)
    ElMessage.success('AI处方生成成功')
    if (detailGap.value && detailGap.value.id === row.id) {
      detailGap.value.ai_prescription = JSON.stringify(res.prescription)
      detailGap.value.ai_prescription_generated_at = res.generated_at
    }
    row.ai_prescription = JSON.stringify(res.prescription)
    row.ai_prescription_generated_at = res.generated_at
    await loadDashboard()
  } catch (e: any) {
    ElMessage.error('AI处方生成失败: ' + (e.message || '请稍后重试'))
  } finally {
    loading.prescription = null
  }
}

/* ── 解决断层 ── */
async function resolveGap(row: any) {
  try {
    await ElMessageBox.confirm('确定标记该断层为已解决吗？', '确认', { type: 'warning' })
    await efApi.resolveGap(row.id)
    ElMessage.success('断层已标记为已解决')
    await loadGaps()
    await loadDashboard()
  } catch { /* cancelled */ }
}

/* ── 知识点管理 ── */
const knowledgePoints = ref<KnowledgePointResponse[]>([])
const showKpDialog = ref(false)
const kpForm = reactive({ subject_id: 2, name: '', code: '', description: '' })

async function loadKnowledgePoints() {
  loading.kp = true
  try { knowledgePoints.value = await efApi.listKnowledgePoints() }
  catch { ElMessage.error('加载知识点失败') }
  finally { loading.kp = false }
}

function resetKpForm() { kpForm.name = ''; kpForm.code = ''; kpForm.description = '' }

async function handleCreateKp() {
  if (!kpForm.name) { ElMessage.warning('请填写知识点名称'); return }
  loading.createKp = true
  try {
    await efApi.createKnowledgePoint({
      subject_id: kpForm.subject_id, name: kpForm.name,
      code: kpForm.code || undefined, description: kpForm.description || undefined,
    })
    ElMessage.success('知识点创建成功')
    showKpDialog.value = false
    resetKpForm()
    await loadKnowledgePoints()
  } catch { ElMessage.error('创建失败') }
  finally { loading.createKp = false }
}

/* ── 工具函数 ── */
function formatDate(dt: string | null): string {
  if (!dt) return '-'
  return new Date(dt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const gapLevelLabel = efApi.gapLevelLabel
const gapLevelTag = efApi.gapLevelTag
const gapStatusLabel = efApi.gapStatusLabel
const errorTypeLabel = efApi.errorTypeLabel
const errorTypeTag = efApi.errorTypeTag
const sourceTypeLabel = efApi.sourceTypeLabel
const sourceTypeTag = efApi.sourceTypeTag
const difficultyLabel = efApi.difficultyLabel
const difficultyTag = efApi.difficultyTag

function errorTypeColor(t: string): string {
  const map: Record<string, string> = { conceptual: '#f56c6c', procedural: '#e6a23c', careless: '#909399', omission: '#e6a23c', unknown: '#909399' }
  return map[t] || '#909399'
}
function distPercent(count: number): number {
  const total = Object.values(dash.value.error_type_distribution).reduce((s, v) => s + (v as number), 0) || 1
  return Math.round((count / total) * 100)
}
function formatPrescription(raw: string | null): string {
  if (!raw) return ''
  try {
    const obj = JSON.parse(raw)
    let html = ''
    if (obj.weakness_analysis) {
      html += `<div style="margin-bottom:16px"><div style="font-weight:600;color:#f56c6c;margin-bottom:8px">薄弱点分析</div><div style="line-height:1.8;color:#606266">${obj.weakness_analysis}</div></div>`
    }
    if (obj.action_prescription) {
      const lines = obj.action_prescription.split('\n').map((l: string) => `<p style="margin:4px 0">${l}</p>`).join('')
      html += `<div><div style="font-weight:600;color:#67c23a;margin-bottom:8px">行动处方</div><div style="line-height:1.8;color:#606266">${lines}</div></div>`
    }
    return html
  } catch {
    return `<div style="white-space:pre-wrap">${raw}</div>`
  }
}

onMounted(() => {
  loadDashboard()
  loadErrors()
  loadGaps()
  loadKnowledgePoints()
})
</script>

<style scoped>
.error-funnel-console { padding: 20px; }
.page-title { margin: 0 0 16px 0; font-size: 18px; font-weight: 500; color: #303133; }
.kpi-row { margin-bottom: 16px; }
.kpi-card { text-align: center; padding: 8px 0; }
.kpi-value { font-size: 26px; font-weight: 600; color: #409eff; line-height: 1.4; }
.kpi-label { font-size: 12px; color: #909399; }
.main-tabs { margin-top: 8px; }
.filter-bar { display: flex; gap: 12px; margin-bottom: 16px; align-items: center; }
.dist-item { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.dist-label { width: 100px; font-size: 13px; color: #606266; flex-shrink: 0; }
.dist-count { width: 50px; font-size: 13px; color: #909399; text-align: right; flex-shrink: 0; }
.kp-hot-item { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.kp-rank { width: 24px; height: 24px; border-radius: 50%; background: #f56c6c; color: #fff; font-size: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kp-name { flex: 1; font-size: 13px; color: #303133; }
.prescription-content { padding: 0 4px; }
</style>
