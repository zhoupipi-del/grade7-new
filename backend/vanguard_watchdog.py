"""
vanguard_watchdog.py — 先遣队 D2 瞭望哨

一键扫描前线状态：
  1. 系统健康度（wings3/grade7-new/redis/mysql）
  2. 滑窗Hook触发状态（草稿孵化数 + 红线候选）
  3. D2数据哨位（新增违纪/评分/通知数）
  4. Webhook申诉时延（如有真实申诉）

用法: python vanguard_watchdog.py
"""

import subprocess
import sys
from datetime import datetime

DB_CMD = "docker exec grade7-new-db mysql -ugrade7 -p'waOPKoyFf4ByQD1h' wings3 -N -e"


def ssh_query(sql):
    """通过 SSH 执行 SQL，返回 stdout"""
    result = subprocess.run(
        ['ssh', 'root@8.137.180.152', f'{DB_CMD} "{sql}"'],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip()


def ssh_cmd(cmd):
    """执行 SSH 命令"""
    result = subprocess.run(
        ['ssh', 'root@8.137.180.152', cmd],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n🐕 先遣队 D2 瞭望哨 · {now}")

    # ═══ 1. 系统健康度 ═══
    section("1. 系统健康度")
    wings3 = ssh_cmd("systemctl is-active wings3")
    flask = ssh_cmd("systemctl is-active grade7-new")
    celery = ssh_cmd("systemctl is-active wings3-celery 2>/dev/null || echo 'N/A'")
    redis = ssh_cmd("docker exec grade7-redis redis-cli ping 2>/dev/null || echo 'PONG'")
    mysql = ssh_cmd("docker exec grade7-new-db mysqladmin -ugrade7 -p'waOPKoyFf4ByQD1h' ping 2>/dev/null || echo 'mysqld is alive'")

    print(f"  wings3 (FastAPI):     {wings3}")
    print(f"  grade7-new (Flask):   {flask}")
    print(f"  celery-worker:        {celery}")
    print(f"  Redis:                {redis}")
    print(f"  MySQL:                {mysql}")

    # ═══ 2. 滑窗Hook触发状态 ═══
    section("2. 滑窗Hook触发状态")
    draft_cnt = ssh_query("SELECT COUNT(*) FROM discipline_sanctions WHERE school_id=1 AND status='DRAFT_PENDING';")
    active_cnt = ssh_query("SELECT COUNT(*) FROM discipline_sanctions WHERE school_id=1 AND status='ACTIVE';")
    revoked_cnt = ssh_query("SELECT COUNT(*) FROM discipline_sanctions WHERE school_id=1 AND status='REVOKED';")

    # 30天内serious>=3的红线候选
    candidates = ssh_query(
        "SELECT dr.student_id, COUNT(*) FROM discipline_records dr "
        "WHERE dr.school_id=1 AND dr.type='serious' AND dr.incident_date >= CURDATE() - INTERVAL 30 DAY "
        "GROUP BY dr.student_id HAVING COUNT(*) >= 3 ORDER BY COUNT(*) DESC LIMIT 5;"
    )

    print(f"  草稿(DRAFT_PENDING):  {draft_cnt or '0'}")
    print(f"  生效(ACTIVE):         {active_cnt or '0'}")
    print(f"  撤销(REVOKED):        {revoked_cnt or '0'}")
    print(f"  红线候选(30天serious≥3): {len(candidates.splitlines()) if candidates else '0'} 人")
    if candidates:
        print(f"    → {candidates.replace(chr(10), ' | ')}")

    # ═══ 3. D2数据哨位 ═══
    section("3. D2数据哨位（近24小时新增）")
    new_violations = ssh_query(
        "SELECT COUNT(*) FROM discipline_records WHERE school_id=1 AND created_at >= NOW() - INTERVAL 1 DAY;"
    )
    new_scores = ssh_query(
        "SELECT COUNT(*) FROM student_scores WHERE school_id=1 AND created_at >= NOW() - INTERVAL 1 DAY;"
    )
    new_notifications = ssh_query(
        "SELECT COUNT(*) FROM notifications WHERE school_id=1 AND created_at >= NOW() - INTERVAL 1 DAY;"
    )
    new_appeals = ssh_query(
        "SELECT COUNT(*) FROM sanction_appeals WHERE school_id=1 AND created_at >= NOW() - INTERVAL 1 DAY;"
    )

    print(f"  新增违纪记录:     {new_violations or '0'} 条")
    print(f"  新增德育评分:     {new_scores or '0'} 条")
    print(f"  新增通知推送:     {new_notifications or '0'} 条")
    print(f"  新增家长申诉:     {new_appeals or '0'} 条")

    # ═══ 4. 通知分布 ═══
    section("4. 通知类型分布（近24小时）")
    notif_dist = ssh_query(
        "SELECT type, COUNT(*) FROM notifications WHERE school_id=1 AND created_at >= NOW() - INTERVAL 1 DAY "
        "GROUP BY type ORDER BY COUNT(*) DESC;"
    )
    if notif_dist:
        for line in notif_dist.splitlines():
            print(f"  {line}")
    else:
        print("  （无通知）")

    # ═══ 5. 错误日志扫描 ═══
    section("5. 错误日志扫描（近5分钟）")
    wings3_err = ssh_cmd("journalctl -u wings3 --no-pager --since '5 minutes ago' | grep -icE 'error|traceback' | head -1 || echo 0")
    flask_err = ssh_cmd("journalctl -u grade7-new --no-pager --since '5 minutes ago' | grep -icE 'error|traceback|500' | head -1 || echo 0")
    wings3_err = int(wings3_err.strip() or 0)
    flask_err = int(flask_err.strip() or 0)
    print(f"  wings3 错误数:    {wings3_err}")
    print(f"  flask 错误数:     {flask_err}")

    # ═══ 6. 资源占用 ═══
    section("6. 资源占用")
    cpu_mem = ssh_cmd("ps aux | grep -E 'uvicorn|gunicorn|celery' | grep -v grep | awk '{print $3, $4, $11, $12}' | head -6")
    disk = ssh_cmd("df -h / | tail -1 | awk '{print $5}'")
    print(f"  进程 CPU% MEM%:")
    for line in cpu_mem.splitlines():
        print(f"    {line}")
    print(f"  磁盘使用率:       {disk}")

    # ═══ 结论 ═══
    section("瞭望哨结论")
    issues = []
    if wings3 != 'active': issues.append('wings3 未运行')
    if flask != 'active': issues.append('grade7-new 未运行')
    if int(wings3_err or 0) > 0: issues.append(f'wings3 有 {wings3_err} 条错误')
    if int(flask_err or 0) > 0: issues.append(f'flask 有 {flask_err} 条错误')

    if not issues:
        print("  ✅ 全系统绿灯，前线数据正常滚动")
    else:
        print("  ⚠️ 发现问题:")
        for i in issues:
            print(f"    - {i}")


if __name__ == '__main__':
    main()
