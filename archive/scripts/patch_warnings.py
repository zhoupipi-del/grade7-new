"""Patch risk_models warnings endpoint to add multi-tenant isolation."""
import sys

filepath = '/root/backend/modules/risk_models/routers.py'

try:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
except FileNotFoundError:
    print(f"ERROR: {filepath} not found")
    sys.exit(1)

changes = 0

# Change 1: Add grade_id and class_id params + verify_entity_ownership before the TODO
old = """    status: Optional[str] = Query(None, description="active/handled/false_positive/expired"),
    risk_level: Optional[str] = Query(None, description="normal/attention/intervention"),
    days: int = Query(7, description="最近N天的预警"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询风险预警列表

    默认返回最近7天的活跃预警
    """
    # TODO: 实现查询逻辑
    return []"""

new = """    status: Optional[str] = Query(None, description="active/handled/false_positive/expired"),
    risk_level: Optional[str] = Query(None, description="normal/attention/intervention"),
    grade_id: Optional[int] = Query(None, description="按年级筛选"),
    class_id: Optional[int] = Query(None, description="按班级筛选"),
    days: int = Query(7, description="最近N天的预警"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询风险预警列表

    默认返回最近7天的活跃预警
    """
    # P1 多租户隔离：校验 grade_id / class_id 归属
    if grade_id:
        await verify_entity_ownership(db, Grade, grade_id, current_user, '年级不存在')
    if class_id:
        await verify_entity_ownership(db, SchoolClass, class_id, current_user, '班级不存在')

    # TODO: 实现查询逻辑
    return []"""

if old in content:
    content = content.replace(old, new)
    changes += 1
    print("[OK] Risk models warnings endpoint: added grade_id/class_id + verify guards")
else:
    print("[FAIL] Could not find warnings endpoint in risk_models/routers.py")
    sys.exit(1)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"---DONE: {changes} changes---")
