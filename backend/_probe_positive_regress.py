"""W3-BE-RBAC-002 补丁后正向回归 — 确认管理角色既有调用面未被误伤

覆盖前端实际调用的两个端点:
  GET /discipline/drafts                       (frontend/src/api/behavior.ts:303)
  GET /discipline/escalation-trigger/{id}      (frontend/src/api/behavior.ts:328)

只打印结构化结果, 不打印任何口令。
"""

import json
import pathlib
import sys

import requests

BASE = "http://127.0.0.1:8000/api/v1"
CREDS = pathlib.Path("C:/Users/Administrator/.wings3_audit_accounts.json")

# 本校(school_id=1)学生 id, 由命令行给出
own_student_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

data = json.loads(CREDS.read_text(encoding="utf-8"))
accounts = data["accounts"]


def login(username: str) -> str | None:
    a = accounts[username]
    r = requests.post(
        f"{BASE}/auth/login",
        json={"username": a["username"], "password": a["password"]},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    body = r.json()
    return body.get("access_token") or body.get("data", {}).get("access_token")


def get(tok: str, path: str, params: dict | None = None):
    return requests.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {tok}"},
        params=params or {},
        timeout=15,
    )


results = []
for user in ["ms_admin", "grade_leader", "class_teacher"]:
    tok = login(user)
    if not tok:
        results.append({"role_account": user, "error": "LOGIN_FAILED"})
        continue

    r1 = get(tok, "/discipline/drafts")
    b1 = r1.json() if r1.status_code == 200 else {}
    p1 = b1.get("data", b1)
    results.append(
        {
            "role_account": user,
            "path": "GET /discipline/drafts",
            "status": r1.status_code,
            "total": p1.get("total"),
            "items": len(p1.get("items") or []),
            "verdict": "OK" if r1.status_code == 200 else "REGRESSION",
        }
    )

    r2 = get(tok, f"/discipline/escalation-trigger/{own_student_id}")
    b2 = r2.json() if r2.status_code == 200 else {}
    p2 = b2.get("data", b2)
    results.append(
        {
            "role_account": user,
            "path": f"GET /discipline/escalation-trigger/{own_student_id}",
            "status": r2.status_code,
            "serious_count": p2.get("serious_count"),
            "triggered": p2.get("triggered"),
            "verdict": "OK" if r2.status_code == 200 else "REGRESSION",
        }
    )

print(json.dumps(results, ensure_ascii=False, indent=2))
pathlib.Path("positive_regress_after.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
)
