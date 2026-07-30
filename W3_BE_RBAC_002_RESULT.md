# W3-BE-RBAC-002 动态验收结果报告

> 生成时间：2026-07-31 00:5x（本地）
> 验收对象：**FastAPI「Wings 3.0」`backend/`**（非 Flask `grade7-new/`）
> 报告状态：**结论为「不予关闭」**

---

## 一、结论摘要

| 项 | 结果 |
|---|---|
| 原修复是否生效 | **是（部分）** — 8 类受保护端点中 18/20 已收口 |
| 自动化用例 | **28 / 30 通过，2 失败** |
| 全端点 × 低权限角色探针 | **20 端点 × 6 低权限角色 = 120 组合，12 组穿透** |
| 跨租户追加取证 | **5 / 5 低权限账号读到外校学生违纪明细** |
| 残留缺陷 | **R1（3 项子缺陷）+ R2（2 项子缺陷）= 5 项** |
| **W3-BE-RBAC-002 状态** | 🔴 **OPEN（不予关闭）** |

**不予关闭的理由**：在原修复未覆盖的两个端点上，仍存在**可实证的处分数据越权**——
① 一处泄漏**未生效的内部处分草稿全字段**（含年级组长/审批人意见、铁证快照），危害等级高于已生效处分；
② 另一处服务层**完全没有 `school_id` 条件**，构成**跨租户读泄漏**，直接违反项目既定的多租户双保险约定。详见第六节。

---

## 二、验收环境指纹（隔离性证明）

| 项 | 值 | 隔离性 |
|---|---|---|
| 目标实例 | `uvicorn app:app --host 127.0.0.1 --port 8000` | 仅回环，不对外 |
| 进程 PID | 24396（父 14040），启动于 2026-07-31 00:35:22 | — |
| 实例日志自报数据库 | `127.0.0.1:3307/wings3_audit_test` | ✅ **非** Flask 旧库 `grade7_new` |
| 数据库表数 | 108（`create_all` 建立 + `alembic stamp head` → `f7c2a91d4b60`） | 全新空库 |
| 业务数据来源 | 100% 由 `backend/_seed_audit_accounts.py` 生成的合成数据 | ✅ 无任何真实学生/家长/处分/心理数据 |
| Redis | Docker `wings3-audit-redis` (redis:7-alpine) `127.0.0.1:6380`，`requirepass` 开启 | ✅ 与本机 Redis 3.0.504 隔离 |
| MySQL | Docker `grade7-new-db` (mysql:8.0) `127.0.0.1:3307` | 与 Flask 同容器但**不同库** |
| 模块加载 | 32 发现 / 14 加载 / 0 熔断 / 18 未启用（本校未开通） | `discipline` ✅ 已注册 |

**运行版本指纹**

```
Python      3.13.14
FastAPI     0.138.0
SQLAlchemy  2.0.51
Pydantic    2.13.4
健康检查     {"message":"ok","detail":"Wings 3.0 Core Online"}
```

**代码基线**

```
分支    audit/w3-be-rbac-002     （未合入 master）
检查点  bd63d47  fix(rbac): restrict sanction records and add parent child endpoint
父提交  4165c8c  （修复前基线）
差异包  W3_BE_RBAC_002_before_test.patch（861 行）
```

---

## 三、合成账号与数据拓扑

账号 12 个，覆盖全部 9 种角色，统一 `audit_` 前缀、`display_name` 带 `AUDIT_TEST` 标记。
**口令为 18 位随机四类字符，仅写入仓库外文件 `C:/Users/Administrator/.wings3_audit_accounts.json`，全程未打印至终端、未写入日志、未进入本报告、未提交 Git。**

```
组织  梨江中学(school=1) ← branch=1 ← org=1
年级  年级A(1)                          年级B(2)
班级  班A1(1)      班A2(2)              班B1(3)
学生  学生A1(1)    学生A2(2)            学生B1(3)
绑定  audit_class_teacher→班A1      audit_class_teacher_b→班A2
      audit_grade_leader→年级A      audit_grade_leader_b→年级B
      audit_parent→学生A1           audit_parent_b→学生A2
      audit_student→学生A1
```

处分数据 4 条：

