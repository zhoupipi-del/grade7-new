# REAL-EVENT-READY-001 — 第一次真实业务事件前只读就绪检查

> **时间**：2026-08-17T11:51-11:58+0800 ｜ **性质**：纯只读取证，零修改
> **目标**：证明"第一条真实事件一出现，现有系统有能力接住"——不是证明业务已闭环
> **纪律**：不修代码 / 不新建账号 / 不处理 19 条存量 / 不做 synthetic / 不做 R2 / 不修 STEP0-KG-001 / 不继续 Fabric

---

## 总判定

```text
BLOCKED: 梨江中学（school 1）无真实 counselor 审核人
  users.role='counselor' = 0 个
  school 1 仅有的 4 条 counselor assignment（teacher_user_id 435-438）为
  R1 测试残留 orphan（对应用户已删除）
  19 条真实 PENDING_REVIEW 全部属于 school 1 → 当前无任何真实授权用户可处理
```

### BLOCKER TYPE（周主任 2026-08-17 正式口径）

```text
BLOCKER TYPE:
Operational Identity / Authorization Readiness

NOT:
- backend defect
- frontend defect
- workflow defect
- deployment defect
- migration defect
- CF-04 state-machine defect
```

**不得为把检查变成 READY 而制造"看起来真实"的 counselor**——必须等学校确认具体心理老师后，再建立与真人对应的账号与 assignment。

技术链路（①②④⑤）全部就绪，唯一阻塞在 ③ 真实审核人。

---

## ① Production provenance — PASS

```text
本地 HEAD              a66d92e（Step 0 基线，未部署生产=预期）
生产 current           82b9405-r1b → commit 82b9405（release.json: deployed=True, current_switched=True）
frontend-current       20260816.2（R1 Review UI）
alembic current        cf04ops_20260816 (head) == release.json alembic_head ✅
git remote 包含生产    origin/reconcile/prod-20260816 含 82b9405 ✅
```

## ② CF-04 operational readiness — PASS

```text
Review UI 生产可访问    GET /app/ai-prescription-review → 200 ✅
history API            GET /history?review_status=PENDING_REVIEW → 200, total=19 ✅
confirm/modify/reject  路由存在（routers.py:604/639/676）✅
counselor ENUM         生产 users.role 含 counselor ✅（cf04ops_20260816 migration 生效）
COUNSELOR history gate 生产 routers.py 命中 2 处 ✅
19 条 PENDING 保持      8-14:6 + 8-15:7 + 8-16:6 = 19 ✅
                        （今天 07:49 rdi scan 后未新增 = R4 dedup 生效证明）
synthetic 残留          r1_gate_synthetic = 0 ✅
```

## ③ Real reviewer readiness — BLOCKED ← 唯一阻塞

```text
users.role='counselor'          = 0（梨江无真实心理老师账号）
teacher_role_assignments(counselor) = 6 条，其中：
  school 1: teacher_user_id 435/436/437/438 = R1 测试 orphan（用户已删）✗
  school 10006: uid 422 = audit_psych_A（is_active=0, role=teacher）✗ 审计测试账号
  school 10007: uid 427 = audit_psych_B（is_active=0, role=teacher）✗ 审计测试账号
19 条 PENDING_REVIEW 归属      全部 school 1（梨江）
school 1 active teacher 类用户  13 个（admin/grade7_leader/ct_2501... 无 counselor）
```

结论：**梨江 0 个真实授权审核人**。即使 UI/API/状态机全绿，第一条真实 PENDING 也无"真实授权心理老师"可处理。

## ④ Closure downstream readiness — PASS（代码/证据层）

```text
activate_prescription_after_review  tasks.py:1315 存在
CONFIRMED/MODIFIED → activate       任务 docstring: "activate...触发真正的 bridge" ✅
REJECTED 不生成工单                  reject 端点注释 "REJECTED 为终态，永不触发 bridge"，不调用 activate ✅
PENDING 不 activate                 _ensure_pending（routers.py:583），confirm/modify/reject 全部经其校验 ✅
（未重新制造 synthetic——引用 R1 Gate 12/12 已有证据）
```

## ⑤ Frozen-line integrity — PASS

```text
a66d92e 仍为 Step 0 基线           ✅（本地 HEAD；生产 backend 无 app/ = Step 0 未部署，符合冻结）
STEP0-KG-001                      OPEN（manifest 记录 "现在不修"）✅
R2 未实现                          modules 内通知/站内信触发命中 = 0 ✅
Edge/Vault/WireGuard/Headscale     生产 modules/core 命中 = 0；生产无 wings_contracts/edge 实现 ✅
```

---

## 观察项（只报告，不修）

```text
OBS-2（升格为生产证据）: R4 PRODUCTION EVIDENCE
  R4 dedup 在 2026-08-17 07:49 真实 rdi scan 后首次于正常生产调度生效
  —— PENDING 未从 19 增至 25（8-14:6 + 8-15:7 + 8-16:6 = 19 保持）。
  去重机制第一次在实际生产中发挥作用。
  仍不能替代未来真实人工审核闭环。

OBS-1（卫生清理，非解除 BLOCKED 必要条件）:
  school 1 残留 4 条 orphan assignment（teacher_user_id 435-438，用户不存在）
  —— R1 测试清理不完全（setup 多次重建账号导致旧 uid assignment 残留）。
  授权解析不会把不存在的用户当有效 reviewer（_counselor_scope_covers 基于
  teacher_user_id join users），因此不构成 READY 的技术阻塞。
  顺序：真实审核人授权（必要条件）→ 顺手清理 orphan（卫生）。
  建议随 REAL-REVIEWER-ONBOARD-001 落地窗口一并清理，本轮不动。
```

## 下一步状态：人工等待点（非开发）

```text
WAITING_FOR_REAL_REVIEWER_IDENTITY
等梨江确定心理老师之后，才授权以下小动作包（当前不执行）：
```

### REAL-REVIEWER-ONBOARD-001（待授权动作包）

```text
1. 核验真人身份/工号/学校
2. 创建或转换其生产账号为 counselor
3. 建 school_id=1 assignment
4. is_active=1
5. 验证 ResourceScope（Capability + Scope）
6. 清理 435-438 orphan（卫生项）
7. 重新执行 REAL-EVENT-READY-001 第③组

预期结果：READY
```

**注意：READY 后仍不处理 19 条处方。** READY 仅表示"真事件出现时，有真实授权的人能够接住"。随后才进入 R5/⑦ 真实审核闭环（真实登录 → 真实 PENDING → confirm/modify/reject → 留证 → 下游责任链 → follow-up → outcome）。

## 主线状态（周主任 2026-08-17 冻结口径）

```text
Secure Fabric        FROZEN
Step 0               COMPLETE（a66d92e）
STEP0-KG-001         OPEN / DEFERRED

CF-04 R1             UI PATH PROVEN
CF-04 R4             PROD DEDUP EVIDENCE OBSERVED
CF-04 R2             NOT AUTHORIZED

REAL-EVENT-READY-001 BLOCKED
Blocker              NO REAL COUNSELOR

Real-event closure   WAITING_REAL_EVENT
```

本次检查已达成目的（证明"真事件出现时系统能否接住"的缺口=人员/授权），**就此停止，不继续找事做**。
