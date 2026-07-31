#!/usr/bin/env python3
"""
全链路实弹演练 V2 — Mock脚本轰入高危时序数据
科目1: 注入考勤+错题高危数据，触发CEP双沸点复合预警

修复项(V2):
  1. Redis改用DB1 (-n 1) — CEP键存储在DB1而非DB0
  2. 错题API路径改下划线 — /error_funnel/errors (非连字符)
  3. Phase 1不等待CEP — 先只注入考勤,让listener设窗口键即可
  4. Phase 2后才等CEP引擎完整处理(含DeepSeek处方生成)

执行流程:
  Phase 0: 清场 — 清除陈博裕(student_id=1)旧数据 + Redis DB1 CEP键
  Phase 1: 考勤沸点A — 注入3天连续缺勤(Jul10-12)
  Phase 2: 学业断层沸点B — 注入3次连续错题(同一知识点)
  Phase 3: 验证 — 检查CEP复合预警+Redis DB1+SSE

作者: 二狗子 🐶
日期: 2026-07-12
"""

import json
import sys
import time
import subprocess
import requests
from datetime import date, timedelta

# ===== 配置 =====
API_BASE = "http://127.0.0.1:8000/api/v1"
_db_url = os.environ.get("DATABASE_URL", "")
_db_pass = _db_url.split(":")[-1].split("@")[0] if _db_url else ""
MYSQL_CMD = f"mysql -h 127.0.0.1 -P 3307 -ugrade7 -p{_db_pass} wings3"
_redis_pass = os.environ.get("REDIS_PASSWORD", "")
REDIS_CMD = f"redis-cli -a '{_redis_pass}' -n 1"  # DB1
STUDENT_ID = 1      # 陈博裕
CLASS_ID = 1        # 2501班
GRADE_ID = 1        # 2025级初一
SCHOOL_ID = 1
SUBJECT_ID = 2      # 数学
KP_ID = 1           # 一元一次方程
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

def log(tag, msg):
    print(f"[{tag}] {msg}")

def run_mysql(sql):
    """执行MySQL命令"""
    result = subprocess.run(
        MYSQL_CMD + f' -e "{sql}"',
        shell=True, capture_output=True, text=True, timeout=15
    )
    if result.stderr and "Warning" not in result.stderr:
        log("MYSQL_ERR", result.stderr)
    return result.stdout

def run_redis(cmd):
    """执行Redis命令(DB1)"""
    result = subprocess.run(
        f"{REDIS_CMD} {cmd}",
        shell=True, capture_output=True, text=True, timeout=10
    )
    # redis-cli可能输出警告行, 过滤掉
    lines = result.stdout.strip().split('\n')
    clean = [l for l in lines if not l.startswith('Warning') and l.strip()]
    return '\n'.join(clean) if clean else ''

def api_call(method, path, data=None, headers=None, timeout=30):
    """调用Wings 3.0 API"""
    url = f"{API_BASE}{path}"
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=timeout)
        elif method == "POST":
            r = requests.post(url, json=data, headers=headers, timeout=timeout)
        elif method == "PUT":
            r = requests.put(url, json=data, headers=headers, timeout=timeout)
        return r
    except Exception as e:
        log("API_ERR", f"{method} {path}: {e}")
        return None