| # | 学生 | 班级 | 年级 | 等级 | 状态 | 用途 |
|---|---|---|---|---|---|---|
| 1 | A1 | A1 | A | WARNING | ACTIVE | 公开记录 |
| 2 | A2 | A2 | A | DEMERIT | ACTIVE | 同年级他班对照 |
| 3 | B1 | B1 | B | SERIOUS_WARN | ACTIVE | 跨年级对照 |
| 4 | A1 | A1 | A | PROBATION | **DRAFT_PENDING** | **内部草稿，家长不可见** |

---

## 四、路由核验（测试前置门槛）

已导出 `openapi-wings3-rbac002.json`（151 条路径）。用户指定必须存在的两条路由：

| 路径 | 状态 |
|---|---|
| `GET /api/v1/discipline/sanctions` | ✅ 存在 |
| `GET /api/v1/discipline/parent-portal/children/{child_id}/discipline-records` | ✅ 存在 |

匿名探针（10 个 discipline 端点，无 Token）：**10/10 返回 401，零数据泄漏**。

---

## 五、测试结果矩阵

### 5.1 自动化用例（`test_rbac_sanctions.py`，30 例）

| 用例 | 方法 | 路径 | 角色 | 组织/年级/班级/家长绑定 | 期望 | 实际 | 条数 | 越权泄漏 | 判定 |
|---|---|---|---|---|---|---|---|---|---|
| TC-01 | GET | /discipline/sanctions | anonymous | 无 | 401 | 401 | 0 | 无 | PASS |
| TC-02 | GET | /discipline/sanctions | parent | bound=学生A1 | 403 | 403 | 0 | 无 | PASS |
| TC-03 | GET | /discipline/sanctions | student | bound=学生A1 | 403 | 403 | 0 | 无 | PASS |
| TC-04 | GET | /discipline/sanctions | teacher | 无 | 403 | 403 | 0 | 无 | PASS |
| TC-05 | GET | /discipline/sanctions | counselor | 无 | 403 | 403 | 0 | 无 | PASS |
| TC-13a | GET | /discipline/sanctions | group_admin | org=1 | 403 | 403 | 0 | 无 | PASS |
| TC-13b | GET | /discipline/sanctions | branch_admin | branch=1 | 403 | 403 | 0 | 无 | PASS |
| TC-14 | GET | /discipline/sanctions | ms_admin | school=1 | 200/total=4 | 200 | 4 | 无 | PASS |
| TC-06 | GET | /discipline/sanctions | class_teacher | class=A1 | 200/total=2 | 200 | 2 | 无 | PASS |
| TC-07 | GET | /discipline/sanctions?class_id=A2 | class_teacher | class=A1(强制) | 参数被忽略/total=2 | 200 | 2 | 无 | PASS |
| TC-07b | GET | /discipline/sanctions | class_teacher | class=A2 | 200/total=1 | 200 | 1 | 无 | PASS |
| TC-08 | GET | /discipline/sanctions | grade_leader | grade=A | 200/total=3 | 200 | 3 | 无 | PASS |
| TC-09 | GET | /discipline/sanctions?grade_id=B | grade_leader | grade=A(强制) | 参数被忽略/total=3 | 200 | 3 | 无 | PASS |
| TC-09b | GET | /discipline/sanctions | grade_leader | grade=B | 200/total=1 | 200 | 1 | 无 | PASS |
| TC-17 | GET | /discipline/sanctions?student_id=B1 | class_teacher | class=A1(强制) | 200/total=0 | 200 | 0 | 无 | PASS |
| TC-18 | GET | /discipline/sanctions/{本班} | class_teacher | class=A1 | 200 | 200 | 1 | 无 | PASS |
| TC-19 | GET | /discipline/sanctions/{他班} | class_teacher | class=A1 | 403/404 | 403 | 0 | 无 | PASS |
| TC-20 | GET | /discipline/sanctions/{他年级} | grade_leader | grade=A | 403/404 | 403 | 0 | 无 | PASS |
| TC-10 | GET | /parent-portal/children/A1/... | parent | bound=学生A1 | 200/records=1/无草稿 | 200 | 1 | 无 | PASS |
| TC-11 | GET | /parent-portal/children/A2/... | parent | bound=学生A1 | 403 | 403 | 0 | 无 | PASS |
| TC-11b | GET | /parent-portal/children/B1/... | parent | bound=学生A1 | 403 | 403 | 0 | 无 | PASS |
| TC-12 | GET | /discipline/sanctions?school_id=1 | parent | bound=学生A1 | 403 | 403 | 0 | 无 | PASS |
| TC-21 | GET | /parent-portal/children/A1/... | student | bound=学生A1 | 403 | 403 | 0 | 无 | PASS |
| TC-22 | GET | /parent-portal/children/A1/... | ms_admin | 无家长绑定 | 403 | 403 | 0 | 无 | PASS |
| TC-15 | GET | /discipline/sanctions/{id} | parent | bound=学生A1 | 403 | 403 | — | 无 | PASS |
| TC-16 | GET | /discipline/stats | parent | bound=学生A1 | 403 | 403 | — | 无 | PASS |
| **TC-23** | **GET** | **/discipline/drafts** | **teacher** | **无** | **403** | **200** | **1** | **全校草稿全字段** | **FAIL** |
| TC-24 | GET | /discipline/stats | counselor | 无 | 403 | 403 | — | 无 | PASS |
| **TC-25** | **GET** | **/discipline/escalation-trigger/{sid}** | **student** | **bound=学生A1** | **403** | **200** | — | **任意学生违纪画像** | **FAIL** |
| TC-26 | GET | /discipline/appeals | parent | bound=学生A1 | 403 | 403 | — | 无 | PASS |

