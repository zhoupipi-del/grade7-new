<template>
  <div class="student-coach-container">
    <!-- ═══ 页面标题 ═══ -->
    <div class="page-header">
      <div class="page-title-row">
        <el-icon class="title-icon" :size="24"><Reading /></el-icon>
        <h2 class="page-title">审题助手 — AI 逐句翻译</h2>
        <el-tag type="success" effect="dark" size="small">P0 审题翻译</el-tag>
      </div>
      <p class="page-subtitle">
        把数学应用题逐句翻译成数学表达式，帮你理清题目中的数量关系。不直接给答案，教你审题方法。
      </p>
    </div>

    <!-- ═══ 主内容区：双栏布局 ═══ -->
    <el-row :gutter="20">
      <!-- 左侧：输入区 + 结果区 -->
      <el-col :span="16">
        <!-- 输入卡片 -->
        <el-card class="input-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">输入数学题目</span>
              <el-dropdown trigger="click" @command="loadDemo">
                <el-button type="primary" plain size="small">
                  试试示例 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="(demo, idx) in DEMO_QUESTIONS"
                      :key="idx"
                      :command="demo"
                    >
                      {{ demo.title }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>

          <el-form :model="form" label-position="top" class="input-form">
            <!-- 题目输入 -->
            <el-form-item label="数学应用题">
              <el-input
                v-model="form.question_text"
                type="textarea"
                :rows="5"
                placeholder="请在此粘贴或输入数学应用题全文&#10;&#10;例如：小明和小红从相距 120 公里的两地同时出发相向而行，小明骑自行车速度为每小时 15 公里，小红步行速度为每小时 5 公里，请问他们几小时后相遇？"
                :maxlength="5000"
                show-word-limit
                resize="vertical"
              />
            </el-form-item>

            <!-- 年级和知识点选择 -->
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="年级">
                  <el-select v-model="form.grade_level" placeholder="选择年级" style="width: 100%">
                    <el-option
                      v-for="g in GRADE_OPTIONS"
                      :key="g.value"
                      :label="g.label"
                      :value="g.value"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="知识点 (可选)">
                  <el-select
                    v-model="selectedCategory"
                    placeholder="知识点分类"
                    style="width: 100%"
                    clearable
                    @change="onCategoryChange"
                  >
                    <el-option
                      v-for="cat in categoryOptions"
                      :key="cat.value"
                      :label="cat.label"
                      :value="cat.value"
                    />
                  </el-select>
                  <el-select
                    v-if="selectedCategory"
                    v-model="form.knowledge_point"
                    placeholder="具体知识点"
                    style="width: 100%; margin-top: 8px"
                    clearable
                  >
                    <el-option
                      v-for="pt in currentPoints"
                      :key="pt"
                      :label="pt"
                      :value="pt"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 操作按钮 -->
            <el-form-item>
              <el-button
                type="primary"
                size="large"
                :loading="translating"
                :disabled="!canSubmit"
                @click="handleTranslate"
                class="translate-btn"
              >
                <el-icon><MagicStick /></el-icon>
                {{ translating ? 'AI 正在逐句分析...' : '开始翻译' }}
              </el-button>
              <el-button
                v-if="!translating"
                size="large"
                @click="handleClear"
                :disabled="!form.question_text && !result"
              >
                清空重置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ═══ 结果区 ═══ -->

        <!-- 加载态 -->
        <el-card v-if="translating" class="result-card" shadow="never">
          <div class="loading-skeleton">
            <div class="skeleton-header">
              <el-skeleton :rows="1" animated />
            </div>
            <div v-for="i in 4" :key="i" class="skeleton-row">
              <el-skeleton :rows="1" animated :throttle="500" />
            </div>
            <div class="skeleton-vars">
              <el-skeleton :rows="1" animated />
            </div>
          </div>
        </el-card>

        <!-- 错误态 -->
        <el-alert
          v-if="errorMsg"
          :title="errorMsg"
          type="error"
          show-icon
          :closable="true"
          @close="errorMsg = ''"
          class="error-alert"
        >
          <template #default>
            <el-button type="primary" size="small" @click="handleTranslate" style="margin-top: 8px">
              重试翻译
            </el-button>
          </template>
        </el-alert>

        <!-- 空态 (初次进入) -->
        <el-empty
          v-if="!result && !translating && !errorMsg"
          description="输入一道数学应用题，点击「开始翻译」，AI 会逐句帮你分析题目"
          :image-size="120"
          class="empty-holder"
        >
          <template #image>
            <el-icon :size="80" color="#c0c4cc"><Reading /></el-icon>
          </template>
        </el-empty>

        <!-- 成功态：逐句翻译展示 -->
        <div v-if="result && !translating" class="result-area">
          <!-- 逐句翻译卡片流 -->
          <div
            v-for="(item, idx) in result.translations"
            :key="idx"
            class="sentence-card-wrapper"
            :style="{ animationDelay: `${idx * 0.12}s` }"
          >
            <el-card class="sentence-card" shadow="hover">
              <div class="sentence-step">
                <div class="step-number">{{ idx + 1 }}</div>
                <div class="step-content">
                  <!-- 原句 -->
                  <div class="original-text">
                    <el-tag type="info" size="small" effect="plain">原句</el-tag>
                    <span class="text-content">{{ item.sentence }}</span>
                  </div>

                  <!-- 数学表达式 (核心高亮) -->
                  <div class="math-box">
                    <el-tag type="warning" size="small" effect="dark">数学表达</el-tag>
                    <div class="math-expression">
                      <code>{{ item.math_expression }}</code>
                    </div>
                  </div>

                  <!-- 中文解释 -->
                  <div class="explain-text">
                    <el-icon class="explain-icon"><ChatDotRound /></el-icon>
                    <span>{{ item.explanation }}</span>
                  </div>
                </div>
              </div>
            </el-card>
          </div>

          <!-- ═══ 变量汇总面板 ═══ -->
          <el-card
            v-if="result.suggested_variables && Object.keys(result.suggested_variables).length > 0"
            class="variable-panel"
            shadow="hover"
          >
            <template #header>
              <div class="card-header">
                <span class="card-title">变量声明</span>
                <el-tag type="warning" size="small" effect="plain">
                  {{ Object.keys(result.suggested_variables).length }} 个变量
                </el-tag>
              </div>
            </template>
            <div class="variable-grid">
              <div
                v-for="(meaning, variable) in result.suggested_variables"
                :key="variable"
                class="variable-item"
              >
                <span class="var-symbol">{{ variable }}</span>
                <el-divider direction="vertical" />
                <span class="var-meaning">{{ meaning }}</span>
              </div>
            </div>
            <div class="variable-tip">
              <el-icon><InfoFilled /></el-icon>
              使用中文单字变量（如 明、红、长、宽）降低认知门槛，让数学更直观
            </div>
          </el-card>

          <!-- 翻译元信息 -->
          <div class="meta-footer">
            <span v-if="result.translation_id">
              <el-icon><Clock /></el-icon> 翻译 ID: {{ result.translation_id }}
            </span>
          </div>
        </div>
      </el-col>

      <!-- ═══ 右侧：历史记录 ═══ -->
      <el-col :span="8">
        <el-card class="history-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">翻译历史</span>
              <el-button text size="small" @click="loadHistory" :loading="historyLoading">
                <el-icon><Refresh /></el-icon> 刷新
              </el-button>
            </div>
          </template>

          <div v-if="historyLoading" class="history-loading">
            <el-skeleton :rows="5" animated />
          </div>

          <el-empty
            v-else-if="historyItems.length === 0"
            description="暂无翻译记录"
            :image-size="60"
          />

          <div v-else class="history-list">
            <div
              v-for="item in historyItems"
              :key="item.id"
              class="history-item"
              @click="loadHistoryItem(item)"
            >
              <div class="history-question">
                {{ truncate(item.question_text, 60) }}
              </div>
              <div class="history-meta">
                <el-tag size="small" type="info">{{ gradeShortLabel(item.grade_level) }}</el-tag>
                <span v-if="item.knowledge_point" class="history-point">
                  {{ item.knowledge_point }}
                </span>
                <span class="history-time">{{ formatTime(item.created_at) }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Reading,
  ArrowDown,
  MagicStick,
  ChatDotRound,
  InfoFilled,
  Clock,
  Refresh,
} from '@element-plus/icons-vue'
import {
  translateQuestion,
  getTranslationHistory,
  GRADE_OPTIONS,
  KNOWLEDGE_CATEGORIES,
  gradeShortLabel,
  type TranslateResponse,
  type TranslationHistoryItem,
} from '@/api/teachMath'

// ═════════════════════════════════════════════
// 表单状态
// ═════════════════════════════════════════════

const form = reactive({
  question_text: '',
  grade_level: '八年级下',
  knowledge_point: '',
})

const selectedCategory = ref<string>('')

const categoryOptions = computed(() =>
  Object.entries(KNOWLEDGE_CATEGORIES).map(([key, cat]) => ({
    label: cat.label,
    value: key,
  }))
)

const currentPoints = computed(() => {
  if (!selectedCategory.value) return []
  const cat = KNOWLEDGE_CATEGORIES[selectedCategory.value as keyof typeof KNOWLEDGE_CATEGORIES]
  return cat ? [...cat.points] : []
})

const canSubmit = computed(
  () => form.question_text.trim().length >= 5 && form.grade_level
)

function onCategoryChange(_val: string) {
  // 切换知识点分类时清空具体知识点选择
  form.knowledge_point = ''
}

// ═════════════════════════════════════════════
// 翻译状态
// ═════════════════════════════════════════════

const translating = ref(false)
const result = ref<TranslateResponse | null>(null)
const errorMsg = ref('')

async function handleTranslate() {
  if (!canSubmit.value || translating.value) return

  translating.value = true
  errorMsg.value = ''
  result.value = null

  try {
    const payload: any = {
      question_text: form.question_text.trim(),
      grade_level: form.grade_level,
    }
    if (form.knowledge_point) {
      payload.knowledge_point = form.knowledge_point
    }

    const res = await translateQuestion(payload)
    result.value = res

    // 翻译成功后刷新历史
    loadHistory()

    ElMessage.success(`AI 完成 ${res.translations.length} 句翻译`)
  } catch (err: any) {
    console.error('[StudentCoach] translate failed', err)
    const detail = err?.response?.data?.detail || err?.message || ''
    errorMsg.value = detail ? `翻译失败：${detail}` : '翻译请求失败，请检查网络后重试'
    ElMessage.error('翻译失败，请重试')
  } finally {
    translating.value = false
  }
}

function handleClear() {
  form.question_text = ''
  form.knowledge_point = ''
  selectedCategory.value = ''
  result.value = null
  errorMsg.value = ''
}

// ═════════════════════════════════════════════
// 示例题目
// ═════════════════════════════════════════════

const DEMO_QUESTIONS = [
  {
    title: '行程相遇问题',
    text: '小明和小红从相距 120 公里的两地同时出发相向而行，小明骑自行车速度为每小时 15 公里，小红步行速度为每小时 5 公里，请问他们几小时后相遇？',
    grade: '八年级下',
    point: '行程问题',
    category: 'word_problems',
  },
  {
    title: '工程合作问题',
    text: '一项工程，甲单独做需要 12 天完成，乙单独做需要 18 天完成。如果两人合作，需要多少天完成？',
    grade: '八年级下',
    point: '工程问题',
    category: 'word_problems',
  },
  {
    title: '利润打折问题',
    text: '某商店进了一批商品，进价为每件 80 元。按 30% 的利润率标价，后又打九折出售，每件可获利多少元？',
    grade: '八年级下',
    point: '利润问题',
    category: 'word_problems',
  },
  {
    title: '一元一次方程',
    text: '某数的 3 倍加上 5 等于这个数的 7 倍减去 11，求这个数。',
    grade: '八年级上',
    point: '一元一次方程',
    category: 'algebra',
  },
]

function loadDemo(demo: (typeof DEMO_QUESTIONS)[number]) {
  form.question_text = demo.text
  form.grade_level = demo.grade
  form.knowledge_point = demo.point
  selectedCategory.value = demo.category
  result.value = null
  errorMsg.value = ''
}

// ═════════════════════════════════════════════
// 历史记录
// ═════════════════════════════════════════════

const historyItems = ref<TranslationHistoryItem[]>([])
const historyLoading = ref(false)

async function loadHistory() {
  historyLoading.value = true
  try {
    historyItems.value = await getTranslationHistory(20)
  } catch (err) {
    console.error('[StudentCoach] load history failed', err)
  } finally {
    historyLoading.value = false
  }
}

function loadHistoryItem(item: TranslationHistoryItem) {
  form.question_text = item.question_text
  form.grade_level = item.grade_level
  form.knowledge_point = item.knowledge_point || ''

  // 回填知识点分类
  selectedCategory.value = ''
  if (item.knowledge_point) {
    for (const [key, cat] of Object.entries(KNOWLEDGE_CATEGORIES)) {
      if ((cat.points as readonly string[]).includes(item.knowledge_point)) {
        selectedCategory.value = key
        break
      }
    }
  }

  // 如果 history item 里有 llm_response，直接渲染
  const llm = item.llm_response as Record<string, unknown>
  if (llm && Array.isArray(llm.translations)) {
    result.value = {
      translations: llm.translations as TranslateResponse['translations'],
      suggested_variables: (llm.suggested_variables || {}) as TranslateResponse['suggested_variables'],
      raw_llm_response: llm,
      translation_id: item.id,
    }
  } else {
    result.value = null
  }

  errorMsg.value = ''

  // 滚动到顶部查看结果
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ═════════════════════════════════════════════
// 工具函数
// ═════════════════════════════════════════════

function truncate(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function formatTime(isoStr: string | null): string {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return ''
  }
}

// ═════════════════════════════════════════════
// 生命周期
// ═════════════════════════════════════════════

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
/* ═══ 容器 ═══ */
.student-coach-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 4px;
}

/* ═══ 页面标题 ═══ */
.page-header {
  margin-bottom: 24px;
}

.page-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  color: #67c23a;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}

.page-subtitle {
  margin: 8px 0 0 34px;
  color: #909399;
  font-size: 14px;
  line-height: 1.6;
}

/* ═══ 卡片通用 ═══ */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  color: #303133;
  font-size: 15px;
}

