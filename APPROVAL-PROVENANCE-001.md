# APPROVAL-PROVENANCE-001 — 审批工作台后端能力溯源（只读取证）

> 发起：周主任（德育主任）｜性质：Read-Only Provenance｜日期：2026-08-17
> 关联决策：OPENING-APPROVAL-001（通过/驳回真接、催办假提示改真）
> 纪律：**本报告零代码改动**，仅取证。接线方案见 §6，待拍板后执行。

---

## 0. 结论（一句话）

**后端 approval engine 已真实存在且完整可用；前端 `approval.ts` 的 API 层也已写好；唯一缺口是审批页 `approval-center/Index.vue` 的"通过/驳回"按钮是 demo stub 未接真实 API，以及"催办"虽真调后端、但后端返回"催办通知已发送"的假文案。**

→ 这属**接线（wiring）**，不是新功能开发。完全落在你定的红线内
（不重构 engine / 不新增审批类型 / 不重画拓扑 / 不接企业微信 / 不接钉钉 / 不改数据库）。

---

## 1. 你的假设 vs 证据

| 你的怀疑 | 证据 | 判定 |
|---|---|---|
| 后端 approval engine 已经存在 | `modules/approval/routers.py` 全 662 行，含真实 approve/reject/urge 端点与 DB 落库逻辑 | ✅ 成立 |
| 前端 approval-center 没接 | `frontend/src/views/approval-center/Index.vue:428` `handleApprove` 仅 `ElMessage.success` + 注释 "In real mode, would call approveRequest API"；`handleReject` 同（:439） | ✅ 成立 |
| 读链通、写链可能已有接口 | 前端 `approval.ts:73-83` 已导出 `approveRequest`/`rejectRequest` 且路径正确（`POST /approval/requests/{id}/approve`）；审批页**没调用**它们 | ✅ 成立 |
| 催办假提示 | 根因在**后端**：`routers.py:399` `UrgeResponse(message="催办通知已发送")`，仅 `logger.info` 不实际发送 | ✅ 成立 |

---

## 2. 后端端点全表（modules/approval/routers.py）

| 方法+路径 | 行号 | 真实逻辑 | 权限校验 |
|---|---|---|---|
| `GET /chains` | 167 | 列出本校审批链模板 | `_require_staff` |
| `POST /chains` | 191 | 建链（版本自增） | `_require_admin`（仅 ms_admin） |
| `GET /chains/{id}` | 207 | 链详情 | `_require_staff` |
| `PUT /chains/{id}` | 220 | 改链（节点变→新版本） | `_require_admin` |
| `POST /chains/{id}/activate` | 234 | 激活（停用同业务旧版） | `_require_admin` |
| `DELETE /chains/{id}` | 251 | 软删除 | `_require_admin` |
| `GET /pending-count` | 269 | 待审批计数（行级 scope 收敛） | `_require_staff` |
| `GET /tickets?type=todo|done` | 297 | 动态链工单视图（拓扑映射） | `_require_staff` + `student_id_scope` |
| `POST /tickets/{id}/urge` | 364 | **催办（仅 logger + 假 message）** | `_require_staff` + school 校验 |
| `GET /requests` | 411 | 分页列表 | `_require_staff` + `student_id_scope` |
| `GET /requests/{id}` | 472 | 详情 | `_require_staff` + `get_student_or_403` |
| `POST /requests/{id}/approve` | **509** | **真实批准：改节点→推进→commit** | `_require_staff` + school 校验 |
| `POST /requests/{id}/reject` | **596** | **真实驳回：终止为 rejected→commit** | `_require_staff` + school 校验 |

---

## 3. 10 项核查清单（你要的答案）