**汇总：28 PASS / 2 FAIL**。取证明细：`rbac_test_results.json`

### 5.2 全端点 × 低权限角色穿透探针（`probe_discipline_matrix.py`）

非破坏性设计：写操作一律指向不存在的 ID（999999），未修改任何数据。

20 个 discipline 端点 × 6 类低权限角色（teacher / counselor / parent / student / group_admin / branch_admin）：

- **18 个端点：全部 6 角色均返回 403 —— 已完全收口** ✅
- **2 个端点：全部 6 角色均返回 200 —— 完全放行** ❌

```
GET /discipline/drafts                        teacher=200 counselor=200 parent=200 student=200 group_admin=200 branch_admin=200
GET /discipline/escalation-trigger/{sid}      teacher=200 counselor=200 parent=200 student=200 group_admin=200 branch_admin=200
```

矩阵原始数据：`discipline_authz_matrix.json`

---

## 六、残留缺陷（W3-BE-RBAC-002 不予关闭的依据）

### 🔴 R1 — `GET /api/v1/discipline/drafts` 处分草稿箱越权（高危）

`modules/discipline/routers.py:451 list_drafts`。三条独立子缺陷：

**R1-a 无角色闸门**
装饰器上无 `require_role`，函数体内也无角色判断。家长、学生、普通教师、心理教师、集团管理员、片区管理员**均可读取**。
实测泄漏字段（全字段返回，无脱敏）：

```
student_id, student_name, class_id, class_name, grade_id, level, status, reason,
evidence, evidence_snapshot, creator_id, creator_name, approver_id, approver_name,
approver_comment, grade_leader_id, grade_leader_name, grade_leader_comment,
grade_leader_reviewed_at, document_no, behavior_record_id, auto_generated, ...
```

危害高于已生效处分：草稿是**尚未审批生效的内部拟处分**，含 `grade_leader_comment` / `approver_comment` 等内部审批意见与 `evidence_snapshot` 铁证快照。**学生本人可看到学校正在酝酿对自己的留校察看处分及内部评语。**

**R1-b 班主任可伪造 `class_id` 横向越权**
第 470–471 行：

```python
if current_user.role == UserRole.CLASS_TEACHER:
    _cid = _cid or current_user.class_id     # ← 用 or，客户端显式传参会覆盖绑定
```

对比 `list_sanctions` 的正确写法是 `class_id = current_user.class_id`（无条件覆盖）。
实测：班主任B（绑定班A2）请求 `?class_id=1` → 返回**班A1 学生A1 的草稿**（total=1）。

**R1-c 年级组长未做年级收口**
docstring 声称「年级组长：看全年级」，实现中对 GRADE_LEADER **无任何过滤**。
实测：年级组长B（绑定年级2）无参数请求 → 返回**年级1 的草稿**。

### 🔴 R2 — `GET /api/v1/discipline/escalation-trigger/{student_id}` 越权（**升级为高危**）

**R2-a 无角色闸门 + 无学生归属校验（校内横向越权）**

`modules/discipline/routers.py:573 check_escalation_trigger`。
任意已登录用户可对**任意 `student_id`** 探测：30 天窗口内严重违纪计数 `serious_count`、证据列表 `evidence`、已有草稿数 `existing_draft_count`、是否触发升级 `triggered`。
实测：家长（绑定学生A1）查询**学生B1**（跨年级他人孩子）→ 200，返回完整画像结构。
构成**全校学生违纪画像可枚举**（student_id 为自增整数，可遍历）。

