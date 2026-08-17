# APPROVAL-AUTH-001 — 审批权限语义只读取证（R4 收口前 Gate）

日期：2026-08-17 23:25 之后
执行方式：READ ONLY，未写代码、未部署
结论：**R4 NOT YET PROVEN → 需补一刀再部署**。后端 approve/reject 写链只有「角色 + 学校」两层校验，**缺资源范围（班级/年级）校验**；且 `moral_education_staff → grade_leader` 映射是错误扩大授权。

---

## 0. 先纠正上一轮我的一处误判（provenance 诚实）

上一轮交付开场白我说「节点读错字段会导致所有 ROLE 节点退化成只 ms_admin 能批」——**这是错的，作废**。正确事实：

- 模板 `TenantApprovalChain.nodes` 字段是 `approver_type + approver_value`（`models.py:25-37`）。
- 但工单创建时 `_template_to_snapshot`（`services.py:181`）把模板的 `approver_value` **重命名成 `role`** 写入运行时 `chain_config.nodes[].role`；`build_appeal_chain_config`（`services.py:103`）同样用 `role` 键。
- 因此运行时节点角色字段就叫 `role`，我的 `_check_node_assignee` 读 `node.get("role")` 是**正确的**。
- 真实结论：「班主任可批 class_teacher 节点、年级组长可批 grade_leader 节点」这一层**成立**。

所以 R4 的真问题不是「字段读错」，而是下面两件事。

---

## 1. R4 现状精确证据（对应你列的 6 问）

| # | 你的质疑 | 代码证据 | 现状 |
|---|---|---|---|
| 1 | 节点是否固化具体 assignee | `chain_config.nodes[].approver_id`（services.py:188 默认 None）；节点**无** `assignee_id / scope_id / grade_id / class_id` 字段 | ❌ 节点只有 role，无具体人/范围 |
| 2 | 若无 assignee，ResourceScope 如何解析 | 写链 approve/reject（`routers.py:574`/`662`）只调 `_check_node_assignee`，**未调 `student_id_scope`** | ❌ 写链无资源范围校验 |
| 3 | class_teacher 是否限定具体班级 | 列表读链按 `student_id_scope` 过滤（`routers.py:327-330`），**写链无**；节点无 class 字段 | ❌ 直连 API 可越权批他班 |
| 4 | grade_leader 是否限定具体年级 | 同上，基于 student scope 可间接定位，但写链未用 | ❌ 写链未隔离 |
| 5 | `moral_education_staff` 真实制度语义 | `DEFAULT_CHAINS`（services.py:488-568）节点角色含 `dean / principal / moral_education_staff`，**三者均不在 `UserRole` 枚举**；我的映射 `moral_education_staff → {grade_leader, ms_admin}`（routers.py:90） | ⚠️ 错误扩大授权 |
| 6 | principal 谁能代行 | `principal → {ms_admin}`（routers.py:92）；生产由超管代行 | ✅ 合理 |

**已挡住的部分（写链现状）**：
- 非 staff 角色（家长/学生/心理）→ `_require_staff` 403（`routers.py:72-77`）
- 跨校 → `school_id == user.school_id` 查询条件 → 404（`routers.py:590`/`675`）
- 终态重复操作 → `current_status != "pending"` → 400（`routers.py:596`/`681`）
- 跨角色（班主任批校长节点）→ `_check_node_assignee` 角色映射（成立）

**未挡住的部分（P1）**：
- **P1-A**：写链缺 `student_id_scope`，2501 班主任可直连批 2502 班、A 年级组长可批 B 年级。
- **P1-B**：`moral_education_staff → grade_leader` 让任意年级组长能批「德育干事审批」节点。

---

## 2. 节点字段与工单创建取证

**节点运行时结构**（`services.py:179-191` 快照）：

```json
{
  "node_index": 0,
  "role": "class_teacher",          // 来自模板 approver_value
  "label": "班主任",
  "status": "pending",
  "approver_id": null,             // 审批后才填，创建时不固化具体人
  "approved_at": null,
  "comment": null
}
```

