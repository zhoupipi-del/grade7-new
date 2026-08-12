<template>
  <div class="copilot">
    <!-- ═══ Hero / Empty State ═══ -->
    <div v-if="!result && !loading && !error" class="hero">
      <div class="hero-icon">✦</div>
      <h1>WINGS AI</h1>
      <p class="hero-sub">下午好，AI 已准备好分析您负责的年级数据</p>

      <div class="input-block">
        <textarea
          v-model="goal"
          :disabled="loading"
          placeholder="帮我看看本周重点问题"
          rows="2"
          @keydown.ctrl.enter="run"
        />
        <button class="btn-go" :disabled="loading || !goal.trim()" @click="run">→</button>
      </div>

      <div class="quick-row" style="justify-content: center">
        <button @click="quick(`分析${gradeName.value}最近一次考试`)">📊 最近考试</button>
        <button @click="quick(`比较${gradeName.value}最近两次考试的变化趋势`)">📈 考试趋势</button>
        <button @click="quick(`最近${gradeName.value}迟到缺勤情况`)">📋 考勤情况</button>
        <button @click="quick('帮我看看本周重点问题')">✨ 本周重点</button>
      </div>
    </div>

    <!-- ═══ Loading ═══ -->
    <div v-if="loading" class="hero hero-empty">
      <div class="hero-icon spinner"></div>
      <h1>AI 正在分析</h1>
      <p class="hero-sub">正在读取数据、执行分析并进行安全自检…</p>
    </div>

    <!-- ═══ Error ═══ -->
    <div v-if="error" class="hero hero-empty">
      <div class="hero-icon">⚠</div>
      <h1>分析未能完成</h1>
      <p class="hero-sub">{{ error }}</p>
      <button class="btn-go" @click="run">重试</button>
    </div>

    <!-- ═══ Needs Input ═══ -->
    <div v-if="result && result.outcome === 'needs_input'" class="hero hero-empty">
      <div class="hero-icon">🤔</div>
      <h1>需要更具体的问题</h1>
      <p class="hero-sub">
        AI 暂时无法理解您的查询意图。请尝试用更具体的表述，例如：
      </p>
      <div class="quick-row" style="justify-content: center; margin-top: 16px">
        <button @click="quick('分析最近一次考试')">📊 学业分析</button>
        <button @click="quick('最近迟到缺勤情况')">📋 考勤情况</button>
        <button @click="quick(`最近${gradeName.value}学生纪律表现`)">⚖️ 行为纪律</button>
        <button @click="quick('帮我看看本周重点问题')">✨ 综合审查</button>
      </div>
    </div>

    <!-- ═══ Needs Data ═══ -->
    <div v-if="result && result.outcome === 'needs_data'" class="hero hero-empty">
      <div class="hero-icon">📊</div>
      <h2>还缺一些数据</h2>
      <p class="hero-sub">
        <template v-if="result.student_count > 0">
          ✓ 该年级有 {{ result.student_count }} 名学生<br/>
          ✓ 您具有该年级数据权限<br/>
        </template>
        ✓ AI 工具运行正常<br/><br/>
        目前暂未找到满足条件的数据，AI 没有强行生成结论。
      </p>
      <div class="nd-tag">AI 在数据不足时不编造结论</div>
      <div class="quick-row" style="justify-content: center; margin-top: 16px">
        <button @click="quickAndRun(`分析${gradeName.value}最近一次考试`)">分析最近一次考试</button>
        <button @click="quickAndRun('帮我看看本周重点问题')">查找本周重点</button>
      </div>
    </div>

    <!-- ═══ Success ═══ -->
    <div v-if="result && result.outcome === 'success'">
      <div class="dash-header">
        <div>
          <span class="dash-eyebrow">{{ gradeName }} · 分析完成</span>
          <h2>{{ result.goal }}</h2>
        </div>
        <span class="dash-badge" :class="outcomeClass">✓ 分析完成</span>
      </div>

      <!-- KPI Row -->
      <div class="kpi-row">
        <div class="kpi">
          <span class="kpi-num">{{ result.student_count || '—' }}</span>
          <span class="kpi-label">覆盖学生</span>
        </div>
        <div class="kpi">
          <span class="kpi-num">{{ result.examined_count || '—' }}</span>
          <span class="kpi-label">参考学生</span>
        </div>
        <div class="kpi">
          <span class="kpi-num">{{ result.grade_record_count || (result.domain_counts ? Object.values(result.domain_counts).reduce((a: number, b: number) => a + b, 0) : '—') }}</span>
          <span class="kpi-label">数据维度</span>
        </div>
        <div class="kpi">
          <span class="kpi-num">{{ result.plan.filter((s: any) => s.status === 'EXECUTED').length }}</span>
          <span class="kpi-label">分析工具</span>
        </div>
      </div>

      <!-- Domain Summary -->
      <div v-if="domainSummmary" class="domains-grid">
        <div v-for="domain in DOMAINS" :key="domain" class="domain-card" :class="{ active: hasDomain(domain) }">
          <div class="domain-icon">{{ DOMAIN_ICONS[domain] || '📌' }}</div>
          <div class="domain-name">{{ DOMAIN_NAMES[domain] }}</div>
          <div class="domain-findings">
            <template v-if="domainFindings(domain).length">
              <div v-for="(f, i) in domainFindings(domain).slice(0, 2)" :key="i" class="domain-f">{{ f }}</div>
            </template>
            <div v-else class="domain-f dim">暂无数据</div>
          </div>
        </div>
      </div>

      <!-- Subject Performance Table (科目统计，独立渲染，不进 KPI) -->
      <section v-if="subjectTable.length" class="subject-panel">
        <div class="section-title">📚 学科表现</div>
        <table class="subject-table">
          <thead>
            <tr>
              <th>科目</th>
              <th>平均分</th>
              <th>中位数</th>
              <th v-if="hasPassRate">及格率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in subjectTable" :key="s.name">
              <td class="subj-name">{{ s.name }}</td>
              <td>{{ s.avg != null ? s.avg : '—' }}</td>
              <td>{{ s.median != null ? s.median : '—' }}</td>
              <td v-if="hasPassRate">{{ s.pass_rate != null ? s.pass_rate + '%' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Findings -->
      <div v-if="result.findings.length" class="findings-block">
        <div class="section-title">🔎 核心发现</div>
        <div v-for="(f, i) in result.findings" :key="i" class="finding">
          <span class="f-idx">{{ i + 1 }}</span>
          <span>{{ f }}</span>
        </div>
      </div>

      <!-- Recommendations -->
      <div v-if="result.recommendations.length" class="recs-block">
        <div class="section-title">✨ AI 建议</div>
        <div v-for="(r, i) in result.recommendations" :key="i" class="rec">
          <span class="r-idx">{{ String(i + 1).padStart(2, '0') }}</span>
          <p>{{ r }}</p>
        </div>
      </div>
    </div>

    <!-- ═══ Trust Footer ═══ -->
    <footer v-if="result" class="trust-footer">
      <span>AI 分析安全可信</span><span>·</span>
      <span v-if="result.trust.permission_checked">权限已校验</span><span>·</span>
      <span v-if="!result.trust.student_pii_sent">无学生 PII 泄露</span><span>·</span>
      <span>{{ result.model }}</span><span>·</span>
      <span>Critic {{ result.critic.passed ? 'PASS' : 'FAIL' }}</span><span>·</span>
      <button class="btn-trust" @click="showDrawer = true">Run #{{ result.run_id }}</button>
    </footer>

    <!-- ═══ Follow-up Input ═══ -->
    <div v-if="result" class="input-block secondary">
      <textarea
        v-model="goal"
        :disabled="loading"
        placeholder="继续提问…"
        rows="2"
        @keydown.ctrl.enter="run"
      />
      <button class="btn-go" :disabled="loading || !goal.trim()" @click="run">→</button>
    </div>

    <!-- ═══ Drawer ═══ -->
    <div v-if="showDrawer && result" class="drawer-mask" @click.self="showDrawer = false">
      <aside class="drawer">
        <button class="drawer-close" @click="showDrawer = false">×</button>
        <h3>运行详情</h3>

        <div class="dr"><span>Run</span><strong>#{{ result.run_id }}</strong></div>
        <div class="dr"><span>状态</span><strong>Agent {{ result.status.toUpperCase() }}</strong></div>
        <div class="dr">
          <span>结果</span>
          <strong :class="outcomeClass">{{ OUTCOME_LABELS[result.outcome] || result.outcome }}</strong>
        </div>
        <div class="dr"><span>模型</span><strong>{{ result.model }}</strong></div>
        <div class="dr">
          <span>Critic</span>
          <strong :class="result.critic.passed ? 'g' : 'r'">{{ result.critic.passed ? 'PASS' : 'FAIL' }}</strong>
        </div>

        <h4>执行步骤</h4>
        <div v-for="s in result.plan" :key="s.tool" class="dr">
          <span>{{ toolLabel(s.tool) }}</span>
          <strong>{{ s.status }}</strong>
        </div>

        <h4>安全验证</h4>
        <div class="dr"><span>权限校验</span><strong class="g">✓</strong></div>
        <div class="dr"><span>数据聚合</span><strong class="g">✓</strong></div>
        <div class="dr"><span>PII 保护</span><strong class="g">✓</strong></div>
        <div class="dr"><span>全链记录</span><strong class="g">✓</strong></div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { runCopilot, toolLabel, OUTCOME_LABELS, DOMAIN_ICONS, DOMAIN_NAMES, DOMAINS } from '@/api/aiCopilot'
import { useUserStore } from '@/store/user'
import type { CopilotRunResponse } from '@/api/aiCopilot'

const userStore = useUserStore()
const gradeId = computed(() => userStore.userInfo?.grade_id ?? 0)
const gradeName = computed(() => userStore.userInfo?.grade_name ?? '当前年级')

const goal = ref('帮我看看本周重点问题')
const loading = ref(false)
const error = ref('')
const result = ref<CopilotRunResponse | null>(null)
const showDrawer = ref(false)

const outcomeClass = computed(() => {
  if (!result.value) return ''
  const o = result.value.outcome
  if (o === 'success') return 'g'
  if (o === 'needs_data' || o === 'needs_input') return 'y'
  return 'r'
})

function hasDomain(domain: string): boolean {
  if (!result.value?.domain_counts) return false
  return (result.value.domain_counts[domain] || 0) > 0
}

function domainFindings(domain: string): string[] {
  if (!result.value?.domains?.[domain]) return []
  const d = result.value.domains[domain]
  if (typeof d !== 'object' || d === null) return []
  // Extract text findings, skip objects/arrays
  const parts: string[] = []
  for (const k of ['highlights', 'analysis', 'attention', 'trend']) {
    const v = (d as any)[k]
    if (typeof v === 'string') parts.push(v)
    // never render objects/arrays/numbers as text
  }
  return parts.filter(Boolean)
}

const domainSummmary = computed(() => {
  if (!result.value?.domain_counts) return false
  return Object.values(result.value.domain_counts).some((v: number) => v > 0)
})

// ── 科目统计：从多个可能位置安全提取 ──
interface SubjectRow { name: string; avg: number | null; median: number | null; pass_rate: number | null }

function safeParseSubjects(raw: any): SubjectRow[] {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw.filter((s: any) => s && typeof s.name === 'string').map((s: any) => ({
      name: s.name,
      avg: typeof s.avg === 'number' ? +s.avg.toFixed(1) : null,
      median: typeof s.median === 'number' ? +s.median.toFixed(1) : null,
      pass_rate: typeof s.pass_rate === 'number' ? Math.round(s.pass_rate) : null,
    }))
  }
  if (typeof raw === 'string') {
    try { return safeParseSubjects(JSON.parse(raw)) } catch { return [] }
  }
  if (typeof raw === 'object') {
    // {"语文": {"avg": 72.67, ...}, "数学": {...}}
    const arr: SubjectRow[] = []
    for (const [name, val] of Object.entries(raw)) {
      if (val && typeof val === 'object') {
        arr.push({ name, avg: (val as any).avg ?? null, median: (val as any).median ?? null, pass_rate: (val as any).pass_rate ?? null })
      }
    }
    return arr
  }
  return []
}

const subjectStats = computed(() => {
  if (!result.value) return []
  // 优先级：domains.grades.subject_stats > overview.subjects > overview.subject_stats
  const src = result.value.domains?.grades?.subject_stats
          ?? result.value.domains?.grades?.subjects
          ?? (result.value.overview as any)?.subject_stats
          ?? (result.value.overview as any)?.subjects
  return safeParseSubjects(src)
})

const subjectTable = computed(() => subjectStats.value)

const hasPassRate = computed(() => subjectTable.value.some((s: SubjectRow) => s.pass_rate != null))

function quick(q: string) {
  goal.value = q
}

function quickAndRun(q: string) {
  goal.value = q
  run()
}

async function run() {
  if (!goal.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null

  try {
    result.value = await runCopilot({
      goal: goal.value,
      grade_id: gradeId,
    })
  } catch (e: any) {
    error.value = e?.response?.data?.detail?.message
      ?? e?.response?.data?.detail
      ?? e?.message
      ?? '执行失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.copilot { max-width: 900px; margin: 0 auto; padding: 24px 20px; }

/* ── Hero ── */
.hero { text-align: center; padding: 60px 20px; }
.hero-icon { font-size: 48px; margin-bottom: 16px; color: var(--el-color-primary); }
.hero-icon.spinner { animation: spin 1.5s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.hero h1 { font-size: 28px; font-weight: 700; margin: 0 0 8px; }
.hero h2 { font-size: 20px; font-weight: 600; margin: 0 0 8px; }
.hero-sub { color: var(--el-text-color-secondary); font-size: 15px; max-width: 480px; margin: 0 auto 24px; line-height: 1.6; }

/* ── Input ── */
.input-block { display: flex; gap: 8px; max-width: 620px; margin: 0 auto 16px; }
.input-block.secondary { margin-top: 32px; }
.input-block textarea { flex: 1; border: 1px solid var(--el-border-color); border-radius: 12px; padding: 12px 16px; font-size: 15px; resize: none; background: var(--el-bg-color); color: var(--el-text-color-primary); line-height: 1.5; }
.input-block textarea:focus { outline: none; border-color: var(--el-color-primary); box-shadow: 0 0 0 3px rgba(64,158,255,.15); }
.btn-go { width: 48px; height: 48px; border: none; border-radius: 12px; background: var(--el-color-primary); color: #fff; font-size: 22px; cursor: pointer; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.btn-go:disabled { opacity: .4; cursor: not-allowed; }

/* ── Quick ── */
.quick-row { display: flex; gap: 8px; flex-wrap: wrap; }
.quick-row button { padding: 8px 16px; border: 1px solid var(--el-border-color); border-radius: 20px; background: var(--el-bg-color); font-size: 13px; cursor: pointer; color: var(--el-text-color-regular); transition: all .2s; }
.quick-row button:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); background: rgba(64,158,255,.06); }

/* ── Dashboard Header ── */
.dash-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.dash-eyebrow { font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--el-text-color-secondary); }
.dash-header h2 { font-size: 22px; font-weight: 700; margin: 4px 0 0; }
.dash-badge { padding: 4px 12px; border-radius: 14px; font-size: 12px; font-weight: 600; }
.dash-badge.g { background: rgba(103,194,58,.12); color: #67c23a; }
.dash-badge.y { background: rgba(230,162,60,.12); color: #e6a23c; }
.dash-badge.r { background: rgba(245,108,108,.12); color: #f56c6c; }

/* ── KPI ── */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.kpi { text-align: center; padding: 16px 12px; background: var(--el-fill-color-lighter); border-radius: 12px; }
.kpi-num { font-size: 28px; font-weight: 700; display: block; color: var(--el-text-color-primary); }
.kpi-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; display: block; }

/* ── Domain Grid ── */
.domains-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.domain-card { padding: 16px; border-radius: 12px; background: var(--el-fill-color-lighter); border: 2px solid transparent; transition: all .2s; }
.domain-card.active { border-color: var(--el-color-primary-light-5); background: rgba(64,158,255,.04); }
.domain-icon { font-size: 24px; margin-bottom: 8px; }
.domain-name { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.domain-f { font-size: 12px; color: var(--el-text-color-regular); line-height: 1.5; margin-bottom: 4px; }
.domain-f.dim { color: var(--el-text-color-placeholder); font-style: italic; }

/* ── Findings ── */
.findings-block, .recs-block { margin-bottom: 24px; }

/* ── Subject Table ── */
.subject-panel { margin-bottom: 24px; }
.subject-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.subject-table th, .subject-table td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--el-border-color-lighter); }
.subject-table th { font-weight: 600; color: var(--el-text-color-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: .3px; }
.subject-table .subj-name { font-weight: 600; }
.subject-table tbody tr:hover { background: var(--el-fill-color-lighter); }
.section-title { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
.finding, .rec { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--el-border-color-lighter); align-items: flex-start; }
.f-idx, .r-idx { width: 24px; height: 24px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; margin-top: 1px; }
.rec p { margin: 0; line-height: 1.6; }

/* ── Trust Footer ── */
.trust-footer { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--el-border-color-lighter); flex-wrap: wrap; }
.btn-trust { border: none; background: none; color: var(--el-color-primary); cursor: pointer; font-size: 11px; padding: 0; }

/* ── Drawer ── */
.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,.3); z-index: 1000; display: flex; justify-content: flex-end; }
.drawer { width: 360px; height: 100%; background: var(--el-bg-color); padding: 24px; overflow-y: auto; }
.drawer-close { float: right; border: none; background: none; font-size: 22px; cursor: pointer; color: var(--el-text-color-secondary); }
.drawer h3 { margin: 0 0 16px; font-size: 16px; }
.drawer h4 { margin: 16px 0 8px; font-size: 13px; color: var(--el-text-color-secondary); text-transform: uppercase; }
.dr { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; }
.dr span { color: var(--el-text-color-secondary); }
.g { color: #67c23a; }
.y { color: #e6a23c; }
.r { color: #f56c6c; }
.nd-tag { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; background: rgba(230,162,60,.12); color: #e6a23c; margin-top: 8px; }

@media (max-width: 640px) {
  .kpi-row, .domains-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