> 对照：同功能的 `GET /discipline/escalation/{student_id}` **已正确加上** `require_role(MS_ADMIN, GRADE_LEADER, CLASS_TEACHER)`。R2-a 属于原修复的遗漏，非设计意图差异。

**R2-b 服务层无 `school_id` 过滤 → 跨租户越权（本轮追加取证，🔴 高危）**

`modules/discipline/services.py:594 detect_escalation_trigger(db, student_id)` **签名中根本没有 `school_id` 参数**，SQL WHERE 仅为：

```python
.where(
    BehaviorRecord.student_id == student_id,
    BehaviorRecord.type == "serious",
    BehaviorRecord.status == "active",
    BehaviorRecord.incident_date >= window_start,
    BehaviorRecord.incident_date <= window_end,
)
```

直接违反项目既定的**多租户双保险**约定（Router `verify_entity_ownership` + Service `WHERE school_id`），此处两道全缺。

**动态复现（`_probe_cross_tenant.py` + `_probe_xt_http.py`，隔离库内合成外校数据，取证后已删除）**：

在隔离库新建 `school_id=2` 的合成外校，含 1 名学生（`student_id=4`）与 3 条 30 天内严重违纪；随后以 `school_id=1` 的账号发起请求：

| 调用方（school_id=1） | HTTP | `triggered` | `serious_count` | `evidence` 条数 | 判定 |
|---|---|---|---|---|---|
| STUDENT | 200 | true | 3 | 3 | 🔴 CROSS_TENANT_LEAK |
| PARENT | 200 | true | 3 | 3 | 🔴 CROSS_TENANT_LEAK |
| TEACHER | 200 | true | 3 | 3 | 🔴 CROSS_TENANT_LEAK |
| CLASS_TEACHER | 200 | true | 3 | 3 | 🔴 CROSS_TENANT_LEAK |
| GRADE_LEADER | 200 | true | 3 | 3 | 🔴 CROSS_TENANT_LEAK |

5/5 全部读到**外校学生的违纪明细原文**（`description` 字段逐条返回）。取证数据已清理，核验残留：`schools=1 / students=3 / discipline_records=0`。

> 影响面判定：单校部署下 R2-b 退化为 R2-a；但本项目 `School` 表已承载多校（生产存在 `school_id=99/100` 等学段隔离租户），因此该缺陷在生产语义下**成立且为高危**。

---

## 七、本次验收顺带发现的环境/架构缺陷（独立于 RBAC-002）

| 编号 | 等级 | 描述 |
|---|---|---|
| **W3-ENV-WEBHOOK-001** | 🟠 中 | `discipline/routers.py:596` 在 **import 期**硬性 `raise ValueError`（`WEBHOOK_SECRET` 未配置）。而 `backend/.env` 中**并无该变量**。后果：模块加载器捕获异常后**静默跳过整个 discipline 模块**，`/api/v1/discipline/*` 全部 404，但应用照常启动、健康检查照常 200。首次启动即复现。建议：改为运行期惰性校验，或在 `.env.example` 中显式声明为必填项。 |
| **W3-ENV-REDIS-001** | 🟠 中 | 本机 Windows 原生 Redis **3.0.504** 无任何认证（`REDIS_PASSWORD` 被服务端忽略），且不支持 redis-py 6.x 的 RESP3 `HELLO` 握手 → 事件总线静默降级、跨模块事件注入全部跳过，而应用不报致命错。本次验收已改用隔离的 Redis 7 容器规避。 |
| **W3-DB-FK-001** | 🟠 中 | `growth` 模块 5 个外键类型与被引用主键不匹配（`Integer` vs `BigInteger`）：`growth_timeline_events.reporter_id/student_id`、`growth_periodical_snapshots.student_id`、`growth_active_composite_alerts.resolved_by/student_id`。空库 `create_all` 直接触发 MySQL errno 3780。本次以**内存态剥离外键**规避，**未改动任何源码**。 |
| **W3-DB-ALEMBIC-001** | 🟡 低 | 迁移基线 `2d8813121d03` 是针对既有库的增量脚本（首条 DDL 即 `DROP INDEX ... ON workload_logs`），**无法在空库上执行**。空库只能走 `create_all` + `alembic stamp head`。 |
| **W3-ARCH-DAG-001** | 🟡 低 | 模块加载器报 **DAG 循环依赖**，涉及 `{homework_mgmt, error_funnel, research, parent_portal, growth}`。当前靠降级排序兜底，未阻断启动。 |
| **W3-ENV-EXPOSE-001** | 🔴 **高** | 计划任务 `Grade7ManagementSystem`（见下节）拉起的 Flask 应用监听 **`0.0.0.0:5000`**，即**对整个局域网开放**，而非仅回环。 |

