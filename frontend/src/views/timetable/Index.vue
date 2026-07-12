<template>
  <div class="timetable-mgmt">
    <el-card class="header-card">
      <div class="header">
        <h3>课程表管理</h3>
        <div class="actions">
          <el-button type="primary" @click="showSlotDialog = true">+ 新增课节</el-button>
        </div>
      </div>
    </el-card>

    <!-- 筛选栏 -->
    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="班级">
          <el-select v-model="filterClassId" clearable placeholder="选择班级" @change="fetchSlots" style="width:160px">
            <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="教师">
          <el-select v-model="filterTeacherId" clearable filterable placeholder="选择教师" @change="fetchSlots" style="width:160px">
            <el-option v-for="t in teachers" :key="t.id" :label="t.display_name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="filterSemester" placeholder="2025-2026-1" @change="fetchSlots" style="width:140px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchSlots">查询</el-button>
          <el-button v-if="filterClassId && filterSemester" @click="goWeekView">查看课表</el-button>
          <el-button v-if="filterTeacherId && filterSemester" @click="goTeacherWeekView">教师课表</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 课节列表 -->
    <el-card>
      <el-table :data="slots" stripe v-loading="loading">
        <el-table-column prop="class_name" label="班级" width="100" v-if="!filterClassId" />
        <el-table-column label="时间" width="160">
          <template #default="{ row }">
            周{{ row.day_of_week }} 第{{ row.period_start }}-{{ row.period_end }}节
          </template>
        </el-table-column>
        <el-table-column prop="course_name" label="课程" width="100" />
        <el-table-column prop="teacher_name" label="教师" width="100" />
        <el-table-column prop="classroom_name" label="教室" width="120" />
        <el-table-column label="周模式" width="80">
          <template #default="{ row }">
            <el-tag :type="row.week_pattern === 'every' ? '' : 'warning'" size="small">
              {{ weekPatternLabel(row.week_pattern) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="semester" label="学期" width="130" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" size="small" @click="doDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增课节弹窗 -->
    <el-dialog v-model="showSlotDialog" title="新增课节" width="520px" @opened="onSlotDialogOpen">
      <el-form :model="slotForm" label-width="100px">
        <el-form-item label="班级" required>
          <el-select v-model="slotForm.class_id" placeholder="选择班级" style="width:100%">
            <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程" required>
          <el-select v-model="slotForm.course_id" filterable placeholder="选择课程" style="width:100%">
            <el-option v-for="c in courses" :key="c.id" :label="`${c.name} (${c.periods_per_week}节/周)`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="授课教师" required>
          <el-select v-model="slotForm.teacher_user_id" filterable placeholder="选择教师" style="width:100%">
            <el-option v-for="t in teachers" :key="t.id" :label="t.display_name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="教室">
          <el-select v-model="slotForm.classroom_id" clearable placeholder="不选=本班教室" style="width:100%">
            <el-option v-for="r in classrooms" :key="r.id" :label="`${r.name} (${r.capacity}人)`" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="星期" required>
              <el-select v-model="slotForm.day_of_week" style="width:100%">
                <el-option v-for="d in 7" :key="d" :label="`周${d}`" :value="d" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="起始节" required>
              <el-input-number v-model="slotForm.period_start" :min="1" :max="10" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="结束节" required>
              <el-input-number v-model="slotForm.period_end" :min="1" :max="10" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="周模式">
          <el-radio-group v-model="slotForm.week_pattern">
            <el-radio value="every">每周</el-radio>
            <el-radio value="odd">单周</el-radio>
            <el-radio value="even">双周</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="学期" required>
          <el-input v-model="slotForm.semester" placeholder="2025-2026-1" />
        </el-form-item>
      </el-form>

      <!-- 冲突预览 -->
      <el-alert v-if="conflicts.length" title="冲突检测" type="warning" :closable="false" style="margin-top:12px">
        <div v-for="(c, i) in conflicts" :key="i" style="font-size:13px;margin-bottom:4px">
          <el-tag :type="c.severity === 'error' ? 'danger' : 'warning'" size="small">{{ c.conflict_type }}</el-tag>
          {{ c.conflict_detail }}
        </div>
      </el-alert>

      <template #footer>
        <el-button @click="showSlotDialog = false">取消</el-button>
        <el-button @click="previewConflict" :loading="checking">检测冲突</el-button>
        <el-button type="primary" @click="doCreateSlot(false)" :loading="creating">创建</el-button>
        <el-button v-if="conflicts.length" type="warning" @click="doCreateSlot(true)" :loading="creating">强制创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listSlots, createSlot, deleteSlot, checkConflict, type CourseSlot, type ConflictDetail } from '@/api/timetable'
import { listClassrooms, type Classroom } from '@/api/timetable'
import { listCourses, type Course } from '@/api/timetable'
import { listTeachers, type TeacherListItem } from '@/api/teachers'

const router = useRouter()
const loading = ref(false)
const slots = ref<CourseSlot[]>([])
const classrooms = ref<Classroom[]>([])
const courses = ref<Course[]>([])
const teachers = ref<TeacherListItem[]>([])
const classes = ref<any[]>([])

const filterClassId = ref<number | null>(null)
const filterTeacherId = ref<number | null>(null)
const filterSemester = ref('2025-2026-2')

const showSlotDialog = ref(false)
const slotForm = ref({
  class_id: null as number | null, course_id: null as number | null,
  teacher_user_id: null as number | null, classroom_id: null as number | null,
  day_of_week: 1, period_start: 1, period_end: 1,
  week_pattern: 'every', semester: '2025-2026-2',
})
const conflicts = ref<ConflictDetail[]>([])
const checking = ref(false)
const creating = ref(false)

function weekPatternLabel(p: string) { return p === 'every' ? '每周' : p === 'odd' ? '单周' : '双周' }

async function fetchSlots() {
  loading.value = true
  try {
    const res = await listSlots({
      class_id: filterClassId.value || undefined,
      teacher_user_id: filterTeacherId.value || undefined,
      semester: filterSemester.value || undefined,
    })
    slots.value = res.data
  } finally { loading.value = false }
}

async function previewConflict() {
  checking.value = true
  try {
    const res = await checkConflict({ ...slotForm.value as any, class_id: slotForm.value.class_id!, course_id: slotForm.value.course_id!, teacher_user_id: slotForm.value.teacher_user_id! })
    conflicts.value = res.data.conflicts
  } finally { checking.value = false }
}

async function doCreateSlot(autoResolve: boolean) {
  creating.value = true
  try {
    const res = await createSlot(slotForm.value as any, autoResolve)
    if (res.data.created === false) {
      conflicts.value = res.data.conflicts?.conflicts || []
      return
    }
    showSlotDialog.value = false
    fetchSlots()
  } finally { creating.value = false }
}

async function doDelete(id: number) {
  await deleteSlot(id)
  fetchSlots()
}

function goWeekView() {
  router.push(`/timetable/week/${filterClassId.value}?semester=${filterSemester.value}`)
}
function goTeacherWeekView() {
  router.push(`/timetable/week/teacher/${filterTeacherId.value}?semester=${filterSemester.value}`)
}

async function onSlotDialogOpen() {
  slotForm.value.semester = filterSemester.value || '2025-2026-2'
  conflicts.value = []
}

onMounted(async () => {
  const [cRes, coRes, tRes] = await Promise.all([
    listClassrooms(), listCourses(), listTeachers({ page_size: 200 })
  ])
  classrooms.value = cRes.data
  courses.value = coRes.data
  teachers.value = tRes.data.teachers
  // 获取班级列表 - 使用已有 API
  try {
    const { listClasses } = await import('@/api/classMgmt')
    const clsRes = await listClasses()
    classes.value = clsRes.data.classes || clsRes.data || []
  } catch { /* fallback */ }
  fetchSlots()
})
</script>

<style scoped>
.timetable-mgmt { padding: 0; }
.header-card { margin-bottom: 12px; }
.header { display:flex; justify-content:space-between; align-items:center; }
.header h3 { margin:0; }
.filter-card { margin-bottom: 12px; }
</style>