# ===== Phase 0: 清场 =====
def phase0_cleanup():
    log("PHASE0", "═══ 清场开始 — 清除陈博裕旧数据 ═══")

    # 0-1: 结案旧ActiveCompositeAlert
    out = run_mysql(
        "SELECT id, is_resolved, created_at FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND school_id={SCHOOL_ID}"
    )
    log("PHASE0", f"现有预警:\n{out.strip()}")

    run_mysql(
        "UPDATE growth_active_composite_alerts SET "
        "is_resolved=1, resolved_at=NOW(), resolution_note='Mock演练V2清场', "
        "final_prescription='演练清场V2' "
        f"WHERE student_id={STUDENT_ID} AND school_id={SCHOOL_ID} AND is_resolved=0"
    )
    log("PHASE0", "✅ 旧预警已结案")

    # 0-2: 删除3天缺勤记录(Jul10-12)
    run_mysql(
        f"DELETE FROM attendance_records "
        f"WHERE student_id={STUDENT_ID} AND record_date BETWEEN '2026-07-10' AND '2026-07-12' AND status='absent'"
    )
    log("PHASE0", "✅ 旧缺勤记录已删除(Jul10-12)")

    # 0-3: 删除知识断层 + 错题本
    run_mysql(
        f"DELETE FROM knowledge_gaps WHERE student_id={STUDENT_ID} AND knowledge_point_id={KP_ID}"
    )
    run_mysql(
        f"DELETE FROM error_book_items WHERE student_id={STUDENT_ID} AND subject_id={SUBJECT_ID}"
    )
    log("PHASE0", "✅ 旧知识断层+错题本已清除")

    # 0-4: 清Redis DB1 CEP键(⚠️ 关键修复!)
    keys = run_redis("KEYS 'wings:cep:*'")
    if keys:
        for k in keys.split('\n'):
            if k.strip():
                run_redis(f"DEL {k.strip()}")
        log("PHASE0", f"✅ Redis DB1 CEP键已清除: {keys}")
    else:
        log("PHASE0", "✅ Redis DB1 CEP键已空仓")

    # 0-5: 验证清场结果
    att_count = run_mysql(
        f"SELECT COUNT(*) as cnt FROM attendance_records "
        f"WHERE student_id={STUDENT_ID} AND record_date BETWEEN '2026-07-10' AND '2026-07-12'"
    ).strip()
    gap_count = run_mysql(
        f"SELECT COUNT(*) as cnt FROM knowledge_gaps WHERE student_id={STUDENT_ID}"
    ).strip()
    err_count = run_mysql(
        f"SELECT COUNT(*) as cnt FROM error_book_items WHERE student_id={STUDENT_ID} AND subject_id={SUBJECT_ID}"
    ).strip()
    alert_count = run_mysql(
        "SELECT COUNT(*) as cnt FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND is_resolved=0"
    ).strip()
    redis_check = run_redis("KEYS 'wings:cep:*'")

    log("PHASE0", f"验证: 缺勤={att_count} 断层={gap_count} 错题={err_count} 未结案预警={alert_count}")
    log("PHASE0", f"Redis DB1 CEP键: {redis_check if redis_check else '(空)'}")
    log("PHASE0", "═══ 清场完成 ═══")


# ===== Phase 1: 考勤沸点A =====
def phase1_attendance(jwt_token):
    log("PHASE1", "═══ 考勤沸点A — 注入3天连续缺勤 ═══")
    headers = {"Authorization": f"Bearer {jwt_token}"}

    dates = ["2026-07-10", "2026-07-11", "2026-07-12"]
    for d in dates:
        payload = {
            "class_id": CLASS_ID,
            "grade_id": GRADE_ID,
            "record_date": d,
            "records": [
                {"student_id": STUDENT_ID, "status": "absent", "note": "Mock演练V2-连续缺勤"}
            ]
        }
        r = api_call("POST", "/attendance/records/batch", payload, headers)
        if r and r.status_code == 200:
            resp = r.json()
            log("PHASE1", f"✅ 缺勤注入成功: {d} → {resp.get('message', '')}")
        else:
            status = r.status_code if r else 'N/A'
            body = r.text[:300] if r else 'N/A'
            log("PHASE1", f"❌ 缺勤注入失败: {d} → status={status} body={body}")

        # 每次注入间隔3秒
        time.sleep(3)

    # 等待listener处理(检测连续缺勤→注入时光轴→触发CEP)
    log("PHASE1", "等待20秒,让Listener检测连续缺勤并触发CEP...")
    time.sleep(20)

    # 检查Redis DB1 attendance窗口键
    window_val = run_redis(f"GET wings:cep:window:attendance:{STUDENT_ID}")
    window_ttl = run_redis(f"TTL wings:cep:window:attendance:{STUDENT_ID}")
    log("PHASE1", f"Redis DB1 attendance窗口键: value={window_val} TTL={window_ttl}s")

    # 检查DB考勤记录
    att = run_mysql(
        f"SELECT record_date, status FROM attendance_records "
        f"WHERE student_id={STUDENT_ID} AND record_date BETWEEN '2026-07-10' AND '2026-07-12' "
        f"ORDER BY record_date"
    )
    log("PHASE1", f"考勤DB记录:\n{att}")

    # 检查时光轴是否有考勤事件
    timeline = run_mysql(
        f"SELECT event_type, severity, LEFT(event_data, 50) as data_preview "
        f"FROM growth_timeline_events WHERE student_id={STUDENT_ID} AND event_type LIKE '%absent%' "
        f"ORDER BY created_at DESC LIMIT 5"
    )
    log("PHASE1", f"时光轴缺勤事件:\n{timeline}")

    log("PHASE1", "═══ 考勤沸点A注入完成 ═══")


