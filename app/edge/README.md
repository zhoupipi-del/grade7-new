# WINGS Edge Core — Step 0 契约说明

> 源：WINGS Secure Fabric **BASELINE FINAL v1.0 FROZEN** / Step 0
> 状态：Step 0 契约落地（Edge Agent / Headscale / WireGuard / DERP / Vault 实现 / 数据迁移 / Fabric Manager **不在本轮**）

## Step 0 目的

在不动 Edge 运行时（Agent/Fabric/Vault 全部不实现）的前提下，把 **Connector 接口、Edge↔Cloud 协议、StudentDataProvider 抽象** 三类契约先落到代码，使 CF-03 Privacy Gateway 具备 **Edge-ready** 结构（数据源可替换、去标识化与访问分离、搬迁零修改）。

## 文件地图

| 文件 | 内容 |
|---|---|
| `app/edge/base.py` | `ConnectorStatus` / `HealthStatus` / `FieldDef` / `DataSchema` / `DeltaBatch` / `BaseConnector`（冻结契约） |
| `app/edge/protocol.py` | `TaskType` / `TaskStatus` / `EdgeTask` / `TaskResult` / `EdgeHeartbeat`（含 ERRATA-001/002） |
| `app/ai/privacy/base.py` | `StudentDataProvider` 抽象（四方法，冻结契约） |
| `app/ai/privacy/cloud_provider.py` | `CloudStudentDataProvider` 适配器声明（NOT_WIRED，见下） |
| `app/ai/privacy/psych_provider.py` | `PsychDataProvider` 抽象（最小接口，由 CF-01 call site 提取） |
| `core/privacy_gateway.py` | CF-03 Edge-ready：新增 `PRIVACY_GATEWAY_PROVIDER` 配置（默认 `cloud`） |

## BaseConnector 使用说明

```python
from datetime import datetime, timedelta
from app.edge.base import BaseConnector, DataSchema, DeltaBatch, HealthStatus, ConnectorStatus

class SisConnector(BaseConnector):
    name = "sis"  # property

    async def health_check(self) -> HealthStatus:
        return HealthStatus(connector_name="sis", status=ConnectorStatus.HEALTHY,
                            latency_ms=12, last_check=datetime.now())

    async def read_schema(self) -> DataSchema:
        return DataSchema(entity_type="student", fields=[], primary_key="id",
                          updated_at_field="updated_at", supports_delta=True)

    async def fetch_delta(self, since, cursor=None) -> DeltaBatch:
        return DeltaBatch(entity_type="student", records=[], next_cursor=None, has_more=False)

    async def fetch_by_id(self, entity_type, entity_id) -> dict:
        return {}
```

## DataSchema / DeltaBatch 示例

```python
from app.edge.base import FieldDef, DataSchema, DeltaBatch

schema = DataSchema(
    entity_type="attendance",
    fields=[
        FieldDef(name="student_id", data_type="string", classification="student_pii",
                 storage_policy="TOKENIZED_CLOUD"),
        FieldDef(name="event_time", data_type="datetime"),
    ],
    primary_key="id",
    updated_at_field="updated_at",
    supports_delta=True,
)

batch = DeltaBatch(entity_type="attendance", records=[{"id": 1}],
                   next_cursor="abc", has_more=True)
```

## EdgeTask / TaskResult / EdgeHeartbeat 示例

```python
from uuid import uuid4
from datetime import datetime
from app.edge.protocol import EdgeTask, TaskResult, TaskStatus, TaskType, EdgeHeartbeat
from app.edge.base import HealthStatus, ConnectorStatus

task = EdgeTask(task_id=uuid4(), school_id=1, task_type=TaskType.SYNC_DELTA,
                connector_name="sis", created_at=datetime.now())
result = TaskResult(task_id=task.task_id, status=TaskStatus.SUCCESS,
                    started_at=datetime.now(), finished_at=datetime.now())
hb = EdgeHeartbeat(
    edge_id="edge-01", school_id=1, version="0.1.0", timestamp=datetime.now(),
    cpu_percent=3.2, memory_percent=41.0, disk_percent=55.0,
    connectors={"sis": HealthStatus(connector_name="sis", status=ConnectorStatus.HEALTHY,
                                    latency_ms=12, last_check=datetime.now())},
    pending_tasks=0,
)
```

