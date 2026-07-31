<template>
  <div class="student-dashboard">
    <!-- 顶部操作 -->
    <div class="page-header">
      <h2 class="page-title">学籍管理</h2>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="showCreate">新建学籍</el-button>
        <el-upload
          :action="uploadUrl"
          :show-file-list="false"
          accept=".xlsx,.xls,.csv"
          :before-upload="handleImport"
          style="display: inline-block; margin-left: 8px"
        >
          <el-button :icon="Upload">批量导入</el-button>
        </el-upload>
        <el-button :icon="RefreshRight" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <div class="stat-card" :style="{ borderLeftColor: '#409eff' }">
          <div class="stat-label">在读学生</div>
          <div class="stat-value">{{ stats?.total_students || 0 }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" :style="{ borderLeftColor: '#67c23a' }">
          <div class="stat-label">原生数据</div>
          <div class="stat-value">{{ stats?.sync_summary?.native || 0 }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" :style="{ borderLeftColor: '#e6a23c' }">
          <div class="stat-label">遗留系统</div>
          <div class="stat-value">{{ stats?.sync_summary?.legacy || 0 }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" :style="{ borderLeftColor: '#909399' }">
          <div class="stat-label">批量导入</div>
          <div class="stat-value">{{ stats?.sync_summary?.imported || 0 }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filterKeyword"
        placeholder="搜索姓名/学号..."
        :prefix-icon="Search"
        clearable
        style="width: 240px"
        @input="debouncedSearch"
      />
      <el-select v-model="filterGradeId" placeholder="全部年级" clearable style="width: 140px; margin-left: 8px" @change="loadList">
        <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-select v-model="filterClassId" placeholder="全部班级" clearable style="width: 140px; margin-left: 8px" @change="loadList">
        <el-option v-for="c in allClasses" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 120px; margin-left: 8px" @change="loadList">
        <el-option label="在读" value="active" />
        <el-option label="休学" value="suspended" />
        <el-option label="已转学" value="transferred" />
        <el-option label="已毕业" value="graduated" />
        <el-option label="已离校" value="inactive" />
      </el-select>
    </div>

    <!-- 学生表格 -->
    <el-card shadow="hover" class="table-card">
      <el-table
        :data="students"
        border stripe
        v-loading="loading"
        @row-click="(row: any) => goDetail(row)"
        style="cursor: pointer"
      >
        <el-table-column type="index" width="50" label="#" />
        <el-table-column prop="student_no" label="学号" width="110" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="class_name" label="班级" width="90" />
        <el-table-column prop="grade_name" label="年级" width="80" />
        <el-table-column label="性别" width="60">
          <template #default="{ row }">{{ row.gender === 'M' ? '男' : row.gender === 'F' ? '女' : '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              :type="statusTagType(row.registry_status)"
              size="small"
            >
              {{ REGISTRY_STATUS_LABELS[row.registry_status as keyof typeof REGISTRY_STATUS_LABELS] || row.registry_status || '在读' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" width="90">
          <template #default="{ row }">
            <el-tag :type="syncTagType(row.sync_status)" size="small" effect="plain">
              {{ SYNC_STATUS_LABELS[row.sync_status as keyof typeof SYNC_STATUS_LABELS] || '原生' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enrolled_at" label="入学日期" width="110">
          <template #default="{ row }">{{ row.enrolled_at || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click.stop="goDetail(row)">详情</el-button>
            <el-button
              v-if="row.registry_status === 'active'"
              size="small" type="warning" link
              @click.stop="quickSuspend(row)"
            >休学</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 16px; text-align: right">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadList"
        />
      </div>
    </el-card>

    <!-- 新建学籍弹窗 -->
    <el-dialog v-model="createVisible" title="新建学籍" width="620px" destroy-on-close>
      <el-form :model="createForm" label-width="100px" :rules="createRules">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="姓名" required><el-input v-model="createForm.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="性别">
              <el-radio-group v-model="createForm.gender">
                <el-radio value="M">男</el-radio>
                <el-radio value="F">女</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="年级" required>
              <el-select v-model="createForm.grade_id" style="width: 100%" @change="onGradeChange">
                <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="班级" required>
              <el-select v-model="createForm.class_id" style="width: 100%">
                <el-option v-for="c in createClassOptions" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="出生日期"><el-date-picker v-model="createForm.birth_date" type="date" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="身份证号"><el-input v-model="createForm.id_card" maxlength="18" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="民族"><el-input v-model="createForm.nationality" placeholder="如: 汉族" /></el-form-item>
        <el-form-item label="家庭地址"><el-input v-model="createForm.address" /></el-form-item>
        <el-divider content-position="left">家长信息</el-divider>
        <el-row :gutter="16">
          <el-col :span="8"><el-input v-model="createForm.parent1_name" placeholder="家长1姓名" /></el-col>
          <el-col :span="8"><el-input v-model="createForm.parent1_phone" placeholder="电话" /></el-col>
          <el-col :span="8"><el-input v-model="createForm.parent1_relation" placeholder="关系" /></el-col>
        </el-row>
        <el-row :gutter="16" style="margin-top: 8px">
          <el-col :span="8"><el-input v-model="createForm.parent2_name" placeholder="家长2姓名" /></el-col>
          <el-col :span="8"><el-input v-model="createForm.parent2_phone" placeholder="电话" /></el-col>
          <el-col :span="8"><el-input v-model="createForm.parent2_relation" placeholder="关系" /></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建学籍</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Upload, RefreshRight, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getGrades, getClasses } from '@/api/classes'
import {
  listStudents, createStudent, suspendStudent, getRegistryStats,
  REGISTRY_STATUS_LABELS, SYNC_STATUS_LABELS,
  type StudentDetail, type RegistryStats,
} from '@/api/students'

const router = useRouter()

// ── 状态 ──
const loading = ref(false)
const students = ref<StudentDetail[]>([])
const stats = ref<RegistryStats | null>(null)
const grades = ref<Array<{ id: number; name: string }>>([])
const allClasses = ref<Array<{ id: number; name: string; grade_id: number }>>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)

const filterKeyword = ref('')
const filterGradeId = ref('')
const filterClassId = ref('')
const filterStatus = ref('')

let searchTimer: ReturnType<typeof setTimeout> | null = null

// 新建
const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({
  name: '', gender: '', grade_id: 0, class_id: 0,
  birth_date: null as any, id_card: '', nationality: '', address: '',
  parent1_name: '', parent1_phone: '', parent1_relation: '',
  parent2_name: '', parent2_phone: '', parent2_relation: '',
})
const createRules = {}

const createClassOptions = computed(() => {
  if (!createForm.value.grade_id) return []
  return allClasses.value.filter(c => c.grade_id === createForm.value.grade_id)
})

// ── 标签 ──
function statusTagType(status?: string): 'success' | 'warning' | 'info' | 'danger' | undefined {
  const m: Record<string, 'success' | 'warning' | 'info' | 'danger' | undefined> = { active: 'success', suspended: 'warning', transferred: 'info', graduated: undefined, inactive: 'danger' }
  return m[status || 'active'] || 'info'
}
function syncTagType(status?: string): 'success' | 'warning' | 'info' | undefined {
  const m: Record<string, 'success' | 'warning' | 'info' | undefined> = { native: 'success', legacy: 'warning', imported: 'info' }
  return m[status || 'native'] || undefined
}

// ── 搜索 ──
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadList() }, 300)
}

// ── 加载 ──
async function loadAll() {
  loading.value = true
  try {
    const [gRes, cRes, sRes] = await Promise.all([
      getGrades().catch(() => ({ data: [] })),
      getClasses().catch(() => ({ data: [] })),
      getRegistryStats().catch(() => null),
    ])
    grades.value = (gRes as any)?.data || gRes || []
    allClasses.value = (cRes as any)?.data || cRes || []
    stats.value = sRes ? (sRes as RegistryStats) : null
    await loadList()
  } catch (e) {
    console.error('Load student dashboard error:', e)
  } finally {
    loading.value = false
  }
}

async function loadList() {
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (filterKeyword.value) params.keyword = filterKeyword.value
    if (filterGradeId.value) params.grade_id = filterGradeId.value
    if (filterClassId.value) params.class_id = filterClassId.value
    if (filterStatus.value) params.status = filterStatus.value
    const res = await listStudents(params)
    students.value = (res as any)?.items || []
    total.value = (res as any)?.total || 0
  } catch (e) {
    console.error('Load students error:', e)
  }
}

// ── 导航 ──
function goDetail(row: any) {
  router.push({ path: '/student-registry/detail', query: { id: String(row.id) } })
}

// ── 新建 ──
function showCreate() { createVisible.value = true }
function onGradeChange() { createForm.value.class_id = 0 }

async function doCreate() {
  if (!createForm.value.name || !createForm.value.grade_id || !createForm.value.class_id) {
    ElMessage.warning('请填写姓名、年级和班级')
    return
  }
  creating.value = true
  try {
    const body: any = { ...createForm.value }
    if (body.birth_date) body.birth_date = new Date(body.birth_date).toISOString().slice(0, 10)
    else delete body.birth_date
    await createStudent(body)
    ElMessage.success('学籍创建成功')
    createVisible.value = false
    loadAll()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

// ── 快速休学 ──
async function quickSuspend(row: any) {
  try {
    const { value: reason } = await ElMessageBox.prompt('休学原因', '确认休学', { inputType: 'textarea' })
    await suspendStudent(row.id, { change_type: 'suspend', reason: reason || '' })
    ElMessage.success(`${row.name} 已标记休学`)
    loadList()
  } catch {}
}

// ── 导入 ──
const uploadUrl = '/api/v1/student-registry/students/batch-import'
async function handleImport(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const { batchImportStudents } = await import('@/api/students')
    const res = await batchImportStudents(formData)
    const result = res as any
    ElMessage.success(`导入完成: 成功 ${result.success}, 失败 ${result.failed}`)
    loadAll()
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  }
  return false // 阻止默认上传
}

onMounted(loadAll)
</script>

<style scoped>
.student-dashboard {
  padding: 20px;
  color: #c9d1d9;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title { font-size: 20px; font-weight: 700; color: #f0f6fc; margin: 0; }
.header-actions { display: flex; gap: 8px; }

.stats-row { margin-bottom: 16px; }
.stat-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-left: 4px solid;
  border-radius: 8px;
  padding: 16px 20px;
  transition: transform 0.2s;
}
.stat-card:hover { transform: translateY(-2px); }
.stat-label { font-size: 13px; color: #8b949e; }
.stat-value { font-size: 24px; font-weight: 700; color: #f0f6fc; }

.filter-bar {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
}

.table-card {
  background: #161b22 !important;
  border: 1px solid #30363d !important;
}
</style>
