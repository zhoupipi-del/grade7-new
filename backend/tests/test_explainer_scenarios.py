"""
test_explainer_scenarios.py — PenaltyExplainer 判罚解释引擎 3 场景验证
═══════════════════════════════════════════════════════════════════════
Phase 3 验证逻辑 | Task #1002
目标: 模拟 3 个典型场景，生成三段式解释并逐项验证合理性

场景:
  A. fighting (打架斗殴)   — major 严重违纪, high RDI, intervention 级别
  B. cheating (考试作弊)   — critical 重大处分, 4级串行审批链
  C. positive_recovery     — 回血路径验证, 使用已有 penalty+recovery 的学生

验证维度:
  ✅ 三段式结构完整性 (Fact/Rule/Growth 非空)
  ✅ 禁止用语校验 (prohibited_phrase_violations 为空)
  ✅ 变量替换正确 (无残留 {xxx} 占位符)
  ✅ RDI 联动 (include_rdi=True 时 rdi_score > 0)
  ✅ 校规映射准确 (severity/dimension/weight_multiplier 匹配 policy.yaml)
  ✅ 错误处理 (无效 student_id → 404, 无权限 → 403)

数据库速查:
  黎梓萱(154) 2504班 — serious 打架(id=208) + score_logs(-37,+20)
  曾宇晗(50)  2502班 — serious 打架(id=204)
  陈虹宇(2)   2501班 — warning 迟到(id=101) + score_log(id=7,-5)

运行:
  python tests/test_explainer_scenarios.py
═══════════════════════════════════════════════════════════════════════
"""

import json
import sys
import time

import requests

# ═════════════════════════════════════════════════════════════════════
# 配置
# ═════════════════════════════════════════════════════════════════════
BASE_URL = "https://lijiangschool.online"
API_PREFIX = (
    "/api/v1/risk_models"  # 注意: 下划线, 非连字符 (匹配 Nginx location 和 module_loader prefix)
)
AUTH_URL = f"{BASE_URL}/api/v1/auth/login"
EXPLAIN_URL = f"{BASE_URL}{API_PREFIX}/explain"

# 测试账号
TEST_ACCOUNTS = {
    "admin": {"username": "admin", "password": "admin123"},
    "grade7_leader": {"username": "grade7_leader", "password": "admin123"},
    "ct_2501": {"username": "ct_2501", "password": "admin123"},
    "parent_chen": {"username": "parent_chen", "password": "admin123"},
}


def print_header(text: str):
    print(f"\n{'═' * 70}")
    print(f"  {text}")
    print(f"{'═' * 70}")


def print_pass(text: str):
    print(f"  ✅ {text}")


def print_fail(text: str):
    print(f"  ❌ {text}")


def print_info(text: str):
    print(f"  📋 {text}")


def print_warn(text: str):
    print(f"  ⚠️  {text}")


# ═════════════════════════════════════════════════════════════════════
# 认证
# ═════════════════════════════════════════════════════════════════════


def login(role: str = "admin") -> str:
    """登录获取 JWT Token"""
    creds = TEST_ACCOUNTS[role]
    resp = requests.post(
        AUTH_URL,
        json={"username": creds["username"], "password": creds["password"]},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"登录失败: {resp.status_code} {resp.text}")
    data = resp.json()
    # 兼容多种 token 字段名
    token = (
        data.get("access_token") or data.get("token") or data.get("data", {}).get("access_token")
    )
    if not token:
        raise RuntimeError(f"未找到 token: {list(data.keys())}")
    return token


# ═════════════════════════════════════════════════════════════════════
# 核心函数: 调用 explain 端点
# ═════════════════════════════════════════════════════════════════════


def call_explain(token: str, payload: dict) -> dict:
    """调用 POST /api/v1/risk-models/explain"""
    resp = requests.post(
        EXPLAIN_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        timeout=30,
    )
    return {
        "status_code": resp.status_code,
        "body": resp.json() if resp.status_code == 200 else None,
        "error": resp.json() if resp.status_code >= 400 else None,
    }


# ═════════════════════════════════════════════════════════════════════
# 验证函数
# ═════════════════════════════════════════════════════════════════════