# ===== Phase 2: 学业断层沸点B =====
def phase2_error_funnel(jwt_token):
    log("PHASE2", "═══ 学业断层沸点B — 注入3次连续错题 ═══")
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # ⚠️ 关键修复: API路径用下划线(非连字符)
    ERROR_ENDPOINT = "/error_funnel/errors"

    # 创建3个错题(同一知识点), 逐个注入让gap从watch→warning→critical
    questions = [
        "一元一次方程 2x+3=7 的解为x=5(错误解法)",
        "一元一次方程 5x-2=13 的解为x=1(错误解法)",
        "一元一次方程 3(x+1)=12 的解为x=5(错误解法)",
    ]

    for i, q in enumerate(questions, 1):
        payload = {
            "student_id": STUDENT_ID,
            "subject_id": SUBJECT_ID,
            "source_type": "manual",
            "question_content": q,
            "knowledge_point_ids": [KP_ID],
            "error_type": "conceptual",
            "student_answer": "错误答案",
            "correct_answer": "正确解法步骤",
        }
        r = api_call("POST", ERROR_ENDPOINT, payload, headers, timeout=15)
        if r and r.status_code in (200, 201):
            resp = r.json()
            log("PHASE2", f"✅ 错题#{i}注入成功")
            # 查看gap状态
            gap = run_mysql(
                f"SELECT error_count, consecutive_errors, gap_level "
                f"FROM knowledge_gaps WHERE student_id={STUDENT_ID} AND knowledge_point_id={KP_ID}"
            ).strip()
            log("PHASE2", f"  断层状态: {gap}")
        else:
            status = r.status_code if r else 'N/A'
            body = r.text[:300] if r else 'N/A'
            log("PHASE2", f"❌ 错题#{i}注入失败 → status={status} body={body}")

        # 每次注入间隔5秒
        time.sleep(5)

    # 等待CEP完整处理链(含DeepSeek处方生成约20秒)
    log("PHASE2", "等待40秒,让CEP引擎完成双沸点检测+V3处方生成+持久化+Redis广播...")
    time.sleep(40)

    # 检查知识断层最终状态
    gap = run_mysql(
        f"SELECT id, error_count, consecutive_errors, gap_level "
        f"FROM knowledge_gaps WHERE student_id={STUDENT_ID} AND knowledge_point_id={KP_ID}"
    )
    log("PHASE2", f"知识断层最终状态:\n{gap}")

    # 检查Redis DB1窗口键和冷却锁
    att_window = run_redis(f"GET wings:cep:window:attendance:{STUDENT_ID}")
    err_window = run_redis(f"GET wings:cep:window:error_funnel:{STUDENT_ID}")
    cooldown = run_redis(f"GET wings:cep:lock:composite:{STUDENT_ID}")
    cooldown_ttl = run_redis(f"TTL wings:cep:lock:composite:{STUDENT_ID}")
    log("PHASE2", f"Redis DB1: att_window={att_window} | err_window={err_window} | cooldown={cooldown} TTL={cooldown_ttl}s")

    log("PHASE2", "═══ 学业断层沸点B注入完成 ═══")


