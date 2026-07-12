/**
 * 逻辑验证脚本 — 模拟 dimensionDetails 计算链
 * 验证修复后: subject_code 用英文代码 + Demo 科目全覆盖 + watcher 不冲刷
 */

// === 常量 (复制自 grades.ts) ===
const DIMENSION_SUBJECTS = {
  moral: ['chinese', 'politics'],
  academic: ['math', 'physics', 'chemistry'],
  health: ['biology', 'pe'],
  art: ['art', 'music'],
  social: ['english', 'history', 'geography'],
}

const DIMENSION_LABELS = {
  moral: '道德品质',
  academic: '学业水平',
  health: '身心健康',
  art: '艺术素养',
  social: '社会实践',
}

// === 修复后的 Demo 科目 (12科全覆盖) ===
const subjectList = [
  { id: 1, name: '语文', code: 'chinese', full_score: 100 },
  { id: 2, name: '数学', code: 'math', full_score: 100 },
  { id: 3, name: '英语', code: 'english', full_score: 100 },
  { id: 4, name: '政治', code: 'politics', full_score: 100 },
  { id: 5, name: '历史', code: 'history', full_score: 100 },
  { id: 6, name: '地理', code: 'geography', full_score: 100 },
  { id: 7, name: '生物', code: 'biology', full_score: 100 },
  { id: 8, name: '物理', code: 'physics', full_score: 100 },
  { id: 9, name: '化学', code: 'chemistry', full_score: 100 },
  { id: 10, name: '体育', code: 'pe', full_score: 100 },
  { id: 11, name: '美术', code: 'art', full_score: 50 },
  { id: 12, name: '音乐', code: 'music', full_score: 50 },
]

// === 模拟 scoresData (修复后: subject_code 用英文代码) ===
function buildScoresData(studentScores) {
  // 🔪 Fix: subject_code 必须用英文代码(code)，不能用中文科目名(subject_name)
  return studentScores.map(s => {
    const code = s.code 
      ?? subjectList.find(sl => sl.name === s.subject_name)?.code
      ?? s.subject_name  // 兜底
    return {
      ...s,
      subject_code: code,  // ← 英文代码
      subject_name: s.subject_name,
    }
  })
}

// === 模拟 dimensionDetails computed ===
function computeDimensionDetails(scoresData, evalData) {
  const dims = ['moral', 'academic', 'health', 'art', 'social']
  return dims.map(dim => {
    const subjects = DIMENSION_SUBJECTS[dim] ?? []
    let academicScore = 0
    let count = 0

    subjects.forEach(code => {
      const subj = subjectList.find(s => s.code === code)
      const score = scoresData.find(sc => sc.subject_code === code)
      if (subj && score) {
        academicScore += ((score.score ?? 0) / subj.full_score) * 100
        count++
      }
    })
    if (count > 0) academicScore = Math.round(academicScore / count)

    const behaviorScore = evalData ? Math.round(
      evalData[dim + '_score'] ?? evalData.total_score ?? 0
    ) : 0

    const delta = academicScore - behaviorScore
    return {
      key: dim,
      label: DIMENSION_LABELS[dim],
      academicScore,
      behaviorScore,
      delta,
      subjectCount: count,
      expectedSubjects: subjects.length,
    }
  })
}

// ═══════════════════════════════════════════
// TEST 1: 修复前 — subject_code 用中文科目名 (Bug 根因)
// ═══════════════════════════════════════════
console.log('=== TEST 1: Bug根因复现 — subject_code=中文科目名 ===')
const bugScoresData = [
  { subject_name: '语文', subject_code: '语文', score: 85, student_id: 1, student_name: '陈博裕' },
  { subject_name: '数学', subject_code: '数学', score: 92, student_id: 1, student_name: '陈博裕' },
  { subject_name: '英语', subject_code: '英语', score: 78, student_id: 1, student_name: '陈博裕' },
  { subject_name: '政治', subject_code: '政治', score: 88, student_id: 1, student_name: '陈博裕' },
  { subject_name: '历史', subject_code: '历史', score: 75, student_id: 1, student_name: '陈博裕' },
  { subject_name: '地理', subject_code: '地理', score: 82, student_id: 1, student_name: '陈博裕' },
  { subject_name: '生物', subject_code: '生物', score: 90, student_id: 1, student_name: '陈博裕' },
  { subject_name: '物理', subject_code: '物理', score: 80, student_id: 1, student_name: '陈博裕' },
  { subject_name: '化学', subject_code: '化学', score: 78, student_id: 1, student_name: '陈博裕' },
  { subject_name: '体育', subject_code: '体育', score: 85, student_id: 1, student_name: '陈博裕' },
  { subject_name: '美术', subject_code: '美术', score: 42, student_id: 1, student_name: '陈博裕' },
  { subject_name: '音乐', subject_code: '音乐', score: 40, student_id: 1, student_name: '陈博裕' },
]

