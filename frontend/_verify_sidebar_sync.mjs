/**
 * _verify_sidebar_sync.mjs — 侧边栏登录状态同步逻辑验证
 *
 * 验证三层Bug修复：
 *   Bug #1: display_name → real_name 字段映射
 *   Bug #2: role "ms_admin" → "MS_ADMIN" 大写归一化
 *   Bug #3: currentRoleLabel 用 currentRole(已大写) 替代 userInfo.role(可能小写)
 */

// ── 模拟后端 UserOut 返回格式 ──
const backendUserOut = {
  id: 1,
  username: 'admin',
  display_name: '德育处管理员',  // 后端用 display_name
  role: 'ms_admin',              // 后端用小写 enum value
  school_id: 1,
  school_name: '梨江中学',
  grade_id: null,
  class_id: null,
  is_active: true,
}

// ── 模拟前端 UserInfo 类型 ──
const UserRoleList = ['MS_ADMIN', 'GRADE_LEADER', 'CLASS_TEACHER', 'PARENT', 'STUDENT']
const roleMap = {
  MS_ADMIN: '德育处管理员',
  GRADE_LEADER: '年级组长',
  CLASS_TEACHER: '班主任',
  PARENT: '家长',
  STUDENT: '学生',
}

// ── 旧 setUserInfo (Bug版): 直接存入后端原始数据 ──
function setUserInfo_OLD(raw) {
  return {
    ...raw,  // 直接展开，不做归一化
  }
}

// ── 新 setUserInfo (Fix版): 归一化写入 ──
function setUserInfo_NEW(raw) {
  return {
    id: raw.id ?? 0,
    username: raw.username ?? '',
    real_name: raw.real_name || raw.display_name || '',  // 🔪 Fix #1
    role: (typeof raw.role === 'string' ? raw.role.toUpperCase() : raw.role),  // 🔪 Fix #2
    school_id: raw.school_id ?? 0,
    school_name: raw.school_name || '',
    class_id: raw.class_id ?? null,
    class_name: raw.class_name ?? null,
    grade_id: raw.grade_id ?? null,
    grade_name: raw.grade_name ?? null,
    avatar: raw.avatar ?? null,
  }
}

// ── 旧 currentRoleLabel (Bug版): userInfo.role 直接查找 ──
function currentRoleLabel_OLD(userInfo) {
  return userInfo ? roleMap[userInfo.role] : '未登录'
}

// ── 新 currentRoleLabel (Fix版): 用 currentRole (已大写) 查找 ──
function currentRole(userInfo) {
  return userInfo?.role ?? null
}
function currentRoleLabel_NEW(userInfo) {
  const cr = currentRole(userInfo)
  return cr ? roleMap[cr] : '未登录'
}

// ── 测试场景 ──
const tests = [
  {
    name: 'Bug根因复现: 旧setUserInfo + 旧currentRoleLabel',
    userInfo: setUserInfo_OLD(backendUserOut),
    labelFn: currentRoleLabel_OLD,
  },
  {
    name: 'Fix验证: 新setUserInfo + 新currentRoleLabel',
    userInfo: setUserInfo_NEW(backendUserOut),
    labelFn: currentRoleLabel_NEW,
  },
  {
    name: '班主任角色: 新归一化验证',
    userInfo: setUserInfo_NEW({
      ...backendUserOut,
      display_name: '张老师',
      role: 'class_teacher',
      class_id: 2501,
    }),
    labelFn: currentRoleLabel_NEW,
  },
  {
    name: '混合数据源: 前端格式(已有real_name) + 新归一化',
    userInfo: setUserInfo_NEW({
      id: 5,
      username: 'ct_2501',
      real_name: '张老师',       // 前端格式，已有 real_name
      display_name: '张老师',    // 后端格式也有
      role: 'CLASS_TEACHER',     // 前端格式，已大写
      school_id: 1,
      school_name: '梨江中学',
      class_id: 2501,
    }),
    labelFn: currentRoleLabel_NEW,
  },
]

let allPass = true
console.log('=== 侧边栏登录状态同步 — 逻辑验证 ===\n')

for (const t of tests) {
  const info = t.userInfo
  const label = t.labelFn(info)
  const cr = currentRole(info)

  // 检查项
  const nameOk = info.real_name !== undefined && info.real_name !== ''
  const roleOk = UserRoleList.includes(cr)
  const labelOk = label !== undefined && label !== 'undefined' && label !== ''
  const avatarOk = info.real_name?.charAt(0) !== undefined

  const pass = nameOk && roleOk && labelOk && avatarOk
  if (!pass) allPass = false

  console.log(`TEST: ${t.name}`)
  console.log(`  real_name = "${info.real_name}" ${nameOk ? '✅' : '❌ undefined/空'}`)
  console.log(`  currentRole = "${cr}" ${roleOk ? '✅' : '❌ 不在UserRole列表'}`)
  console.log(`  roleLabel = "${label}" ${labelOk ? '✅' : '❌ undefined/空'}`)
  console.log(`  avatarFirstChar = "${info.real_name?.charAt(0) ?? 'N/A'}" ${avatarOk ? '✅' : '❌'}`)
  console.log(`  RESULT: ${pass ? '✅ PASS' : '❌ FAIL'}\n`)
}

console.log(`\n=== 最终结果: ${allPass ? '✅ 全部通过' : '❌ 有失败项'} ===`)
process.exit(allPass ? 0 : 1)