---

## 八、W3-ENV-PROCESS-001 — 端口进程来源排查

**状态：🟡 部分查明，仍 OPEN**

已查明的持久化来源：

```
计划任务名  Grade7ManagementSystem
触发器      ① 开机启动（延迟 30 秒）  ② 用户登录（延迟 10 秒）
运行主体    Administrator，RunLevel = Highest
动作        powershell -NoProfile -WindowStyle Hidden -Command
            "Start-Process 'C:\...\Python312\python.exe'
             -ArgumentList '-u','app.py'
             -WorkingDirectory 'C:\Users\Administrator\WorkBuddy\2026-05-22-task-7\student-mgmt'
             -WindowStyle Hidden"
监听        waitress serve(app, host="0.0.0.0", port=5000, threads=4)
最近运行    2026-07-28 08:49:49，结果码 0
当前 5000   无监听（进程已退出）
```

**这意味着本机存在第三套代码库**，此前未纳入审计范围：

| # | 路径 | 技术栈 | 端口 | 审计状态 |
|---|---|---|---|---|
| 1 | `2026-05-26-20-55-49/grade7-new/` | Flask 3.1.0 | 5000 | 非本次目标 |
| 2 | `2026-05-26-20-55-49/backend/` | FastAPI Wings 3.0 | 8000 | ✅ 本次验收目标 |
| 3 | `2026-05-22-task-7/student-mgmt/` | Flask + waitress | **0.0.0.0:5000** | ❌ **从未审计，开机自启，局域网暴露** |

**仍未查明**：上一轮会话中占用 8000 端口的进程（PID 24056）来源。服务、计划任务、启动项三处扫描均未命中 8000。当前 8000 的占用者已确认是本次审计实例（PID 24396 / 父 14040，命令行为我们自己的 uvicorn）。

**留置动作**：若 8000 再次出现非预期监听，先用
`Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select CommandLine,CreationDate,ParentProcessId`
完整取证后再终止，**不得凭进程名臆断**。

---

## 九、建议补丁（**未实施，待确认**）

两处修复均为单文件、与现有写法一致的最小改动，但**会改变现有行为**（当前前端 `frontend/src/api/behavior.ts:303/328` 有调用），依据「影响现有功能时停手确认」的铁律，**已停手等待指令**。

```python
# modules/discipline/routers.py  —— R1
@router.get(
    "/drafts",
    dependencies=[
        Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER))
    ],
)
async def list_drafts(...):
    # R1-b: or → 无条件覆盖，与 list_sanctions 保持一致
    if current_user.role == UserRole.CLASS_TEACHER:
        _cid = current_user.class_id
    # R1-c: 补齐年级组长收口
    elif current_user.role == UserRole.GRADE_LEADER:
        grade_id = current_user.grade_id
```

```python
# modules/discipline/routers.py  —— R2-a
@router.get(
    "/escalation-trigger/{student_id}",
    dependencies=[
        Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER))
    ],
)
async def check_escalation_trigger(...):
    # 并补学生归属校验（与 list_sanctions / parent_discipline_records 同款写法）
```

```python
# modules/discipline/services.py  —— R2-b（跨租户，需改服务层签名）
async def detect_escalation_trigger(
    db: AsyncSession,
    student_id: int,
    school_id: int,          # ← 新增必填参数
) -> dict:
    ...
    .where(
        BehaviorRecord.school_id == school_id,   # ← 新增租户条件
        BehaviorRecord.student_id == student_id,
        ...
    )
```

**R2-b 调用面清点（已完成，全仓 grep，排除 `.venv`）**：

| 调用点 | 上下文 | 改造成本 |
|---|---|---|
| `modules/discipline/routers.py:587` | HTTP 入口，`current_user.school_id` 现成 | 加一个实参 |
| `modules/behavior/services.py:103` | 严重违纪落库 Hook，作用域内已有 `student` 对象 | 传 `student.school_id` |

即 R2-b 影响 **3 个文件、2 处调用点**，无 Celery / 事件总线 / 定时任务调用，改造面可控。

