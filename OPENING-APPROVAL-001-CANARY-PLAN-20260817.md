# UAT-APPROVAL-CANARY — OPENING-APPROVAL-001 安全验收脚本

> 配套：`APPROVAL-AUTH-001-20260817.md`（R4 打回证据）、`OPENING-APPROVAL-001-DELIVERY-20260817.md`（接线交付）
> 适用范围：仅用于验证 R1/R2/R3/R4/R5 接线正确性。**绝不使用任何真实业务工单、真实处分、真实学生后果。**

---

## 0. 安全前提（必须满足，否则不执行）

| 约束 | 说明 |
|---|---|
| 不碰真实待办 | 验收对象是一个**临时创建的 canary 工单**，source_type=`canary`、source_id=0，**不关联任何真实违纪/处分记录** |
| 无真实学生后果 | canary 工单即使 approve/reject，因无真实 source，不会触发家长外发、不会激活下游处分、不会进入学生档案 |
| 无 SLA/升级副作用 | canary 在脚本内创建→测试→**立即删除**，生命周期 < 1 分钟；即便 Celery 30min 扫描也来不及拾取 |
| 先部署后验收 | 本脚本在**维护窗口部署 OPENING-APPROVAL-001 之后**运行；未部署则跑的是旧逻辑，无意义 |
| 指定账号 | 用真实账号发请求验证权限矩阵，但只对上述 canary 工单操作 |

---

## 1. canary 工单构造

直接 ORM 插入一条 `approval_requests` 行（绕过业务 create 流程，避免连带副作用）：

```text
approval_requests:
  student_id      = <运行时从 students 表取一个真实学生 S（仅借用其 id 做 scope 隔离测试）>
  event_type      = "canary_smoke"
  source_type     = "canary"          # 关键：无真实 source
  source_id       = 0
  severity        = "major"
  approval_mode   = "serial_and"
  chain_config    = [
    {role:"class_teacher",       status:"pending", label:"班主任审批"},
    {role:"grade_leader",        status:"pending", label:"年级组长审批"},
    {role:"moral_education_staff", status:"pending", label:"德育处审批"}
  ]
  current_status  = "pending"
  current_step    = 0
  school_id       = <生产 school_id>
```

> 为什么借用真实 student_id：R4-A 的 `student_id_scope` 按学生 scope 隔离，必须用真实学生 id 才能验证"同角色错误班级/年级 403"。该学生本人**不产生任何记录变化**（canary 工单 source 是假的）。

运行期自动发现：
- `S` = 取一个真实 student（记其 class_id=C、grade_id=G）
- `U_cls` = 该班 class_teacher（UserRole=class_teacher，其 assignment 含 C）
- `U_grd` = 该年级 grade_leader（UserRole=grade_leader，其 assignment 含 G）
- `U_grd_other` = 另一年级的 grade_leader（scope 不含 G）→ 用于"错误年级 403"
- `U_cls_other` = 另一班的 class_teacher（scope 不含 C）→ 用于"错误班级 403"
- `U_admin` = ms_admin（school-wide，可批 moral_education_staff 节点）
- `U_other_school` = 另一 school 的 staff → 用于"跨校 404"

---

## 2. 验收矩阵（期望结果）

| # | 动作 | 期望 | 验证点 |
|---|---|---|---|
| 1 | `U_cls` POST `/requests/{canary}/approve` | **200**，node0=approved，current_step=1 | R1 真写链 + next node 激活 |
| 2 | `U_grd` POST `/requests/{canary}/approve` | **200**，node1=approved，current_step=2 | 年级组长节点真推进 |
| 3 | `U_admin` POST `/requests/{canary}/approve` | **200**，current_status=approved，completed_at 非空 | moral_education_staff 仅 ms_admin 可批（R4-B） |
| 4 | `U_cls_other` POST `/requests/{canary}/approve`（新 canary） | **403** | R4-A 资源范围：2501班主任不能批2502班 |
| 5 | `U_grd_other` POST `/requests/{canary}/approve`（新 canary） | **403** | R4-A 资源范围：A年级组长不能批B年级 |
| 6 | `U_other_school` POST `/requests/{canary}/approve` | **404** | 跨校隔离 |
| 7 | 已 approved 的 canary 再 approve | **400** | 终态不可重复 |
| 8 | 新 canary 由 `U_cls` reject，reason="canary测试退回" | **200**，current_status=rejected，node.comment=原因 | R2 真驳回 + 理由落库（operation evidence） |
| 9 | canary 某 pending 节点 urge | 返回含"站内提醒"文案；notifications 表该角色 +1 条 | R5 真实站内通知、无外发谎称 |
| 10 | 前端：完成上述任一后，待办列表 `loadTickets()` 数量即时 -1 | 列表与拓扑同步 | R3 刷新无 demo 数据 |

> 第 4/5/6/7 步各用独立 canary 工单，避免相互状态干扰。所有 canary 在脚本末尾统一 DELETE。

---

## 3. 执行方式（维护窗口内，经 dev-mgmt）

```bash
# 1) 先按五步部署铁律发布 OPENING-APPROVAL-001（差异锁定→import冒烟→路由级smoke→release.json→翻转restart+health）
# 2) 在生产 backend 容器内运行 canary 脚本：
cd /opt/wings3/current/backend
set -a && . /opt/wings3/config/production.env && set +a
python scripts/uat_approval_canary.py        # 本脚本随发布一并带到 releases/<ver>/backend/scripts/
```

脚本内部（`scripts/uat_approval_canary.py`）伪代码：

```python
async def main():
    async with async_session() as db:
        canary = make_canary(db, student=S)          # 插入 canary 行
        try:
            assert await call_approve(U_cls, canary) == 200
            assert await call_approve(U_grd, canary) == 200
            assert await call_approve(U_admin, canary) == 200
            # R4-A
            assert await call_approve(U_cls_other, new_canary()) == 403
            assert await call_approve(U_grd_other, new_canary()) == 403
            # 跨校
            assert await call_approve(U_other_school, new_canary()) == 404
            # 终态
            assert await call_approve(U_admin, canary) == 400
            # 驳回
            assert await call_reject(U_cls, new_canary(), "canary测试退回") == 200
            # 催办
            assert "站内提醒" in await call_urge(U_grd, new_canary())
        finally:
            await delete_canaries(db)                 # 清理，绝不残留
```

> 调用层建议直接用 HTTP（带各账号真实 JWT）以覆盖 auth/school_id 注入；若 JWT 获取不便，可退化为直接构造 User 对象调用 router 协程（验证业务逻辑等价）。两种方式均需在脚本注释中标明。

---

## 4. 通过判据

全部 10 项期望命中，且：

- canary 工单在 `approval_requests` 表中 **0 残留**（脚本 finally 删除）；
- `notifications` 表仅新增 canary 相关的站内提醒，无真实家长/外部通道记录；
- 真实业务待办数量在验收前后**无变化**（证明没碰真实工单）。

三项全过 → R4 视为 **PROVEN**，OPENING-APPROVAL-001 可签"R4 已满足"，Deployment 由 HOLD 转为可发布（仍须维护窗口）。

任一项失败 → 回滚本次发布（ln -sfn 上一 release + restart），定位后重跑，不进入开学。
