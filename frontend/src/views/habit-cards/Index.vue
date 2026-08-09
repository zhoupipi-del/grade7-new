<template>
  <div class="habit-cards-dashboard">
    <!-- 班级选择 -->
    <div class="top-bar">
      <div class="page-title">
        <span class="title-icon">🦊</span>
        <h2>小学虚拟萌卡荣誉生态</h2>
      </div>
      <el-select
        v-model="selectedClassId"
        placeholder="选择班级"
        class="class-picker"
        @change="onClassChange"
      >
        <el-option
          v-for="cls in classes"
          :key="cls.id"
          :label="cls.class_name"
          :value="cls.id"
        />
      </el-select>
    </div>

    <!-- 头像墙组件 -->
    <ClassAvatarWall
      v-if="selectedClassId"
      :key="selectedClassId"
      :class-id="selectedClassId"
      :school-id="userSchoolId"
    />
    <div v-else class="empty-hint">
      请从上方下拉框选择一个班级，进入萌卡荣誉生态
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/store/user'
import ClassAvatarWall from './ClassAvatarWall.vue'
import { getClasses } from '@/api/classes'

const userStore = useUserStore()
const userSchoolId = ref<number>(Number(userStore.schoolId || 99))

const classes = ref<any[]>([])
const selectedClassId = ref<number | null>(null)

async function fetchClasses() {
  try {
    const res: any = await getClasses()
    classes.value = res.classes || res.data?.classes || []
    if (classes.value.length > 0) {
      selectedClassId.value = classes.value[0].id
    }
  } catch (e: any) {
    console.error('班级加载失败:', e)
  }
}

function onClassChange() {
  // key 绑定自动触发重渲染
}

onMounted(fetchClasses)
</script>

<style scoped>
.habit-cards-dashboard {
  max-width: 1200px;
  margin: 0 auto;
}

.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 16px 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
}
.title-icon { font-size: 22px; }

.class-picker {
  width: 200px;
}

.empty-hint {
  text-align: center;
  color: #8b949e;
  padding: 60px;
  font-size: 15px;
}
</style>