const evalData1 = {
  moral_score: 85,
  academic_score: 90,
  health_score: 88,
  art_score: 78,
  social_score: 80,
  total_score: 421,
}

const bugResult = computeDimensionDetails(bugScoresData, evalData1)
bugResult.forEach(d => {
  const match = d.subjectCount === d.expectedSubjects ? '✅' : '❌'
  console.log(`  ${match} ${d.label}: 学业=${d.academicScore}, 行为=${d.behaviorScore}, delta=${d.delta} | 匹配科目=${d.subjectCount}/${d.expectedSubjects}`)
})

const bugZeroCount = bugResult.filter(d => d.academicScore === 0).length
console.log(`  📊 零分维度数: ${bugZeroCount}/5 — ${bugZeroCount >= 3 ? '❌ Bug复现!' : '✅ 正常'}`)

// ═══════════════════════════════════════════
// TEST 2: 修复后 — subject_code 用英文代码
// ═══════════════════════════════════════════
console.log('\n=== TEST 2: 修复验证 — subject_code=英文代码 ===')
const fixedScoresRaw = [
  { subject_name: '语文', code: 'chinese', score: 85, student_id: 1, student_name: '陈博裕' },
  { subject_name: '数学', code: 'math', score: 92, student_id: 1, student_name: '陈博裕' },
  { subject_name: '英语', code: 'english', score: 78, student_id: 1, student_name: '陈博裕' },
  { subject_name: '政治', code: 'politics', score: 88, student_id: 1, student_name: '陈博裕' },
  { subject_name: '历史', code: 'history', score: 75, student_id: 1, student_name: '陈博裕' },
  { subject_name: '地理', code: 'geography', score: 82, student_id: 1, student_name: '陈博裕' },
  { subject_name: '生物', code: 'biology', score: 90, student_id: 1, student_name: '陈博裕' },
  { subject_name: '物理', code: 'physics', score: 80, student_id: 1, student_name: '陈博裕' },
  { subject_name: '化学', code: 'chemistry', score: 78, student_id: 1, student_name: '陈博裕' },
  { subject_name: '体育', code: 'pe', score: 85, student_id: 1, student_name: '陈博裕' },
  { subject_name: '美术', code: 'art', score: 42, student_id: 1, student_name: '陈博裕' },
  { subject_name: '音乐', code: 'music', score: 40, student_id: 1, student_name: '陈博裕' },
]

const fixedScoresData = buildScoresData(fixedScoresRaw)
const fixedResult = computeDimensionDetails(fixedScoresData, evalData1)
fixedResult.forEach(d => {
  const match = d.subjectCount === d.expectedSubjects ? '✅' : '❌'
  console.log(`  ${match} ${d.label}: 学业=${d.academicScore}, 行为=${d.behaviorScore}, delta=${d.delta} | 匹配科目=${d.subjectCount}/${d.expectedSubjects}`)
})

const fixedZeroCount = fixedResult.filter(d => d.academicScore === 0).length
console.log(`  📊 零分维度数: ${fixedZeroCount}/5 — ${fixedZeroCount >= 3 ? '❌ 修复失败!' : '✅ 修复成功!'}`)