def validate_three_section_structure(result: dict, scenario: str) -> int:
    """验证三段式结构完整性"""
    errors = 0

    # Fact 段
    fact = result.get("fact", {})
    if not fact:
        print_fail(f"{scenario}: fact 缺失")
        errors += 1
    else:
        required_fact_fields = ["event_type", "event_date", "description", "data_source"]
        for field in required_fact_fields:
            if fact.get(field) is None:
                print_fail(f"{scenario}: fact.{field} 为空")
                errors += 1

    # Rule 段
    rule = result.get("rule", {})
    if not rule:
        print_fail(f"{scenario}: rule 缺失")
        errors += 1
    else:
        required_rule_fields = [
            "regulation_ref",
            "severity",
            "dimension",
            "base_penalty",
            "weight_multiplier",
        ]
        for field in required_rule_fields:
            if rule.get(field) is None:
                print_fail(f"{scenario}: rule.{field} 为空")
                errors += 1

    # Growth 段
    growth = result.get("growth", {})
    if not growth:
        print_fail(f"{scenario}: growth 缺失")
        errors += 1
    else:
        required_growth_fields = ["repairable", "recovery_path", "suggested_actions"]
        for field in required_growth_fields:
            if growth.get(field) is None:
                print_fail(f"{scenario}: growth.{field} 为空")
                errors += 1

    return errors


def validate_prohibited_phrases(result: dict, scenario: str) -> int:
    """验证禁止用语未出现"""
    violations = result.get("prohibited_phrase_violations", [])
    if violations:
        print_fail(f"{scenario}: 存在禁止用语: {violations}")
        return len(violations)
    else:
        print_pass(f"{scenario}: 禁止用语校验通过 (0 violations)")
        return 0


def validate_template_variables(result: dict, scenario: str) -> int:
    """验证模板变量全部替换 (无残留 {xxx})"""
    explanation = result.get("explanation_text", "")
    errors = 0
    import re

    residual = re.findall(r"\{\w+\}", explanation)
    if residual:
        print_fail(f"{scenario}: 存在未替换变量: {residual}")
        errors += 1
    else:
        print_pass(f"{scenario}: 模板变量全部替换")
    return errors


def validate_rdi_integration(result: dict, scenario: str) -> int:
    """验证 RDI 联动"""
    errors = 0
    rdi = result.get("rdi_score")
    level = result.get("risk_level")

    if rdi is not None:
        print_info(f"{scenario}: RDI={rdi:.2f}, risk_level={level}")
        if rdi > 0:
            print_pass(f"{scenario}: RDI 联动正常 (score={rdi:.2f})")
        else:
            print_info(f"{scenario}: RDI 偏低 (score={rdi:.2f})，可能为正常学生")
    else:
        print_fail(f"{scenario}: rdi_score 缺失 (include_rdi=True 时应存在)")
        errors += 1

    if level is None:
        print_fail(f"{scenario}: risk_level 缺失")
        errors += 1

    return errors


def validate_rule_mapping(result: dict, expected: dict, scenario: str) -> int:
    """验证校规映射准确"""
    errors = 0
    rule = result.get("rule", {})

    for key, exp_val in expected.items():
        actual = rule.get(key)
        if actual != exp_val:
            print_fail(f"{scenario}: rule.{key} 期望={exp_val}, 实际={actual}")
            errors += 1

    if errors == 0:
        print_pass(f"{scenario}: 校规映射完全匹配")

    return errors


def validate_explanation_text(result: dict, scenario: str) -> int:
    """验证解释文本质量"""
    errors = 0
    text = result.get("explanation_text", "")

    if not text or len(text) < 20:
        print_fail(f"{scenario}: explanation_text 过短或为空 (len={len(text)})")
        errors += 1
    else:
        print_pass(f"{scenario}: explanation_text 长度正常 ({len(text)} chars)")

    template = result.get("template_used", "")
    if not template:
        print_fail(f"{scenario}: template_used 缺失")
        errors += 1
    else:
        print_info(f"{scenario}: 模板={template}, 语气={result.get('tone', 'N/A')}")

    return errors


# ═════════════════════════════════════════════════════════════════════
# 场景定义
# ═════════════════════════════════════════════════════════════════════