| # | 核查项 | 结论 | 证据 |
|---|---|---|---|
| 1 | approval router 全部 endpoints | ✅ 全在 | §2 表 |
| 2 | approve / reject / complete / transition 是否存在 | ✅ approve + reject 实存在；complete/transition 由 approve 隐式完成（末节点通过→`current_status="approved"`） | `routers.py:509` `:596` |
| 3 | request schema | ✅ `ApproveRequestInput{comment?}`；`RejectRequestInput{comment:str, min 1, max 500}`（**驳回理由后端强制必填**） | `schemas.py:155-162` |
| 4 | 当前节点权限如何校验 | ⚠️ role + school 校验在；**行级 student scope 在 approve/reject/urge 缺失**（见 §5-A1） | `routers.py:65-77` `_require_staff`；`:522-527` school 过滤；`get_student_or_403` 仅用于 `get_request`(:488) |
| 5 | 是否校验 assignee / role / school | role✅ school✅（404/403）；**per-node 指派角色未校验**（见 §5-A1） | `routers.py:509-532` |
| 6 | terminal 状态重复操作是否 409 | ⚠️ 返回 **400** 非 409（`if current_status!="pending": raise 400`） | `routers.py:531` `:615` |
| 7 | audit/event 是否落库 | ⚠️ **无独立审计表**；但节点 JSON 内嵌 `approver_id`(operator) / `approved_at`·`rejected_at`(operated_at) / `comment`(reject_reason)，`from→to` 状态可由 `current_status`+节点 status 推导 | `routers.py:550-555` `:633-644`；`db.commit()` |
| 8 | approve 后是否推进 next node | ✅ serial_and：`current_step+=1`；末节点→`approved`+`completed_at`；parallel_or 全通过判定 | `routers.py:559-584` |
| 9 | reject 后状态是什么 | ✅ `current_status="rejected"`、`completed_at` 落库、节点 `status="rejected"`、理由入 `comment`，终态 | `routers.py:642-645` |
| 10 | SLA / escalation 是否受影响 | ✅ Celery beat 每 30min 扫描 pending（`approval.check_timeout_approvals`），per-node 超时 auto_approve/escalate/deny；审批后 `updated_at=now` 重置下节点计时；升级走 `NotificationService.notify_by_role`（真实站内通知） | `tasks.py:706` `:233-358` `:573` |

---

## 4. 催办假提示根因（P1 Truthfulness）

调用链：
```
前端 triggerUrge (Index.vue:403)
  → urgeTicketNode (approval.ts:53)  ← 真发起 HTTP POST
  → 后端 urge_ticket_node (routers.py:364)
       · 仅 logger.info("[URGE]...")               ← 无任何实际发送
       · return UrgeResponse(message="催办通知已发送")  ← 假文案源头
  → 前端 ElMessage.success('催办通知已推送至审批人（钉钉/企业微信）') (Index.vue:414)
```

**判定：假提示两端都有份**——后端返回假文案，前端又叠加"钉钉/企业微信"误导。
修复只需改文案 +（可选）真发站内提醒，不动外部通道。

---

## 5. 接线前必须决策的 5 个缺口（A1–A5）

### A1｜per-node 指派角色未校验（影响 R4 严格门）
- 现状：approve/reject 只校验"你是 staff 角色 + 同校"，**不校验你的角色是否等于当前待审节点的 `role`**。即班主任可批本应校长批的节点。
- 风险：责任闭环在"谁批的"层面被放宽（节点记录 `approver_id` 但不过滤）。
- 决策：①**加 ~5 行校验**（读 `nodes[current_step]["role"]`，USER 型比对 `approver_id`，不匹配→403）——推荐，属"接线级"小改、不改库；②或开学先接受（链仍正确推进，主要危险"按钮成功但无状态变化"已消除）。
- 注意：你原 gate "非审批人→403" 若含"非本节点指派人"，则必须选①。

### A2｜终态重复返回 400 而非 409
- 现状：后端用 400。前端接线时**须同时处理 400 与 409** 视作"已处理"，避免误判失败。
- 影响：仅前端兼容处理，后端可不改（或顺手改 409，但非必须）。

### A3｜审计是内嵌 JSON，非独立审计表
- 现状：operator/operated_at/reject_reason 已落 `chain_config` JSON，但无独立 immutable 审计表。
- 判定：**满足开学标准**（"审计是真的"→理由+操作人+时间已入库），但合规口径弱于独立表。开学后可视需要补 `approval_audit_log` 表。

