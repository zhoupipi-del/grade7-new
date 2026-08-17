<!--
  WINGS 教研 · AI 作文批改
  =========================
  路径：frontend/src/views/research-ai/EssayGrader.vue
  路由：/research-ai/essay
  - 同步调用后端 /research_ai/essay/grade（约 30-60 秒，前端 loading）
  - 结果落库，教师可复核改分
  - 标注"AI 初评，教师复核为准"
-->
<template>
  <div class="essay-grader">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>📝 AI 作文批改</span>
          <el-tag type="info" size="small">AI 初评 · 教师复核为准</el-tag>
        </div>
      </template>

      <el-radio-group v-model="form.subject" size="large" style="margin-bottom: 16px">
        <el-radio-button label="chinese">📖 语文作文</el-radio-button>
        <el-radio-button label="english">🔤 English Essay</el-radio-button>
      </el-radio-group>

      <el-form :model="form" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="年级">
              <el-select v-model="form.grade" style="width: 100%">
                <el-option v-for="g in grades" :key="g" :label="g" :value="g" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="总分">
              <el-select v-model="form.total_score_config" style="width: 100%">
                <el-option :value="50" label="50分" />
                <el-option :value="60" label="60分（中考标准）" />
                <el-option :value="40" label="40分" />
                <el-option :value="100" label="100分" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="学生姓名">
              <el-input v-model="form.student_name" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="学号">
              <el-input v-model="studentIdInput" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="作文题面">
          <el-input
            v-model="form.essay_prompt"
            type="textarea"
            :rows="4"
            placeholder="粘贴题目+材料+要求"
          />
        </el-form-item>
        <el-form-item label="学生作文">
          <el-input
            v-model="form.essay_text"
            type="textarea"
            :rows="10"
            placeholder="粘贴学生作文文本（支持OCR后粘贴）"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="评分标准">
          <el-input
            v-model="form.rubric"
            type="textarea"
            :rows="3"
            placeholder="留空则使用中考标准预设，可自定义覆盖"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" @click="submitGrade" :loading="grading">
            🚀 开始 AI 批改
          </el-button>
          <el-button size="large" @click="loadSample">📋 载入示例</el-button>
          <el-button size="large" @click="clearAll">🗑️ 清空</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 结果 -->
    <el-card v-if="result" shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>批改结果</span>
          <div>
            <el-button size="small" @click="exportDoc">📄 导出Word</el-button>
            <el-button size="small" @click="openReview">✏️ 教师复核</el-button>
          </div>
        </div>
      </template>

      <div class="score-hero">
        <div class="total">
          {{ result.ai_total_score }}<small> / {{ result.total_score_config }}</small>
        </div>
        <div class="grade-label">{{ result.ai_grade_label }}</div>
      </div>

      <el-row :gutter="12" style="margin: 16px 0">
        <el-col v-for="(v, k) in result.ai_dimensions" :key="k" :span="4" :xs="12">
          <div class="dim-card">
            <div class="dim-name">{{ dimLabel(String(k)) }}</div>
            <div class="dim-score">
              {{ v }}<small>/{{ dimMax(String(k)) }}</small>
            </div>
            <el-progress
              :percentage="Math.min(100, (Number(v) / dimMax(String(k))) * 100)"
              :show-text="false"
            />
          </div>
        </el-col>
      </el-row>

      <h3>逐段批注</h3>
      <div
        v-for="(a, i) in result.ai_annotations"
        :key="i"
        class="anno"
        :class="a.type"
      >
        <div class="quote">"{{ a.quote }}"</div>
        <div>
          <el-tag size="small" :type="annoTagType(a.type)">{{ annoTypeLabel(a.type) }}</el-tag>
          {{ a.comment }}
        </div>
        <div v-if="a.suggestion" class="suggest">→ {{ a.suggestion }}</div>
      </div>

      <template v-if="result.subject === 'english' && result.ai_grammar_errors?.length">
        <h3>语法/用词错误清单</h3>
        <el-table :data="result.ai_grammar_errors" border size="small">
          <el-table-column prop="original" label="错误原句">
            <template #default="{ row }">
              <span style="color: #dc2626; text-decoration: line-through">{{ row.original }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="error_type" label="类型" width="120" />
          <el-table-column prop="explanation" label="说明" min-width="200" />
          <el-table-column prop="correction" label="正确表达">
            <template #default="{ row }">
              <span style="color: #047857; font-weight: 600">{{ row.correction }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <h3>总体评语</h3>
      <div class="comment-box">{{ result.ai_comment }}</div>
      <div v-if="result.ai_chinese_summary" style="margin-top: 10px">
        <strong style="color: #047857">中文概要：</strong>
        <div class="comment-box" style="background: #d1fae5">{{ result.ai_chinese_summary }}</div>
      </div>

      <h3>修改后范文（基于学生原文润色）</h3>
      <div class="refined">{{ result.ai_refined_essay }}</div>

      <h3>提升建议</h3>
      <ol>
        <li v-for="(t, i) in result.ai_tips" :key="i">{{ t }}</li>
      </ol>

      <div class="disclaimer">
        本结果由 AI 初评生成，仅供教师参考，最终成绩与评语请以教师复核为准。
      </div>
    </el-card>

    <!-- 历史 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>批改记录</span>
          <el-button size="small" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table :data="history" border size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="学科" width="80">
          <template #default="{ row }">{{ row.subject === 'english' ? '英语' : '语文' }}</template>
        </el-table-column>
        <el-table-column prop="grade" label="年级" width="110" />
        <el-table-column prop="student_name" label="学生" width="100" />
        <el-table-column label="AI分" width="80">
          <template #default="{ row }">{{ row.ai_total_score }}/{{ row.total_score_config }}</template>
        </el-table-column>
        <el-table-column label="终评" width="80">
          <template #default="{ row }">{{ row.final_score ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.review_status === 'reviewed' ? 'success' : 'warning'" size="small">
              {{ row.review_status === 'reviewed' ? '已复核' : '待复核' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewRecord(row)">回看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="reviewDialog" title="教师复核" width="500px">
      <el-form label-width="80px">
        <el-form-item label="最终分数">
          <el-input-number
            v-model="review.final_score"
            :min="0"
            :max="result?.total_score_config || 100"
          />
          <span style="margin-left: 10px; color: #909399">留空则采纳 AI 评分</span>
        </el-form-item>
        <el-form-item label="教师评语">
          <el-input v-model="review.teacher_comment" type="textarea" :rows="5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button type="primary" @click="submitReview">确认复核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const grades = ['七年级', '八年级', '九年级']
const form = reactive({
  subject: 'chinese',
  grade: '八年级',
  total_score_config: 60,
  student_id: undefined as number | undefined,
  student_name: '',
  essay_prompt: '',
  essay_text: '',
  rubric: '',
})
const studentIdInput = ref('')
const grading = ref(false)
const result = ref<any>(null)
const history = ref<any[]>([])
const reviewDialog = ref(false)
const review = reactive({
  final_score: undefined as number | undefined,
  teacher_comment: '',
})

async function submitGrade() {
  if (!form.essay_prompt.trim()) {
    ElMessage.warning('请填写作文题面')
    return
  }
  if (!form.essay_text.trim()) {
    ElMessage.warning('请粘贴学生作文')
    return
  }
  form.student_id = studentIdInput.value ? Number(studentIdInput.value) : undefined
  grading.value = true
  result.value = null
  try {
    const data = await request.post<any>('/research_ai/essay/grade', { ...form })
    result.value = data
    if (data.ai_grade_label === 'ERROR') {
      ElMessage.error(data.ai_comment || 'AI 批改失败')
    } else {
      ElMessage.success('批改完成')
    }
    loadHistory()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '批改失败')
  } finally {
    grading.value = false
  }
}

function loadSample() {
  if (form.subject === 'chinese') {
    form.grade = '八年级'
    form.total_score_config = 60
    form.student_name = '李明'
    studentIdInput.value = '20240815'
    form.essay_prompt =
      '生活中总有一些人让我们感动。请以"那一刻，我长大了"为题写一篇记叙文，不少于600字。'
    form.essay_text =
      '那一刻，我长大了\n\n一直以来我都是家里的小皇帝……（示例作文，请替换为真实学生作文）'
  } else {
    form.grade = '八年级'
    form.total_score_config = 60
    form.student_name = 'Wang Mei'
    studentIdInput.value = '20240822'
    form.essay_prompt =
      'Suppose you are Li Hua. Write an email to your pen pal Peter about your favorite Chinese traditional festival. 80-100 words.'
    form.essay_text =
      "Dear Peter,\n\nHow is it going? I'm glad to hear that you are interesting in Chinese traditional festivals..."
  }
}

function clearAll() {
  form.essay_prompt = ''
  form.essay_text = ''
  form.rubric = ''
  form.student_name = ''
  studentIdInput.value = ''
  result.value = null
}

async function loadHistory() {
  try {
    const data = await request.get<any[]>('/research_ai/essay/records', {
      params: { limit: 20 },
    })
    history.value = data || []
  } catch {
    /* ignore */
  }
}

async function viewRecord(row: any) {
  const data = await request.get<any>(`/research_ai/essay/records/${row.id}`)
  result.value = data
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openReview() {
  if (!result.value) return
  review.final_score = result.value.final_score ?? undefined
  review.teacher_comment = result.value.teacher_comment || ''
  reviewDialog.value = true
}

async function submitReview() {
  if (!result.value) return
  const payload: any = {}
  if (review.final_score != null) payload.final_score = review.final_score
  if (review.teacher_comment) payload.teacher_comment = review.teacher_comment
  await request.post(`/research_ai/essay/records/${result.value.id}/review`, payload)
  ElMessage.success('复核已保存')
  reviewDialog.value = false
  await loadHistory()
  const data = await request.get<any>(`/research_ai/essay/records/${result.value.id}`)
  result.value = data
}

function exportDoc() {
  const r = result.value
  if (!r) return
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html400000">
<head><meta charset="utf-8"><title>作文批改报告</title>
<style>body{font-family:宋体;font-size:14px;line-height:1.8;}h1,h2{font-family:黑体;} .score{font-size:36px;color:#2563eb;text-align:center;font-weight:bold;} .refined{background:#f9fafb;border:1px dashed #ccc;padding:12px;white-space:pre-wrap;}</style>
</head><body>
<h1 style="text-align:center;">作文批改报告</h1>
<p style="text-align:center;">学生：${r.student_name || '—'} | ${r.subject === 'english' ? '英语' : '语文'} | ${r.grade} | ${new Date().toLocaleString('zh-CN')}</p>
<h2>评分：<span class="score">${r.ai_total_score}/${r.total_score_config}</span></h2>
<p style="text-align:center;"><strong>${r.ai_grade_label || ''}</strong></p>
<h2>总体评语</h2><p>${r.ai_comment || ''}</p>
<h2>修改后范文</h2><div class="refined">${r.ai_refined_essay || ''}</div>
<h2>提升建议</h2><ol>${(r.ai_tips || []).map((t: string) => `<li>${t}</li>`).join('')}</ol>
<p style="text-align:center;color:#666;margin-top:30px;border-top:1px solid #ccc;padding-top:10px;">AI 初评，教师复核为准 · WINGS 教研助手</p>
</body></html>`
  const blob = new Blob(['\ufeff' + html], { type: 'application/msword' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${r.student_name || '学生'}_作文批改.doc`
  a.click()
  URL.revokeObjectURL(url)
}

function dimLabel(k: string) {
  const map: any = {
    content: '内容',
    expression: '表达',
    structure: '结构',
    handwriting: '书写',
    development: '发展等级',
    language_accuracy: '语言准确',
    vocabulary_syntax: '词汇句式',
    organization: '组织结构',
  }
  return map[k] || k
}
function dimMax(k: string) {
  const isEn = result.value?.subject === 'english'
  const total = result.value?.total_score_config || 60
  // 与后端 services_essay.py RUBRIC_CONFIGS 完全一致的维度上限
  const cnConfigs: Record<number, any> = {
    50:  { content: 20, expression: 20, structure: 0, handwriting: 5, development: 5 },
    60:  { content: 20, expression: 20, structure: 0, handwriting: 5, development: 15 },
    40:  { content: 15, expression: 15, structure: 0, handwriting: 5, development: 5 },
    100: { content: 30, expression: 30, structure: 15, handwriting: 10, development: 15 },
  }
  const enConfigs: Record<number, any> = {
    50:  { content: 15, language_accuracy: 15, vocabulary_syntax: 10, organization: 5, handwriting: 5 },
    60:  { content: 18, language_accuracy: 18, vocabulary_syntax: 12, organization: 7, handwriting: 5 },
    40:  { content: 12, language_accuracy: 12, vocabulary_syntax: 8, organization: 4, handwriting: 4 },
    100: { content: 30, language_accuracy: 25, vocabulary_syntax: 20, organization: 15, handwriting: 10 },
  }
  const map = isEn ? enConfigs[total] || enConfigs[60] : cnConfigs[total] || cnConfigs[60]
  return map[k] ?? 20
}
function annoTagType(t: string) {
  return ({ highlight: 'success', issue: 'danger', suggestion: 'primary' } as any)[t] || 'info'
}
function annoTypeLabel(t: string) {
  return ({ highlight: '亮点', issue: '问题', suggestion: '建议' } as any)[t] || t
}
function fmt(s: string) {
  return s ? new Date(s).toLocaleString('zh-CN') : ''
}

onMounted(loadHistory)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.score-hero {
  text-align: center;
  padding: 24px;
  background: linear-gradient(135deg, #dbeafe, #d1fae5);
  border-radius: 8px;
}
.score-hero .total {
  font-size: 3rem;
  font-weight: 800;
  color: #2563eb;
}
.score-hero .total small {
  font-size: 1.2rem;
  color: #6b7280;
  font-weight: 400;
}
.grade-label {
  font-size: 1rem;
  color: #374151;
  margin-top: 4px;
}
.dim-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}
.dim-name {
  font-size: 0.85rem;
  color: #374151;
  font-weight: 600;
}
.dim-score {
  font-size: 1.5rem;
  font-weight: 700;
  color: #2563eb;
}
.dim-score small {
  font-size: 0.9rem;
  color: #6b7280;
  font-weight: 400;
}
.anno {
  border-left: 3px solid #2563eb;
  background: #f9fafb;
  padding: 10px 14px;
  margin-bottom: 10px;
  border-radius: 0 6px 6px 0;
}
.anno.highlight {
  border-left-color: #047857;
  background: #d1fae5;
}
.anno.issue {
  border-left-color: #dc2626;
  background: #fee2e2;
}
.anno .quote {
  font-style: italic;
  color: #374151;
  margin-bottom: 4px;
}
.anno .suggest {
  color: #1d4ed8;
  margin-top: 4px;
  font-size: 0.9rem;
}
.comment-box {
  background: #dbeafe;
  border-radius: 6px;
  padding: 14px 18px;
  line-height: 1.8;
}
.refined {
  background: #f9fafb;
  border: 1px dashed #d1d5db;
  border-radius: 6px;
  padding: 16px;
  white-space: pre-wrap;
  line-height: 1.8;
}
.disclaimer {
  text-align: center;
  color: #6b7280;
  font-size: 0.82rem;
  border-top: 1px solid #e5e7eb;
  padding-top: 10px;
  margin-top: 20px;
}
h3 {
  font-size: 1rem;
  margin: 18px 0 10px;
  padding-bottom: 4px;
  border-bottom: 2px solid #dbeafe;
}
</style>
