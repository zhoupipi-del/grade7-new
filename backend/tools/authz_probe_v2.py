#!/usr/bin/env python3
"""
authz_probe.py — 对象级越权探针  v2

v1 有一个致命 bug（2026-07-23 由维护者发现）：
    FastAPI 的 openapi.json 里 path 已包含 include_router 的 prefix
    （module_loader.py:415 → f"/api/v1/{code}"）。v1 又让用户传 --prefix
    /api/v1 再拼一次，结果请求 /api/v1/api/v1/... 全部 404，
    而 404 被算作"正确拒绝" → **探针报告 0 越权，所有洞全部"通过"**。

这是最危险的失效模式：工具报平安。所以 v2 的核心不是修那一行拼接，
而是加三道对照实验，任何一道不过就拒绝出具报告：

  对照 A（id 真实性）：用 admin token 打 foreign id → 必须 2xx
      不过 = 这个 id 根本不存在，后面所有 404 都是"查无此物"而非"被拒绝"
  对照 B（可达性）  ：用调用者 token 打自己的 id → 必须 2xx
      不过 = URL 拼错 / token 失效，此时全绿毫无意义
  对照 C（检出力）  ：可选，指定一个已知有洞的端点 → 必须被检出
      不过 = 探针的判定逻辑本身失灵

对照不过一律 exit 2 并明确说明"本次结果不可采信"。

其他修正：
  - 不再有 --prefix 拼接。openapi 里的 path 就是完整路径，直接用。
    仍保留 --path-prefix 作为反向代理场景的显式覆盖，带警告。
  - 400/422 归入「待人工」桶，不计入越权也不计入通过
    （多数 GET 带必填 Query，缺参就是 422，v1 会误报成越权）

用法：
  python authz_probe.py \
      --base http://127.0.0.1:8000 \
      --token-admin    eyJ...   \
      --token-student  eyJ...   \
      --token-teacher  eyJ...   \
      --foreign-student-id 812  --own-student-id 权限内的id \
      --foreign-class-id   17   --own-class-id   1

退出码：0 = 无越权且对照全过；1 = 发现越权；2 = 对照未过，结果不可采信
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

OWNED_PARAMS = {
    "student_id": ("foreign_student_id", "own_student_id"),
    "class_id": ("foreign_class_id", "own_class_id"),
    "grade_id": ("foreign_grade_id", "own_grade_id"),
}

DENY_CODES = {401, 403, 404}
MANUAL_CODES = {400, 422}  # 参数问题，判不了权限，交人工
SAFE_METHODS = {"get", "head"}


# ══════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════


def http(method: str, url: str, token: str | None, timeout: float = 10.0):
    req = urllib.request.Request(url, method=method.upper())
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            return r.status, r.read(4096)
    except urllib.error.HTTPError as e:
        return e.code, e.read(2048)
    except Exception as e:
        return -1, str(e).encode()


def load_openapi(base: str) -> dict:
    status, body = http("GET", f"{base.rstrip('/')}/openapi.json", None)
    if status != 200:
        die(f"拉不到 /openapi.json (HTTP {status})。实例跑起来了吗？")
    return json.loads(body)


def die(msg: str, code: int = 2):
    print(f"\n[FATAL] {msg}", file=sys.stderr)
    print("[FATAL] 本次探测结果不可采信，已中止。", file=sys.stderr)
    sys.exit(code)


# ══════════════════════════════════════════════════════════════
# 目标枚举
# ══════════════════════════════════════════════════════════════


def collect_targets(spec: dict, include_writes: bool, name_filter: str | None):
    out = []
    for path, item in (spec.get("paths") or {}).items():
        hits = [p for p in OWNED_PARAMS if "{" + p + "}" in path]
        if not hits:
            continue
        if name_filter and name_filter not in path:
            continue
        for method, op in (item or {}).items():
            if method not in ("get", "head", "post", "put", "patch", "delete"):
                continue
            if method not in SAFE_METHODS and not include_writes:
                continue
            out.append(
                {
                    "path": path,
                    "method": method,
                    "params": hits,
                    "summary": (op or {}).get("summary", ""),
                }
            )
    return out


def build_url(base: str, path_prefix: str, path: str, ids: dict, which: int) -> str | None:
    """
    which=0 用 foreign id（探测越权），which=1 用 own id（对照 B）。
    路径里还有填不了的占位符则返回 None（跳过，不算通过）。
    """
    filled = path
    for param, keys in OWNED_PARAMS.items():
        ph = "{" + param + "}"
        if ph in filled:
            v = ids.get(keys[which])
            if v is None:
                return None
            filled = filled.replace(ph, str(v))
    if "{" in filled:
        return None
    return f"{base.rstrip('/')}{path_prefix}{filled}"


# ══════════════════════════════════════════════════════════════
# 对照实验
# ══════════════════════════════════════════════════════════════


def control_a_ids_exist(base, pfx, targets, ids, admin_token) -> tuple[bool, str]:
    """用 admin 打 foreign id，证明这些 id 真实存在。"""
    if not admin_token:
        return True, "跳过（未提供 --token-admin，后续 404 无法区分'不存在'与'被拒绝'）"
    for t in targets:
        url = build_url(base, pfx, t["path"], ids, which=0)
        if not url:
            continue
        status, _ = http(t["method"], url, admin_token)
        if 200 <= status < 300:
            return True, f"OK — admin 可读 {t['path']}，foreign id 确认存在"
    return (
        False,
        "admin 用 foreign id 打遍所有端点都拿不到 2xx —— id 可能不存在，或 admin token 失效",
    )


def control_b_reachable(base, pfx, targets, ids, actors) -> tuple[bool, str]:
    """用调用者自己的 id 打，证明 URL 拼对了、token 有效。"""
    for name, token, _ in actors:
        for t in targets:
            url = build_url(base, pfx, t["path"], ids, which=1)
            if not url:
                continue
            status, _ = http(t["method"], url, token)
            if 200 <= status < 300:
                return True, f"OK — {name} 用自己的 id 拿到 2xx（{t['path']}）"
    return False, (
        "所有调用者用自己的 id 也拿不到任何 2xx。"
        "典型原因：URL 前缀拼错（openapi 里 path 已含 /api/v1，不要再传 --path-prefix）、"
        "token 过期、own-id 填错"
    )


def control_c_canary(base, pfx, ids, actor_token, canary_path, canary_method) -> tuple[bool, str]:
    """打一个已知有洞的端点，证明探针确实能检出。"""
    if not canary_path:
        return True, "跳过（未指定 --canary-path）"
    url = build_url(base, pfx, canary_path, ids, which=0)
    if not url:
        return False, f"canary 路径 {canary_path} 的参数填不全"
    status, _ = http(canary_method, url, actor_token)
    if 200 <= status < 300:
        return True, f"OK — 已知漏洞端点被成功检出（{canary_path} → {status}）"
    return False, (
        f"已知有洞的 {canary_path} 返回 {status}，探针没检出。"
        "要么该洞已修（换一个 canary），要么判定逻辑失灵"
    )


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument(
        "--path-prefix",
        default="",
        help="⚠️ 通常不需要。openapi 里的 path 已是完整路径。仅在反向代理额外加了前缀时才用",
    )
    ap.add_argument("--token-admin", default=None, help="用于对照 A")
    ap.add_argument("--token-student", default=None)
    ap.add_argument("--token-teacher", default=None)
    for p in ("student", "class", "grade"):
        ap.add_argument(f"--foreign-{p}-id", type=int, default=None)
        ap.add_argument(f"--own-{p}-id", type=int, default=None)
    ap.add_argument(
        "--canary-path",
        default=None,
        help="已知有洞的端点路径，如 /api/v1/registry/students/{student_id}",
    )
    ap.add_argument("--canary-method", default="get")
    ap.add_argument("--include-writes", action="store_true")
    ap.add_argument("--filter", dest="name_filter", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument(
        "--skip-controls", action="store_true", help="⚠️ 跳过对照实验。除非你清楚为什么，否则别用"
    )
    args = ap.parse_args()

    if args.path_prefix:
        print(f"⚠️  你传了 --path-prefix {args.path_prefix!r}。")
        print("   openapi.json 里的 path 通常已含完整前缀，再拼一次会全 404，")
        print("   而 404 被判为'正确拒绝' → 探针会假装一切正常。对照 B 会拦住这种情况。\n")

    if args.include_writes:
        print("⚠️  写操作探测已开启，会产生副作用。确认这是测试环境，回车继续：")
        input()

    ids = {}
    for p in ("student", "class", "grade"):
        ids[f"foreign_{p}_id"] = getattr(args, f"foreign_{p}_id")
        ids[f"own_{p}_id"] = getattr(args, f"own_{p}_id")

    actors = [
        (n, t, d)
        for n, t, d in [
            ("student", args.token_student, "学生：除本人外应一律拒绝"),
            ("teacher", args.token_teacher, "班主任：本班外应拒绝"),
        ]
        if t
    ]
    if not actors:
        die("至少要给一个 --token-student / --token-teacher")

    spec = load_openapi(args.base)
    targets = collect_targets(spec, args.include_writes, args.name_filter)
    print(f"候选端点 {len(targets)} 个（路径参数含 student_id/class_id/grade_id）\n")
    if not targets:
        die("一个候选端点都没找到。--filter 写错了？还是 openapi 结构不同？")

    # ── 对照实验 ──
    if not args.skip_controls:
        print("═══ 对照实验（不过则结果不可采信）" + "═" * 25)
        ok_a, msg_a = control_a_ids_exist(
            args.base, args.path_prefix, targets, ids, args.token_admin
        )
        print(f"  A id 真实性 : {'PASS' if ok_a else 'FAIL'} — {msg_a}")
        ok_b, msg_b = control_b_reachable(args.base, args.path_prefix, targets, ids, actors)
        print(f"  B 可达性    : {'PASS' if ok_b else 'FAIL'} — {msg_b}")
        ok_c, msg_c = control_c_canary(
            args.base, args.path_prefix, ids, actors[0][1], args.canary_path, args.canary_method
        )
        print(f"  C 检出力    : {'PASS' if ok_c else 'FAIL'} — {msg_c}")
        print()
        if not (ok_a and ok_b and ok_c):
            die("对照实验未通过 —— 无论探测结果多好看，都不能作为'已修复'的证据")
    else:
        print("⚠️  已跳过对照实验，本次结果的可信度由你自己负责\n")

    # ── 正式探测 ──
    leaks, manual, skipped, checked = [], [], 0, 0
    for actor, token, desc in actors:
        print(f"── 以 {actor} 探测（{desc}）" + "─" * 22)
        for t in targets:
            url = build_url(args.base, args.path_prefix, t["path"], ids, which=0)
            if url is None:
                skipped += 1
                continue
            status, body = http(t["method"], url, token)
            checked += 1
            if status == -1:
                print(f"  [连接失败] {t['method'].upper():6} {t['path']}")
                continue
            if status in DENY_CODES:
                continue
            if status in MANUAL_CODES:
                manual.append({**t, "actor": actor, "status": status})
                continue
            if status >= 500:
                print(f"  [500]  {t['method'].upper():6} {t['path']}  ← 不是越权，是崩了")
                leaks.append({**t, "actor": actor, "status": status, "kind": "error"})
                continue
            preview = body[:120].decode("utf-8", "replace").replace("\n", " ")
            print(f"  [越权 {status}] {t['method'].upper():6} {t['path']}")
            print(f"              {preview}")
            leaks.append({**t, "actor": actor, "status": status, "kind": "idor"})
        print()

    # ── 汇总 ──
    idor = [x for x in leaks if x["kind"] == "idor"]
    errs = [x for x in leaks if x["kind"] == "error"]
    print("=" * 60)
    print(f"探测 {checked} 次 / 跳过 {skipped} 个（参数填不全）")
    print(f"越权 {len(idor)}   500 崩溃 {len(errs)}   待人工(400/422) {len(manual)}")

    if manual:
        print("\n待人工判断（缺必填参数，权限判不了）：")
        for x in manual[:20]:
            print(f"  {x['actor']:8} {x['status']} {x['method'].upper():6} {x['path']}")

    if idor:
        print("\n未修复端点：")
        for x in idor:
            print(f"  {x['actor']:8} {x['method'].upper():6} {x['path']}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(
                {"idor": idor, "errors": errs, "manual": manual}, f, ensure_ascii=False, indent=2
            )
        print(f"\n明细 → {args.json_out}")

    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
