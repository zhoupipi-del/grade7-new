"""
patch_multi_tenant.py — P0 多租户隔离修复补丁脚本 (v2)

一次性为 7 个模块路由文件添加 verify_entity_ownership 校验，
防止 ID 遍历越权攻击（跨校访问其他学校数据）。

修改清单:
  - dashboard/routers.py: class-drilldown/{class_id}
  - risk_models/routers.py: calculate + explain (student_id)
  - discipline/routers.py: 14+ 端点 (sanction_id/student_id/appeal_id)
  - evaluation/routers.py: 5+ 端点 (student_id/class_id/indicator_id)
  - attendance/routers.py: 3 端点 (class_id/student_id)
  - behavior/routers.py: 6 端点 (record_id/student_id/appeal_id)
  - red_flag/routers.py: 2 端点 (routine_id/class_id)

用法: python3 patch_multi_tenant.py
"""

import os

BASE = "/root/backend"


def patch_file(filepath, patches):
    """对文件应用一组文本替换 patches"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    for desc, old, new in patches:
        if old in content:
            content = content.replace(old, new, 1)
            print(f"  OK {desc}")
        else:
            print(f"  SKIP: {desc} -- pattern not found")

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Written {filepath}")
    else:
        print(f"  No changes to {filepath}")

    return content != original


# ═══════════════════════════════════════════════════════════════
# 1. dashboard/routers.py — class-drilldown/{class_id}
# ═══════════════════════════════════════════════════════════════

def patch_dashboard():
    f = os.path.join(BASE, "modules/dashboard/routers.py")
    # 读取文件确认 class-drilldown 端点存在
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()

    patches = [
        # 添加 verify_entity_ownership 导入
        (
            "dashboard: add verify_entity_ownership import",
            "from core.routers import get_current_user, get_db",
            "from core.routers import get_current_user, get_db, verify_entity_ownership",
        ),
        # 添加 Class 模型导入
        (
            "dashboard: add Class model import",
            "from core.models import User, UserRole, Student",
            "from core.models import User, UserRole, Student, Class as SchoolClass",
        ),
    ]

    # 在 class-drilldown 端点加校验 — 用动态查找避免引号嵌套
    # 寻找 docstring 行 + import 行的组合
    marker = '班级下钻明细'
    if marker in content:
        # 找到 docstring 行的完整内容
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if marker in line and 'class-drilldown' not in line:
                # 这是 docstring 行
                docstring_line = line
                # 下一行应该是 from modules.behavior...
                next_line = lines[i + 1] if i + 1 < len(lines) else ''
                indent = len(docstring_line) - len(docstring_line.lstrip())
                indent_str = ' ' * indent
                check_line = f"{indent_str}# P0 多租户隔离：校验 class_id 是否属于当前用户学校"
                check_line2 = f"{indent_str}await verify_entity_ownership(db, SchoolClass, class_id, current_user, '班级不存在')"
                # 在 docstring 和 from import 之间插入校验
                old_block = docstring_line + '\n' + next_line
                new_block = docstring_line + '\n' + check_line + '\n' + check_line2 + '\n\n' + next_line
                patches.append((
                    "dashboard: add class_id ownership check in class-drilldown",
                    old_block,
                    new_block,
                ))
                break
    else:
        print("  SKIP: dashboard class-drilldown not found (may not have this endpoint)")

    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 2. risk_models/routers.py — calculate + explain (student_id)
# ═══════════════════════════════════════════════════════════════

def patch_risk_models():
    f = os.path.join(BASE, "modules/risk_models/routers.py")
    patches = [
        # 添加导入
        (
            "risk_models: add verify_entity_ownership import",
            "from core.routers import get_db, get_current_user",
            "from core.routers import get_db, get_current_user, verify_entity_ownership",
        ),
        # 添加 Student 模型导入
        (
            "risk_models: add Student model import",
            "from core.models import User, UserRole",
            "from core.models import User, UserRole, Student",
        ),
        # calculate 端点：权限检查后加 student_id 校验
        (
            "risk_models: add student_id check in calculate",
            '    # 权限检查\n    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:\n        raise HTTPException(status_code=403, detail="权限不足")\n\n    calculator = RiskDeviationIndexCalculator(db, current_user.school_id)',
            '    # 权限检查\n    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:\n        raise HTTPException(status_code=403, detail="权限不足")\n\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, request.student_id, current_user, \'学生不存在\')\n\n    calculator = RiskDeviationIndexCalculator(db, current_user.school_id)',
        ),
        # explain 端点：权限检查后加 student_id 校验
        (
            "risk_models: add student_id check in explain",
            '    # 权限检查\n    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:\n        raise HTTPException(status_code=403, detail="权限不足")\n\n    # -- Step 1: 可选的 RDI 计算 --',
            '    # 权限检查\n    if current_user.role not in [UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER, UserRole.MS_ADMIN]:\n        raise HTTPException(status_code=403, detail="权限不足")\n\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, request.student_id, current_user, \'学生不存在\')\n\n    # -- Step 1: 可选的 RDI 计算 --',
        ),
    ]
    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 3. discipline/routers.py — 14+ 端点
# ═══════════════════════════════════════════════════════════════

def patch_discipline():
    f = os.path.join(BASE, "modules/discipline/routers.py")
    patches = [
        # 添加导入
        (
            "discipline: add verify_entity_ownership import",
            "from core.routers import get_db, get_current_user, require_role",
            "from core.routers import get_db, get_current_user, require_role, verify_entity_ownership",
        ),
        # 添加 Student 模型导入
        (
            "discipline: add Student model import",
            "from core.models import User, UserRole",
            "from core.models import User, UserRole, Student",
        ),
        # ── GET /sanctions/{sanction_id} ──
        (
            "discipline: GET sanctions/{id} add check",
            '    """查看单条处分详情"""\n    sanction = await DisciplineService.get_sanction(db, sanction_id)',
            '    """查看单条处分详情"""\n    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    sanction = await DisciplineService.get_sanction(db, sanction_id)',
        ),
        # ── PUT /sanctions/{sanction_id} ──
        (
            "discipline: PUT sanctions/{id} add check",
            '    """编辑处分 -- 仅 PENDING 状态可编辑"""\n    try:\n        sanction = await DisciplineService.update_sanction(\n            db, sanction_id, body.model_dump(exclude_none=True),\n        )',
            '    """编辑处分 -- 仅 PENDING 状态可编辑"""\n    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    try:\n        sanction = await DisciplineService.update_sanction(\n            db, sanction_id, body.model_dump(exclude_none=True),\n        )',
        ),
        # ── DELETE /sanctions/{sanction_id} ──
        (
            "discipline: DELETE sanctions/{id} add check",
            '    """删除处分 -- 仅 PENDING 状态可删除，仅德育处管理员"""\n    try:\n        ok = await DisciplineService.delete_sanction(db, sanction_id)',
            '    """删除处分 -- 仅 PENDING 状态可删除，仅德育处管理员"""\n    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    try:\n        ok = await DisciplineService.delete_sanction(db, sanction_id)',
        ),
        # ── POST /sanctions/{sanction_id}/approve ──
        (
            "discipline: POST approve add check",
            '        # 角色守卫 -- 确定当前用户属于哪一级审批人\n        reviewer_role = _resolve_reviewer_role(current_user)\n\n        sanction = await DisciplineService.approve_sanction(\n            db, sanction_id',
            '        # P0 多租户隔离：校验处分是否属于当前用户学校\n        await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n\n        # 角色守卫 -- 确定当前用户属于哪一级审批人\n        reviewer_role = _resolve_reviewer_role(current_user)\n\n        sanction = await DisciplineService.approve_sanction(\n            db, sanction_id',
        ),
        # ── POST /sanctions/{sanction_id}/reject ──
        (
            "discipline: POST reject add check",
            '        reviewer_role = _resolve_reviewer_role(current_user)\n\n        sanction = await DisciplineService.reject_sanction(\n            db, sanction_id',
            '        # P0 多租户隔离：校验处分是否属于当前用户学校\n        await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n\n        reviewer_role = _resolve_reviewer_role(current_user)\n\n        sanction = await DisciplineService.reject_sanction(\n            db, sanction_id',
        ),
        # ── POST /sanctions/{sanction_id}/revoke ──
        (
            "discipline: POST revoke add check",
            '    try:\n        sanction = await DisciplineService.revoke_sanction(\n            db, sanction_id,\n            revoke_reason=body.revoke_reason,\n            revoke_date=body.revoke_date,\n        )',
            '    # P0 多租户隔离：校验处分是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, sanction_id, current_user, \'处分记录不存在\')\n    try:\n        sanction = await DisciplineService.revoke_sanction(\n            db, sanction_id,\n            revoke_reason=body.revoke_reason,\n            revoke_date=body.revoke_date,\n        )',
        ),
        # ── GET /escalation/{student_id} ──
        (
            "discipline: GET escalation/{student_id} add check",
            '    """评估学生是否需要从违纪升级为处分"""\n    return await DisciplineService.check_escalation(db, student_id)',
            '    """评估学生是否需要从违纪升级为处分"""\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    return await DisciplineService.check_escalation(db, student_id)',
        ),
        # ── POST /escalation/{student_id} ──
        (
            "discipline: POST escalation/{student_id} add check",
            '    try:\n        sanction = await DisciplineService.escalate_to_sanction(\n            db, student_id, current_user.id,\n        )',
            '    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    try:\n        sanction = await DisciplineService.escalate_to_sanction(\n            db, student_id, current_user.id,\n        )',
        ),
        # ── GET /drafts/{draft_id} ──
        (
            "discipline: GET drafts/{draft_id} add check",
            '    """草稿详情 -- 含铁证快照解析"""\n    draft = await DisciplineService.get_sanction(db, draft_id)',
            '    """草稿详情 -- 含铁证快照解析"""\n    # P0 多租户隔离：校验草稿是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, draft_id, current_user, \'处分草稿不存在\')\n    draft = await DisciplineService.get_sanction(db, draft_id)',
        ),
        # ── POST /drafts/{draft_id}/submit ──
        (
            "discipline: POST drafts/{draft_id}/submit add check",
            '    try:\n        sanction = await DisciplineService.submit_draft(\n            db, draft_id,\n            confirm_reason=body.confirm_reason,\n            submitter_id=current_user.id,\n        )',
            '    # P0 多租户隔离：校验草稿是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, draft_id, current_user, \'处分草稿不存在\')\n    try:\n        sanction = await DisciplineService.submit_draft(\n            db, draft_id,\n            confirm_reason=body.confirm_reason,\n            submitter_id=current_user.id,\n        )',
        ),
        # ── DELETE /drafts/{draft_id} ──
        (
            "discipline: DELETE drafts/{draft_id} add check",
            '    """废弃草稿 -- 物理删除 DRAFT_PENDING 记录"""\n    try:\n        ok = await DisciplineService.discard_draft(db, draft_id)',
            '    """废弃草稿 -- 物理删除 DRAFT_PENDING 记录"""\n    # P0 多租户隔离：校验草稿是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineSanction, draft_id, current_user, \'处分草稿不存在\')\n    try:\n        ok = await DisciplineService.discard_draft(db, draft_id)',
        ),
        # ── GET /escalation-trigger/{student_id} ──
        (
            "discipline: GET escalation-trigger/{student_id} add check",
            '    return await DisciplineService.detect_escalation_trigger(db, student_id)\n\n\n# ═══════════════════════════════════════════════════════════════\n# Phase 4: 家校申诉',
            '    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    return await DisciplineService.detect_escalation_trigger(db, student_id)\n\n\n# ═══════════════════════════════════════════════════════════════\n# Phase 4: 家校申诉',
        ),
        # ── GET /appeals/{appeal_id} ──
        (
            "discipline: GET appeals/{appeal_id} add check",
            '    """查看单条申诉详情"""\n    appeal = await DisciplineService.get_appeal(db, appeal_id)',
            '    """查看单条申诉详情"""\n    # P0 多租户隔离：校验申诉是否属于当前用户学校\n    await verify_entity_ownership(db, SanctionAppeal, appeal_id, current_user, \'申诉记录不存在\')\n    appeal = await DisciplineService.get_appeal(db, appeal_id)',
        ),
        # ── POST /appeals/{appeal_id}/review ──
        (
            "discipline: POST appeals/{appeal_id}/review add check",
            '    try:\n        result = await DisciplineService.review_appeal(\n            db, appeal_id,\n            action=body.action,',
            '    # P0 多租户隔离：校验申诉是否属于当前用户学校\n    await verify_entity_ownership(db, SanctionAppeal, appeal_id, current_user, \'申诉记录不存在\')\n    try:\n        result = await DisciplineService.review_appeal(\n            db, appeal_id,\n            action=body.action,',
        ),
    ]
    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 4. evaluation/routers.py — student_id/class_id/indicator_id
# ═══════════════════════════════════════════════════════════════

def patch_evaluation():
    f = os.path.join(BASE, "modules/evaluation/routers.py")
    patches = [
        # 添加导入
        (
            "evaluation: add verify_entity_ownership import",
            "from core.routers import get_db, get_current_user, require_role",
            "from core.routers import get_db, get_current_user, require_role, verify_entity_ownership",
        ),
        # 添加 Student, Class 模型导入
        (
            "evaluation: add Student/Class model imports",
            "from core.models import User, UserRole",
            "from core.models import User, UserRole, Student, Class as SchoolClass",
        ),
        # ── GET /students/{student_id}/scores ──
        (
            "evaluation: GET students/{id}/scores add check",
            '    """获取单个学生的五维分 + 总分"""\n    result = await EvaluationService.get_dimension_scores(db, student_id, semester)',
            '    """获取单个学生的五维分 + 总分"""\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    result = await EvaluationService.get_dimension_scores(db, student_id, semester)',
        ),
        # ── GET /classes/{class_id}/ranking ──
        (
            "evaluation: GET classes/{id}/ranking add check",
            '    """班级排名 -- 按总分降序，返回前 N 名"""\n    ranking = await EvaluationService.get_class_ranking(db, class_id, semester, limit)',
            '    """班级排名 -- 按总分降序，返回前 N 名"""\n    # P0 多租户隔离：校验 class_id 是否属于当前用户学校\n    await verify_entity_ownership(db, SchoolClass, class_id, current_user, \'班级不存在\')\n    ranking = await EvaluationService.get_class_ranking(db, class_id, semester, limit)',
        ),
        # ── GET /students/{student_id}/logs ──
        (
            "evaluation: GET students/{id}/logs add check",
            '    """评分流水审计 -- 家长质疑"为什么扣分"时的精确回溯"""\n    offset = (page - 1) * per_page\n    logs, total = await EvaluationService.get_score_logs(db, student_id, per_page, offset)',
            '    """评分流水审计 -- 家长质疑"为什么扣分"时的精确回溯"""\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    offset = (page - 1) * per_page\n    logs, total = await EvaluationService.get_score_logs(db, student_id, per_page, offset)',
        ),
        # ── GET /students/{student_id}/final-evaluation ──
        (
            "evaluation: GET students/{id}/final-evaluation add check",
            '    result = await EvaluationService.get_final_evaluation(\n        db, student_id, current_user.school_id, semester\n    )\n    return result',
            '    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    result = await EvaluationService.get_final_evaluation(\n        db, student_id, current_user.school_id, semester\n    )\n    return result',
        ),
        # ── GET /students/{student_id}/discipline-veto ──
        (
            "evaluation: GET students/{id}/discipline-veto add check",
            '    return await EvaluationService.check_discipline_veto(db, student_id, semester)',
            '    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    return await EvaluationService.check_discipline_veto(db, student_id, semester)',
        ),
        # ── PUT /indicators/{indicator_id} ──
        (
            "evaluation: PUT indicators/{id} add check",
            '    """更新评价指标"""\n    indicator = await EvaluationService.update_indicator(\n        db, indicator_id, current_user.school_id',
            '    """更新评价指标"""\n    # P0 多租户隔离：校验指标是否属于当前用户学校\n    await verify_entity_ownership(db, EvaluationIndicator, indicator_id, current_user, \'指标不存在\')\n    indicator = await EvaluationService.update_indicator(\n        db, indicator_id, current_user.school_id',
        ),
        # ── POST /indicators/{indicator_id}/toggle ──
        (
            "evaluation: POST indicators/{id}/toggle add check",
            '    """切换指标启用/禁用状态"""\n    indicator = await EvaluationService.toggle_indicator(db, indicator_id, current_user.school_id)',
            '    """切换指标启用/禁用状态"""\n    # P0 多租户隔离：校验指标是否属于当前用户学校\n    await verify_entity_ownership(db, EvaluationIndicator, indicator_id, current_user, \'指标不存在\')\n    indicator = await EvaluationService.toggle_indicator(db, indicator_id, current_user.school_id)',
        ),
        # ── DELETE /indicators/{indicator_id} ──
        (
            "evaluation: DELETE indicators/{id} add check",
            '    """删除指标（仅当无关联评分记录时可用）"""\n    try:\n        deleted = await EvaluationService.delete_indicator(db, indicator_id, current_user.school_id)',
            '    """删除指标（仅当无关联评分记录时可用）"""\n    # P0 多租户隔离：校验指标是否属于当前用户学校\n    await verify_entity_ownership(db, EvaluationIndicator, indicator_id, current_user, \'指标不存在\')\n    try:\n        deleted = await EvaluationService.delete_indicator(db, indicator_id, current_user.school_id)',
        ),
    ]
    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 5. attendance/routers.py — class_id/student_id 路径参数
# ═══════════════════════════════════════════════════════════════

def patch_attendance():
    f = os.path.join(BASE, "modules/attendance/routers.py")
    patches = [
        # 添加导入
        (
            "attendance: add verify_entity_ownership import",
            "from core.routers import get_db, get_current_user",
            "from core.routers import get_db, get_current_user, verify_entity_ownership",
        ),
        # 添加 Student, Class 模型导入
        (
            "attendance: add Student/Class model imports",
            "from core.models import User, UserRole",
            "from core.models import User, UserRole, Student, Class as SchoolClass",
        ),
        # ── GET /records/class/{class_id} ──
        (
            "attendance: GET records/class/{class_id} add check",
            '    records = await AttendanceService.get_class_attendance(\n        db=db,\n        school_id=current_user.school_id,\n        class_id=class_id',
            '    # P0 多租户隔离：校验 class_id 是否属于当前用户学校\n    await verify_entity_ownership(db, SchoolClass, class_id, current_user, \'班级不存在\')\n\n    records = await AttendanceService.get_class_attendance(\n        db=db,\n        school_id=current_user.school_id,\n        class_id=class_id',
        ),
        # ── GET /records/student/{student_id} ──
        (
            "attendance: GET records/student/{student_id} add check",
            '    """查询某学生的考勤历史"""\n    records = await AttendanceService.get_student_history(\n        db=db,\n        school_id=current_user.school_id,\n        student_id=student_id',
            '    """查询某学生的考勤历史"""\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    records = await AttendanceService.get_student_history(\n        db=db,\n        school_id=current_user.school_id,\n        student_id=student_id',
        ),
        # ── GET /calendar/{student_id} ──
        (
            "attendance: GET calendar/{student_id} add check",
            '    calendar = await AttendanceService.get_student_calendar(\n        db=db,\n        school_id=current_user.school_id,\n        student_id=student_id,\n    )\n    return calendar',
            '    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    calendar = await AttendanceService.get_student_calendar(\n        db=db,\n        school_id=current_user.school_id,\n        student_id=student_id,\n    )\n    return calendar',
        ),
    ]
    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 6. behavior/routers.py — record_id/student_id/appeal_id
# ═══════════════════════════════════════════════════════════════

def patch_behavior():
    f = os.path.join(BASE, "modules/behavior/routers.py")
    patches = [
        # 添加导入
        (
            "behavior: add verify_entity_ownership import",
            "from core.routers import get_db, get_current_user, require_role",
            "from core.routers import get_db, get_current_user, require_role, verify_entity_ownership",
        ),
        # 添加 Student 模型导入
        (
            "behavior: add Student model import",
            "from core.models import User, UserRole",
            "from core.models import User, UserRole, Student",
        ),
        # ── GET /records/{record_id} ──
        (
            "behavior: GET records/{record_id} add check",
            '    record = await BehaviorService.get_record(db, record_id)\n    if not record:\n        raise HTTPException(status_code=404, detail="违纪记录不存在")\n    return _format_record(record)',
            '    # P0 多租户隔离：校验违纪记录是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, \'违纪记录不存在\')\n    record = await BehaviorService.get_record(db, record_id)\n    return _format_record(record)',
        ),
        # ── PUT /records/{record_id} ──
        (
            "behavior: PUT records/{record_id} add check",
            '    """编辑违纪记录"""\n    record = await BehaviorService.update_record(db, record_id, body.model_dump(exclude_none=True))',
            '    """编辑违纪记录"""\n    # P0 多租户隔离：校验违纪记录是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, \'违纪记录不存在\')\n    record = await BehaviorService.update_record(db, record_id, body.model_dump(exclude_none=True))',
        ),
        # ── DELETE /records/{record_id} ──
        (
            "behavior: DELETE records/{record_id} add check",
            '    """删除违纪记录 -- 仅德育处管理员"""\n    ok = await BehaviorService.delete_record(db, record_id)',
            '    """删除违纪记录 -- 仅德育处管理员"""\n    # P0 多租户隔离：校验违纪记录是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, \'违纪记录不存在\')\n    ok = await BehaviorService.delete_record(db, record_id)',
        ),
        # ── POST /records/{record_id}/resolve ──
        (
            "behavior: POST records/{record_id}/resolve add check",
            '    """标记违纪已解决"""\n    record = await BehaviorService.resolve_record(db, record_id)',
            '    """标记违纪已解决"""\n    # P0 多租户隔离：校验违纪记录是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineRecord, record_id, current_user, \'违纪记录不存在\')\n    record = await BehaviorService.resolve_record(db, record_id)',
        ),
        # ── GET /escalation/{student_id} ──
        (
            "behavior: GET escalation/{student_id} add check",
            '    """查询学生的累计扣分升级风险"""\n    return await BehaviorService.get_escalation_risk(db, student_id)',
            '    """查询学生的累计扣分升级风险"""\n    # P0 多租户隔离：校验 student_id 是否属于当前用户学校\n    await verify_entity_ownership(db, Student, student_id, current_user, \'学生不存在\')\n    return await BehaviorService.get_escalation_risk(db, student_id)',
        ),
        # ── POST /appeals/{appeal_id}/review ──
        (
            "behavior: POST appeals/{appeal_id}/review add check",
            '    """审核申诉（班主任/年级组长/德育处）"""\n    appeal = await BehaviorService.review_appeal(\n        db, appeal_id, body.status',
            '    """审核申诉（班主任/年级组长/德育处）"""\n    # P0 多租户隔离：校验申诉是否属于当前用户学校\n    await verify_entity_ownership(db, DisciplineAppeal, appeal_id, current_user, \'申诉不存在\')\n    appeal = await BehaviorService.review_appeal(\n        db, appeal_id, body.status',
        ),
    ]
    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 7. red_flag/routers.py — routine_id/class_id
# ═══════════════════════════════════════════════════════════════

def patch_red_flag():
    f = os.path.join(BASE, "modules/red_flag/routers.py")
    patches = [
        # 添加导入
        (
            "red_flag: add verify_entity_ownership import",
            "from core.routers import get_current_user, require_role, get_db",
            "from core.routers import get_current_user, require_role, get_db, verify_entity_ownership",
        ),
        # 添加 Class 模型导入
        (
            "red_flag: add Class model import",
            "from core.models import User, UserRole",
            "from core.models import User, UserRole, Class as SchoolClass",
        ),
        # ── DELETE /routines/{routine_id} ──
        (
            "red_flag: DELETE routines/{routine_id} add check",
            '    """删除一条常规评分"""\n    ok = await FlagService.delete_routine(db, routine_id, user.school_id)',
            '    """删除一条常规评分"""\n    # P0 多租户隔离：校验评分记录是否属于当前用户学校\n    await verify_entity_ownership(db, RoutineScore, routine_id, user, \'评分记录不存在\')\n    ok = await FlagService.delete_routine(db, routine_id, user.school_id)',
        ),
        # ── GET /evaluations/trends/{class_id} ──
        (
            "red_flag: GET evaluations/trends/{class_id} add check",
            '    trends = await FlagService.get_class_trends(\n        db=db,\n        school_id=user.school_id,\n        class_id=class_id,\n    )',
            '    # P0 多租户隔离：校验 class_id 是否属于当前用户学校\n    await verify_entity_ownership(db, SchoolClass, class_id, user, \'班级不存在\')\n\n    trends = await FlagService.get_class_trends(\n        db=db,\n        school_id=user.school_id,\n        class_id=class_id,\n    )',
        ),
    ]
    return patch_file(f, patches)


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("P0 多租户隔离修复 -- verify_entity_ownership 注入")
    print("=" * 60)

    results = {}
    modules = [
        ("dashboard", patch_dashboard),
        ("risk_models", patch_risk_models),
        ("discipline", patch_discipline),
        ("evaluation", patch_evaluation),
        ("attendance", patch_attendance),
        ("behavior", patch_behavior),
        ("red_flag", patch_red_flag),
    ]

    for name, func in modules:
        print(f"\n{'--' * 20}")
        print(f"模块: {name}")
        print(f"{'--' * 20}")
        try:
            results[name] = func()
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = False

    # 汇总
    print(f"\n{'=' * 60}")
    print("修改汇总:")
    changed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        icon = "OK" if ok else "FAIL"
        print(f"  [{icon}] {name}")
    print(f"\n修改: {changed}/{total} 个模块")
    print("=" * 60)

    if changed == total:
        print("\n全部模块已修改! 需要重启 wings3 服务使改动生效。")
    else:
        print("\n部分模块修改失败，请检查上方日志。")


if __name__ == "__main__":
    main()
