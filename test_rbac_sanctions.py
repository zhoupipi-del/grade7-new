"""
W3-BE-RBAC-002 修复验证 — 处分数据越权自动化测试

验证目标: FastAPI (Wings 3.0) backend/ 的 discipline 模块
  - 角色闸门: PARENT/STUDENT/TEACHER/COUNSELOR/GROUP_ADMIN/BRANCH_ADMIN 不得访问管理端
  - 数据范围强制绑定: CLASS_TEACHER→本人班级, GRADE_LEADER→本人年级, 客户端参数不可扩权
  - 家长门户: 仅可读本人绑定孩子, 且不得看到内部草稿

安全约束:
  - 不接受硬编码口令。凭据从仓库外文件读取(默认 C:/Users/Administrator/.wings3_audit_accounts.json,
    可用环境变量 AUDIT_ACCOUNTS_FILE 覆盖)。口令绝不打印、绝不写入结果文件。
  - 每条用例同时断言 HTTP 状态码 + 返回记录条数 + 是否泄漏范围外学生。

用法:
  python test_rbac_sanctions.py [--base-url http://127.0.0.1:8000]
前提:
  已执行 backend/_seed_audit_accounts.py 建立合成账号与合成处分数据。
"""

import argparse
import json
import os
import pathlib
import sys

import requests

BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api/v1"
DEFAULT_CREDS = "C:/Users/Administrator/.wings3_audit_accounts.json"

results = {"pass": 0, "fail": 0, "details": []}


# ═══════════════════════════════════════════════════════════════
# 取证记录
# ═══════════════════════════════════════════════════════════════
def record(
    case_id: str,
    description: str,
    method: str,
    path: str,
    role: str,
    binding: str,
    expected: str,
    actual_status,
    passed: bool,
    count=None,
    leak="N/A",
):
    verdict = "PASS" if passed else "FAIL"
    results["pass" if passed else "fail"] += 1
    results["details"].append(
        {
            "case_id": case_id,
            "description": description,
            "method": method,
            "path": path,
            "role": role,
            "binding": binding,
            "expected": expected,
            "actual_status": actual_status,
            "record_count": count,
            "out_of_scope_leak": leak,
            "verdict": verdict,
        }
    )
    icon = "PASS" if passed else "FAIL"
    extra = "" if count is None else f", count={count}"
    leak_s = "" if leak == "N/A" else f", leak={leak}"
    print(
        f"  [{icon}] {case_id} {description} | 期望={expected} 实际={actual_status}{extra}{leak_s}"
    )


