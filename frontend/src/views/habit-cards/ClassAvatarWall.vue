<template>
  <div class="gamified-container">
    <div class="header-hub">
      <div class="hub-title">
        <span class="hub-emoji">🦊</span>
        <span>Wings 小学虚拟卡牌荣誉生态控制台</span>
      </div>
      <div class="selected-counter">
        已锁定学生：<strong>{{ selectedStudents.length }}</strong> 人
      </div>
    </div>

    <!-- 卡牌模板选择条 -->
    <div class="card-templates-bar">
      <div
        v-for="card in cardTemplates"
        :key="card.id"
        class="template-pill"
        :class="[
          card.card_rarity,
          { active: selectedCardId === card.id }
        ]"
        @click="selectedCardId = card.id"
      >
        <span class="pill-rarity-dot" :class="card.card_rarity"></span>
        <span class="pill-name">{{ card.card_name }}</span>
        <span class="pill-points">+{{ card.reward_points }}</span>
      </div>
    </div>

    <!-- 学生头像墙 -->
    <div class="avatar-wall-grid" v-if="!loadingStudents">
      <div
        v-for="student in students"
        :key="student.id"
        class="student-avatar-card"
        :class="{ 'is-selected': selectedStudents.includes(student.id) }"
        @click="toggleSelectStudent(student.id)"
      >
        <div class="avatar-circle" :style="{ background: getAvatarColor(student.id) }">
          {{ student.name?.substring(0, 1) || '?' }}
        </div>
        <div class="student-info">
          <span class="s-name">{{ student.name }}</span>
          <span class="s-id">{{ student.student_no || 'ID:' + student.id }}</span>
        </div>
        <div class="check-mark">✓</div>
      </div>
    </div>
    <div v-else class="skeleton-loader">正在加载教室头像墙...</div>

    <!-- 底部发卡操作栏 -->
    <div class="dock-action-bar" v-if="selectedStudents.length > 0 && selectedCardId">
      <button @click="fireIssueEngine" :disabled="issuing" class="laser-fire-btn">
        ⚡ {{ issuing ? '充能中...' : `闪击充能！向这 ${selectedStudents.length} 名学生注入资产` }}
      </button>
    </div>

    <!-- 盲盒弹窗 -->
    <el-dialog
      v-model="blindBoxVisible"
      title="🎁 神秘盲盒已开启！"
      width="460px"
      custom-class="blindbox-dark-dialog"
      :close-on-click-modal="false"
      center
    >
      <div v-if="blindBoxResult" class="blindbox-content">
        <div class="blindbox-card-reveal" :class="blindBoxResult.card_rarity">
          <div class="rarity-glow" :class="blindBoxResult.card_rarity"></div>
          <div class="card-display-name">{{ blindBoxResult.card_name }}</div>
          <div class="card-rarity-tag">{{ rarityLabel(blindBoxResult.card_rarity) }}</div>
        </div>
        <div class="ai-letter-section" v-if="blindBoxResult.ai_praise_letter">
          <h4>🤖 DeepSeek 表彰信</h4>
          <p class="letter-text">{{ blindBoxResult.ai_praise_letter }}</p>
          <button class="share-btn" @click="copyLetter">
            📋 一键复制朋友圈文案
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getCardTemplates,
  batchIssueCards,
  getStudentWallet,
  openBlindbox,
  type CardTemplate,
  type BlindBoxResponse,
} from '@/api/habitCards'
import { getStudents } from '@/api/classes'

const props = defineProps<{
  classId: number
  schoolId: number
}>()

const cardTemplates = ref<CardTemplate[]>([])
const students = ref<any[]>([])
const loadingStudents = ref(false)
const selectedCardId = ref<number | null>(null)
const selectedStudents = ref<number[]>([])
const issuing = ref(false)

// 盲盒
const blindBoxVisible = ref(false)
const blindBoxResult = ref<BlindBoxResponse | null>(null)

const rarityLabel = (r: string) =>
  ({ legendary: '传说', epic: '史诗', rare: '稀有', common: '普通' }[r] || r)

const getAvatarColor = (id: number) => {
  const colors = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff', '#2dd4bf', '#f778ba']
  return colors[id % colors.length]
}

