# WINGS Secure Fabric — Step 0 交付报告

> **基线**：BASELINE FINAL v1.0 FROZEN（9.8/10）｜ **commit**：`a66d92e`（已 push）
> **范围**：仅 Step 0 契约落地 + CF-03 Edge-ready ｜ **时间**：2026-08-16T19:14-19:30+0800
> **纪律遵守**：不重新设计架构 / 不做 Agent/Headscale/WireGuard/DERP/Vault/迁移/Fabric Manager / 不碰 CF-04 R2 / 不碰 19 条存量 / 无 migration / 无生产 DML

## 状态（周主任 2026-08-17 签收）

```text
Step 0: ACCEPTED — CONTRACT LAYER COMPLETE
CF-03 Provider Integration: KNOWN GAP / NOT_WIRED

WINGS Secure Fabric
BASELINE FINAL v1.0 FROZEN
STEP 0
  CONTRACT LAYER: COMPLETE
  commit: a66d92e

Known Gap:
  STEP0-KG-001
  CF-03 production acquisition path NOT_WIRED

No architecture drift.
No business-semantic change.
No Fabric implementation.
No production migration.
```

**精确验收口径**（不是"全部 PASS"）：

```text
Contract tests          PASS
Static typing           PASS
CF-03 regression        PASS
CF-01 regression        PASS
Provider equivalence    DEFERRED
Production wiring       NOT_WIRED
```

---

## 1. FACTS

### 修改文件（git diff --stat：11 文件 +567 行，纯新增 + 1 处配置）

| 文件 | 变更 |
|---|---|
| `wings_contracts/edge/base.py` | 新增（97 行）：`ConnectorStatus`/`HealthStatus`/`FieldDef`/`DataSchema`/`DeltaBatch`/`BaseConnector`（冻结契约照抄） |
| `wings_contracts/edge/protocol.py` | 新增（70 行）：`TaskType`/`TaskStatus`/`EdgeTask`/`TaskResult`/`EdgeHeartbeat`（含 ERRATA-001 import + ERRATA-002 TaskStatus Enum） |
| `wings_contracts/ai/privacy/base.py` | 新增（64 行）：`StudentDataProvider` 抽象（四方法冻结契约） |
| `wings_contracts/ai/privacy/cloud_provider.py` | 新增（87 行）：`CloudStudentDataProvider` 适配器声明（NOT_WIRED，冲突记录见 RISKS） |
| `wings_contracts/ai/privacy/psych_provider.py` | 新增（82 行）：`PsychDataProvider` 最小接口（CF-01 call site 提取） |
| `wings_contracts/edge/README.md` | 新增（163 行）：契约说明 + 示例 + ERRATA-001~003 + fail-closed 纪律 + NON-GOALS |
| `core/privacy_gateway.py` | +4 行：`PRIVACY_GATEWAY_PROVIDER` 配置（默认 cloud） |
| `app/{__init__,edge/__init__,ai/__init__,ai/privacy/__init__}.py` | 包初始化 |

### 验证证据

```text
mypy（6 文件）:  Success, no issues found ✅
pyright（6 文件）: 0 errors, 0 warnings ✅
Contract smoke（6 项）: ALL PASS
  - TaskStatus 仅接受 success/failed/partial（error 拒绝）✅
  - EdgeHeartbeat 正确序列化 HealthStatus ✅
  - FieldDef/DataSchema/DeltaBatch round-trip ✅
  - EdgeTask/TaskResult enum + uuid 关联 ✅
  - CloudStudentDataProvider isinstance StudentDataProvider ✅
  - NOT_WIRED 方法抛 NotImplementedError（诚实接线状态）✅
CF-03 原有测试（test_privacy_gateway.py）: 5/5 PASS ✅
CF-01 原有测试（test_psych_capability.py）: 4/4 PASS ✅
grep 禁用词（app/ 代码）: headscale/wireguard/derp/tailscale/wg0 = 0 ✅
grep Vault 实现: 0 ✅
migration: 0（无新增）✅ ｜ 生产数据 DML: 0 ✅
```

## 2. CONTRACT（最终冻结接口）