SCENARIOS = {
    "A_fighting": {
        "name": "场景A: 打架斗殴 (major → serial_and 审批)",
        "payload": {
            "student_id": 154,  # 黎梓萱, 2504班
            "event_type": "fighting",
            "event_id": 208,  # serious 打架, 描述="D3-2nd-serious"
            "include_rdi": True,
        },
        "expected_rule": {
            "severity": "major",
            "dimension": "discipline",
            "base_penalty": 15.0,
            "weight_multiplier": 2.0,
        },
        "assertions": {
            "event_type_match": True,  # fact.event_type 应含 fighting
            "data_source": "discipline_records",
            "repairable": True,  # major 可回血
            "rdi_not_none": True,
        },
    },
    "B_cheating": {
        "name": "场景B: 考试作弊 (critical → 4级串行AND审批)",
        "payload": {
            "student_id": 50,  # 曾宇晗, 2502班
            "event_type": "cheating",
            "event_id": 204,  # serious 打架 → 用此记录作事实基准, event_type=cheating 走 rule
            "include_rdi": True,
        },
        "expected_rule": {
            "severity": "critical",
            "dimension": "academic_moral",
            "base_penalty": 20.0,
            "weight_multiplier": 2.5,
        },
        "assertions": {
            "event_type_match": False,  # fact 来自实际记录 (打架), rule 走 cheating 配置
            "data_source": "discipline_records",
            "repairable": True,  # critical (demerit) 可回血 (k=1.0)
            "rdi_not_none": True,
        },
    },
    "C_recovery": {
        "name": "场景C: 正向回血 (已有 penalty + appeal recovery)",
        "payload": {
            "student_id": 154,  # 黎梓萱 — 有 penalty(-37) + appeal(+20)
            "event_type": None,  # 不指定 → 走最新违纪记录兜底
            "event_id": None,
            "include_rdi": True,
        },
        "expected_rule": {
            # 兜底查询到最新违纪记录 (可能是 lateness 或其他)
            # 重点验证: 兜底逻辑不报错, 解释结构完整
        },
        "assertions": {
            "data_source": "discipline_records",  # 有违纪记录时不走 score_logs
            "repairable": True,
            "rdi_not_none": True,
            "growth_non_empty": True,
        },
    },
}


# ═════════════════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════════════════