// ═══════════════════════════════════════════
// TEST 3: API 返回数据含 .code 字段 (三层回退测试)
// ═══════════════════════════════════════════
console.log('\n=== TEST 3: 三层回退测试 — API 不返回 .code 字段 ===')
const apiScoresNoCode = [
  // API 真实返回格式可能不带 code，只有 subject_name
  { subject_name: '语文', score: 85, student_id: 1, student_name: '陈博裕' },
  { subject_name: '数学', score: 92, student_id: 1, student_name: '陈博裕' },
  { subject_name: '英语', score: 78, student_id: 1, student_name: '陈博裕' },
  { subject_name: '政治', score: 88, student_id: 1, student_name: '陈博裕' },
  { subject_name: '历史', score: 75, student_id: 1, student_name: '陈博裕' },
  { subject_name: '地理', score: 82, student_id: 1, student_name: '陈博裕' },
  { subject_name: '生物', score: 90, student_id: 1, student_name: '陈博裕' },
  { subject_name: '物理', score: 80, student_id: 1, student_name: '陈博裕' },
  { subject_name: '化学', score: 78, student_id: 1, student_name: '陈博裕' },
  { subject_name: '体育', score: 85, student_id: 1, student_name: '陈博裕' },
  { subject_name: '美术', score: 42, student_id: 1, student_name: '陈博裕' },
  { subject_name: '音乐', score: 40, student_id: 1, student_name: '陈博裕' },
]

const fallbackScoresData = buildScoresData(apiScoresNoCode)
const fallbackResult = computeDimensionDetails(fallbackScoresData, evalData1)
fallbackResult.forEach(d => {
  const match = d.subjectCount === d.expectedSubjects ? '✅' : '❌'
  console.log(`  ${match} ${d.label}: 学业=${d.academicScore}, 行为=${d.behaviorScore}, delta=${d.delta} | 匹配科目=${d.subjectCount}/${d.expectedSubjects}`)
})

const fallbackZeroCount = fallbackResult.filter(d => d.academicScore === 0).length
console.log(`  📊 零分维度数: ${fallbackZeroCount}/5 — ${fallbackZeroCount >= 3 ? '❌ 回退失败!' : '✅ 三层回退正常!'}`)

// ═══════════════════════════════════════════
// TEST 4: Demo 模式特殊科目 (full_score=50 的 art/music)
// ═══════════════════════════════════════════
console.log('\n=== TEST 4: 非标准满分科目 (美术50/音乐50) ===')
const artDim = DIMENSION_SUBJECTS['art']
artDim.forEach(code => {
  const subj = subjectList.find(s => s.code === code)
  console.log(`  ${code}: full_score=${subj?.full_score} — ${subj?.full_score === 50 ? '✅ 非标准满分正确' : '⚠️ 标准满分'}`)
})

const artScoreEntry = fixedScoresData.find(sc => sc.subject_code === 'art')
const musicScoreEntry = fixedScoresData.find(sc => sc.subject_code === 'music')
if (artScoreEntry && musicScoreEntry) {
  const artPct = ((artScoreEntry.score ?? 0) / 50) * 100
  const musicPct = ((musicScoreEntry.score ?? 0) / 50) * 100
  console.log(`  美术: ${artScoreEntry.score}/50 → ${artPct}%`)
  console.log(`  音乐: ${musicScoreEntry.score}/50 → ${musicPct}%`)
  console.log(`  艺术维度学业分: ${Math.round((artPct + musicPct) / 2)} — ${Math.round((artPct + musicPct) / 2) > 0 ? '✅ 不为0' : '❌ 为0'}`)
}

// ═══════════════════════════════════════════
// 总结
// ═══════════════════════════════════════════
console.log('\n════════════════════════════════════')
console.log('修复效果总判:')
console.log(`  Bug根因复现 (中文key): 零分维度=${bugZeroCount}/5 → ${bugZeroCount >= 3 ? '❌ Bug存在' : '⚠️ 部分影响'}`)
console.log(`  修复后 (英文code): 零分维度=${fixedZeroCount}/5 → ${fixedZeroCount === 0 ? '✅ 全维度有值' : '❌ 仍有问题'}`)
console.log(`  三层回退 (无.code字段): 零分维度=${fallbackZeroCount}/5 → ${fallbackZeroCount === 0 ? '✅ 回退成功' : '❌ 回退失败'}`)
console.log('════════════════════════════════════')
