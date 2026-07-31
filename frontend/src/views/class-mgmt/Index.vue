<template>
  <div class="class-mgmt-page">
    <!-- 顶部操作栏 -->
    <div class="page-header">
      <h2 class="page-title">班级管理</h2>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="showCreateDialog">新建班级</el-button>
        <el-button :icon="RefreshRight" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <!-- 统计概览 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-label">班级总数</div>
          <div class="stat-value">{{ stats?.total_classes || 0 }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-label">学生总数</div>
          <div class="stat-value">{{ stats?.total_students || 0 }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-label">平均班额</div>
          <div class="stat-value">{{ stats?.avg_class_size ? stats.avg_class_size.toFixed(1) : '-' }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-label">最大 / 最小班</div>
          <div class="stat-value small">
            {{ stats?.largest_class?.name || '-' }}
            /
            {{ stats?.smallest_class?.name || '-' }}
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 年级Tab切换 -->
    <el-tabs v-model="activeGradeId" @tab-change="loadClasses" type="card" class="grade-tabs">
      <el-tab-pane
        v-for="g in grades"
        :key="g.id"
        :label="g.name"
        :name="String(g.id)"
      />
    </el-tabs>

    <!-- 班级卡片网格 -->
    <div v-loading="loading" class="class-grid">
      <div
        v-for="cls in classes"
        :key="cls.id"
        class="class-card"
        @click="showClassDetail(cls)"
      >
        <div class="class-card-header">
          <span class="class-name">{{ cls.name }}</span>
          <el-tag :type="cls.is_active ? 'success' : 'info'" size="small">
            {{ cls.is_active ? '在读' : '停用' }}
          </el-tag>
        </div>
        <div class="class-card-body">
          <div class="class-stat">
            <span class="label">学生数</span>
            <span class="value">{{ cls.student_count }}</span>
          </div>
          <div class="class-stat">
            <span class="label">班主任</span>
            <span class="value">{{ cls.head_teacher_name || '未分配' }}</span>
          </div>
        </div>
        <div class="class-card-footer">
          <span class="slogan">{{ cls.class_slogan || '暂无班级口号' }}</span>
        </div>
      </div>
    </div>

    <!-- 新建班级弹窗 -->
    <el-dialog v-model="createVisible" title="新建班级" width="480px" destroy-on-close>
      <el-form :model="createForm" label-width="90px">
        <el-form-item label="班级名称" required>
          <el-input v-model="createForm.name" placeholder="如: 2501班" />
        </el-form-item>
        <el-form-item label="所属年级" required>
          <el-select v-model="createForm.grade_id" style="width: 100%">
            <el-option v-for="g in grades" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="班主任">
          <el-select v-model="createForm.head_teacher_id" filterable placeholder="搜索教师" style="width: 100%">
            <el-option v-for="t in teachers" :key="t.id" :label="`${t.name} (${t.subject || '无科目'})`" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="班级口号">
          <el-input v-model="createForm.class_slogan" placeholder="班级口号或寄语" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 班级详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detailClass?.name" size="560px" destroy-on-close>
      <template v-if="detailClass">
        <!-- 基本信息 -->
        <div class="detail-section">
          <h4>基本信息</h4>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="班级名称">{{ detailClass.name }}</el-descriptions-item>
            <el-descriptions-item label="学生人数">
              <el-tag type="primary" size="small">{{ detailClass.student_count }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="班主任">
              <template v-if="detailClass.head_teacher_name">
                {{ detailClass.head_teacher_name }}
                <el-button type="danger" link size="small" @click="removeTeacher">移除</el-button>
              </template>
              <el-button v-else type="primary" link size="small" @click="showAssignTeacher">分配班主任</el-button>
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-switch
                v-model="detailClass.is_active"
                active-text="在读"
                inactive-text="停用"
                @change="(val: string | number | boolean) => toggleActive(!!val)"
              />
            </el-descriptions-item>
            <el-descriptions-item label="班级口号" :span="2">{{ detailClass.class_slogan || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 学生名单 -->
        <div class="detail-section">
          <div class="section-header">
            <h4>学生名单 ({{ classStudents.length }})</h4>
            <el-button type="primary" size="small" :icon="Plus" @click="showAssignStudents">分配学生</el-button>
          </div>
          <el-table :data="classStudents" border stripe size="small" max-height="320">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="姓名" width="80" />
            <el-table-column prop="student_no" label="学号" width="110" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.registry_status === 'active' ? 'success' : 'warning'" size="small">
                  {{ REGISTRY_STATUS_LABELS[row.registry_status as keyof typeof REGISTRY_STATUS_LABELS] || row.registry_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="removeStudent(row as any)">移出</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </el-drawer>

    <!-- 分配学生弹窗（拖拽式） -->
    <el-dialog v-model="assignVisible" title="分配学生到班级" width="700px" destroy-on-close>
      <el-row :gutter="16">
        <!-- 左侧：未分配学生池 -->
        <el-col :span="12">
          <div class="pool-header">
            <span>未分配学生</span>
            <el-input v-model="poolSearch" size="small" placeholder="搜索..." clearable style="width: 140px" />
          </div>
          <div class="student-pool">
            <div
              v-for="s in filteredPool"
              :key="s.id"
              class="pool-item"
              :class="{ selected: poolSelected.has(s.id) }"
              @click="togglePoolSelect(s.id)"
            >
              <span class="pool-name">{{ s.name }}</span>
              <span class="pool-no">{{ s.student_no }}</span>
            </div>
            <el-empty v-if="!filteredPool.length" description="无未分配学生" :image-size="60" />
          </div>
        </el-col>
        <!-- 右侧：操作区 -->
        <el-col :span="12">
          <div style="text-align: center; padding-top: 80px">
            <div class="transfer-arrow">
              <el-button
                type="primary"
                :icon="DArrowRight"
                :disabled="poolSelected.size === 0"
                @click="doAssign"
                size="large"
                circle
              />
            </div>
            <p style="margin-top: 12px; color: #8b949e; font-size: 13px">
              选中 {{ poolSelected.size }} 人
            </p>
            <p style="color: #6e7681; font-size: 12px">
              将分配到 <strong>{{ detailClass?.name }}</strong>
            </p>
          </div>
        </el-col>
      </el-row>
    </el-dialog>

    <!-- 调班弹窗 -->
    <el-dialog v-model="transferVisible" title="学生调班" width="400px" destroy-on-close>
      <el-form :model="transferForm" label-width="90px">
        <el-form-item label="学生">
          <span>{{ transferForm.student_name }}</span>
        </el-form-item>
        <el-form-item label="目标班级">
          <el-select v-model="transferForm.target_class_id" style="width: 100%">
            <el-option
              v-for="c in classesForTransfer"
              :key="c.id"
              :label="c.name"
              :value="c.id"
              :disabled="c.id === detailClass?.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="调班原因">
          <el-input v-model="transferForm.reason" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferVisible = false">取消</el-button>
        <el-button type="warning" :loading="transferring" @click="doTransfer">确认调班</el-button>
      </template>
    </el-dialog>

    <!-- 分配班主任弹窗 -->
    <el-dialog v-model="teacherVisible" title="分配班主任" width="400px" destroy-on-close>
      <el-select v-model="teacherForm.head_teacher_id" filterable placeholder="搜索教师" style="width: 100%">
        <el-option v-for="t in teachers" :key="t.id" :label="`${t.name} (${t.subject || '无科目'})`" :value="t.id" />
      </el-select>
      <template #footer>
        <el-button @click="teacherVisible = false">取消</el-button>
        <el-button type="primary" :loading="teacherAssigning" @click="doAssignTeacher">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, RefreshRight, DArrowRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getGrades } from '@/api/classes'
import {
  listClasses, createClass, updateClass,
  assignStudentsToClass, transferStudent, assignHeadTeacher,
  getClassStudents, getClassStats,
  type ClassDetail, type ClassStats,
} from '@/api/classMgmt'
import { listStudents, REGISTRY_STATUS_LABELS, type StudentDetail } from '@/api/students'
import { listTeachers } from '@/api/teachers'

// ── 状态 ──
const loading = ref(false)
const grades = ref<Array<{ id: number; name: string }>>([])
const classes = ref<ClassDetail[]>([])
const stats = ref<ClassStats | null>(null)
const activeGradeId = ref('')
const teachers = ref<Array<{ id: number; name: string; subject?: string }>>([])

// 新建
const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', grade_id: 0, head_teacher_id: undefined as number | undefined, class_slogan: '' })

// 详情抽屉
const detailVisible = ref(false)
const detailClass = ref<ClassDetail | null>(null)
const classStudents = ref<StudentDetail[]>([])

// 分配学生
const assignVisible = ref(false)
const poolSearch = ref('')
const poolStudents = ref<StudentDetail[]>([])
const poolSelected = ref<Set<number>>(new Set())

// 调班
const transferVisible = ref(false)
const transferring = ref(false)
const transferForm = ref({ student_id: 0, student_name: '', target_class_id: 0, reason: '' })
const classesForTransfer = ref<ClassDetail[]>([])

// 分配班主任
const teacherVisible = ref(false)
const teacherAssigning = ref(false)
const teacherForm = ref({ head_teacher_id: 0 })

// ── 计算 ──
const filteredPool = computed(() => {
  if (!poolSearch.value) return poolStudents.value
  const kw = poolSearch.value.toLowerCase()
  return poolStudents.value.filter(s =>
    s.name.includes(kw) || s.student_no.includes(kw)
  )
})

// ── 加载 ──
async function loadAll() {
  loading.value = true
  try {
    const [gRes, sRes] = await Promise.all([
      getGrades().catch(() => ({ data: [] })),
      getClassStats().catch(() => null),
    ])
    grades.value = (gRes as any)?.data || gRes || []
    if (!activeGradeId.value && grades.value.length) {
      activeGradeId.value = String(grades.value[0].id)
    }
    stats.value = sRes ? (sRes as ClassStats) : null
    await loadClasses()
  } catch (e) {
    console.error('Load class mgmt error:', e)
  } finally {
    loading.value = false
  }
}

async function loadClasses() {
  try {
    const params: any = {}
    if (activeGradeId.value) params.grade_id = Number(activeGradeId.value)
    const res = await listClasses(params)
    classes.value = (res as any)?.items || res || []
  } catch (e) {
    console.error('Load classes error:', e)
  }
}

async function loadTeachers() {
  try {
    const res = await listTeachers()
    teachers.value = (res as any)?.data || res || []
  } catch {}
}

// ── 新建班级 ──
function showCreateDialog() {
  createForm.value = { name: '', grade_id: Number(activeGradeId.value) || 0, head_teacher_id: undefined, class_slogan: '' }
  createVisible.value = true
}

async function doCreate() {
  if (!createForm.value.name || !createForm.value.grade_id) {
    ElMessage.warning('请填写班级名称和年级')
    return
  }
  creating.value = true
  try {
    await createClass(createForm.value as any)
    ElMessage.success('班级创建成功')
    createVisible.value = false
    loadAll()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

// ── 班级详情 ──
async function showClassDetail(cls: ClassDetail) {
  detailClass.value = cls
  detailVisible.value = true
  try {
    const res = await getClassStudents(cls.id)
    classStudents.value = (res as any)?.items || res || []
  } catch {}
}

async function toggleActive(val: boolean) {
  if (!detailClass.value) return
  try {
    await updateClass(detailClass.value.id, { is_active: val })
    ElMessage.success(`班级已${val ? '启用' : '停用'}`)
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
    detailClass.value.is_active = !val // 回滚
  }
}

// ── 分配学生 ──
async function showAssignStudents() {
  assignVisible.value = true
  poolSelected.value = new Set()
  poolSearch.value = ''
  try {
    // 加载所有学生，过滤出未分配或可调的学生
    const res = await listStudents({ page_size: 1000, status: 'active' })
    poolStudents.value = (res as any)?.items || []
  } catch {}
}

function togglePoolSelect(id: number) {
  const s = new Set(poolSelected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  poolSelected.value = s
}

async function doAssign() {
  if (!detailClass.value || poolSelected.value.size === 0) return
  try {
    await assignStudentsToClass(detailClass.value.id, {
      student_ids: [...poolSelected.value],
    })
    ElMessage.success(`已分配 ${poolSelected.value.size} 名学生到 ${detailClass.value.name}`)
    assignVisible.value = false
    showClassDetail(detailClass.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '分配失败')
  }
}

// ── 移除学生 → 调班 ──
function removeStudent(row: StudentDetail) {
  transferForm.value = {
    student_id: row.id,
    student_name: row.name,
    target_class_id: 0,
    reason: '',
  }
  classesForTransfer.value = classes.value
  transferVisible.value = true
}

async function doTransfer() {
  if (!transferForm.value.target_class_id) {
    ElMessage.warning('请选择目标班级')
    return
  }
  transferring.value = true
  try {
    await transferStudent({
      student_id: transferForm.value.student_id,
      target_class_id: transferForm.value.target_class_id,
      reason: transferForm.value.reason || undefined,
    })
    ElMessage.success('调班完成')
    transferVisible.value = false
    if (detailClass.value) showClassDetail(detailClass.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '调班失败')
  } finally {
    transferring.value = false
  }
}

// ── 分配班主任 ──
function showAssignTeacher() { teacherVisible.value = true; teacherForm.value.head_teacher_id = 0 }

async function removeTeacher() {
  await ElMessageBox.confirm('确认移除班主任？', '提示')
  if (!detailClass.value) return
  try {
    await updateClass(detailClass.value.id, { head_teacher_id: 0 } as any)
    ElMessage.success('班主任已移除')
    detailClass.value.head_teacher_name = undefined
    detailClass.value.head_teacher_id = undefined
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function doAssignTeacher() {
  if (!detailClass.value || !teacherForm.value.head_teacher_id) {
    ElMessage.warning('请选择教师')
    return
  }
  teacherAssigning.value = true
  try {
    await assignHeadTeacher(detailClass.value.id, { head_teacher_id: teacherForm.value.head_teacher_id })
    ElMessage.success('班主任已分配')
    teacherVisible.value = false
    // 回写
    const t = teachers.value.find(x => x.id === teacherForm.value.head_teacher_id)
    if (t) detailClass.value.head_teacher_name = t.name
    detailClass.value.head_teacher_id = teacherForm.value.head_teacher_id
  } catch (e: any) {
    ElMessage.error(e?.message || '分配失败')
  } finally {
    teacherAssigning.value = false
  }
}

// ── 生命周期 ──
onMounted(() => {
  loadAll()
  loadTeachers()
})
</script>

<style scoped>
.class-mgmt-page {
  padding: 20px;
  color: #c9d1d9;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
  margin: 0;
}
.header-actions {
  display: flex;
  gap: 8px;
}

.stats-row {
  margin-bottom: 16px;
}
.stat-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px 20px;
  text-align: center;
}
.stat-label { font-size: 13px; color: #8b949e; }
.stat-value { font-size: 24px; font-weight: 700; color: #f0f6fc; }
.stat-value.small { font-size: 16px; }

.grade-tabs {
  margin-bottom: 16px;
}

.class-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.class-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
}
.class-card:hover {
  border-color: #409eff;
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(64,158,255,0.15);
}
.class-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.class-name { font-size: 18px; font-weight: 700; color: #f0f6fc; }
.class-card-body {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
}
.class-stat { text-align: center; }
.class-stat .label { font-size: 12px; color: #8b949e; display: block; }
.class-stat .value { font-size: 15px; font-weight: 600; color: #c9d1d9; }
.class-card-footer { border-top: 1px solid #21262d; padding-top: 10px; }
.slogan { font-size: 13px; color: #6e7681; font-style: italic; }

/* 抽屉 */
.detail-section {
  margin-bottom: 24px;
}
.detail-section h4 {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
  margin: 0 0 12px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h4 { margin: 0; }

/* 学生池 */
.pool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: #f0f6fc;
  font-weight: 600;
}
.student-pool {
  height: 360px;
  overflow-y: auto;
  border: 1px solid #30363d;
  border-radius: 8px;
  background: #0d1117;
  padding: 8px;
}
.pool-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}
.pool-item:hover { background: #21262d; }
.pool-item.selected {
  background: rgba(64,158,255,0.15);
  border: 1px solid #409eff;
}
.pool-name { font-size: 14px; color: #c9d1d9; }
.pool-no { font-size: 12px; color: #8b949e; }
.transfer-arrow { display: flex; justify-content: center; }
</style>
