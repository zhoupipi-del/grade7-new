#!/usr/bin/env python3
"""
全链路实弹演练 — Mock脚本轰入高危时序数据
科目1: 注入考勤+错题高危数据，触发CEP双沸点复合预警

执行流程:
  Phase 0: 清场 — 清除陈博裕(student_id=1)旧数据
  Phase 1: 考勤沸点A — 注入3天连续缺勤(Jul10-12)
  Phase 2: 学业断层沸点B — 注入3次连续错题(同一知识点)
  Phase 3: 验证 — 检查CEP复合预警+Redis+SSE

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
REDIS_CMD = f"redis-cli -a '{_redis_pass}'"
STUDENT_ID = 1      # 陈博裕
CLASS_ID = 1        # 2501班
GRADE_ID = 1        # 2025级初一
SCHOOL_ID = 1
SUBJECT_ID = 2      # 数学
KP_ID = 1           # 一元一次方程
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# 状态标记
ERROR_COUNT = 0
SUCCESS_COUNT = 0

def log(tag, msg):
    print(f"[{tag}] {msg}")

def run_mysql(sql):
    """执行MySQL命令"""
    result = subprocess.run(
        f"{MYSQL_CMD} -e \"{sql}\"",
        shell=True, capture_output=True, text=True, timeout=15
    )
    if result.stderr and "Warning" not in result.stderr:
        log("MYSQL_ERR", result.stderr)
    return result.stdout

def run_redis(cmd):
    """执行Redis命令"""
    result = subprocess.run(
        f"{REDIS_CMD} {cmd}",
        shell=True, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()

def api_call(method, path, data=None, headers=None):
    """调用Wings 3.0 API"""
    url = f"{API_BASE}{path}"
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            r = requests.post(url, json=data, headers=headers, timeout=30)
        elif method == "PUT":
            r = requests.put(url, json=data, headers=headers, timeout=10)
        return r
    except Exception as e:
        log("API_ERR", f"{method} {path}: {e}")
        return None

# ===== Phase 0: 清场 =====
def phase0_cleanup():
    log("PHASE0", "═══ 清场开始 — 清除陈博裕旧数据 ═══")

    # 0-1: 解结旧ActiveCompositeAlert
    out = run_mysql(
        "SELECT id, is_resolved FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND school_id={SCHOOL_ID}"
    )
    log("PHASE0", f"现有预警: {out.strip()}")

    run_mysql(
        "UPDATE growth_active_composite_alerts SET "
        "is_resolved=1, resolved_at=NOW(), resolution_note='Mock演练清场-自动结案', "
        "final_prescription='演练清场' "
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

    # 0-4: 清Redis CEP键
    keys = run_redis("KEYS 'wings:cep:*'")
    if keys:
        for k in keys.split('\n'):
            if k.strip():
                run_redis(f"DEL {k.strip()}")
        log("PHASE0", f"✅ Redis CEP键已清除: {keys}")
    else:
        log("PHASE0", "✅ Redis CEP键已空仓(无需清除)")

    # 0-5: 验证清场结果
    att_count = run_mysql(
        f"SELECT COUNT(*) FROM attendance_records "
        f"WHERE student_id={STUDENT_ID} AND record_date BETWEEN '2026-07-10' AND '2026-07-12'"
    ).strip()
    gap_count = run_mysql(
        f"SELECT COUNT(*) FROM knowledge_gaps WHERE student_id={STUDENT_ID}"
    ).strip()
    err_count = run_mysql(
        f"SELECT COUNT(*) FROM error_book_items WHERE student_id={STUDENT_ID} AND subject_id={SUBJECT_ID}"
    ).strip()
    alert_count = run_mysql(
        "SELECT COUNT(*) FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND is_resolved=0"
    ).strip()

    log("PHASE0", f"验证: 缺勤={att_count} 断层={gap_count} 错题={err_count} 未结案预警={alert_count}")
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
                {"student_id": STUDENT_ID, "status": "absent", "note": "Mock演练-连续缺勤"}
            ]
        }
        r = api_call("POST", "/attendance/records/batch", payload, headers)
        if r and r.status_code == 200:
            log("PHASE1", f"✅ 缺勤注入成功: {d} → {r.json().get('message', r.json())}")
        else:
            log("PHASE1", f"❌ 缺勤注入失败: {d} → status={r.status_code if r else 'N/A'} body={r.text if r else 'N/A'}")

        # 每次注入间隔3秒,让EventBus/Listener有时间处理
        time.sleep(3)

    # 等待listener处理完毕
    log("PHASE1", "等待15秒,让CEP引擎处理考勤沸点...")
    time.sleep(15)

    # 检查Redis attendance窗口键
    window_key = run_redis(f"GET wings:cep:window:attendance:{STUDENT_ID}")
    log("PHASE1", f"Redis attendance窗口键: {window_key}")
    ttl = run_redis(f"TTL wings:cep:window:attendance:{STUDENT_ID}")
    log("PHASE1", f"窗口键TTL: {ttl}s")

    # 检查DB考勤记录
    att = run_mysql(
        f"SELECT record_date, status FROM attendance_records "
        f"WHERE student_id={STUDENT_ID} AND record_date BETWEEN '2026-07-10' AND '2026-07-12' "
        f"ORDER BY record_date"
    )
    log("PHASE1", f"考勤DB记录:\n{att}")

    log("PHASE1", "═══ 考勤沸点A注入完成 ═══")


# ===== Phase 2: 学业断层沸点B =====
def phase2_error_funnel(jwt_token):
    log("PHASE2", "═══ 学业断层沸点B — 注入3次连续错题 ═══")
    headers = {"Authorization": f"Bearer {jwt_token}"}

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
        r = api_call("POST", "/error-funnel/errors", payload, headers)
        if r and r.status_code in (200, 201):
            resp = r.json()
            log("PHASE2", f"✅ 错题#{i}注入成功 → {resp.get('message', resp)}")
        else:
            log("PHASE2", f"❌ 错题#{i}注入失败 → status={r.status_code if r else 'N/A'} body={r.text[:200] if r else 'N/A'}")

        # 每次注入间隔5秒,让聚合引擎有时间计算
        time.sleep(5)

    # 等待CEP处理(DeepSeek处方生成约20秒)
    log("PHASE2", "等待30秒,让CEP引擎处理学业断层沸点+V3处方生成...")
    time.sleep(30)

    # 检查知识断层状态
    gap = run_mysql(
        f"SELECT id, error_count, consecutive_errors, gap_level "
        f"FROM knowledge_gaps WHERE student_id={STUDENT_ID} AND knowledge_point_id={KP_ID}"
    )
    log("PHASE2", f"知识断层状态:\n{gap}")

    # 检查Redis窗口键
    att_window = run_redis(f"GET wings:cep:window:attendance:{STUDENT_ID}")
    err_window = run_redis(f"GET wings:cep:window:error_funnel:{STUDENT_ID}")
    cooldown = run_redis(f"GET wings:cep:lock:composite:{STUDENT_ID}")
    log("PHASE2", f"Redis: attendance_window={att_window} | error_funnel_window={err_window} | cooldown_lock={cooldown}")

    # 检查冷却锁TTL
    cooldown_ttl = run_redis(f"TTL wings:cep:lock:composite:{STUDENT_ID}")
    log("PHASE2", f"冷却锁TTL: {cooldown_ttl}s")

    log("PHASE2", "═══ 学业断层沸点B注入完成 ═══")


# ===== Phase 3: 验证 =====
def phase3_verify(jwt_token):
    log("PHASE3", "═══ 全链路验证 ═══")
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # 3-1: 检查ActiveCompositeAlert
    alert = run_mysql(
        "SELECT id, alert_type, title, is_resolved, created_at, "
        "LEFT(ai_prescription, 100) as prescription_preview "
        f"FROM growth_active_composite_alerts WHERE student_id={STUDENT_ID} AND is_resolved=0 "
        "ORDER BY created_at DESC LIMIT 1"
    )
    log("PHASE3", f"新预警记录:\n{alert}")

    # 3-2: 获取预警详情(API)
    # 先获取alert_id
    alert_id = run_mysql(
        f"SELECT id FROM growth_active_composite_alerts "
        f"WHERE student_id={STUDENT_ID} AND is_resolved=0 ORDER BY created_at DESC LIMIT 1"
    ).strip()
    # 去掉表头行
    lines = alert_id.split('\n')
    if len(lines) >= 2 and lines[1].strip():
        alert_id_val = lines[1].strip()
        log("PHASE3", f"预警ID: {alert_id_val}")

        r = api_call("GET", f"/growth/alerts/{alert_id_val}", headers=headers)
        if r and r.status_code == 200:
            detail = r.json()
            log("PHASE3", f"✅ API获取预警详情成功")
            log("PHASE3", f"  alert_type: {detail.get('alert_type')}")
            log("PHASE3", f"  title: {detail.get('title')}")
            log("PHASE3", f"  is_resolved: {detail.get('is_resolved')}")
            log("PHASE3", f"  AI处方长度: {len(detail.get('ai_prescription', '') or '')}字符")
        else:
            log("PHASE3", f"❌ API获取预警详情失败: status={r.status_code if r else 'N/A'}")
    else:
        log("PHASE3", "❌ 未找到新预警记录!")

    # 3-3: 检查成长时光轴(是否有新事件注入)
    timeline = run_mysql(
        f"SELECT COUNT(*) FROM growth_timeline_events WHERE student_id={STUDENT_ID}"
    ).strip()
    log("PHASE3", f"成长时光轴事件数: {timeline}")

    # 3-4: 检查Redis全部CEP键
    cep_keys = run_redis("KEYS 'wings:cep:*'")
    log("PHASE3", f"Redis CEP键: {cep_keys if cep_keys else '(空)'}")

    # 3-5: SSE端点连通性检查
    try:
        r = requests.get(
            f"{API_BASE}/notifications/stream",
            headers=headers,
            timeout=5,
            stream=True
        )
        content_type = r.headers.get('content-type', '')
        if r.status_code == 200 and 'text/event-stream' in content_type:
            log("PHASE3", "✅ SSE端点连通 (text/event-stream)")
            # 读几行看看有没有COMPOSITE_ALERT事件
            for line in r.iter_lines(decode_unicode=True):
                if line:
                    log("PHASE3_SSE", line[:200])
                    if 'COMPOSITE_ALERT' in line:
                        log("PHASE3", "✅✅✅ SSE捕获到COMPOSITE_ALERT事件!")
                        break
                # 只读5秒
                break
        else:
            log("PHASE3", f"❌ SSE端点异常: status={r.status_code} content-type={r.headers.get('content-type')}")
    except Exception as e:
        log("PHASE3", f"SSE检查(超时正常): {e}")

    # 3-6: 最终统计
    log("PHASE3", "═══ 全链路验证结果汇总 ═══")
    final_alert = run_mysql(
        "SELECT id, alert_type, is_resolved, "
        "LENGTH(ai_prescription) as rx_len, created_at "
        f"FROM growth_active_composite_alerts WHERE student_id={STUDENT_ID} AND is_resolved=0"
    )
    log("PHASE3", f"最终预警:\n{final_alert}")

    final_gap = run_mysql(
        f"SELECT id, error_count, consecutive_errors, gap_level "
        f"FROM knowledge_gaps WHERE student_id={STUDENT_ID} AND knowledge_point_id={KP_ID}"
    )
    log("PHASE3", f"最终断层:\n{final_gap}")

    final_redis = run_redis("KEYS 'wings:cep:*'")
    log("PHASE3", f"最终Redis: {final_redis if final_redis else '(空)'}")

    log("PHASE3", "═══ 实弹演练科目1完成 ═══")


# ===== 主流程 =====
def main():
    log("MAIN", "🚀 全链路实弹演练科目1 — Mock脚本轰入高危时序数据")
    log("MAIN", f"目标: 陈博裕(student_id={STUDENT_ID}, class_id={CLASS_ID})")
    log("MAIN", f"考勤沸点A: 3天连续缺勤(Jul10-12)")
    log("MAIN", f"学业断层沸点B: 3次连续错题(一元一次方程, kp_id={KP_ID})")

    # Phase 0: 清场
    phase0_cleanup()

    # 登录获取JWT
    log("MAIN", "登录Wings 3.0获取JWT...")
    login_data = {
        "username": ADMIN_USER,
        "password": ADMIN_PASS
    }
    r = api_call("POST", "/auth/login", login_data)
    if not r or r.status_code != 200:
        log("MAIN", f"❌ 登录失败! status={r.status_code if r else 'N/A'} body={r.text if r else 'N/A'}")
        sys.exit(1)

    token = r.json().get("access_token") or r.json().get("token")
    if not token:
        # 可能response.data里有token
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
    phase3_verify(token)

    log("MAIN", "🏁 全链路实弹演练科目1完成!")
    log("MAIN", "接下来执行科目2(TimetableEnricher)→科目3(CEP引爆验证)→科目4(SSE前端弹窗)")


if __name__ == "__main__":
    main()