const toggleSelectStudent = (id: number) => {
  const idx = selectedStudents.value.indexOf(id)
  if (idx > -1) {
    selectedStudents.value.splice(idx, 1)
  } else {
    selectedStudents.value.push(id)
  }
}

// 拉取模板
async function fetchTemplates() {
  try {
    const res = await getCardTemplates(props.schoolId)
    if (res.cards) {
      cardTemplates.value = res.cards
      if (res.cards.length > 0 && !selectedCardId.value) {
        selectedCardId.value = res.cards[0].id
      }
    }
  } catch (e: any) {
    ElMessage.error('卡牌模板加载失败: ' + (e.message || e))
  }
}

// 拉取学生列表
async function fetchStudents() {
  loadingStudents.value = true
  try {
    const res: any = await getStudents({ class_id: props.classId })
    students.value = res.students || res.data?.students || []
  } catch (e: any) {
    ElMessage.error('学生头像墙加载失败: ' + (e.message || e))
  } finally {
    loadingStudents.value = false
  }
}

// 发起闪击
async function fireIssueEngine() {
  if (!selectedCardId.value || selectedStudents.value.length === 0) return
  issuing.value = true
  try {
    const res = await batchIssueCards({
      school_id: props.schoolId,
      teacher_id: 0, // 后端会用 get_current_user 覆盖
      card_id: selectedCardId.value,
      student_ids: [...selectedStudents.value],
      note: '班级日常表现优异，高光一刻触发',
    })
    if (res.status === 'success' || res.issued_count) {
      ElMessage.success(`🎉 资产发放大获全胜！成功下发 ${res.issued_count || selectedStudents.value.length} 个样本！`)
      selectedStudents.value = []
    }
  } catch (e: any) {
    ElMessage.error('发卡链路中断: ' + (e.message || e))
  } finally {
    issuing.value = false
  }
}

// 打开盲盒
async function openBlindBox(currentStudentId: number) {
  try {
    const res = await openBlindbox({
      parent_user_id: 0, // 后端会用 get_current_user 覆盖
      student_id: currentStudentId,
      school_id: props.schoolId,
    })
    blindBoxResult.value = res
    blindBoxVisible.value = true
  } catch (e: any) {
    ElMessage.error('盲盒开启失败: ' + (e.message || e))
  }
}

function copyLetter() {
  if (blindBoxResult.value?.ai_praise_letter) {
    navigator.clipboard.writeText(blindBoxResult.value.ai_praise_letter)
    ElMessage.success('表彰信已复制，快去刷爆朋友圈吧！')
  }
}

onMounted(() => {
  fetchTemplates()
  fetchStudents()
})

// 暴露方法给父组件
defineExpose({ openBlindBox })
</script>

<style scoped>
.gamified-container {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 24px;
  color: #e6edf3;
}

.header-hub {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #30363d;
  padding-bottom: 16px;
  margin-bottom: 20px;
}