> 附带核查：下游 `create_escalation_draft`（`services.py:707`）的 `school_id` 取自 `student.school_id`，**写入侧租户正确**，不存在跨租户写。R2-b 是**纯读泄漏**。

> 注：`current_user.role` 为 str/Enum 混用，实际编码时需沿用文件内既有的 `UserRole(user_role)` 归一化写法，不可裸比较。

**需要确认的问题**：`/discipline/drafts` 与 `/escalation-trigger` 当前是否有 TEACHER 或其他角色的合法调用场景？若有，闸门角色集合需相应放宽并补充数据域过滤，而非简单收紧。

---

## 十、产物清单

| 文件 | 说明 |
|---|---|
| `W3_BE_RBAC_002_RESULT.md` | 本报告 |
| `rbac_test_results.json` | 30 条用例结构化取证 |
| `discipline_authz_matrix.json` | 20 端点 × 6 角色穿透矩阵 |
| `backend/xt_cross_tenant_probe.json` | R2-b 跨租户越权取证结果（5 账号） |
| `backend/_probe_cross_tenant.py` | 跨租户合成外校播种/清理（带隔离库安全闸门） |
| `backend/_probe_xt_http.py` | 跨租户 HTTP 取证（不打印任何口令） |
| `openapi-wings3-rbac002.json` | 目标实例 OpenAPI 快照（151 路径） |
| `test_rbac_sanctions.py` | 测试脚本（已移除「口令=用户名」硬编码，改读仓库外凭据） |
| `probe_discipline_matrix.py` | 非破坏性穿透探针 |
| `backend/_seed_audit_accounts.py` | 合成数据播种器（带隔离库安全闸门，支持 `--cleanup`） |
| `backend/_init_audit_schema.py` | 空库建表（内存态剥离类型不匹配外键） |
| `backend/_run_audit_instance.sh` | 审计实例启动器（隔离库校验 + 密钥仓库外注入） |
| `backend/alembic_audit.ini` | 纯 ASCII 版 alembic 配置（原文件中文注释在 GBK 环境下崩溃） |

---

## 十一、凭据与数据处置

**当前状态：审计实例仍在运行，主合成数据与凭据文件尚未清理**，以便复核或在补丁确认后立即回归。

**R2-b 跨租户取证数据（外校 `school_id=2` + 1 学生 + 3 条违纪）已在取证结束后立即删除**，残留核验：`schools=1 / students=3 / discipline_records=0`。

仓库外凭据文件（**均未进入 Git**）：

- `C:/Users/Administrator/.wings3_audit_secrets.env` — `WEBHOOK_SECRET` / `REDIS_PASSWORD`
- `C:/Users/Administrator/.wings3_audit_accounts.json` — 12 个合成账号口令 + 拓扑

复核完成后的清理指令：

```bash
# 1) 删除全部合成账号/学生/班级/年级/处分 + 凭据文件
cd backend && DATABASE_URL="...wings3_audit_test" ./.venv/Scripts/python.exe _seed_audit_accounts.py --cleanup

# 2) 停止审计实例
Stop-Process -Id <uvicorn_pid> -Force

# 3) 销毁隔离 Redis
docker rm -f wings3-audit-redis

# 4) 如需彻底销毁隔离库
docker exec grade7-new-db mysql -u root -p -e "DROP DATABASE wings3_audit_test;"

# 5) 删除密钥文件
rm C:/Users/Administrator/.wings3_audit_secrets.env
```

---

## 十二、最终判定

> **W3-BE-RBAC-002：不予关闭（OPEN）**
>
> 原修复对 `sanctions` / `stats` / `appeals` / `escalation` / 家长门户共 18 个端点的收口**已在隔离环境下动态验证有效**，包括数据范围强制绑定与参数伪造防护。
> 但 `drafts`（R1，3 条子缺陷）与 `escalation-trigger`（R2，2 条子缺陷）两处越权仍可实证复现：
> 前者泄漏内部处分草稿全字段（含审批意见与铁证快照），后者服务层无 `school_id` 条件、已实测**跨租户读到外校学生违纪明细**。
> 建议：将 R1（a/b/c）与 R2（a/b）共 5 项补入本 Finding 后重新修复并回归，全绿方可关闭。
>
> **同时提请注意**：`W3-ENV-EXPOSE-001`（开机自启的未审计 Flask 服务监听 `0.0.0.0:5000`）等级为高，且完全独立于本 Finding，建议单独立项。