**工单创建固化**（`behavior/services.py:235-258`）：

```python
ApprovalRequest(
    student_id=student.id,         // 工单有 student_id（关键，可用于资源范围校验）
    class_id=student.class_id,
    grade_id=student.grade_id,
    chain_config=chain_config,     // 节点仍是纯 role，无 assignee/scope
)
```

→ 工单具备 `student_id` 且能定位班级/年级，但**节点本身不固化具体责任人**。

---

## 3. 两个待你拍板

**Q1｜德育干事节点（`moral_education_staff`）开学前谁批？**
- 选项 A（推荐）：映射改为 `{MS_ADMIN}`，由周彭/超管代行；等「德育干事」岗位设立后再配具体人（改模板节点为 USER 型或加角色映射）。
- 选项 B：你确认德育干事=某年级组长，保留 `grade_leader`（需明确指定哪几位）。
- 依据：`DEFAULT_CHAINS.behavior_minor` 节点 1 就是 `moral_education_staff`（services.py:499-500）；该岗位在你开学前 5 问中属于「设不设」范畴，当前可能无人。

**Q2｜R4 收口深度：role + student_id_scope 是否足够，还是必须 USER 型固化 assignee？**
- 方案 X（接线级，推荐，不动 engine/不改库）：role 校验 + 写链 `student_id_scope` 校验。基于工单已有 `student_id` + 审批人 assignment scope，能精确挡住你举的全部越权例子（2501/2502、A 年级/B 年级）。
- 方案 Y（重构级，超出 Opening 红线）：create 时用 Resolver 把 `resolved_owner` 固化成 USER 型节点 `approver_id`，approve 直接 `user.id == approver_id`。最干净，但需改 create 逻辑 + 节点结构，属新功能，不建议在 Opening 窗口做。

---

## 4. 接线级修复方案（若你拍板 X + Q1=A）

仅改 `modules/approval/routers.py` 两处，不动库、不动 engine：

- **R4-A**：approve/reject 在 `_check_node_assignee` 调用前加
  ```python
  scope = await student_id_scope(db, user)
  if scope is not None and ar.student_id not in scope:
      raise HTTPException(403, "该工单不在您的责任范围内")
  ```
- **R4-B**：`NODE_ROLE_TO_USER_ROLES["moral_education_staff"]` 由 `{GRADE_LEADER, MS_ADMIN}` 改为 `{MS_ADMIN}`。

> 说明：`student_id_scope` 对 ms_admin 返回 `None`（全校可见），故超管代行 dean/principal/moral_education_staff 不受影响；对班主任/年级组长返回其责任学生列表，工单 `student_id` 不在列表即 403，精确隔离班级/年级。

---

## 5. 验收 Gate（UAT-APPROVAL-CANARY，不碰真实工单）

创建明确标识 canary 工单（无真实处分 / 无学生后果 / 无家长外发 / 无下游副作用），跑：

1. 正确审批人 approve 200 → next node 激活
2. 错误角色 403
3. **同角色错班级/年级 403**（验证 R4-A）
4. 跨校 404
5. 重复终态 400
6. reject reason 落库（operator + 时间 + comment）
7. urge notification +1
8. cleanup

---

## 6. 判定

```
R1 real approve wiring       CODE READY
R2 real reject wiring        CODE READY
R3 refresh / no demo data    CODE READY
R5 truthful urge             CODE READY

R4 authorization             NOT YET PROVEN
  ├─ P1-A 写链缺 student_id_scope       → 待 R4-A 接线
  └─ P1-B moral_education_staff 扩大授权 → 待 Q1 拍板 + R4-B

Deployment                  HOLD
```

原因：审批是状态改变类操作，比「多看一张名单」危险得多。错误的人能点「通过」比按钮是 stub 更严重。先在权限语义上补这一刀，再进维护窗口发布。
