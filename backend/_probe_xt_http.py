"""R2-b 跨租户越权 HTTP 取证 — 只打印结构化结果,不打印任何口令"""

import json
import pathlib
import sys

import requests

BASE = "http://127.0.0.1:8000/api/v1"
CREDS = pathlib.Path("C:/Users/Administrator/.wings3_audit_accounts.json")

xt_student_id = int(sys.argv[1])
xt_school_id = int(sys.argv[2]) if len(sys.argv) > 2 else 2
OUT = sys.argv[3] if len(sys.argv) > 3 else "xt_cross_tenant_probe.json"

data = json.loads(CREDS.read_text(encoding="utf-8"))
accounts = data["accounts"]  # dict: 短名 -> {username, password, role}


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


results = []
for user in ["student", "parent", "teacher", "class_teacher", "grade_leader", "ms_admin"]:
    tok = login(user)
    if not tok:
        results.append({"role_account": user, "error": "LOGIN_FAILED"})
        continue
    r = requests.get(
        f"{BASE}/discipline/escalation-trigger/{xt_student_id}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    entry = {
        "role_account": user,
        "path": f"/discipline/escalation-trigger/{xt_student_id}",
        "target_student_school_id": xt_school_id,
        "caller_school_id": 1,
        "status": r.status_code,
    }
    if r.status_code == 200:
        body = r.json()
        payload = body.get("data", body)
        entry["triggered"] = payload.get("triggered")
        entry["serious_count"] = payload.get("serious_count")
        ev = payload.get("evidence") or []
        entry["evidence_count"] = len(ev)
        entry["evidence_desc_sample"] = [e.get("description") for e in ev]
        entry["verdict"] = (
            "CROSS_TENANT_LEAK" if len(ev) > 0 or payload.get("serious_count") else "NO_DATA"
        )
    else:
        entry["verdict"] = "BLOCKED"
    results.append(entry)

print(json.dumps(results, ensure_ascii=False, indent=2))
pathlib.Path(OUT).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
