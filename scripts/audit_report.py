#!/usr/bin/env python3
"""
自动化巡检脚本 — 每日凌晨运行，生成系统健康报告

功能：
1. 孤儿数据检查（外键引用不存在）
2. 异常空值检查（关键评分表有NULL或0分）
3. 权限异常检查（access_logs中高频越权尝试）
4. 数据一致性检查（跨表数据不一致）
5. 数学模型输入数据质量检查

使用方法：
    cd /opt/grade7-new
    source venv/bin/activate
    python3 scripts/audit_report.py

配置 crontab（每天凌晨2点运行）：
    crontab -e
    # 添加以下行：
    0 2 * * * cd /opt/grade7-new && source venv/bin/activate && python3 scripts/audit_report.py 2>&1 | mail -s "德育平台巡检报告" admin@example.com
"""

import sys
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ── 加载环境变量（从 systemd service 文件）──
print("=" * 60)
print("🔍 德育管理平台自动化巡检脚本")
print("=" * 60)
print()

# 设置必需的环境变量（巡检脚本不需要加密，用随机值）
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    print("  ⚠️  使用随机 SECRET_KEY（巡检脚本不需要加密）")

if not os.environ.get("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)
    print("  ⚠️  使用随机 JWT_SECRET_KEY（巡检脚本不需要加密）")

if not os.environ.get("DATABASE_URL"):
    print("⚠️  DATABASE_URL 环境变量未设置，尝试从 systemd service 文件读取...")
    service_file = "/etc/systemd/system/grade7-new.service"
    if os.path.exists(service_file):
        with open(service_file, "r") as f:
            for line in f:
                if line.strip().startswith("Environment="):
                    env_str = line.strip()[12:].strip('"')
                    # 可能包含多个环境变量，用空格分隔
                    for item in env_str.split():
                        if "=" in item:
                            key, value = item.split("=", 1)
                            os.environ[key.strip()] = value.strip()
                    print(f"  ✓ 从 systemd service 文件加载环境变量")
                    break

    # 如果还是没有，使用默认值
    if not os.environ.get("DATABASE_URL"):
        print("  ⚠️  使用默认 DATABASE_URL（从 service 文件复制）")
        os.environ["DATABASE_URL"] = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"

print()


def main():
    """主函数 — 在应用上下文内执行所有巡检逻辑"""
    from app import create_app
    from models import db, Student, Class, Grade, User, DisciplineRecord, Score, Exam
    from models import MentalHealthAssessment, RiskRecord, Attendance, QualityScore, WingsScore
    from models import RoutineScore, Task, Notice, NoticeReceipt, HomeVisit, LeaveRequest
    from sqlalchemy import func, text
    from sqlalchemy.exc import SQLAlchemyError

    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("开始巡检...")
        print("=" * 60)
        print()

        report = {}
        all_pass = True

        # ── 1. 孤儿数据检查 ──
        print("🔍 1. 检查孤儿数据...")
        orphans = []

        # 1.1 DisciplineRecord → Student
        orphan_count = DisciplineRecord.query.filter(
            ~DisciplineRecord.student_id.in_(db.session.query(Student.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "DisciplineRecord",
                "foreign_key": "student_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（DisciplineRecord.student_id 不存在于 Student）")
        else:
            print("  ✓ DisciplineRecord → Student：无孤儿记录")

        # 1.2 Score → Student
        orphan_count = Score.query.filter(
            ~Score.student_id.in_(db.session.query(Student.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "Score",
                "foreign_key": "student_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（Score.student_id 不存在于 Student）")
        else:
            print("  ✓ Score → Student：无孤儿记录")

        # 1.3 Score → Exam
        orphan_count = Score.query.filter(
            ~Score.exam_id.in_(db.session.query(Exam.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "Score",
                "foreign_key": "exam_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（Score.exam_id 不存在于 Exam）")
        else:
            print("  ✓ Score → Exam：无孤儿记录")

        # 1.4 MentalHealthAssessment → Student
        orphan_count = MentalHealthAssessment.query.filter(
            ~MentalHealthAssessment.student_id.in_(db.session.query(Student.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "MentalHealthAssessment",
                "foreign_key": "student_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（MentalHealthAssessment.student_id 不存在于 Student）")
        else:
            print("  ✓ MentalHealthAssessment → Student：无孤儿记录")

        # 1.5 Attendance → Student
        orphan_count = Attendance.query.filter(
            ~Attendance.student_id.in_(db.session.query(Student.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "Attendance",
                "foreign_key": "student_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（Attendance.student_id 不存在于 Student）")
        else:
            print("  ✓ Attendance → Student：无孤儿记录")

        # 1.6 QualityScore → Student
        orphan_count = QualityScore.query.filter(
            ~QualityScore.student_id.in_(db.session.query(Student.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "QualityScore",
                "foreign_key": "student_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（QualityScore.student_id 不存在于 Student）")
        else:
            print("  ✓ QualityScore → Student：无孤儿记录")

        # 1.7 WingsScore → Student
        orphan_count = WingsScore.query.filter(
            ~WingsScore.student_id.in_(db.session.query(Student.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "WingsScore",
                "foreign_key": "student_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（WingsScore.student_id 不存在于 Student）")
        else:
            print("  ✓ WingsScore → Student：无孤儿记录")

        # 1.8 NoticeReceipt → Notice
        orphan_count = NoticeReceipt.query.filter(
            ~NoticeReceipt.notice_id.in_(db.session.query(Notice.id))
        ).count()
        if orphan_count > 0:
            orphans.append({
                "table": "NoticeReceipt",
                "foreign_key": "notice_id",
                "orphan_count": orphan_count,
            })
            print(f"  ⚠️  发现 {orphan_count} 条孤儿记录（NoticeReceipt.notice_id 不存在于 Notice）")
        else:
            print("  ✓ NoticeReceipt → Notice：无孤儿记录")

        total_orphans = sum(o["orphan_count"] for o in orphans)
        if total_orphans > 0:
            all_pass = False
            print(f"\n  🔴 孤儿数据检查未通过：共 {total_orphans} 条孤儿记录")
        else:
            print(f"\n  🟢 孤儿数据检查通过：无孤儿记录")

        report["orphan_records"] = {
            "status": "PASS" if total_orphans == 0 else "FAIL",
            "total_orphans": total_orphans,
            "details": orphans,
        }
        print()

        # ── 2. 异常空值检查 ──
        print("🔍 2. 检查异常空值...")
        issues = []

        # 2.1 Score 表中的 NULL 或 0 分
        total_scores = Score.query.count()
        if total_scores > 0:
            null_scores = Score.query.filter(Score.score == None).count()
            zero_scores = Score.query.filter(Score.score == 0).count()
            null_pct = (null_scores / total_scores) * 100
            zero_pct = (zero_scores / total_scores) * 100

            if null_pct > 5.0:
                issues.append({
                    "table": "Score",
                    "column": "score",
                    "issue": "NULL",
                    "count": null_scores,
                    "percentage": round(null_pct, 2),
                })
                print(f"  ⚠️  Score.score 有 {null_scores} 条 NULL（占比 {round(null_pct, 2)}%）")

            if zero_pct > 5.0:
                issues.append({
                    "table": "Score",
                    "column": "score",
                    "issue": "0分",
                    "count": zero_scores,
                    "percentage": round(zero_pct, 2),
                })
                print(f"  ⚠️  Score.score 有 {zero_scores} 条 0分（占比 {round(zero_pct, 2)}%）")

            if null_pct <= 5.0 and zero_pct <= 5.0:
                print(f"  ✓ Score 异常空值检查通过（NULL: {round(null_pct, 2)}%, 0分: {round(zero_pct, 2)}%）")
        else:
            print("  ⚠️  Score 表中无数据")

        # 2.2 QualityScore 表中的 NULL
        total_quality = QualityScore.query.count()
        if total_quality > 0:
            null_quality = QualityScore.query.filter(QualityScore.score == None).count()
            null_pct = (null_quality / total_quality) * 100

            if null_pct > 5.0:
                issues.append({
                    "table": "QualityScore",
                    "column": "score",
                    "issue": "NULL",
                    "count": null_quality,
                    "percentage": round(null_pct, 2),
                })
                print(f"  ⚠️  QualityScore.score 有 {null_quality} 条 NULL（占比 {round(null_pct, 2)}%）")
            else:
                print(f"  ✓ QualityScore 异常空值检查通过（NULL: {round(null_pct, 2)}%）")
        else:
            print("  ⚠️  QualityScore 表中无数据")

        if issues:
            all_pass = False
            print(f"\n  🟡 异常空值检查未通过：发现 {len(issues)} 个问题")
        else:
            print(f"\n  🟢 异常空值检查通过：无异常空值")

        report["abnormal_nulls"] = {
            "status": "PASS" if not issues else "WARN",
            "issues": issues,
        }
        print()

        # ── 3. 权限异常检查（需要 access_log 表）──
        print("🔍 3. 检查权限异常...")
        try:
            # 检查 access_log 表是否存在
            result = db.session.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                AND table_name = 'access_log'
            """))
            
            if result.scalar() == 0:
                print("  ⚠️  access_log 表不存在，跳过权限异常检查")
                report["permission_anomalies"] = {
                    "status": "SKIP",
                    "reason": "access_log 表不存在",
                }
            else:
                # 检查高频越权尝试（单用户）
                since = datetime.utcnow() - timedelta(days=1)
                
                result = db.session.execute(text("""
                    SELECT user_id, COUNT(*) as attempt_count
                    FROM access_log
                    WHERE status_code = 403
                    AND created_at >= :since
                    GROUP BY user_id
                    HAVING attempt_count >= 5
                """), {"since": since})
                
                anomalies = []
                for row in result.fetchall():
                    anomalies.append({
                        "user_id": row[0],
                        "attempt_count": row[1],
                    })
                    print(f"  ⚠️  用户 {row[0]} 在最近24h内有 {row[1]} 次越权尝试")
                
                if anomalies:
                    all_pass = False
                    print(f"\n  🔴 权限异常检查未通过：发现 {len(anomalies)} 个用户有高频越权尝试")
                else:
                    print(f"\n  🟢 权限异常检查通过：无高频越权尝试")
                
                report["permission_anomalies"] = {
                    "status": "PASS" if not anomalies else "FAIL",
                    "anomalies": anomalies,
                }
        except SQLAlchemyError as e:
            print(f"  ⚠️  权限异常检查失败: {e}")
            report["permission_anomalies"] = {
                "status": "ERROR",
                "error": str(e),
            }
        print()

        # ── 4. 数据一致性检查 ──
        print("🔍 4. 检查数据一致性...")
        issues = []

        # 4.1 Student.class_id 引用的 Class 是否存在
        orphan_students = Student.query.filter(
            Student.is_active == True,
            ~Student.class_id.in_(db.session.query(Class.id))
        ).count()
        if orphan_students > 0:
            issues.append({
                "type": "Student.class_id 引用不存在的 Class",
                "count": orphan_students,
            })
            print(f"  ⚠️  发现 {orphan_students} 个学生引用了不存在的 Class")

        # 4.2 Class.grade_id 引用的 Grade 是否存在
        orphan_classes = Class.query.filter(
            Class.is_active == True,
            ~Class.grade_id.in_(db.session.query(Grade.id))
        ).count()
        if orphan_classes > 0:
            issues.append({
                "type": "Class.grade_id 引用不存在的 Grade",
                "count": orphan_classes,
            })
            print(f"  ⚠️  发现 {orphan_classes} 个班级引用了不存在的 Grade")

        # 4.3 User.student_id 引用的 Student 是否存在（对 parent/student 角色）
        # 注意：User 模型可能没有 student_id 字段，需要根据模型定义调整
        # 暂时跳过此检查
        print("  ⚠️  跳过 User.student_id 检查（需要根据实际模型调整）")
        
        if issues:
            all_pass = False
            print(f"\n  🔴 数据一致性检查未通过：发现 {len(issues)} 个问题")
        else:
            print(f"\n  🟢 数据一致性检查通过：无数据不一致")

        report["data_consistency"] = {
            "status": "PASS" if not issues else "FAIL",
            "issues": issues,
        }
        print()

        # ── 5. 数学模型输入数据质量检查 ──
        print("🔍 5. 检查数学模型输入数据质量...")
        issues = []

        # 5.1 检查是否有足够的历史成绩数据（用于成绩预测）
        exams = Exam.query.count()
        if exams < 2:
            issues.append({
                "model": "成绩预测",
                "issue": "考试次数不足（需要至少2次考试）",
                "current": exams,
                "required": 2,
            })
            print(f"  ⚠️  考试次数不足：当前 {exams} 次，建议至少 2 次")
        else:
            print(f"  ✓ 考试次数充足：当前 {exams} 次")

        # 5.2 检查是否有足够的心理健康评估数据（用于心理风险预测）
        mh_count = MentalHealthAssessment.query.count()
        if mh_count < 10:
            issues.append({
                "model": "心理风险预测",
                "issue": "心理健康评估记录不足（建议至少10条）",
                "current": mh_count,
                "recommended": 10,
            })
            print(f"  ⚠️  心理健康评估记录不足：当前 {mh_count} 条，建议至少 10 条")
        else:
            print(f"  ✓ 心理健康评估记录充足：当前 {mh_count} 条")

        # 5.3 检查是否有足够的违纪记录（用于违纪预测）
        disc_count = DisciplineRecord.query.count()
        if disc_count < 10:
            issues.append({
                "model": "违纪预测",
                "issue": "违纪记录不足（建议至少10条）",
                "current": disc_count,
                "recommended": 10,
            })
            print(f"  ⚠️  违纪记录不足：当前 {disc_count} 条，建议至少 10 条")
        else:
            print(f"  ✓ 违纪记录充足：当前 {disc_count} 条")

        # 5.4 检查是否有足够的考勤数据（用于考勤预测）
        att_count = Attendance.query.count()
        if att_count < 30:
            issues.append({
                "model": "考勤预测",
                "issue": "考勤记录不足（建议至少30条）",
                "current": att_count,
                "recommended": 30,
            })
            print(f"  ⚠️  考勤记录不足：当前 {att_count} 条，建议至少 30 条")
        else:
            print(f"  ✓ 考勤记录充足：当前 {att_count} 条")

        # 5.5 检查是否有足够的综合素质评分数据（用于综合素质预测）
        quality_count = QualityScore.query.count()
        if quality_count < 10:
            issues.append({
                "model": "综合素质预测",
                "issue": "综合素质评分记录不足（建议至少10条）",
                "current": quality_count,
                "recommended": 10,
            })
            print(f"  ⚠️  综合素质评分记录不足：当前 {quality_count} 条，建议至少 10 条")
        else:
            print(f"  ✓ 综合素质评分记录充足：当前 {quality_count} 条")

        if issues:
            all_pass = False
            print(f"\n  🟡 数学模型数据质量检查未通过：发现 {len(issues)} 个问题")
        else:
            print(f"\n  🟢 数学模型数据质量检查通过：数据充足")

        report["ml_data_quality"] = {
            "status": "PASS" if not issues else "WARN",
            "issues": issues,
        }
        print()

        # ── 6. 生成报告 ──
        print("=" * 60)
        print("📝 生成巡检报告...")
        print("=" * 60)
        print()

        lines = []
        lines.append("# 德育管理平台自动化巡检报告")
        lines.append("")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("## 巡检结果摘要")
        lines.append("")
        lines.append(f"总体状态: {'🟢 全部通过' if all_pass else '⚠️  存在问题，请检查详情'}")
        lines.append("")
        lines.append("| 检查项 | 状态 | 详情 |")
        lines.append("| --- | --- | --- |")

        for key, label in [
            ("orphan_records", "1. 孤儿数据检查"),
            ("abnormal_nulls", "2. 异常空值检查"),
            ("permission_anomalies", "3. 权限异常检查"),
            ("data_consistency", "4. 数据一致性检查"),
            ("ml_data_quality", "5. 数学模型数据质量检查"),
        ]:
            if key not in report:
                continue
            
            data = report[key]
            status_emoji = {
                "PASS": "🟢",
                "WARN": "🟡",
                "FAIL": "🔴",
                "ERROR": "🔴",
                "SKIP": "⚪",
            }.get(data["status"], "⚪")
            
            detail = ""
            if key == "orphan_records":
                detail = f"孤儿记录数: {data['total_orphans']}"
            elif key == "abnormal_nulls":
                detail = f"问题数: {len(data['issues'])}" if data["issues"] else "无异常"
            elif key == "permission_anomalies":
                if data["status"] == "SKIP":
                    detail = data.get("reason", "")
                else:
                    detail = f"异常用户数: {len(data.get('anomalies', []))}"
            elif key == "data_consistency":
                detail = f"问题数: {len(data['issues'])}" if data["issues"] else "无不一致"
            elif key == "ml_data_quality":
                detail = f"问题数: {len(data['issues'])}" if data["issues"] else "数据充足"
            
            lines.append(f"| {label} | {status_emoji} {data['status']} | {detail} |")

        lines.append("")
        lines.append("## 详细报告")
        lines.append("")

        # 详细报告...
        for key, label in [
            ("orphan_records", "1. 孤儿数据检查"),
            ("abnormal_nulls", "2. 异常空值检查"),
            ("permission_anomalies", "3. 权限异常检查"),
            ("data_consistency", "4. 数据一致性检查"),
            ("ml_data_quality", "5. 数学模型数据质量检查"),
        ]:
            if key not in report:
                continue
            
            data = report[key]
            lines.append(f"### {label}")
            lines.append("")
            lines.append(f"状态: {data['status']}")
            lines.append("")
            
            if key == "orphan_records" and data.get("details"):
                lines.append(f"总孤儿记录数: {data['total_orphans']}")
                lines.append("")
                for item in data["details"]:
                    lines.append(f"- **{item['table']}.{item['foreign_key']}**: {item['orphan_count']} 条")
                lines.append("")
            
            elif key == "abnormal_nulls" and data.get("issues"):
                for item in data["issues"]:
                    lines.append(f"- **{item['table']}.{item['column']}** ({item['issue']})")
                    lines.append(f"  - 数量: {item['count']}")
                    lines.append(f"  - 占比: {item['percentage']}%")
                    lines.append("")
            
            elif key == "permission_anomalies":
                if data["status"] == "SKIP":
                    lines.append(f"原因: {data.get('reason', '')}")
                    lines.append("")
                elif data.get("anomalies"):
                    for item in data["anomalies"]:
                        lines.append(f"- **用户ID {item['user_id']}**: {item['attempt_count']} 次越权尝试")
                    lines.append("")
            
            elif key == "data_consistency" and data.get("issues"):
                for item in data["issues"]:
                    lines.append(f"- **{item['type']}**: {item['count']} 条")
                lines.append("")
            
            elif key == "ml_data_quality" and data.get("issues"):
                for item in data["issues"]:
                    lines.append(f"- **{item['model']}**")
                    lines.append(f"  - 问题: {item['issue']}")
                    lines.append(f"  - 当前: {item['current']}")
                    lines.append(f"  - 建议: {item.get('required', item.get('recommended', 'N/A'))}")
                    lines.append("")

        # 修复建议
        lines.append("## 修复建议")
        lines.append("")
        if not all_pass:
            lines.append("### 🔴 必须立即修复")
            lines.append("")
            if report.get("orphan_records", {}).get("status") == "FAIL":
                lines.append("1. **孤儿数据**: 运行 `python3 scripts/data_consistency_check.py` 自动修复或手动删除孤儿记录")
            if report.get("data_consistency", {}).get("status") == "FAIL":
                lines.append("2. **数据一致性**: 检查数据录入逻辑，确保外键引用存在")
            if report.get("permission_anomalies", {}).get("status") == "FAIL":
                lines.append("3. **权限异常**: 检查日志，封禁恶意IP或用户")
            lines.append("")
            
            if report.get("abnormal_nulls", {}).get("status") == "WARN":
                lines.append("### 🟡 建议优化")
                lines.append("")
                lines.append("1. **异常空值**: 检查数据导入逻辑，确保必填字段不为空")
                lines.append("2. **ML数据质量**: 增加数据录入，提高数学模型预测精度")
                lines.append("")
        else:
            lines.append("✅ 所有检查均通过，系统运行正常！")
            lines.append("")

        lines.append("### 📞 联系支持")
        lines.append("")
        lines.append("如有问题，请联系系统管理员。")
        lines.append("")

        report_md = "\n".join(lines)

        # 保存报告到文件
        output_path = project_root / f"logs/audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_md)

        print(f"📄 报告已保存到: {output_path}")
        print()
        print("=" * 60)
        print("📊 巡检报告摘要")
        print("=" * 60)
        print()
        print(report_md[:2000])  # 打印前2000字符
        print()
        print("=" * 60)

        # 返回退出码（用于 crontab）
        sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