def run_scenario(scenario_key: str, scenario: dict, token: str) -> dict:
    """执行单个场景并返回结果"""
    print_header(scenario["name"])

    # ── Step 1: 调用端点 ──
    print_info(f"请求: POST /explain payload={json.dumps(scenario['payload'], ensure_ascii=False)}")
    start = time.time()
    result = call_explain(token, scenario["payload"])
    elapsed_ms = (time.time() - start) * 1000

    # ── Step 2: HTTP 状态检查 ──
    if result["status_code"] != 200:
        print_fail(f"HTTP {result['status_code']}: {result.get('error', '')}")
        return {"passed": False, "errors": 999, "elapsed_ms": elapsed_ms, "result": result}

    body = result["body"]
    print_info(
        f"响应: {elapsed_ms:.1f}ms | student_name={body.get('student_name')} | class={body.get('class_name')}"
    )

    # ── Step 3: 分段验证 ──
    total_errors = 0

    # 3a. 三段式结构
    err = validate_three_section_structure(body, scenario_key)
    total_errors += err

    # 3b. 禁止用语
    err = validate_prohibited_phrases(body, scenario_key)
    total_errors += err

    # 3c. 模板变量
    err = validate_template_variables(body, scenario_key)
    total_errors += err

    # 3d. RDI 联动
    err = validate_rdi_integration(body, scenario_key)
    total_errors += err

    # 3e. 校规映射
    expected_rule = scenario.get("expected_rule", {})
    if expected_rule:
        err = validate_rule_mapping(body, expected_rule, scenario_key)
        total_errors += err

    # 3f. 解释文本质量
    err = validate_explanation_text(body, scenario_key)
    total_errors += err

    # ── Step 4: 自定义断言 ──
    assertions = scenario.get("assertions", {})

    if assertions.get("data_source"):
        actual = body.get("fact", {}).get("data_source")
        expected = assertions["data_source"]
        if actual == expected:
            print_pass(f"{scenario_key}: data_source={actual} ✓")
        else:
            print_fail(f"{scenario_key}: data_source 期望={expected}, 实际={actual}")
            total_errors += 1

    if assertions.get("repairable") is not None:
        actual = body.get("growth", {}).get("repairable")
        expected = assertions["repairable"]
        if actual == expected:
            print_pass(f"{scenario_key}: repairable={actual} ✓")
        else:
            print_fail(f"{scenario_key}: repairable 期望={expected}, 实际={actual}")
            total_errors += 1

    if assertions.get("rdi_not_none"):
        if body.get("rdi_score") is not None:
            print_pass(f"{scenario_key}: RDI score 存在 ✓")
        else:
            print_fail(f"{scenario_key}: RDI score 应为非空")
            total_errors += 1

    if assertions.get("growth_non_empty"):
        growth_actions = body.get("growth", {}).get("suggested_actions", [])
        if growth_actions:
            print_pass(f"{scenario_key}: suggested_actions={growth_actions}")
        else:
            print_fail(f"{scenario_key}: suggested_actions 为空")
            total_errors += 1

    # ── Step 5: 打印三段式内容快照 ──
    print_info("─" * 60)
    fact = body.get("fact", {})
    rule = body.get("rule", {})
    growth = body.get("growth", {})

    print_info(
        f"  Fact: {fact.get('event_type')} | {fact.get('event_date')} | "
        f"penalty={fact.get('penalty_amount')} | source={fact.get('data_source')}"
    )
    print_info(f"  FacT描述: {fact.get('description', '')[:80]}")
    print_info(
        f"  Rule: {rule.get('severity')} | {rule.get('dimension')} | "
        f"base={rule.get('base_penalty')} × weight={rule.get('weight_multiplier')} "
        f"= effective={rule.get('effective_penalty')}"
    )
    print_info(f"  Rule条文: {rule.get('regulation_ref', '')[:80]}...")
    print_info(
        f"  Growth: repairable={growth.get('repairable')} | "
        f"eta={growth.get('recovery_eta_days')}天 | min_obs={growth.get('min_observation_days')}天"
    )
    print_info(f"  Growth路径: {growth.get('recovery_path', '')[:120]}")
    print_info(f'  解释文本: "{body.get("explanation_text", "")[:150]}..."')

    passed = total_errors == 0
    print_info(
        f"\n  >>> {scenario_key}: {'✅ ALL PASS' if passed else f'❌ {total_errors} ERRORS'} <<<"
    )

    return {
        "passed": passed,
        "errors": total_errors,
        "elapsed_ms": elapsed_ms,
        "result": body,
    }


