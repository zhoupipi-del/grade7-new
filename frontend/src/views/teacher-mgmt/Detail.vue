<template>
  <div class="teacher-detail">
    <el-page-header @back="$router.back()" title="返回">
      <template #content>
        <span>{{ detail?.display_name || '教师详情' }}</span>
      </template>
    </el-page-header>

    <el-card class="info-card" v-loading="loading">
      <template #header><h4>基本信息</h4></template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="姓名">{{ detail?.display_name }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ detail?.username }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag :type="detail?.role === 'class_teacher' ? 'warning' : 'info'" size="small">
            {{ detail?.role === 'class_teacher' ? '班主任' : '教师' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="工号">{{ detail?.employee_no || '-' }}</el-descriptions-item>
        <el-descriptions-item label="主教科">{{ detail?.subject || '-' }}</el-descriptions-item>
        <el-descriptions-item label="手机">{{ detail?.phone || '-' }}</el-descriptions-item>
        <el-descriptions-item v-if="detail?.is_homeroom" label="班主任班级">
          {{ detail.homeroom_class_name || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="info-card" v-if="detail">
      <template #header>
        <div class="card-header">
          <h4>扩展信息</h4>
          <el-button type="primary" size="small" @click="showExtDialog = true">
            {{ detail.extension ? '编辑' : '完善' }}
          </el-button>
        </div>
      </template>
      <el-descriptions :column="3" border v-if="detail.extension">
        <el-descriptions-item label="职称">{{ detail.extension.title || '-' }}</el-descriptions-item>
        <el-descriptions-item label="学历">{{ detail.extension.education || '-' }}</el-descriptions-item>
        <el-descriptions-item label="专业">{{ detail.extension.major || '-' }}</el-descriptions-item>
        <el-descriptions-item label="毕业院校">{{ detail.extension.graduate_school || '-' }}</el-descriptions-item>
        <el-descriptions-item label="入职日期">{{ detail.extension.hired_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="办公地点">{{ detail.extension.office_location || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资质证书" :span="2">
          <el-tag v-for="q in detail.extension.qualifications || []" :key="q" size="small" style="margin-right:4px">{{ q }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="暂无扩展信息" />
    </el-card>

    <el-card class="info-card" v-if="detail">
      <template #header>
        <div class="card-header">
          <h4>任教科类</h4>
          <el-button type="primary" size="small" @click="showSubjectDialog = true">分配学科</el-button>
        </div>
      </template>
      <template v-if="detail.subjects_taught?.length">
        <el-tag
          v-for="s in detail.subjects_taught" :key="s.subject_code"
          :type="s.is_primary ? undefined : 'info'" size="small" style="margin-right:6px;margin-bottom:6px"
        >
          {{ s.subject_name }}{{ s.grade_level ? ` (${s.grade_level})` : '' }}
        </el-tag>
      </template>
      <el-empty v-else description="未分配任教学科" />
    </el-card>

    <!-- 扩展信息编辑弹窗 -->
    <el-dialog v-model="showExtDialog" title="编辑扩展信息" width="600px">
      <el-form :model="extForm" label-width="100px">
        <el-form-item label="职称">
          <el-select v-model="extForm.title" clearable placeholder="选择职称">
            <el-option label="特级教师" value="特级" />
            <el-option label="高级教师" value="高级" />
            <el-option label="一级教师" value="一级" />
            <el-option label="二级教师" value="二级" />
            <el-option label="三级教师" value="三级" />
          </el-select>
        </el-form-item>
        <el-form-item label="入职日期">
          <el-date-picker v-model="extForm.hired_at" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="办公电话">
          <el-input v-model="extForm.office_phone" />
        </el-form-item>
        <el-form-item label="办公地点">
          <el-input v-model="extForm.office_location" />
        </el-form-item>
        <el-form-item label="最高学历">
          <el-select v-model="extForm.education" clearable>
            <el-option label="博士" value="博士" />
            <el-option label="硕士" value="硕士" />
            <el-option label="本科" value="本科" />
            <el-option label="大专" value="大专" />
          </el-select>
        </el-form-item>
        <el-form-item label="专业">
          <el-input v-model="extForm.major" />
        </el-form-item>
        <el-form-item label="毕业院校">
          <el-input v-model="extForm.graduate_school" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showExtDialog = false">取消</el-button>
        <el-button type="primary" @click="saveExtension" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 学科分配弹窗 -->
    <el-dialog v-model="showSubjectDialog" title="分配任教学科" width="500px">
      <div v-for="(s, i) in subjectList" :key="i" style="display:flex;gap:8px;margin-bottom:8px;align-items:center">
        <el-select v-model="s.subject_code" placeholder="学科代码" style="width:120px">
          <el-option v-for="sub in SUBJECTS" :key="sub.code" :label="sub.name" :value="sub.code" />
        </el-select>
        <el-input v-model="s.subject_name" placeholder="学科名" style="width:100px" />
        <el-select v-model="s.grade_level" clearable placeholder="年级" style="width:100px">
          <el-option label="初一" value="初一" /><el-option label="初二" value="初二" />
          <el-option label="初三" value="初三" /><el-option label="高一" value="高一" />
        </el-select>
        <el-checkbox v-model="s.is_primary">主教科任</el-checkbox>
        <el-button type="danger" :icon="'Delete'" circle size="small" @click="subjectList.splice(i,1)" />
      </div>
      <el-button type="primary" size="small" @click="subjectList.push({ subject_code:'',subject_name:'',is_primary:true,grade_level:'' })">
        + 添加学科
      </el-button>
      <template #footer>
        <el-button @click="showSubjectDialog = false">取消</el-button>
        <el-button type="primary" @click="saveSubjects" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getTeacherDetail, upsertTeacherExtension, assignSubjects, type TeacherDetail, type SubjectAssignment } from '@/api/teachers'

const SUBJECTS = [
  { code: 'chinese', name: '语文' }, { code: 'math', name: '数学' }, { code: 'english', name: '英语' },
  { code: 'physics', name: '物理' }, { code: 'chemistry', name: '化学' }, { code: 'biology', name: '生物' },
  { code: 'politics', name: '政治' }, { code: 'history', name: '历史' }, { code: 'geography', name: '地理' },
  { code: 'pe', name: '体育' }, { code: 'music', name: '音乐' }, { code: 'art', name: '美术' },
  { code: 'it', name: '信息技术' },
]

const route = useRoute()
const userId = Number(route.params.id)
const loading = ref(false)
const saving = ref(false)
const detail = ref<TeacherDetail | null>(null)

const showExtDialog = ref(false)
const extForm = ref<Record<string, any>>({})
const showSubjectDialog = ref(false)
const subjectList = ref<SubjectAssignment[]>([])

async function fetchDetail() {
  loading.value = true
  try {
    const res = await getTeacherDetail(userId)
    detail.value = res
  } finally {
    loading.value = false
  }
}

function openExtDialog() {
  const ext = detail.value?.extension
  extForm.value = {
    title: ext?.title || '',
    hired_at: ext?.hired_at || '',
    office_phone: ext?.office_phone || '',
    office_location: ext?.office_location || '',
    education: ext?.education || '',
    major: ext?.major || '',
    graduate_school: ext?.graduate_school || '',
  }
  showExtDialog.value = true
}
watch(showExtDialog, (v) => { if (v) openExtDialog() })

function openSubjectDialog() {
  subjectList.value = (detail.value?.subjects_taught || []).map(s => ({ ...s }))
  if (!subjectList.value.length) {
    subjectList.value = [{ subject_code: '', subject_name: '', is_primary: true, grade_level: '' }]
  }
  showSubjectDialog.value = true
}
watch(showSubjectDialog, (v) => { if (v) openSubjectDialog() })

async function saveExtension() {
  saving.value = true
  try {
    await upsertTeacherExtension(userId, extForm.value)
    showExtDialog.value = false
    await fetchDetail()
  } finally {
    saving.value = false
  }
}

async function saveSubjects() {
  saving.value = true
  try {
    const valid = subjectList.value.filter(s => s.subject_code && s.subject_name)
    await assignSubjects(userId, valid)
    showSubjectDialog.value = false
    await fetchDetail()
  } finally {
    saving.value = false
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
.teacher-detail { padding: 0; }
.info-card { margin-top: 12px; }
.card-header { display:flex; justify-content:space-between; align-items:center; }
.card-header h4 { margin:0; }
</style>
