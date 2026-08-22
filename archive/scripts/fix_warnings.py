"""Fix risk_models warnings endpoint - add multi-tenant guards."""
filepath = '/root/backend/modules/risk_models/routers.py'
with open(filepath, 'r') as f:
    content = f.read()

# Change 1: Add grade_id/class_id query params after days param
old1 = 'days: int = Query(7, description="\u6700\u8fd1N\u5929\u7684\u9884\u8b66"),\n    db: AsyncSession = Depends(get_db),'
new1 = 'days: int = Query(7, description="\u6700\u8fd1N\u5929\u7684\u9884\u8b66"),\n    grade_id: Optional[int] = Query(None, description="\u6309\u5e74\u7ea7\u7b5b\u9009"),\n    class_id: Optional[int] = Query(None, description="\u6309\u73ed\u7ea7\u7b5b\u9009"),\n    db: AsyncSession = Depends(get_db),'

if old1 in content:
    content = content.replace(old1, new1)
    print("OK: added grade_id/class_id params")
else:
    print("FAIL: old1 not found")

# Change 2: Add verify guards before TODO
old2 = '    """\n    # TODO: \u5b9e\u73b0\u67e5\u8be2\u903b\u8f91\n    return []'
new2 = '    """\n    # P1 \u591a\u79df\u6237\u9694\u79bb\uff1a\u6821\u9a8c grade_id / class_id \u5f52\u5c5e\n    if grade_id:\n        await verify_entity_ownership(db, Grade, grade_id, current_user, "\u5e74\u7ea7\u4e0d\u5b58\u5728")\n    if class_id:\n        await verify_entity_ownership(db, SchoolClass, class_id, current_user, "\u73ed\u7ea7\u4e0d\u5b58\u5728")\n\n    # TODO: \u5b9e\u73b0\u67e5\u8be2\u903b\u8f91\n    return []'

if old2 in content:
    content = content.replace(old2, new2)
    print("OK: added verify guards")
else:
    print("FAIL: old2 not found")

with open(filepath, 'w') as f:
    f.write(content)
print("DONE")