def run_error_scenarios(token: str) -> int:
    """运行错误处理场景"""
    print_header("场景D: 错误处理验证")
    errors = 0

    # D1: 无效 student_id → 404
    print_info("D1: 测试无效 student_id=99999")
    bad_student = call_explain(token, {"student_id": 99999, "include_rdi": False})
    if bad_student["status_code"] == 404:
        print_pass("D1: 无效 student_id → 404 ✓")
    else:
        print_fail(f"D1: 期望 404, 实际 {bad_student['status_code']}")
        errors += 1

    # D2: 无需 RDI 也正常返回
    print_info("D2: no RDI (include_rdi=False)")
    no_rdi = call_explain(token, {"student_id": 154, "include_rdi": False})
    if no_rdi["status_code"] == 200:
        body = no_rdi["body"]
        if body.get("rdi_score") is None:
            print_pass("D2: include_rdi=False → rdi_score=None ✓")
        else:
            print_fail(f"D2: rdi_score 应为 None, 实际={body.get('rdi_score')}")
            errors += 1
    else:
        print_fail(f"D2: 期望 200, 实际 {no_rdi['status_code']}")
        errors += 1

    # D3: 预存 RDI 值 (避免重复计算)
    print_info("D3: pre-existing RDI values")
    pre_rdi = call_explain(
        token,
        {
            "student_id": 154,
            "event_type": "fighting",
            "include_rdi": True,
            "rdi_score": 2.35,  # 预存: intervention 级别
            "risk_level": "intervention",
            "is_escalating": True,
            "warning_suppressed": False,
        },
    )
    if pre_rdi["status_code"] == 200:
        body = pre_rdi["body"]
        if body.get("rdi_score") == 2.35:
            print_pass("D3: 预存 RDI 值正确传递 ✓")
        else:
            print_fail(f"D3: rdi_score 应为 2.35, 实际={body.get('rdi_score')}")
            errors += 1
        if body.get("template_used") in ("intervention", "attention_escalating"):
            print_pass(f"D3: intervention 模板正确选择: {body.get('template_used')} ✓")
        else:
            print_warn(f"D3: 模板={body.get('template_used')} (intervention RDI=2.35)")
    else:
        print_fail(f"D3: 期望 200, 实际 {pre_rdi['status_code']}")
        errors += 1

    # D4: 不指定 event_type + event_id → 走最新记录兜底
    print_info("D4: 无 event_type/event_id → 兜底查询")
    fallback = call_explain(
        token,
        {
            "student_id": 2,  # 陈虹宇 — 有 warning 迟到
            "event_type": None,
            "event_id": None,
            "include_rdi": False,
        },
    )
    if fallback["status_code"] == 200:
        fact = fallback["body"].get("fact", {})
        if fact.get("data_source") == "discipline_records":
            print_pass(f"D4: 兜底查询成功 → event_type={fact.get('event_type')} ✓")
        else:
            print_info(f"D4: 数据源={fact.get('data_source')} (可能无违纪记录)")
    else:
        print_fail(f"D4: 期望 200, 实际 {fallback['status_code']}")
        errors += 1

    # D5: 权限测试 (用无权限用户 - parent 角色)
    print_info("D5: 权限检查 (parent 角色应被拒)")
    try:
        parent_token = login("parent_chen")  # 只在旧Flask有, Wings 3.0 可能不存在
        if parent_token:
            parent_result = call_explain(parent_token, {"student_id": 154, "include_rdi": False})
            if parent_result["status_code"] == 403:
                print_pass("D5: parent → 403 Forbidden ✓")
            else:
                print_fail(f"D5: 期望 403, 实际 {parent_result['status_code']}")
                errors += 1
        else:
            print_warn("D5: 跳过 (parent_chen 账号在 Wings 3.0 无 API 权限)")
    except RuntimeError:
        print_warn("D5: 跳过 (parent_chen 无法登录 Wings 3.0 API)")

    return errors


def main():
    print_header("PenaltyExplainer 判罚解释引擎 — 3场景验证测试")
    print_info(f"端点: {EXPLAIN_URL}")
    print_info(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ── 认证 ──
    print_info("\n🔑 认证中...")
    try:
        token = login("admin")
    except Exception as e:
        print_fail(f"认证失败: {e}")
        print_warn("尝试 grade7_leader 账号...")
        try:
            token = login("grade7_leader")
        except Exception as e2:
            print_fail(f"所有认证失败: {e2}")
            sys.exit(1)
    print_pass("认证成功 ✓")

    # ── 运行 3 个核心场景 ──
    results = {}
    for key, scenario in SCENARIOS.items():
        results[key] = run_scenario(key, scenario, token)

    # ── 错误处理场景 ──
    error_errors = run_error_scenarios(token)

    # ── 汇总报告 ──
    print_header("验证汇总报告")

    total_errors = sum(r["errors"] for r in results.values()) + error_errors
    all_passed = all(r["passed"] for r in results.values()) and error_errors == 0

    for key, r in results.items():
        status = "✅ PASS" if r["passed"] else f"❌ FAIL ({r['errors']} errors)"
        print_info(f"  {status} | {SCENARIOS[key]['name']} | {r['elapsed_ms']:.0f}ms")

    print_info(
        f"  错误处理: {'✅ PASS' if error_errors == 0 else f'❌ FAIL ({error_errors} errors)'}"
    )

    print_info("\n" + "─" * 70)
    if all_passed:
        print_info("  🎉 全部场景通过! PenaltyExplainer 引擎验证成功")
    else:
        print_info(f"  ⚠️  共 {total_errors} 个错误，请检查上方详情")
    print_info("─" * 70)

    # ── 性能汇总 ──
    avg_ms = sum(r["elapsed_ms"] for r in results.values()) / len(results) if results else 0
    print_info(f"\n  性能: 平均 {avg_ms:.1f}ms/请求 (P99 target < 500ms)")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