`TaskType.EXECUTE_COMMAND` 为**协议保留值**——Step 0 禁止实现 command executor / remote shell / SSH / 远程重启 / Fabric 运维能力。

## CloudStudentDataProvider 注入示例

```python
from app.ai.privacy.base import StudentDataProvider
from app.ai.privacy.cloud_provider import CloudStudentDataProvider

# 依赖注入点（未来 Edge 阶段替换为 EdgeStudentDataProvider，业务零修改）：
provider: StudentDataProvider = CloudStudentDataProvider()
```

> ⚠️ **NOT_WIRED（Step 0 诚实记录）**：`CloudStudentDataProvider` 四方法为适配器声明，尚未接线。
> 原因：CF-03 真实取数在 `AIPrescriptionAggregator.build_student_context`
> （modules/ai_prescription/aggregator.py:75，13 路内嵌 SQL 聚合上下文），与 Provider
> 单类数据门面接口不同构；机械适配会改语义/时间窗口/排序（违反契约 D）。
> `EdgeStudentDataProvider` 是未来实现，本轮不实现。

## PsychDataProvider

最小接口由 CF-01 实际 call site 提取（get_profile / get_screening / get_counseling_meta），
映射 psych_profiles / psych_screening / aggregator psych_deep 读取语义。
**不接线、不复制 resolve_psych_access 权限门**——Capability+Scope+Audit 仍由 Cloud 侧现有调用链执行。
psych full text / questionnaire / encrypted_clog 永不进入普通学生上下文。

## 三层关系（Edge Core / Edge Secure / Fabric Network）

```text
Edge Core        HTTPS Outbound / Connector / Outbox          — 本轮契约落地
Edge Secure      可选：Identity Vault / Psych Vault / Privacy Gateway（依赖 Provider 抽象，未实现）
Fabric Network   可选：WireGuard / Headscale / 实时双向       — 本轮明确不做
```

学校仅要求"心理数据留校"时：`Core + Secure + HTTPS`，**无需 WireGuard**（AD-09：Edge Secure 可在 HTTPS 阶段启用，不依赖 Fabric Network）。

## ERRATA（源：BASELINE FINAL v1.0 FROZEN / ERRATA-001~003）

### ERRATA-001（已应用）
`app/edge/protocol.py` 补 `from .base import HealthStatus`（原文档代码块缺 import，mypy/pyright 会报错）。

### ERRATA-002（已应用）
`TaskResult.status` 由自由字符串锁为 `TaskStatus` Enum（SUCCESS/FAILED/PARTIAL），
杜绝 `failed/failure/error/partial_success` 协议漂移。

### ERRATA-003（产品文案 + fail-closed 纪律，正式生效）
产品表措辞改为：

> 标准学校版：Cloud + Edge Core。
> 存量项目可暂以 Cloud 逻辑隔离作为迁移过渡；
> 涉及心理原文的正式新项目优先启用 Edge Secure。

fail-closed 纪律（Edge Secure 停用）：

> 禁用 Edge Secure 不得导致任何 EDGE_ONLY 数据自动回退到 Cloud。
> 涉及 Identity Vault / Psych Vault 的停用必须经过显式迁移、导出、销毁或保留决策。
> 未完成决策时：
> - 原数据继续留 Edge
> - Cloud 不接收原始值
> - Provider 对 EDGE_ONLY 请求 fail closed
> - 不允许因模块关闭而改变 storage_policy

## NON-GOALS（Step 0 明确不做）

```text
✗ Edge Agent 实现
✗ Headscale
✗ WireGuard
✗ DERP
✗ Tailscale
✗ Edge Vault 实现（Identity Vault / Psych Vault）
✗ 数据迁移
✗ Fabric Manager
✗ 远程 shell / command executor / 远程重启
✗ CF-04 R2 责任人通知
✗ 修改 CF-04 已证明的审核状态机 / Review API / UI
✗ 触碰 19 条真实 PENDING_REVIEW
```
