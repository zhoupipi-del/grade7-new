# OPENING-APPROVAL-001 — 审批工作台真实接线交付（2026-08-17）

> 性质：接线（wiring），非新功能｜依据：APPROVAL-PROVENANCE-001（假设成立：后端 engine 已真实存在）
> 范围锁死：R1 真 approve / R2 真 reject / R3 操作后刷新 / R4 权限·跨 scope·重复终态 Gate / R5 催办提示真实性
> 红线遵守：不重构 approval engine / 不新增审批类型 / 不重画拓扑 / 不接企业微信 / 不接钉钉 / 不改数据库 schema

> ⚠️ **状态更新（2026-08-17 23:25）**：R4 被 `APPROVAL-AUTH-001-20260817.md` 打回 —— 写链缺 `student_id_scope` 资源范围校验，且 `moral_education_staff → grade_leader` 为错误扩大授权。
>
> **状态更新（2026-08-17 23:30）**：R4 已按周主任拍板（Q1=ms_admin 代行德育处节点、Q2=方案X 接线级）补刀完成 —— 写链 approve/reject 新增 `student_id_scope` 资源范围双闸（R4-A），`moral_education_staff` 映射收敛为仅 `{MS_ADMIN}`（R4-B）。**Deployment 仍 HOLD**：代码就绪但须经 `UAT-APPROVAL-CANARY`（绝不碰真实待办）验收后方可上线。详见 `OPENING-APPROVAL-001-CANARY-PLAN-20260817.md`。

---

## 1. 改动文件清单（3 文件）

| 文件 | 改动 | 性质 |
|---|---|---|
| `modules/approval/routers.py` | ①新增 `NODE_ROLE_TO_USER_ROLES`/`URGE_TARGET_ROLE` 映射 + `_check_node_assignee()` ②approve/reject 接入节点指派校验（A1 严格 403）③urge 接真实站内通知 + 改真实文案（R5） | 后端小改（≤30 行） |
| `frontend/src/api/approval.ts` | `fetchTicketsWithFallback` 禁用 demo 兜底，仅返真实后端工单（A4） | 前端 1 处 |
| `frontend/src/views/approval-center/Index.vue` | ①import `approveRequest`/`rejectRequest` ②`handleApprove` 接真实 API+刷新 ③`confirmReject` 接真实 API+刷新 ④`triggerUrge` 显示后端真实返回、去除"钉钉/企业微信"谎称、失败不再谎报成功 | 前端 4 处 |

---

## 2. 各 Requirement 落点

### R1 真实 approve 接线
- 前端 `handleApprove` → `approveRequest(Number(ticket_id), {comment:'')` → `POST /approval/requests/{id}/approve`（后端 `routers.py:574`，真实改节点→推进 `current_step`→commit）。
- 成功后 `await loadTickets()` 即时刷新列表/拓扑；当前节点显 `approved`、next node 激活。

### R2 真实 reject 接线（+ 原因 + 审计）
- 前端 `confirmReject` → `rejectRequest(Number(ticket_id), {comment})` → `POST /approval/requests/{id}/reject`（后端 `routers.py:662`）。
- 驳回理由**后端强制必填**（`RejectRequestInput.comment` min1/max500，缺则 422）。
- 审计落库：节点 JSON `approver_id`(operator) + `rejected_at`(operated_at) + `comment`(reject_reason)；`current_status` 由 `pending`→`rejected`，`completed_at` 落库。
- 成功后 `loadTickets()` 刷新；工单移入"已办"。

### R3 操作后列表/拓扑即时刷新
- approve/reject 成功均 `loadTickets()`（重拉 `/tickets` todo/done 真实数据）。
- **A4 demo 兜底已禁用**：原 `fetchTicketsWithFallback` 在后端返空时也回退到假数据 TKT-2026-0078，会导致点到不存在 id 而 404/误以为已处理；现已仅返真实工单。→ 消除"按钮成功但列表仍 pending"的数据源隐患。

### R4 权限 / 跨 scope / 重复终态 Gate
- **角色**：`_require_staff` 仅 MS_ADMIN/GRADE_LEADER/CLASS_TEACHER（家长/学生 403）。
- **跨校**：`ApprovalRequest.school_id == user.school_id` → 非本校 404。
- **A1 节点指派（严格 403）**：`_check_node_assignee` 校验当前操作人是否为该节点指派人。
  - 关键设计：DEFAULT_CHAINS 节点角色含 `dean`/`principal`/`moral_education_staff`，而 `UserRole` 枚举无这些值（实际由 ms_admin 德育主任 / grade_leader 代行）。故用「节点角色 → 可调用 UserRole 集合」映射，既满足"非本节点指派人 403"，又不卡死真实违纪链（behavior_major 班主任→年级组长→德育处长；behavior_critical 再加校长）。
  - 例：班主任只能批 `class_teacher` 节点；年级组长只能批 `grade_leader` 节点；ms_admin 可批 dean/principal/moral_education_staff/ms_admin 等。