### A4｜demo 兜底会污染真实工单列表（高优先级隐患，影响 R3）
- 现状：`fetchTicketsWithFallback`（approval.ts:106）在后端**返回空数组时也回退到假数据**（TKT-2026-0078 等）。
- 危险：若教师看到的是 demo 工单，点"通过"→`approveRequest("TKT-2026-0078")`→后端 `int(ticket_id)` 失败→400/404，**又制造"假成功/假失败"**。
- 决策：**接线时必须禁用/收紧 demo 兜底**（仅后端报错才兜底，且清空列表而非填假数据），确保列表只显示真实工单。

### A5｜urge 方案选型（你给的 A/B/C）
- A（最优，推荐）：后端 `urge_ticket_node` 接 `NotificationService.notify_by_role`，向当前 pending 节点的指派角色发**真实站内提醒**（基础设施已用于超时升级，`tasks.py:573`），文案改"催办已发送站内提醒"。
- B：仅改 `UrgeResponse.message="催办已记录，外部消息通道暂未启用"`，不实际发送。
- C：禁用按钮（文案"外发通道未启用"）。
- 推荐 A：站内通知通道已存在，改动小、开学即真。

---

## 6. 建议接线方案（OPENING-APPROVAL-001，待拍板后执行，未改动任何文件）

范围锁死（沿用你的定义）：
- **R1** 真实 approve 接线
- **R2** 真实 reject 接线（+ 理由 + 审计）
- **R3** 操作后列表/拓扑即时刷新（+ 消除 demo 兜底 A4）
- **R4** 权限/跨 scope/重复终态 Gate（含 A1 决策）
- **R5** 催办提示真实性修正（A5，不接钉钉/企微）

### 改动清单（预计 ≤6 文件，全部前端 + 1 后端小改）
1. `frontend/src/views/approval-center/Index.vue`
   - `handleApprove`（:428）：`ElMessageBox.confirm` 后 `await approveRequest(Number(selectedTicket.ticket_id), {comment})` → 成功 `loadTickets()` + 刷新 pending 角标；失败按 400/409 显示"已处理"、其他显示错误。
   - `confirmReject`（:444）：`await rejectRequest(Number(id), {comment: rejectReason.value})` → 成功 `loadTickets()`；理由必填已由后端强制。
   - `triggerUrge`（:403）：文案改为后端真实返回（去掉"钉钉/企业微信"硬编码），按 A5 方案。
2. `frontend/src/api/approval.ts:106` `fetchTicketsWithFallback`：收紧/禁用 demo 兜底（A4）。
3. `modules/approval/routers.py:364` `urge_ticket_node`：按 A5（推荐 A）接 `NotificationService.notify_by_role` + 改 `UrgeResponse.message`；可选 A1 加 per-node 角色校验（~5 行）。
4.（可选）后端 `approve/reject` 终态返回 409（A2，非必须）。

### Gate 映射（你的验收标准 → 落点）
| 你的 Gate | 落点 |
|---|---|
| 吴晶鑫/正确节点 approve 200 | `approveRequest` → 后端 200 |
| current node COMPLETED/APPROVED | `nodes[current_step].status` 落库 |
| next node 激活 | serial_and `current_step+=1` |
| todo 数量刷新 | `loadTickets()` + `getPendingCount()` |
| audit/event 有记录 | 节点 JSON `approver_id`/`approved_at`/`comment` |
| 非审批人 403 | `_require_staff`（若含 per-node 指派人→A1） |
| 其他年级/学校 403/404 | school_id 过滤 → 404 |
| 重复 approve 409 | 后端 400（前端兼容）/ 可选改 409 |
| 已驳回/已完成不允许再 approve | `current_status!="pending"→400` |
| **不出现：按钮成功但列表仍 pending** | 前端成功必 `loadTickets()` 重拉真实数据（A4 消除 demo 干扰） |

---

## 7. 证据文件定位
- 后端：`modules/approval/routers.py`（端点+逻辑）、`services.py`（链解析/播种）、`schemas.py`（输入契约）、`tasks.py`（SLA/升级）、`models.py`（模板表）
- 前端 API：`frontend/src/api/approval.ts`（已存在完整 API 层）
- 前端页面：`frontend/src/views/approval-center/Index.vue`（stub 缺口在 :428 / :439 / :414）
- 通知基建：`modules/notifications/services.py:73` `notify_by_role`（urge A5 复用）