.hub-title {
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
  display: flex;
  align-items: center;
  gap: 8px;
}
.hub-emoji { font-size: 22px; }
.hub-title span:last-child { color: #58a6ff; }

.selected-counter { color: #8b949e; font-size: 13px; }
.selected-counter strong { color: #3fb950; }

/* 卡牌模板条 */
.card-templates-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.template-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #161b22;
  border: 1px solid #30363d;
  padding: 8px 14px;
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.template-pill:hover { border-color: #8b949e; }
.template-pill.active { transform: scale(1.05); }
.template-pill.common.active { border-color: #8b949e; background: rgba(139,148,158,0.1); }
.template-pill.rare.active { border-color: #58a6ff; background: rgba(88,166,255,0.1); }
.template-pill.epic.active { border-color: #bc8cff; background: rgba(188,140,255,0.1); }
.template-pill.legendary.active { border-color: #d29922; background: rgba(210,153,34,0.1); }

.pill-rarity-dot {
  width: 8px; height: 8px; border-radius: 50%;
}
.pill-rarity-dot.common { background: #8b949e; }
.pill-rarity-dot.rare { background: #58a6ff; }
.pill-rarity-dot.epic { background: #bc8cff; }
.pill-rarity-dot.legendary { background: #d29922; }

.pill-name { color: #e6edf3; font-weight: 500; }
.pill-points { color: #3fb950; font-size: 11px; }

/* 头像墙 */
.avatar-wall-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 14px;
  min-height: 120px;
}

.student-avatar-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px 10px;
  text-align: center;
  cursor: pointer;
  position: relative;
  transition: all 0.2s;
}
.student-avatar-card:hover { border-color: #8b949e; }
.student-avatar-card.is-selected {
  border-color: #3fb950;
  background: rgba(63,185,80,0.05);
  box-shadow: 0 0 12px rgba(63,185,80,0.15);
}

.avatar-circle {
  width: 44px; height: 44px;
  border-radius: 50%;
  margin: 0 auto 10px;
  line-height: 44px;
  font-size: 18px;
  font-weight: bold;
  color: #fff;
}
.s-name { display: block; font-size: 13px; font-weight: 600; color: #c9d1d9; }
.s-id { font-size: 11px; color: #6e7681; }

.check-mark {
  position: absolute;
  top: 6px; right: 6px;
  background: #3fb950; color: #fff;
  width: 18px; height: 18px;
  border-radius: 50%;
  font-size: 11px; line-height: 18px;
  display: none;
}
.is-selected .check-mark { display: block; }

/* 底部发卡 */
.dock-action-bar {
  position: fixed;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
}

.laser-fire-btn {
  background: #238636;
  color: #fff;
  border: 1px solid rgba(240,246,252,0.1);
  padding: 14px 36px;
  border-radius: 30px;
  font-size: 15px;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 4px 24px rgba(35,134,54,0.4);
  transition: background 0.2s, transform 0.15s;
}
.laser-fire-btn:hover { background: #2ea043; transform: translateY(-1px); }
.laser-fire-btn:disabled { background: #21262d; color: #8b949e; cursor: not-allowed; box-shadow: none; }

/* 盲盒弹窗 */
.blindbox-content { text-align: center; padding: 10px 0; }

.blindbox-card-reveal {
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 16px;
  position: relative;
  overflow: hidden;
}
.blindbox-card-reveal.legendary {
  background: linear-gradient(135deg, #2a1f0a, #3d2e0a);
  border: 1px solid #d29922;
}
.blindbox-card-reveal.epic {
  background: linear-gradient(135deg, #1a1430, #2a1f4a);
  border: 1px solid #bc8cff;
}
.blindbox-card-reveal.rare {
  background: linear-gradient(135deg, #0c1b30, #142d4a);
  border: 1px solid #58a6ff;
}
.blindbox-card-reveal.common {
  background: linear-gradient(135deg, #1a1a1a, #2a2a2a);
  border: 1px solid #8b949e;
}

.rarity-glow {
  position: absolute;
  top: -30px; left: -30px; right: -30px; bottom: -30px;
  opacity: 0.15;
  pointer-events: none;
}
.rarity-glow.legendary { background: radial-gradient(circle, #d29922, transparent 70%); }
.rarity-glow.epic { background: radial-gradient(circle, #bc8cff, transparent 70%); }

.card-display-name {
  font-size: 24px; font-weight: bold;
  color: #e6edf3;
  margin-bottom: 4px;
}
.card-rarity-tag {
  display: inline-block;
  padding: 1px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(255,255,255,0.08);
  color: #8b949e;
}

.ai-letter-section h4 {
  color: #58a6ff;
  font-size: 13px;
  margin: 0 0 8px 0;
  font-weight: 600;
}
.letter-text {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #c9d1d9;
  text-align: left;
  white-space: pre-line;
}
.share-btn {
  margin-top: 10px;
  background: #1f6feb;
  color: #fff;
  border: none;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}
.share-btn:hover { background: #388bfd; }

.skeleton-loader {
  color: #8b949e;
  font-size: 14px;
  text-align: center;
  padding: 40px;
}
</style>

<style>
.blindbox-dark-dialog {
  background: #0d1117 !important;
  border: 1px solid #30363d !important;
  border-radius: 12px !important;
}
.blindbox-dark-dialog .el-dialog__header {
  color: #e6edf3 !important;
}
.blindbox-dark-dialog .el-dialog__title {
  color: #e6edf3 !important;
}
.blindbox-dark-dialog .el-dialog__close {
  color: #8b949e !important;
}
</style>