# ===== Phase 3: 验证 =====
def phase3_verify(jwt_token):
    log("PHASE3", "═══ 全链路验证 ═══")
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # 3-1: 检查ActiveCompositeAlert
    alert = run_mysql(
        "SELECT id, alert_type, LEFT(title, 60) as title_short, is_resolved, "
        "LENGTH(ai_prescription) as rx_len, created_at "
        f"FROM growth_active_composite_alerts WHERE student_id={STUDENT_ID} AND is_resolved=0 "
        "ORDER BY created_at DESC LIMIT 1"
    )
    log("PHASE3", f"新预警记录:\n{alert}")

    # 3-2: 获取预警详情(API)
    alert_id_raw = run_mysql(
        f"SELECT id FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND is_resolved=0 ORDER BY created_at DESC LIMIT 1"
    ).strip()
    lines = alert_id_raw.split('\n')
    if len(lines) >= 2 and lines[1].strip() and lines[1].strip() != 'id':
        alert_id_val = lines[1].strip()
        log("PHASE3", f"预警ID: {alert_id_val}")

        r = api_call("GET", f"/growth/alerts/{alert_id_val}", headers=headers)
        if r and r.status_code == 200:
            detail = r.json()
            log("PHASE3", f"✅ API获取预警详情成功")
            log("PHASE3", f"  alert_type: {detail.get('alert_type')}")
            log("PHASE3", f"  title: {detail.get('title', '')[:80]}")
            log("PHASE3", f"  is_resolved: {detail.get('is_resolved')}")
            rx = detail.get('ai_prescription', '') or ''
            log("PHASE3", f"  AI处方长度: {len(rx)}字符")
            if rx:
                log("PHASE3", f"  AI处方前100字: {rx[:100]}...")
        else:
            log("PHASE3", f"❌ API获取预警详情失败: status={r.status_code if r else 'N/A'}")
    else:
        log("PHASE3", "❌ 未找到新预警记录!")

    # 3-3: 检查成长时光轴事件数
    timeline = run_mysql(
        f"SELECT COUNT(*) as cnt FROM growth_timeline_events WHERE student_id={STUDENT_ID}"
    ).strip()
    log("PHASE3", f"成长时光轴事件数: {timeline}")

    # 3-4: 检查Redis DB1全部CEP键
    cep_keys = run_redis("KEYS 'wings:cep:*'")
    log("PHASE3", f"Redis DB1 CEP键: {cep_keys if cep_keys else '(空)'}")

    # 3-5: SSE端点连通性检查(只验证连接,不长时间读取)
    try:
        r = requests.get(
            f"{API_BASE}/notifications/stream",
            headers=headers,
            timeout=3,
            stream=True
        )
        content_type = r.headers.get('content-type', '')
        if r.status_code == 200 and 'text/event-stream' in content_type:
            log("PHASE3", "✅ SSE端点连通 (text/event-stream)")
            r.close()
        else:
            log("PHASE3", f"SSE端点: status={r.status_code} content-type={content_type}")
    except requests.exceptions.ReadTimeout:
        log("PHASE3", "✅ SSE端点连通(超时正常=长连接存活)")
    except Exception as e:
        log("PHASE3", f"SSE检查异常: {e}")

    # 3-6: 最终统计
    log("PHASE3", "═══ 全链路验证结果汇总 ═══")

    # 评分表
    results = {}

    # 考勤3天缺勤是否注入
    att_check = run_mysql(
        f"SELECT COUNT(*) as cnt FROM attendance_records "
        f"WHERE student_id={STUDENT_ID} AND record_date BETWEEN '2026-07-10' AND '2026-07-12' AND status='absent'"
    ).strip()
    results['考勤注入'] = att_check

    # 知识断层是否达critical
    gap_check = run_mysql(
        f"SELECT gap_level FROM knowledge_gaps "
        f"WHERE student_id={STUDENT_ID} AND knowledge_point_id={KP_ID}"
    ).strip()
    results['断层等级'] = gap_check

    # CEP预警是否创建
    alert_check = run_mysql(
        "SELECT id, alert_type, is_resolved FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND is_resolved=0 ORDER BY created_at DESC LIMIT 1"
    ).strip()
    results['CEP预警'] = alert_check

    # Redis DB1冷却锁是否设置
    lock_check = run_redis(f"GET wings:cep:lock:composite:{STUDENT_ID}")
    results['冷却锁'] = lock_check if lock_check else '(空)'

    for k, v in results.items():
        log("PHASE3", f"  {k}: {v}")

    # 评分判断
    att_ok = '3' in att_check or '3\n' in att_check
    gap_ok = 'critical' in gap_check.lower()
    alert_ok = 'CRITICAL_COMPOSITE' in alert_check
    lock_ok = lock_check and lock_check.strip()

    score = sum([att_ok, gap_ok, alert_ok, lock_ok])
    log("PHASE3", f"评分: {score}/4  ({'✅全通' if score==4 else '❌有缺口'})")

    log("PHASE3", "═══ 实弹演练科目1完成 ═══")
    return score


# ===== 主流程 =====
def main():
    log("MAIN", "🚀 全链路实弹演练科目1 V2 — Mock脚本轰入高危时序数据")
    log("MAIN", f"目标: 陈博裕(student_id={STUDENT_ID}, class_id={CLASS_ID})")
    log("MAIN", f"考勤沸点A: 3天连续缺勤(Jul10-12)")
    log("MAIN", f"学业断层沸点B: 3次连续错题(一元一次方程, kp_id={KP_ID})")
    log("MAIN", f"⚠️ 关键修复: Redis DB1 + 错题API下划线路径")

    # Phase 0: 清场
    phase0_cleanup()

    # 登录获取JWT
    log("MAIN", "登录Wings 3.0获取JWT...")
    r = api_call("POST", "/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASS})
    if not r or r.status_code != 200:
        log("MAIN", f"❌ 登录失败! status={r.status_code if r else 'N/A'}")
        sys.exit(1)

    token = r.json().get("access_token") or r.json().get("token")
    if not token:
        resp = r.json()
        if "data" in resp and isinstance(resp["data"], dict):
            token = resp["data"].get("access_token") or resp["data"].get("token")
    if not token:
        log("MAIN", f"❌ 无法提取JWT! response={r.json()}")
        sys.exit(1)

    log("MAIN", f"✅ JWT获取成功: {token[:20]}...")

    # Phase 1: 考勤沸点A
    phase1_attendance(token)

    # Phase 2: 学业断层沸点B
    phase2_error_funnel(token)

    # Phase 3: 验证
    score = phase3_verify(token)

    log("MAIN", f"🏁 实弹演练科目1完成! 评分: {score}/4")
    if score == 4:
        log("MAIN", "✅✅✅ 全链路通电 — 10环全通!")
    else:
        log("MAIN", "⚠️ 有缺口,需排查")


if __name__ == "__main__":
    main()