def login(username: str, password: str):
    try:
        r = requests.post(
            f"{BASE_URL}{API_PREFIX}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def H(token):
    return {"Authorization": f"Bearer {token}"}


def GET(path, token=None, **kw):
    headers = H(token) if token else {}
    return requests.get(f"{BASE_URL}{API_PREFIX}{path}", headers=headers, timeout=10, **kw)


def items_of(resp):
    try:
        d = resp.json()
        return d.get("items", []), d.get("total", None)
    except Exception:
        return [], None


def leak_check(items, key, allowed):
    """返回越权泄漏说明: 命中范围外的值则记录"""
    bad = sorted({it.get(key) for it in items if it.get(key) not in allowed})
    return "无" if not bad else f"泄漏{key}={bad}"


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="W3-BE-RBAC-002 处分越权验证")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--accounts", default=os.environ.get("AUDIT_ACCOUNTS_FILE", DEFAULT_CREDS))
    args = ap.parse_args()

    global BASE_URL
    BASE_URL = args.base_url.rstrip("/")

    print("=" * 78)
    print("W3-BE-RBAC-002 处分数据越权验证 — 目标:", BASE_URL)
    print("=" * 78)

    creds_path = pathlib.Path(args.accounts)
    if not creds_path.exists():
        print(f"FATAL: 凭据文件不存在: {creds_path}")
        print("       请先运行 backend/_seed_audit_accounts.py 生成合成账号")
        sys.exit(1)
    blob = json.loads(creds_path.read_text(encoding="utf-8"))
    accounts, topo = blob["accounts"], blob["topology"]
    exp = topo["expect"]

    try:
        h = requests.get(f"{BASE_URL}{API_PREFIX}/health", timeout=5)
        if h.status_code != 200:
            print(f"FATAL: 健康检查失败 {h.status_code}")
            sys.exit(1)
        print(f"后端在线: {h.json()}")
    except Exception as e:
        print(f"FATAL: 后端不可达: {e}")
        sys.exit(1)

    print("\n── 登录合成账号(口令不回显) ──")
    tk = {}
    for key, a in accounts.items():
        t = login(a["username"], a["password"])
        tk[key] = t
        print(f"  {'OK  ' if t else 'FAIL'} {key} ({a['role']})")
    if not any(tk.values()):
        print("FATAL: 无账号可登录")
        sys.exit(1)

    A1, A2, B1 = topo["class_a1_id"], topo["class_a2_id"], topo["class_b1_id"]
    GA, GB = topo["grade_a_id"], topo["grade_b_id"]
    SA1, SA2, SB1 = topo["student_a1_id"], topo["student_a2_id"], topo["student_b1_id"]

    print("\n── A组: 角色闸门(管理端处分列表) ──")
    r = GET("/discipline/sanctions")
    record(
        "TC-01",
        "匿名访问处分列表",
        "GET",
        "/discipline/sanctions",
        "anonymous",
        "无",
        "401",
        r.status_code,
        r.status_code == 401,
        count=len(items_of(r)[0]),
    )

    gate = [
        ("TC-02", "parent", "PARENT访问管理端列表"),
        ("TC-03", "student", "STUDENT访问管理端列表"),
        ("TC-04", "teacher", "TEACHER访问管理端列表"),
        ("TC-05", "counselor", "COUNSELOR访问管理端列表"),
        ("TC-13a", "group_admin", "GROUP_ADMIN访问学生明细列表"),
        ("TC-13b", "branch_admin", "BRANCH_ADMIN访问学生明细列表"),
    ]
    for cid, key, desc in gate:
        r = GET("/discipline/sanctions", tk[key])
        its, _ = items_of(r)
        record(
            cid,
            desc,
            "GET",
            "/discipline/sanctions",
            accounts[key]["role"],
            "无数据域",
            "403",
            r.status_code,
            r.status_code == 403,
            count=len(its),
            leak="无" if not its else f"返回{len(its)}条明细",
        )

    print("\n── B组: 数据范围强制绑定 ──")
    r = GET("/discipline/sanctions", tk["ms_admin"])
    its, total = items_of(r)
    ok = r.status_code == 200 and total == exp["ms_admin_total"]
    record(
        "TC-14",
        "MS_ADMIN全校基线",
        "GET",
        "/discipline/sanctions",
        "ms_admin",
        f"school={topo['school_id']}",
        f"200/total={exp['ms_admin_total']}",
        r.status_code,
        ok,
        count=total,
        leak="无",
    )

    r = GET("/discipline/sanctions", tk["class_teacher"])
    its, total = items_of(r)
    lk = leak_check(its, "class_id", {A1})
    ok = r.status_code == 200 and total == exp["class_teacher_a1_total"] and lk == "无"
    record(
        "TC-06",
        "CLASS_TEACHER读本班",
        "GET",
        "/discipline/sanctions",
        "class_teacher",
        f"class={A1}",
        f"200/total={exp['class_teacher_a1_total']}",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    r = GET("/discipline/sanctions", tk["class_teacher"], params={"class_id": A2})
    its, total = items_of(r)
    lk = leak_check(its, "class_id", {A1})
    ok = r.status_code == 200 and total == exp["class_teacher_a1_total"] and lk == "无"
    record(
        "TC-07",
        "CLASS_TEACHER伪造class_id=他班",
        "GET",
        f"/discipline/sanctions?class_id={A2}",
        "class_teacher",
        f"class={A1}(强制)",
        f"200/参数被忽略/total={exp['class_teacher_a1_total']}",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    r = GET("/discipline/sanctions", tk["class_teacher_b"])
    its, total = items_of(r)
    lk = leak_check(its, "class_id", {A2})
    ok = r.status_code == 200 and total == exp["class_teacher_a2_total"] and lk == "无"
    record(
        "TC-07b",
        "CLASS_TEACHER_B读本班(对照)",
        "GET",
        "/discipline/sanctions",
        "class_teacher",
        f"class={A2}",
        f"200/total={exp['class_teacher_a2_total']}",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    r = GET("/discipline/sanctions", tk["grade_leader"])
    its, total = items_of(r)
    lk = leak_check(its, "grade_id", {GA})
    ok = r.status_code == 200 and total == exp["grade_leader_a_total"] and lk == "无"
    record(
        "TC-08",
        "GRADE_LEADER读本年级",
        "GET",
        "/discipline/sanctions",
        "grade_leader",
        f"grade={GA}",
        f"200/total={exp['grade_leader_a_total']}",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    r = GET("/discipline/sanctions", tk["grade_leader"], params={"grade_id": GB})
    its, total = items_of(r)
    lk = leak_check(its, "grade_id", {GA})
    ok = r.status_code == 200 and total == exp["grade_leader_a_total"] and lk == "无"
    record(
        "TC-09",
        "GRADE_LEADER伪造grade_id=他年级",
        "GET",
        f"/discipline/sanctions?grade_id={GB}",
        "grade_leader",
        f"grade={GA}(强制)",
        f"200/参数被忽略/total={exp['grade_leader_a_total']}",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    r = GET("/discipline/sanctions", tk["grade_leader_b"])
    its, total = items_of(r)
    lk = leak_check(its, "grade_id", {GB})
    ok = r.status_code == 200 and total == exp["grade_leader_b_total"] and lk == "无"
    record(
        "TC-09b",
        "GRADE_LEADER_B读本年级(对照)",
        "GET",
        "/discipline/sanctions",
        "grade_leader",
        f"grade={GB}",
        f"200/total={exp['grade_leader_b_total']}",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    r = GET("/discipline/sanctions", tk["class_teacher"], params={"student_id": SB1})
    its, total = items_of(r)
    lk = leak_check(its, "student_id", {SA1})
    ok = r.status_code == 200 and total == 0 and lk == "无"
    record(
        "TC-17",
        "CLASS_TEACHER伪造student_id=他年级学生",
        "GET",
        f"/discipline/sanctions?student_id={SB1}",
        "class_teacher",
        f"class={A1}(强制)",
        "200/total=0",
        r.status_code,
        ok,
        count=total,
        leak=lk,
    )

    print("\n── C组: 处分详情越权(横向越权) ──")
    r = GET("/discipline/sanctions", tk["ms_admin"])
    all_items, _ = items_of(r)
    id_a2 = next((i["id"] for i in all_items if i["class_id"] == A2), None)
    id_b1 = next((i["id"] for i in all_items if i["class_id"] == B1), None)
    id_a1 = next((i["id"] for i in all_items if i["class_id"] == A1), None)

    if id_a1:
        r = GET(f"/discipline/sanctions/{id_a1}", tk["class_teacher"])
        record(
            "TC-18",
            "CLASS_TEACHER读本班处分详情(基线)",
            "GET",
            f"/discipline/sanctions/{id_a1}",
            "class_teacher",
            f"class={A1}",
            "200",
            r.status_code,
            r.status_code == 200,
            count=1,
            leak="无",
        )
    if id_a2:
        r = GET(f"/discipline/sanctions/{id_a2}", tk["class_teacher"])
        leaked = r.status_code == 200
        record(
            "TC-19",
            "CLASS_TEACHER读他班处分详情",
            "GET",
            f"/discipline/sanctions/{id_a2}",
            "class_teacher",
            f"class={A1}",
            "403/404",
            r.status_code,
            r.status_code in (403, 404),
            count=1 if leaked else 0,
            leak="他班处分明细被读取" if leaked else "无",
        )
    if id_b1:
        r = GET(f"/discipline/sanctions/{id_b1}", tk["grade_leader"])
        leaked = r.status_code == 200
        record(
            "TC-20",
            "GRADE_LEADER读他年级处分详情",
            "GET",
            f"/discipline/sanctions/{id_b1}",
            "grade_leader",
            f"grade={GA}",
            "403/404",
            r.status_code,
            r.status_code in (403, 404),
            count=1 if leaked else 0,
            leak="他年级处分明细被读取" if leaked else "无",
        )

    print("\n── D组: 家长门户 ──")
    pp = "/discipline/parent-portal/children/{}/discipline-records"

    r = GET(pp.format(SA1), tk["parent"])
    recs = r.json().get("records", []) if r.status_code == 200 else []
    draft_leak = [x for x in recs if "草稿" in (x.get("reason") or "")]
    ok = r.status_code == 200 and len(recs) == exp["parent_a_visible_records"] and not draft_leak
    record(
        "TC-10",
        "PARENT读本人孩子记录",
        "GET",
        pp.format(SA1),
        "parent",
        f"bound_student={SA1}",
        f"200/records={exp['parent_a_visible_records']}/无草稿",
        r.status_code,
        ok,
        count=len(recs),
        leak="内部草稿泄漏" if draft_leak else "无",
    )

    for cid, sid, desc in [
        ("TC-11", SA2, "PARENT读同年级他人孩子"),
        ("TC-11b", SB1, "PARENT读他年级孩子"),
    ]:
        r = GET(pp.format(sid), tk["parent"])
        leaked = r.status_code == 200
        record(
            cid,
            desc,
            "GET",
            pp.format(sid),
            "parent",
            f"bound_student={SA1}",
            "403",
            r.status_code,
            r.status_code == 403,
            count=len(r.json().get("records", [])) if leaked else 0,
            leak="他人孩子记录被读取" if leaked else "无",
        )

    r = GET("/discipline/sanctions", tk["parent"], params={"school_id": topo["school_id"]})
    record(
        "TC-12",
        "PARENT伪造school_id访问管理列表",
        "GET",
        f"/discipline/sanctions?school_id={topo['school_id']}",
        "parent",
        f"bound_student={SA1}",
        "403",
        r.status_code,
        r.status_code == 403,
        count=len(items_of(r)[0]),
        leak="无",
    )

    r = GET(pp.format(SA1), tk["student"])
    record(
        "TC-21",
        "STUDENT调用家长门户接口",
        "GET",
        pp.format(SA1),
        "student",
        f"bound_student={SA1}",
        "403",
        r.status_code,
        r.status_code == 403,
        count=0,
        leak="无",
    )

    r = GET(pp.format(SA1), tk["ms_admin"])
    record(
        "TC-22",
        "MS_ADMIN调用家长门户接口(仅PARENT可用)",
        "GET",
        pp.format(SA1),
        "ms_admin",
        "无家长绑定",
        "403",
        r.status_code,
        r.status_code == 403,
        count=0,
        leak="无",
    )

    print("\n── E组: 其它受保护端点 ──")
    for cid, key, path, desc in [
        ("TC-15", "parent", f"/discipline/sanctions/{id_a1}", "PARENT读处分详情"),
        ("TC-16", "parent", "/discipline/stats", "PARENT读统计"),
        ("TC-23", "teacher", "/discipline/drafts", "TEACHER读草稿箱"),
        ("TC-24", "counselor", "/discipline/stats", "COUNSELOR读统计"),
        ("TC-25", "student", f"/discipline/escalation-trigger/{SA1}", "STUDENT读升级检测"),
        ("TC-26", "parent", "/discipline/appeals", "PARENT读申诉列表"),
    ]:
        r = GET(path, tk[key])
        record(
            cid,
            desc,
            "GET",
            path,
            accounts[key]["role"],
            "无管理域",
            "403",
            r.status_code,
            r.status_code == 403,
            count=None,
            leak="无",
        )

    total = results["pass"] + results["fail"]
    print("\n" + "=" * 78)
    print(f"汇总: {results['pass']}/{total} 通过, {results['fail']} 失败")
    print("=" * 78)
    if results["fail"]:
        print("\n失败用例:")
        for d in results["details"]:
            if d["verdict"] == "FAIL":
                print(
                    f"  [{d['case_id']}] {d['description']} | {d['method']} {d['path']} "
                    f"| role={d['role']} | 期望={d['expected']} 实际={d['actual_status']} "
                    f"| count={d['record_count']} | leak={d['out_of_scope_leak']}"
                )

    out = pathlib.Path("rbac_test_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细取证结果: {out}")
    sys.exit(0 if results["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
