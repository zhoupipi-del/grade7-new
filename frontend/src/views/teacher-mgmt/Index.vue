<template>
  <div class="teacher-mgmt">
    <el-card class="header-card">
      <div class="header">
        <h3>教师管理</h3>
        <div class="stats">
          <el-tag type="info">教师总数: {{ total }}</el-tag>
        </div>
      </div>
    </el-card>

    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="角色筛选">
          <el-select v-model="filterRole" clearable placeholder="全部" @change="fetchList">
            <el-option label="班主任" value="class_teacher" />
            <el-option label="普通教师" value="teacher" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filterActive" clearable placeholder="全部" @change="fetchList">
            <el-option label="在职" :value="true" />
            <el-option label="离职" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input v-model="keyword" placeholder="教师姓名" clearable @clear="fetchList" @keyup.enter="fetchList" style="width:200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchList">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table :data="teachers" stripe v-loading="loading" @row-click="goDetail">
        <el-table-column prop="display_name" label="姓名" width="100" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'class_teacher' ? 'warning' : 'info'" size="small">
              {{ row.role === 'class_teacher' ? '班主任' : '教师' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="employee_no" label="工号" width="100" />
        <el-table-column prop="subject" label="主教科" width="100" />
        <el-table-column prop="title" label="职称" width="100" />
        <el-table-column label="任教科目" min-width="180">
          <template #default="{ row }">
            <template v-if="row.subjects_taught?.length">
              <el-tag v-for="s in row.subjects_taught" :key="s" size="small" style="margin-right:4px">{{ s }}</el-tag>
            </template>
            <span v-else style="color:#909399">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="班主任" width="120">
          <template #default="{ row }">
            <span v-if="row.is_homeroom && row.homeroom_class_name" style="color:#e6a23c">
              是 ({{ row.homeroom_class_name }})
            </span>
            <span v-else>否</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '在职' : '离职' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page" :page-size="pageSize" :total="total"
          layout="total,prev,pager,next" @current-change="fetchList"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listTeachers, type TeacherListItem } from '@/api/teachers'

const router = useRouter()
const loading = ref(false)
const teachers = ref<TeacherListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterRole = ref<string | null>(null)
const filterActive = ref<boolean | null>(null)
const keyword = ref('')

async function fetchList() {
  loading.value = true
  try {
    const res = await listTeachers({
      page: page.value, page_size: pageSize.value,
      role: filterRole.value || undefined,
      is_active: filterActive.value ?? undefined,
      keyword: keyword.value || undefined,
    })
    teachers.value = res.teachers
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function goDetail(row: TeacherListItem) {
  router.push(`/teacher-mgmt/detail/${row.id}`)
}

onMounted(fetchList)
</script>

<style scoped>
.teacher-mgmt { padding: 0; }
.header-card { margin-bottom: 12px; }
.header { display:flex; justify-content:space-between; align-items:center; }
.header h3 { margin:0; }
.filter-card { margin-bottom: 12px; }
.pagination { margin-top:16px; display:flex; justify-content:flex-end; }
</style>
