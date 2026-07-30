"""
discipline 模块全端点 × 全角色 鉴权覆盖探针(非破坏性)

原则:
  - 写操作一律指向不存在的 ID(999999),不会修改任何数据
  - 结果判定: 403=已拦截 / 401=未认证 / 404=鉴权已放行(资源不存在) /
              2xx=鉴权放行且成功 / 422=请求体校验先失败(鉴权结论不确定)
  - 口令从仓库外凭据文件读取,不打印
"""

import json
import os
import pathlib
import sys

import requests

BASE = "http://127.0.0.1:8000/api/v1"
CREDS = pathlib.Path(
    os.environ.get("AUDIT_ACCOUNTS_FILE", "C:/Users/Administrator/.wings3_audit_accounts.json")
)

NOEXIST = 999999

# (method, path, 期望可访问角色集合)
ENDPOINTS = [
    ("POST", "/discipline/sanctions", {"ms_admin", "class_teacher"}),
    ("GET", "/discipline/sanctions", {"ms_admin", "grade_leader", "class_teacher"}),
    ("GET", f"/discipline/sanctions/{NOEXIST}", {"ms_admin", "grade_leader", "class_teacher"}),
    ("PUT", f"/discipline/sanctions/{NOEXIST}", {"ms_admin", "class_teacher"}),
    ("DELETE", f"/discipline/sanctions/{NOEXIST}", {"ms_admin"}),
    ("POST", f"/discipline/sanctions/{NOEXIST}/approve", {"ms_admin", "grade_leader"}),
    ("POST", f"/discipline/sanctions/{NOEXIST}/reject", {"ms_admin", "grade_leader"}),
    ("POST", f"/discipline/sanctions/{NOEXIST}/revoke", {"ms_admin"}),
    ("GET", f"/discipline/escalation/{NOEXIST}", {"ms_admin", "grade_leader", "class_teacher"}),
    ("POST", f"/discipline/escalation/{NOEXIST}", {"ms_admin", "class_teacher"}),
    ("GET", "/discipline/stats", {"ms_admin", "grade_leader", "class_teacher"}),
    ("GET", "/discipline/drafts", {"ms_admin", "grade_leader", "class_teacher"}),
    ("GET", f"/discipline/drafts/{NOEXIST}", {"ms_admin", "grade_leader", "class_teacher"}),
    ("POST", f"/discipline/drafts/{NOEXIST}/submit", {"ms_admin", "class_teacher"}),
    ("DELETE", f"/discipline/drafts/{NOEXIST}", {"ms_admin", "class_teacher"}),
    (
        "GET",
        f"/discipline/escalation-trigger/{NOEXIST}",
        {"ms_admin", "grade_leader", "class_teacher"},
    ),
    ("GET", "/discipline/appeals", {"ms_admin", "grade_leader", "class_teacher"}),
    ("GET", f"/discipline/appeals/{NOEXIST}", {"ms_admin", "grade_leader", "class_teacher"}),
    ("POST", f"/discipline/appeals/{NOEXIST}/review", {"ms_admin", "grade_leader"}),
    ("GET", f"/discipline/parent-portal/children/{NOEXIST}/discipline-records", {"parent"}),
]

LOWPRIV = ["teacher", "counselor", "parent", "student", "group_admin", "branch_admin"]


def main():
    if not CREDS.exists():
        print(f"FATAL: 凭据文件不存在 {CREDS}")
        sys.exit(1)
    blob = json.loads(CREDS.read_text(encoding="utf-8"))
    accounts = blob["accounts"]

    tokens = {}
    for key, a in accounts.items():
        r = requests.post(
            "http://127.0.0.1:8000/api/v1/auth/login",
            json={"username": a["username"], "password": a["password"]},
            timeout=10,
        )
        tokens[key] = r.json().get("access_token") if r.status_code == 200 else None

    findings = []
    rows = []
    print(f"{'ENDPOINT':64} " + " ".join(f"{k[:9]:>9}" for k in LOWPRIV))
    print("-" * 130)
    for method, path, _allowed in ENDPOINTS:
        cells = []
        for key in LOWPRIV:
            t = tokens.get(key)
            if not t:
                cells.append("NOTOK")
                continue
            h = {"Authorization": f"Bearer {t}"}
            try:
                if method == "GET":
                    r = requests.get(BASE + path, headers=h, timeout=10)
                elif method == "DELETE":
                    r = requests.delete(BASE + path, headers=h, timeout=10)
                else:
                    r = requests.request(method, BASE + path, headers=h, json={}, timeout=10)
                code = r.status_code
            except Exception:
                code = "ERR"
            if code in (401, 403):
                mark = f"{code}"
            elif code == 422:
                mark = "422?"
            elif isinstance(code, int) and 200 <= code < 300:
                mark = f"!{code}"
                findings.append((method, path, key, code, "鉴权放行且执行成功"))
            elif code == 404:
                mark = "!404"
                findings.append((method, path, key, code, "鉴权已放行(仅因资源不存在被拒)"))
            else:
                mark = str(code)
            cells.append(mark)
        rows.append((method, path, cells))
        print(f"{method + ' ' + path:64} " + " ".join(f"{c:>9}" for c in cells))

    print("\n" + "=" * 130)
    print(f"低权限角色可穿透端点数: {len(findings)}")
    for f in findings:
        print(f"  [!] {f[0]} {f[1]}  role={f[2]}  http={f[3]}  {f[4]}")
    print(
        "\n图例: 403/401=已拦截  422?=请求体先校验失败(结论不确定)  !404=鉴权已放行  !2xx=完全放行"
    )

    pathlib.Path("discipline_authz_matrix.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "method": m,
                        "path": p,
                        "lowpriv_results": dict(zip(LOWPRIV, c, strict=False)),
                    }
                    for m, p, c in rows
                ],
                "penetrations": [
                    {"method": a, "path": b, "role": c, "http": d, "note": e}
                    for a, b, c, d, e in findings
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\n矩阵已保存: discipline_authz_matrix.json")


if __name__ == "__main__":
    main()