```python
# wings_contracts/edge/base.py
class ConnectorStatus(str, Enum): HEALTHY / DEGRADED / DOWN
class HealthStatus(BaseModel): connector_name, status, latency_ms, last_check, message=None
class FieldDef(BaseModel): name, data_type, nullable=True, classification="internal", storage_policy="CLOUD_ALLOWED", description=None
class DataSchema(BaseModel): entity_type, fields: list[FieldDef], primary_key, updated_at_field, supports_delta=False
class DeltaBatch(BaseModel): entity_type, records: list[dict], next_cursor=None, has_more=False
class BaseConnector(ABC): name / health_check / read_schema / fetch_delta / fetch_by_id

# wings_contracts/edge/protocol.py（ERRATA-001/002 已应用）
class TaskType(str, Enum): SYNC_DELTA / FETCH_RECORD / HEALTH_CHECK / RESOLVE_IDENTITY / AI_CONTEXT_BUILD / EXECUTE_COMMAND(保留值)
class TaskStatus(str, Enum): SUCCESS / FAILED / PARTIAL
class EdgeTask(BaseModel): task_id: UUID, school_id, task_type, connector_name=None, payload={}, created_at, timeout_sec=30
class TaskResult(BaseModel): task_id, status: TaskStatus, data=None, error=None, started_at, finished_at
class EdgeHeartbeat(BaseModel): edge_id, school_id, version, timestamp, cpu/memory/disk_percent, connectors: dict[str, HealthStatus], pending_tasks, vault_status=None, privacy_gateway_status=None, fabric_status=None

# wings_contracts/ai/privacy/base.py
class StudentDataProvider(ABC):
    get_behavior_events(student_token, days=30) -> list[dict]
    get_attendance(student_token, days=30) -> dict
    get_grades(student_token, days=90) -> list[dict]
    get_psych_risk(student_token) -> dict  # 仅 risk_level+trend+confirmed
```

## 3. NON-CHANGES（明确没碰）

```text
✗ CF-04：Review.vue / confirm/modify/reject / review_status 状态机 /
  reviewed_by/at/note / activation / approval_requests / counselor role gate /
  CF04 ENUM migration 全部未动
✗ CF-04 R2 责任人通知：未做
✗ 19 条真实 PENDING_REVIEW：未动
✗ Edge Agent / Headscale / WireGuard / DERP / Tailscale：未实现（仅 README NON-GOALS 文字提及）
✗ Edge Vault（Identity/Psych）：未实现
✗ 数据迁移 / Fabric Manager / 远程 shell：未做
✗ 现有 SQL/ORM/业务逻辑：未重写（privacy_gateway.py 仅 +4 行配置常量）
✗ migration：0 ｜ 生产数据 DML：0
```

## 4. RISKS（真实发现，未顺手修）

```text
R1（记录，不修 → 正式登记为 STEP0-KG-001）: CloudStudentDataProvider NOT_WIRED
  CF-03 真实取数在 AIPrescriptionAggregator.build_student_context
  （modules/ai_prescription/aggregator.py:75，13 路内嵌 SQL 聚合上下文），
  与 Provider 单类数据门面接口不同构。机械适配会改语义/时间窗口/排序
  （违反契约 D）。接线待 Edge 阶段由 EdgeStudentDataProvider 需求驱动。
  等价性验收 = DEFERRED / NOT_APPLICABLE_IN_STEP0（未发生 refactor，无前后对比对象；
  按周主任签收要求不写 PASS）。

R2（记录，不修）: PsychDataProvider 不复制权限门
  现有心理读取语义 = require_psych_access 权限门 + 特定表查询 + role/scope
  脱敏降级，无单一可映射函数；抽 Provider 会削弱 Capability+Scope+Audit
  （违反纪律 E.6）。接线待 Edge 阶段，权限门仍留 Cloud 侧。

R3（观察）: mypy/pyright 需 --explicit-package-bases / --pythonpath venv 才能
  全绿（本地系统 python 无 pydantic）——CI 若引入类型检查需配 venv 路径。
```

## 验收对照（契约 J，精确状态）

```text
A. git diff --stat     ✅ 11 文件 +567
B. git diff 范围       ✅ 仅 app/ + core/privacy_gateway.py
C. mypy / pyright      ✅ 0 issue
D. Pydantic smoke      ✅ 6/6
E. CF-03 测试          ✅ 5/5
F. CF-01 权限测试      ✅ 4/4
G. CF-04 R1 regression ✅ 未触碰（NON-CHANGES §3）
H. grep 无禁用词       ✅
I. 无 migration        ✅
J. 无生产 DML          ✅
+ contract tests       ✅（TaskStatus 枚举 / Heartbeat serialize / FieldDef round-trip /
                          Provider 抽象可实例化 / NOT_WIRED 抛 NotImplementedError）
```

