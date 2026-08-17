from datetime import datetime
from uuid import uuid4
from wings_contracts.edge.base import ConnectorStatus, HealthStatus, FieldDef, DataSchema, DeltaBatch
from wings_contracts.edge.protocol import TaskType, TaskStatus, EdgeTask, TaskResult, EdgeHeartbeat
from wings_contracts.ai.privacy.base import StudentDataProvider
from wings_contracts.ai.privacy.cloud_provider import CloudStudentDataProvider
from wings_contracts.ai.privacy.psych_provider import PsychDataProvider

# 1. TaskStatus 只接受 success/failed/partial
for v in ("success", "failed", "partial"):
    assert TaskStatus(v).value == v
try:
    TaskStatus("error"); raise SystemExit("FAIL: TaskStatus accepted error")
except ValueError:
    pass
print("PASS TaskStatus enum restricted")

# 2. EdgeHeartbeat serialize HealthStatus
now = datetime.now()
hs = HealthStatus(connector_name="sis", status=ConnectorStatus.DEGRADED, latency_ms=5, last_check=now, message="slow")
hb = EdgeHeartbeat(edge_id="e1", school_id=1, version="0.1", timestamp=now, cpu_percent=1.0, memory_percent=2.0, disk_percent=3.0, connectors={"sis": hs}, pending_tasks=0)
assert "degraded" in hb.model_dump_json()
print("PASS EdgeHeartbeat serializes HealthStatus")

# 3. FieldDef/DataSchema/DeltaBatch round-trip
schema = DataSchema(entity_type="attendance", fields=[FieldDef(name="a", data_type="string")], primary_key="id", updated_at_field="updated_at", supports_delta=True)
assert DataSchema.model_validate_json(schema.model_dump_json()) == schema
batch = DeltaBatch(entity_type="attendance", records=[{"a": 1}], next_cursor="x", has_more=True)
assert DeltaBatch.model_validate_json(batch.model_dump_json()) == batch
print("PASS FieldDef/DataSchema/DeltaBatch round-trip")

# 4. TaskResult enum + EdgeTask
task = EdgeTask(task_id=uuid4(), school_id=1, task_type=TaskType.SYNC_DELTA, created_at=now)
tr = TaskResult(task_id=task.task_id, status=TaskStatus.SUCCESS, started_at=now, finished_at=now)
assert tr.status == TaskStatus.SUCCESS and tr.task_id == task.task_id
print("PASS EdgeTask/TaskResult")

# 5. Provider 抽象
p = CloudStudentDataProvider()
assert isinstance(p, StudentDataProvider)
print("PASS CloudStudentDataProvider isinstance StudentDataProvider")
try:
    import asyncio
    asyncio.run(p.get_psych_risk("stu_x"))
    raise SystemExit("FAIL: NOT_WIRED should raise")
except NotImplementedError:
    print("PASS CloudStudentDataProvider NOT_WIRED raises NotImplementedError")

print("\nCONTRACT SMOKE: ALL PASS")