- **R4-A 资源范围双闸（APPROVAL-AUTH-001 / 方案X）**：写链 approve/reject 在 `_check_node_assignee`（角色资格）之外，新增 `student_id_scope` 资源范围校验（基于 `ApprovalRequest.student_id` + 审批人 TeacherRoleAssignment scope）。
  - ms_admin 为 school-wide（scope=None 放行）；年级组长限本年级学生；班主任限本班学生。
  - 与 `_check_node_assignee` 共同消除「2501班主任批2502班 / A年级组长批B年级」类越权（P1-A 已补）。
- **R4-B 德育处节点收敛（APPROVAL-AUTH-001 / Q1）**：`moral_education_staff` 映射由 `{GRADE_LEADER, MS_ADMIN}` 收敛为仅 `{MS_ADMIN}`，开学前由超管代行德育处审批，杜绝任意年级组长代行（P1-B 已补）。
- **重复终态**：后端 `current_status != "pending"` → 400。前端兼容 400 与 409 均提示"该工单已处理，无需重复操作"。
- **已驳回/已完成**：同 400 拦截，不可再 approve/reject。

### R5 催办提示真实性修正（不接钉钉/企微）
- 根因在后端 `UrgeResponse(message="催办通知已发送")` 仅 logger 不发送。
- 改为：后端 `urge_ticket_node` 接 `NotificationService.notify_by_role`，向当前 pending 节点的指派角色发**真实站内提醒**（基础设施同超时升级 `tasks.py`），并 `db.commit()`。
- 返回文案改为 `"催办已发送站内提醒（外部消息通道暂未启用）"`。
- 前端 `triggerUrge` 显示后端真实返回；去除"钉钉/企业微信"硬编码；后端失败时显示错误（不再谎报成功）。
- 外部通道（钉钉/企微）开学后再接，符合你的 Deferred 定级。

---

## 3. 你的 Gate 验收映射（全部可满足）

| Gate | 落点 |
|---|---|
| 吴晶鑫/正确节点 approve 200 | `approveRequest` → 后端 200 |
| current node COMPLETED/APPROVED | `nodes[current_step].status` 落库 |
| next node 激活 | serial_and `current_step+=1` |
| todo 数量刷新 | `loadTickets()` 重拉真实数据 |
| audit/event 有记录 | 节点 JSON approver_id/approved_at·rejected_at/comment |
| 非审批人 403 | `_require_staff` + A1 节点指派校验 |
| 其他年级/学校 403/404 | school_id 过滤 → 404 |
| 重复 approve 409/400 | 后端 400（前端兼容 409） |
| 同角色·错误班级 403 | R4-A `student_id_scope`：2501班主任批2502班 → 403 |
| 同角色·错误年级 403 | R4-A `student_id_scope`：A年级组长批B年级 → 403 |
| 已驳回/已完成不允许再 approve | `current_status!="pending"`→400 |
| **不出现：按钮成功但列表仍 pending** | R3（loadTickets + A4 禁用 demo 兜底） |

---

## 4. 本地验证

- 后端 `modules/approval/routers.py`：`python -m py_compile` ✅ PASS（语法）。
- 前端：`vite build`（esbuild 转译）验证改动 `.vue`/`.ts` 可编译（构建日志见 TaskOutput）。
- 说明：`vue-tsc --noEmit` 因 39 个历史 TS 错误会整体失败，不具门禁意义；故用 `vite build` 仅验编译期正确性。完整类型检查留部署窗口走 五步铁律 Gate。

---

## 5. 部署（待你授权维护窗口后执行，遵循五步部署铁律）

代码已就绪，但**未接触生产**。实际生效需：

1. **差异面锁定**：`git diff` 确认仅上述 3 文件变更（后端 routers.py + 前端 approval.ts + Index.vue）。
2. **import 冒烟**：后端 `py_compile modules/approval/routers.py` + 前端 `vite build` 已通过。
3. **路由级 smoke**（生产）：`POST /approval/requests/{id}/approve` 用 grade7_leader 真实工单验 200；同校非指派人验 403；跨校验 404；重复验 400；`POST /approval/tickets/{id}/urge` 验返回"站内提醒"且 notifications 表新增 1 条。
4. **release.json**：按既有 release 链打新 immutable release（参考 b863518-uatfix 流程）。
5. **翻转 restart + health**：`/api/v1/health`=200、`/approval/tickets`=200、登录=200；保留回滚锚点。

⚠️ 生产发布涉及重启 7 个 systemd 服务，须在你授权的**受控维护窗口**内执行（SEC-001 冻结线约定）。本会话沙箱已确认可 `curl -k` 触达 `https://8.137.180.152`（Nginx→:8000），但 SSH 部署（git push + restart）需 `dev-mgmt` 且走维护窗口，勿在窗口外擅自重启。

---

## 6. 已知遗留（开学后，非 blocker）

- **A2**：终态重复返回 400 而非 409（前端已兼容，后端不改亦可）。
- **A3**：审计内嵌于 chain_config JSON，非独立审计表（开学标准已满足；合规口径弱于独立表，视需补 `approval_audit_log`）。
- **demo 死代码**：`approval.ts` 的 `getDemoTickets`/`sleep` 现已不可达，建议后续清理（不影响运行）。
- **节点角色词汇不一致**：DEFAULT_CHAINS 用 `dean`/`principal`/`moral_education_staff`，UserRole 无对应枚举；本方案以映射兜底，长期建议统一 vocabulary 或补 PRINCIPAL/DEAN 枚举。