### 等价性验收（明确降级，不写 PASS）

```text
CF03-PROVIDER-EQUIVALENCE:
DEFERRED / NOT_APPLICABLE_IN_STEP0

Reason:
AIPrescriptionAggregator.build_student_context currently owns
13-source data acquisition with embedded queries.
Frozen StudentDataProvider's four-method contract is not
isomorphic to the production acquisition path.

Forcing integration in Step 0 would change query semantics
and/or authorization boundaries.

No production call path was rewired.
```

---

## STEP0-KG-001（唯一已知技术债，正式登记）

```text
STEP0-KG-001
CF-03 production acquisition path is not yet Provider-backed.

Affected:
  AIPrescriptionAggregator.build_student_context
  (modules/ai_prescription/aggregator.py:75, 13 路内嵌 SQL)

Current:
  13-source embedded acquisition logic

Target:
  Provider-compatible acquisition boundary

Trigger for remediation:
  - before EdgeStudentDataProvider becomes real, OR
  - before Privacy Gateway moves to Edge Secure

Rule:
  preserve existing data semantics,
  ResourceScope,
  psych capability,
  audit behavior,
  and output shape.

Status: OPEN — 现在不修。未来 Edge Secure 落地前的消除条件。
```

**禁止顺手继续做**（后续无明确授权不得执行）：

```text
✗ 拆 AIPrescriptionAggregator 13 路 SQL
✗ 新增第 5/6/7 个 StudentDataProvider 方法
✗ 做 EdgeStudentDataProvider
✗ 做 Psych Vault
✗ 做 Edge Agent
✗ Headscale / WireGuard / DERP
✗ R2 通知责任人
✗ 动 19 条真实 PENDING_REVIEW
```

---

## ERRATA-004（P0 Release Namespace Collision Remediation）

> 授权：周主任 @ STEP0-PKG-001（2026-08-17）。仅修 Python namespace collision，
> **不重新打开 Secure Fabric，不改变 Step 0 契约语义**。登记为 baseline erratum，
> 不发 v1.1。

```text
ERRATA-004
Step 0 Python namespace collision remediation

Original documented path:
  backend/app/edge/
  backend/app/ai/privacy/

Canonical runtime-safe path:
  backend/wings_contracts/edge/
  backend/wings_contracts/ai/privacy/

Reason:
  backend/app.py is the existing WINGS production entry module.
  A sibling Python package named app shadows app.py and prevents
  normal backend release startup (Attribute "app" not found in module "app").

Semantic contract change:
  NONE

Interface change:
  NONE

Behavior change:
  NONE

Secure Fabric implementation:
  NONE

Remediation scope (rename / import reconciliation only):
  - git mv backend/app → backend/wings_contracts（保留历史）
  - 删除已为空的 backend/app/
  - wings_contracts/ai/privacy/cloud_provider.py 内部 import 改 app.ai.privacy → wings_contracts.ai.privacy
  - audit_pkg/step0_contract_smoke.py import 改 app.edge/app.ai.privacy → wings_contracts.*
  - 两份 Step 0 交付文档 package path 同步
  - 未触碰：BaseConnector interface / StudentDataProvider interface / 方法集 /
    production provider / aggregator 13-source SQL / EdgeStudentDataProvider /
    Vault / WireGuard / Fabric / 业务 DB / migration

Status after remediation:

  Secure Fabric BASELINE FINAL v1.0
  FROZEN

  Step 0
  ACCEPTED — CONTRACT LAYER COMPLETE

  ERRATA-004
  APPLIED

Provenance note:
  a66a6ce = 开学 UAT 发现的两个业务修复（UAT-F1 psych search 500 / UAT-F2 班级花名册横向 scope）
  46481de = UAT-F2 权威源硬化（load_assignment_scopes，与 get_student_or_403 同机制）
  <namespace commit> = 纯发布阻塞 / namespace 修复（ERRATA-004 / STEP0-PKG-001）
```
