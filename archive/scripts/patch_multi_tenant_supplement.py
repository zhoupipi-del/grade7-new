"""
patch_multi_tenant_supplement.py — 补充7个被跳过的多租户校验补丁

v2主脚本因 em dash/box drawing 字符差异跳过了7处，
本脚本用服务器实际文本精确匹配。
"""

import os

BASE = "/root/backend"


def patch_file(filepath, patches):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    for desc, old, new in patches:
        if old in content:
            content = content.replace(old, new, 1)
            print(f"  OK {desc}")
        else:
            print(f"  SKIP: {desc}")
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Written {filepath}")
    else:
        print(f"  No changes to {filepath}")
    return content != original


def patch_risk_models():
    f = os.path.join(BASE, "modules/risk_models/routers.py")
    patches = [
        # explain 端点：服务器用 ── (box drawing) 而非 --
        (
            "risk_models: explain add student_id check",
            '    # \u2500\u2500 Step 1: 可选的 RDI 计算 \u2500\u2500',
            '    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, request.student_id, current_user, \'学生不存在\')\n\n    # \u2500\u2500 Step 1: 可选的 RDI 计算 \u2500\u2500',
        ),
    ]
    return patch_file(f, patches)


def patch_discipline():
    f = os.path.join(BASE, "modules/discipline/routers.py")
    patches = [
        # PUT sanctions — em dash
        (
            "discipline: PUT sanctions add check",
            '    """编辑处分 \u2014 仅 PENDING 状态可编辑"""\n    try:\n        sanction = await DisciplineService.update_sanction(\n            db, sanction_id, body.model_dump(exclude_none=True),\n        )',
            '    """编辑处分 \u2014 仅 PENDING 状态可编辑"""\n    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    try:\n        sanction = await DisciplineService.update_sanction(\n            db, sanction_id, body.model_dump(exclude_none=True),\n        )',
        ),
        # DELETE sanctions — em dash + more code between docstring and try
        (
            "discipline: DELETE sanctions add check",
            '    """删除处分 \u2014 仅 PENDING 状态可删除，仅德育处管理员"""\n    try:\n        ok = await DisciplineService.delete_sanction(db, sanction_id)\n        if not ok:',
            '    """删除处分 \u2014 仅 PENDING 状态可删除，仅德育处管理员"""\n    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    try:\n        ok = await DisciplineService.delete_sanction(db, sanction_id)\n        if not ok:',
        ),
        # POST approve — try comes before role guard comment
        (
            "discipline: POST approve add check",
            '    try:\n        # 角色守卫 \u2014 确定当前用户属于哪一级审批人\n        reviewer_role = _resolve_reviewer_role(current_user)\n\n        sanction = await DisciplineService.approve_sanction(\n            db, sanction_id,\n            comment=body.comment or "",\n            reviewer_id=current_user.id,\n            reviewer_role=reviewer_role,',
            '    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    try:\n        # 角色守卫 \u2014 确定当前用户属于哪一级审批人\n        reviewer_role = _resolve_reviewer_role(current_user)\n\n        sanction = await DisciplineService.approve_sanction(\n            db, sanction_id,\n            comment=body.comment or "",\n            reviewer_id=current_user.id,\n            reviewer_role=reviewer_role,',
        ),
        # GET drafts/{draft_id} — em dash, more complex code block
        (
            "discipline: GET drafts/{draft_id} add check",
            '    """草稿详情 \u2014 含铁证快照解析"""\n    draft = await DisciplineService.get_sanction(db, draft_id)',
            '    """草稿详情 \u2014 含铁证快照解析"""\n    # P0 多租户隔离：校验草稿是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, draft_id, current_user, \'处分草稿不存在\')\n    draft = await DisciplineService.get_sanction(db, draft_id)',
        ),
        # DELETE drafts/{draft_id} — em dash
        (
            "discipline: DELETE drafts/{draft_id} add check",
            '    """废弃草稿 \u2014 物理删除 DRAFT_PENDING 记录"""\n    try:\n        ok = await DisciplineService.discard_draft(db, draft_id)\n        if not ok:',
            '    """废弃草稿 \u2014 物理删除 DRAFT_PENDING 记录"""\n    # P0 多租户隔离：校验草稿是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, draft_id, current_user, \'处分草稿不存在\')\n    try:\n        ok = await DisciplineService.discard_draft(db, draft_id)\n        if not ok:',
        ),
    ]
    return patch_file(f, patches)


def patch_evaluation():
    f = os.path.join(BASE, "modules/evaluation/routers.py")
    patches = [
        # GET classes/{class_id}/ranking — em dash
        (
            "evaluation: GET classes/{id}/ranking add check",
            '    """班级排名 \u2014 按总分降序，返回前 N 名"""\n    ranking = await EvaluationService.get_class_ranking(db, class_id, semester, limit)',
            '    """班级排名 \u2014 按总分降序，返回前 N 名"""\n    # P0 多租户隔离：校验 class_id 是否属于当前用户学校\n    await verify_entity_ownership(db, SchoolClass, class_id, current_user, \'班级不存在\')\n    ranking = await EvaluationService.get_class_ranking(db, class_id, semester, limit)',
        ),
        # GET students/{student_id}/logs — em dash + Chinese quotes
        (
            "evaluation: GET students/{id}/logs add check",
            '    """评分流水审计 \u2014 家长质疑"为什么扣分"时的精确回溯"""\n    offset = (page - 1) * per_page\n    logs, total = await EvaluationService.get_score_logs(db, student_id, per_page, offset)',
            '    """评分流水审计 \u2014 家长质疑"为什么扣分"时的精确回溯"""\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    offset = (page - 1) * per_page\n    logs, total = await EvaluationService.get_score_logs(db, student_id, per_page, offset)',
        ),
    ]
    return patch_file(f, patches)


def patch_behavior():
    f = os.path.join(BASE, "modules/behavior/routers.py")
    patches = [
        # DELETE records/{record_id} — em dash + has _guard decorator
        (
            "behavior: DELETE records/{record_id} add check",
            '    """删除违纪记录 \u2014 仅德育处管理员"""\n    ok = await BehaviorService.delete_record(db, record_id)',
            '    """删除违纪记录 \u2014 仅德育处管理员"""\n    # P0 多租户隔离：校验违纪记录是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, \'违纪记录不存在\')\n    ok = await BehaviorService.delete_record(db, record_id)',
        ),
    ]
    return patch_file(f, patches)


def main():
    print("=" * 60)
    print("P0 多租户隔离修复 -- 补充补丁 (7处被跳过的)")
    print("=" * 60)

    results = {}
    modules = [
        ("risk_models", patch_risk_models),
        ("discipline", patch_discipline),
        ("evaluation", patch_evaluation),
        ("behavior", patch_behavior),
    ]

    for name, func in modules:
        print(f"\n模块: {name}")
        try:
            results[name] = func()
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = False

    changed = sum(1 for v in results.values() if v)
    print(f"\n修改: {changed}/{len(results)} 个模块")
    if changed == len(results):
        print("全部补充补丁已应用!")


if __name__ == "__main__":
    main()
