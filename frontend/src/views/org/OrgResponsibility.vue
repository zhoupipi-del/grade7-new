<template>
  <div class="org-responsibility">
    <!-- ════════════════════════════════════════ -->
    <!-- 组织与责任配置（V1）                     -->
    <!-- ════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><UserFilled /></el-icon>
          组织与责任配置
        </h2>
        <span class="page-subtitle">年级组长 · 班主任 · 任课教师 · 心理负责人（Assignment 唯一责任事实源，缺谁显示「未配置」绝不补假数据）</span>
      </div>
      <div class="header-right">
        <el-tag type="danger" effect="plain" size="small">冲突</el-tag>
        <el-tag type="warning" effect="plain" size="small">缺失</el-tag>
        <el-button type="primary" size="small" @click="openCreate">
          <el-icon><Plus /></el-icon> 新增岗位
        </el-button>
      </div>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- 责任覆盖概览：缺谁显示「未配置」绝不补假数据 -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="overview-card">
      <template #header><span class="overview-title">责任覆盖概览（缺谁显示「未配置」，绝不补假数据）</span></template>
      <div class="overview-grid">
        <div class="ov-item">
          <div class="ov-label">年级组长</div>
          <div class="ov-body">
            <el-tag v-for="g in gradeLeaderCoverage" :key="g.id" size="small"
              :type="g.configured ? 'success' : 'warning'" effect="plain">
              {{ g.name }}{{ g.configured ? ' ✓' : ' · 未配置' }}
            </el-tag>
            <span v-if="!gradeLeaderCoverage.length" class="ov-empty">暂无年级数据</span>
          </div>
        </div>
        <div class="ov-item">
          <div class="ov-label">班主任</div>
          <div class="ov-body">
            <el-tag size="small" :type="missingClasses.length ? 'warning' : 'success'" effect="plain">
              {{ classes.length - missingClasses.length }}/{{ classes.length }} 班已配{{ missingClasses.length ? ' · 缺 ' + missingClasses.length + ' 班' : ' ✓' }}
            </el-tag>
          </div>
        </div>
        <div class="ov-item">
          <div class="ov-label">心理负责人</div>
          <div class="ov-body">
            <el-tag size="small" :type="psychConfigured ? 'success' : 'warning'" effect="plain">
              {{ psychConfigured ? '已配置 ✓' : '未配置' }}
            </el-tag>
          </div>
        </div>
        <div class="ov-item">
          <div class="ov-label">任课教师</div>
          <div class="ov-body">
            <el-tag size="small" type="info" effect="plain">已配置 {{ subjectCount }} 条</el-tag>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- 缺失提示：无班主任的班级                 -->
    <!-- ════════════════════════════════════════ -->
    <el-alert
      v-if="missingClasses.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="missing-alert"
      :title="`${missingClasses.length} 个班级缺少班主任 Assignment（不猜人，待真实名单补齐）`"
    >
      <template #default>
        <el-tag v-for="c in missingClasses" :key="c.id" size="small" effect="plain" class="missing-tag">
          {{ c.name }}
        </el-tag>
      </template>
    </el-alert>

    <!-- ════════════════════════════════════════ -->
    <!-- 岗位分配列表                             -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="list-card">
      <el-table :data="assignments" v-loading="loading" style="width: 100%" size="default" stripe>
        <el-table-column prop="teacher_name" label="教师" width="140">
          <template #default="{ row }">
            <span class="teacher-name">{{ row.teacher_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="role_type" label="岗位" width="140">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role_type)" size="small">
              {{ roleLabel(row.role_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="scope_name" label="作用域" width="130">
          <template #default="{ row }">
            {{ row.scope_name }} <span class="scope-sub">({{ row.scope_type }}{{ row.scope_id ?? '' }})</span>
          </template>
        </el-table-column>
        <el-table-column prop="assigned_at" label="生效时间" width="170">
          <template #default="{ row }">
            {{ fmtTime(row.assigned_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '生效' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="冲突/备注" min-width="150">
          <template #default="{ row }">
            <el-tag v-if="row.conflict" type="danger" size="small" effect="dark">冲突</el-tag>
            <span v-if="row.notes" class="notes-text">{{ row.notes }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button
              :type="row.is_active ? 'warning' : 'success'"
              size="small" text
              @click="toggle(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button type="danger" size="small" text @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!assignments.length && !loading" description="暂无岗位分配" :image-size="60" />
    </el-card>

    <!-- 新增岗位对话框 -->
    <el-dialog v-model="createVisible" title="新增岗位分配" width="480px">
      <el-form :model="createForm" label-width="90px">
        <el-form-item label="教师" required>
          <el-select v-model="createForm.teacher_user_id" filterable placeholder="选择教师" style="width: 100%">
            <el-option
              v-for="t in teachers"
              :key="t.id"
              :label="`${t.username} (${t.real_name || t.display_name || ''})`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="岗位" required>
          <el-select v-model="createForm.role_type" placeholder="选择岗位" style="width: 100%">
            <el-option label="班主任" value="homeroom_teacher" />
            <el-option label="年级组长" value="grade_leader" />
            <el-option label="任课教师" value="subject_teacher" />
            <el-option label="心理负责人" value="counselor" />
            <el-option label="德育主任" value="moral_admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="作用域" required>
          <el-select v-model="createForm.scope_type" placeholder="类型" style="width: 120px; margin-right: 8px">
            <el-option label="班级" value="class" />
            <el-option label="年级" value="grade" />
            <el-option label="学校" value="school" />
          </el-select>
          <el-select
            v-if="createForm.scope_type === 'class'"
            v-model="createForm.scope_id"
            placeholder="选择班级"
            filterable
            style="width: 180px"
          >
            <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <el-select
            v-else-if="createForm.scope_type === 'grade'"
            v-model="createForm.scope_id"
            placeholder="选择年级"
            style="width: 180px"
          >
            <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.notes" placeholder="可选" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * OrgResponsibility.vue — 组织与责任配置页 V1（2026-08-13）
 *
 * 第一版只维护：年级组长/班主任/任课教师/学科班级 Assignment/生效时间/状态/冲突缺失提示。
 * 不做"大而全组织后台"；Assignment 是唯一责任事实源（Resolver 消费）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, UserFilled } from '@element-plus/icons-vue'
import request from '@/api/request'
import { getClasses, getGrades } from '@/api/classes'
import { listTeachers } from '@/api/teachers'

interface Assignment {
  id: number
  teacher_user_id: number
  teacher_name: string
  role_type: string
  scope_type: string
  scope_id: number | null
  scope_name: string
  is_active: boolean
  assigned_at: string | null
  notes: string | null
  conflict: boolean
}

const loading = ref(false)
const creating = ref(false)
const assignments = ref<Assignment[]>([])
const teachers = ref<any[]>([])
const classes = ref<any[]>([])
const grades = ref<any[]>([])
const createVisible = ref(false)

const createForm = ref({
  teacher_user_id: undefined as number | undefined,
  role_type: 'homeroom_teacher',
  scope_type: 'class',
  scope_id: undefined as number | undefined,
  notes: '',
})

const ROLE_LABEL: Record<string, string> = {
  homeroom_teacher: '班主任',
  grade_leader: '年级组长',
  subject_teacher: '任课教师',
  moral_admin: '德育主任',
  counselor: '心理负责人',
}
const ROLE_TAG: Record<string, string> = {
  homeroom_teacher: 'success',
  grade_leader: 'warning',
  subject_teacher: 'primary',
  moral_admin: 'danger',
  counselor: 'info',
}

function roleLabel(r: string) { return ROLE_LABEL[r] || r }
function roleTag(r: string) { return ROLE_TAG[r] || 'info' }
function fmtTime(t: string | null) {
  return t ? t.replace('T', ' ').slice(0, 16) : '—'
}

const missingClasses = computed(() => {
  const assigned = new Set(
    assignments.value.filter((a) => a.role_type === 'homeroom_teacher' && a.is_active).map((a) => a.scope_id),
  )
  return classes.value.filter((c) => !assigned.has(c.id))
})

// 责任覆盖概览（诚实显示「未配置」，绝不补假数据）
const gradeLeaderCoverage = computed(() => {
  const configured = new Set(
    assignments.value
      .filter((a) => a.role_type === 'grade_leader' && a.is_active && a.scope_type === 'grade')
      .map((a) => a.scope_id),
  )
  return grades.value.map((g) => ({ id: g.id, name: g.name, configured: configured.has(g.id) }))
})
const psychConfigured = computed(() =>
  assignments.value.some((a) => a.role_type === 'counselor' && a.is_active),
)
const subjectCount = computed(() =>
  assignments.value.filter((a) => a.role_type === 'subject_teacher' && a.is_active).length,
)

onMounted(async () => {
  await Promise.all([loadAssignments(), loadTeachers(), loadClasses()])
})

async function loadAssignments() {
  loading.value = true
  try {
    const res: any = await request.get('/teachers/roles/all')
    assignments.value = res?.assignments ?? []
  } catch (err: any) {
    ElMessage.error(`加载岗位失败: ${err.message || err}`)
  } finally {
    loading.value = false
  }
}

async function loadTeachers() {
  try {
    const res: any = await listTeachers({ page: 1, page_size: 200 })
    teachers.value = res?.items ?? (Array.isArray(res) ? res : [])
  } catch { /* ignore */ }
}

async function loadClasses() {
  try {
    const res: any = await getClasses()
    classes.value = res?.items ?? (Array.isArray(res) ? res : [])
    const g: any = await getGrades()
    grades.value = g?.items ?? (Array.isArray(g) ? g : [])
  } catch { /* ignore */ }
}

function openCreate() {
  createForm.value = { teacher_user_id: undefined, role_type: 'homeroom_teacher', scope_type: 'class', scope_id: undefined, notes: '' }
  createVisible.value = true
}

async function submitCreate() {
  const f = createForm.value
  if (!f.teacher_user_id || !f.role_type || !f.scope_type) {
    ElMessage.warning('请完整填写教师/岗位/作用域'); return
  }
  if (f.scope_type !== 'school' && !f.scope_id) {
    ElMessage.warning('请选择作用域对象'); return
  }
  creating.value = true
  try {
    await request.post(`/teachers/${f.teacher_user_id}/roles`, {
      role_type: f.role_type,
      scope_type: f.scope_type,
      scope_id: f.scope_type === 'school' ? null : f.scope_id,
      notes: f.notes || undefined,
    })
    ElMessage.success('岗位分配成功')
    createVisible.value = false
    await loadAssignments()
  } catch (err: any) {
    ElMessage.error(`分配失败: ${err.message || err}`)
  } finally {
    creating.value = false
  }
}

async function toggle(row: Assignment) {
  try {
    await request.patch(`/teachers/roles/${row.id}`, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '已停用' : '已启用')
    await loadAssignments()
  } catch (err: any) {
    ElMessage.error(`操作失败: ${err.message || err}`)
  }
}

async function remove(row: Assignment) {
  await ElMessageBox.confirm(`确认删除 ${row.teacher_name} 的「${roleLabel(row.role_type)}」岗位？`, '删除确认', {
    confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
  })
  try {
    await request.delete(`/teachers/roles/${row.id}`)
    ElMessage.success('已删除')
    await loadAssignments()
  } catch (err: any) {
    ElMessage.error(`删除失败: ${err.message || err}`)
  }
}
</script>

<style scoped>
.org-responsibility {
  padding: 16px;
  background: #f5f7fa;
  min-height: calc(100vh - 64px);
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
}
.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.page-subtitle {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
}
.header-right { display: flex; align-items: center; gap: 8px; }
.missing-alert { margin-bottom: 14px; }
.missing-tag { margin-right: 6px; }
.overview-card { border-radius: 10px; margin-bottom: 14px; }
.overview-title { font-weight: 600; font-size: 15px; color: #303133; }
.overview-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.ov-item { border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 12px; }
.ov-label { font-size: 13px; color: #606266; font-weight: 600; margin-bottom: 8px; }
.ov-body { display: flex; flex-wrap: wrap; gap: 6px; }
.ov-empty { font-size: 12px; color: #c0c4cc; }
@media (max-width: 768px) { .overview-grid { grid-template-columns: 1fr; } }
.list-card { border-radius: 10px; }
.teacher-name { font-weight: 600; }
.scope-sub { color: #c0c4cc; font-size: 12px; }
.notes-text { margin-left: 6px; font-size: 12px; color: #909399; }
</style>