.input-card {
  margin-bottom: 20px;
}

.input-form {
  margin-top: 4px;
}

.translate-btn {
  min-width: 180px;
}

/* ═══ 加载骨架 ═══ */
.result-card {
  margin-bottom: 20px;
}

.loading-skeleton {
  padding: 10px 0;
}

.skeleton-header {
  margin-bottom: 20px;
}

.skeleton-row {
  margin-bottom: 16px;
}

.skeleton-vars {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
}

/* ═══ 错误态 ═══ */
.error-alert {
  margin-bottom: 20px;
}

/* ═══ 空态 ═══ */
.empty-holder {
  padding: 60px 0;
  background: #fff;
  border: 1px solid #e6ebf5;
  border-radius: 4px;
}

/* ═══ 结果区：逐句卡片流 ═══ */
.result-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sentence-card-wrapper {
  animation: slideIn 0.4s ease both;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.sentence-card {
  border-left: 4px solid #409eff;
  transition: box-shadow 0.2s, border-left-color 0.2s;
}

.sentence-card:hover {
  border-left-color: #67c23a;
}

.sentence-step {
  display: flex;
  gap: 16px;
}

.step-number {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #66b1ff);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

/* 原句 */
.original-text {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.original-text .text-content {
  color: #606266;
  font-size: 14px;
  line-height: 1.7;
  flex: 1;
}

/* 数学表达 (核心高亮区) */
.math-box {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.math-expression {
  flex: 1;
}

.math-expression code {
  display: block;
  background: linear-gradient(135deg, #fdf6ec, #fef0d9);
  border: 1px solid #f3d19e;
  border-radius: 6px;
  padding: 12px 16px;
  font-family: 'Courier New', 'Source Code Pro', 'Menlo', monospace;
  font-size: 16px;
  font-weight: 700;
  color: #d48806;
  letter-spacing: 0.5px;
  word-break: break-all;
}

/* 解释 */
.explain-text {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: #606266;
  font-size: 14px;
  line-height: 1.7;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 6px;
}

.explain-icon {
  margin-top: 2px;
  color: #67c23a;
}

/* ═══ 变量面板 ═══ */
.variable-panel {
  margin-top: 16px;
  border-left: 4px solid #e6a23c;
}

.variable-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.variable-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #fef7e8;
  border: 1px solid #f5dab1;
  border-radius: 8px;
  transition: transform 0.15s;
}

.variable-item:hover {
  transform: translateY(-1px);
}

.var-symbol {
  font-family: 'Courier New', 'Source Code Pro', monospace;
  font-size: 18px;
  font-weight: 800;
  color: #e6a23c;
  min-width: 28px;
  text-align: center;
}

.var-meaning {
  font-size: 13px;
  color: #606266;
}

.variable-tip {
  margin-top: 14px;
  padding: 8px 12px;
  font-size: 12px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fafafa;
  border-radius: 4px;
}

/* ═══ 元信息 ═══ */
.meta-footer {
  margin-top: 8px;
  font-size: 12px;
  color: #c0c4cc;
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}

/* ═══ 历史记录 ═══ */
.history-card {
  position: sticky;
  top: 20px;
  max-height: calc(100vh - 140px);
  overflow: hidden;
}

.history-loading {
  padding: 10px 0;
}

.history-list {
  max-height: calc(100vh - 260px);
  overflow-y: auto;
}

.history-item {
  padding: 12px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
  margin-bottom: 6px;
}

.history-item:hover {
  background: #f5f7fa;
  border-color: #e4e7ed;
}

.history-question {
  font-size: 13px;
  color: #303133;
  line-height: 1.5;
  margin-bottom: 6px;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.history-point {
  font-size: 12px;
  color: #909399;
}

.history-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-left: auto;
}
</style>
