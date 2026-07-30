"""W3-BE-RBAC-002 补丁后 Hook 链路回归

detect_escalation_trigger 增加了 school_id 必填参数, 其第二个调用点在
modules/behavior/services.py:103 的"严重违纪落库 Hook", 该处 except 会吞掉异常
(只写 error 日志), 因此必须实测走通, 否则参数错误会静默失效。

流程: class_teacher 通过 API 创建一条 serious 违纪 -> Hook 应触发滑窗判定
      -> 已满 3 次则孵化 DRAFT_PENDING 草稿 -> /discipline/drafts 数量 +1

只打印结构化结果, 不打印任何口令。
"""

import json
import pathlib
import sys

import requests

BASE = "http://127.0.0.1:8000/api/v1"
CREDS = pathlib.Path("C:/Users/Administrator/.wings3_audit_accounts.json")
HOOK_TAG = "AUDIT_TEST_HOOK"

student_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

data = json.loads(CREDS.read_text(encoding="utf-8"))
accounts = data["accounts"]


def login(username: str) -> str:
    a = accounts[username]
    r = requests.post(
        f"{BASE}/auth/login",
        json={"username": a["username"], "password": a["password"]},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    return body.get("access_token") or body.get("data", {}).get("access_token")


tok = login("class_teacher")
H = {"Authorization": f"Bearer {tok}"}


def draft_total() -> int:
    r = requests.get(f"{BASE}/discipline/drafts", headers=H, timeout=15)
    b = r.json()
    return (b.get("data", b) or {}).get("total", -1)


before = draft_total()

r = requests.post(
    f"{BASE}/behavior/records",
    headers=H,
    json={
        "student_id": student_id,
        "type": "serious",
        "category": "合成类别",
        "description": f"{HOOK_TAG}_Hook链路回归用严重违纪",
        "points": 10,
    },
    timeout=20,
)

after = draft_total()

out = {
    "create_status": r.status_code,
    "drafts_total_before": before,
    "drafts_total_after": after,
    "hook_effect": "DRAFT_INCUBATED" if after > before else "NO_NEW_DRAFT",
    "verdict": "OK" if r.status_code in (200, 201) else "CREATE_FAILED",
}
print(json.dumps(out, ensure_ascii=False, indent=2))
pathlib.Path("hook_regress_after.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
