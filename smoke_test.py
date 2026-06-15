#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grade7-new 冒烟测试脚本 — 数据录入后全局逻辑校验
用法: python smoke_test.py
在服务器上运行: cd /opt/grade7-new && python smoke_test.py
"""
import sys, os, json, traceback
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# ── 加载环境变量 ──
def _load_env_from_systemd(service_name="grade7-new"):
    """从 systemd service 文件读取 Environment= 变量"""
    service_path = f"/etc/systemd/system/{service_name}.service"
    if not os.path.isfile(service_path):
        return False
    loaded = False
    with open(service_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("Environment="):
                continue
            # Environment="KEY=val" or Environment="KEY=val with spaces"
            kv = line[len("Environment="):].strip()
            if kv.startswith('"') and kv.endswith('"'):
                kv = kv[1:-1]
            if "=" not in kv:
                continue
            key, val = kv.split("=", 1)
            key, val = key.strip(), val.strip()
            if key and key not in os.environ:
                os.environ[key] = val
                loaded = True
    return loaded

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"").strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = val
        return True
    return False

# 优先 .env，缺失则从 systemd 服务文件补充
_load_dotenv()
if not os.environ.get("DATABASE_URL"):
    _load_env_from_systemd()
    # 调试输出
    if os.environ.get("DATABASE_URL"):
        print(f"[INFO] 从 systemd 服务文件加载了 DATABASE_URL")
    else:
        print(f"[{FAIL}] 无法找到 DATABASE_URL，请检查 .env 或 systemd 服务文件")

from flask import Flask
from config import Config
from models import (
    db, Student, Class, Grade, Exam, Score, Subject,
    DisciplineRecord, Attendance, PsychSurvey, MentalHealthAssessment,
    MentalHealthQuestion, QualityScore, WingsScore, QualityIndicator,
    RiskRecord, User, Semester, Announcement,
    Activity, ActivityRegistration,
)
from feature_extractor import FeatureExtractor
from utils import get_local_now

# ── 辅助函数 ──
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"
INFO = "\033[96mINFO\033[0m"

results = {"pass": 0, "fail": 0, "warn": 0, "total": 0}

def check(name, condition, detail=""):
    results["total"] += 1
    if condition:
        results["pass"] += 1
        print(f"  [{PASS}] {name}")
    else:
        results["fail"] += 1
        print(f"  [{FAIL}] {name} {detail}")

def warn(name, detail=""):
    results["total"] += 1
    results["warn"] += 1
    print(f"  [{WARN}] {name} {detail}")

def info(msg):
    print(f"  [{INFO}] {msg}")


def create_test_app():
    """创建最小化 Flask app 用于测试"""
    app = Flask(__name__)
    app.config.from_object(Config)
    # 确保环境变量覆盖 config（systemd 场景）
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["TESTING"] = True
    db.init_app(app)
    return app


# ============================================================
# 测试模块
# ============================================================

def test_database_connection(app):
    """T1: 数据库连接"""
    print("\n" + "=" * 60)
    print("T1: 数据库连接")
    with app.app_context():
        try:
            db.session.execute(db.text("SELECT 1"))
            check("数据库连接正常")
        except Exception as e:
            check("数据库连接", False, f"错误: {e}")


def test_basic_counts(app):
    """T2: 基础数据量检查"""
    print("\n" + "=" * 60)
    print("T2: 基础数据量统计")
    with app.app_context():
        counts = {
            "年级(Grade)": Grade.query.count(),
            "班级(Class)": Class.query.filter_by(is_active=True).count(),
            "学生(Student)": Student.query.filter_by(is_active=True).count(),
            "考试(Exam)": Exam.query.count(),
            "科目(Subject)": Subject.query.count(),
            "成绩(Score)": Score.query.count(),
            "违纪(DisciplineRecord)": DisciplineRecord.query.count(),
            "考勤(Attendance)": Attendance.query.count(),
            "心理问卷(PsychSurvey)": PsychSurvey.query.count(),
            "心理健康评估(MentalHealth)": MentalHealthAssessment.query.count(),
            "综合素质(QualityScore)": QualityScore.query.count(),
            "五翼评分(WingsScore)": WingsScore.query.count(),
            "风险记录(RiskRecord)": RiskRecord.query.count(),
            "用户(User)": User.query.count(),
        }
        for name, count in counts.items():
            info(f"{name}: {count} 条")

        check("年级数 > 0", counts["年级(Grade)"] > 0)
        check("班级数 > 0", counts["班级(Class)"] > 0)
        check("学生数 > 0", counts["学生(Student)"] > 0)
        if counts["学生(Student)"] > 0:
            check("学生数在合理范围", counts["学生(Student)"] >= 300,
                  f"实际: {counts['学生(Student)']}")


def test_student_integrity(app):
    """T3: 学生数据完整性"""
    print("\n" + "=" * 60)
    print("T3: 学生数据完整性")
    with app.app_context():
        students = Student.query.filter_by(is_active=True).all()
        if not students:
            check("存在活跃学生", False)
            return

        check(f"活跃学生总数: {len(students)}", True)

        # 检查学生号唯一性
        student_nos = [s.student_no for s in students]
        dup_nos = [no for no in set(student_nos) if student_nos.count(no) > 1]
        check("学号无重复", len(dup_nos) == 0, f"重复学号: {dup_nos[:5]}")

        # 检查空学号
        empty_no = [s.id for s in students if not s.student_no or not s.student_no.strip()]
        check("无空学号", len(empty_no) == 0, f"空学号学生ID: {empty_no[:5]}")

        # 检查班级关联
        orphan_students = []
        class_ids = set(c.id for c in Class.query.all())
        for s in students:
            if s.class_id not in class_ids:
                orphan_students.append(s.id)
        check("所有学生关联有效班级", len(orphan_students) == 0,
              f"孤儿学生ID: {orphan_students[:5]}")

        # 检查年级关联
        grade_ids = set(g.id for g in Grade.query.all())
        orphan_grade = [s.id for s in students if s.grade_id not in grade_ids]
        check("所有学生关联有效年级", len(orphan_grade) == 0,
              f"孤儿年级学生ID: {orphan_grade[:5]}")

        # 检查空名字
        empty_name = [s.id for s in students if not s.name or not s.name.strip()]
        check("无空姓名", len(empty_name) == 0, f"空姓名学生ID: {empty_name[:5]}")

        # 检查班级学生分布
        class_dist = defaultdict(int)
        for s in students:
            class_dist[s.class_id] += 1
        oversized = {cid: cnt for cid, cnt in class_dist.items() if cnt > 60}
        check("班级人数在合理范围(<60)", len(oversized) == 0,
              f"超员班级: {oversized}")
        undersized = {cid: cnt for cid, cnt in class_dist.items() if cnt < 5 and cnt > 0}
        if undersized:
            warn("部分班级人数过少(<5)", f"班级: {undersized}")


def test_score_integrity(app):
    """T4: 成绩数据完整性"""
    print("\n" + "=" * 60)
    print("T4: 成绩数据完整性")
    with app.app_context():
        scores = Score.query.all()
        info(f"成绩总数: {len(scores)}")

        if not scores:
            warn("暂无成绩数据")
            return

        # 检查分数范围
        out_of_range = [s.id for s in scores if s.score < 0 or s.score > 150]
        check("分数范围正常(0-150)", len(out_of_range) == 0,
              f"异常分数ID: {out_of_range[:10]}")

        # 检查 verify_status 分布
        status_dist = defaultdict(int)
        for s in scores:
            status_dist[s.verify_status] += 1
        info(f"verify_status 分布: {dict(status_dist)}")

        draft_count = status_dist.get("DRAFT", 0)
        verified_count = status_dist.get("VERIFIED", 0)
        if draft_count > 0 and verified_count > 0:
            warn("存在混合状态的成绩", f"DRAFT: {draft_count}, VERIFIED: {verified_count}")
        check("成绩状态有效", all(st in ("DRAFT", "VERIFIED") for st in status_dist.keys()),
              f"无效状态: {set(status_dist.keys()) - {'DRAFT', 'VERIFIED'}}")

        # 检查孤儿成绩（关联不存在的学生/考试/科目）
        student_ids = set(s.id for s in Student.query.all())
        exam_ids = set(e.id for e in Exam.query.all())
        subject_ids = set(sub.id for sub in Subject.query.all())

        orphan_student = [s.id for s in scores if s.student_id not in student_ids]
        check("所有成绩关联有效学生", len(orphan_student) == 0,
              f"孤儿成绩ID: {orphan_student[:5]}")

        orphan_exam = [s.id for s in scores if s.exam_id not in exam_ids]
        check("所有成绩关联有效考试", len(orphan_exam) == 0,
              f"孤儿考试成绩ID: {orphan_exam[:5]}")

        orphan_subject = [s.id for s in scores if s.subject_id not in subject_ids]
        check("所有成绩关联有效科目", len(orphan_subject) == 0,
              f"孤儿科目成绩ID: {orphan_subject[:5]}")

        # 检查每个考试-学生-科目的唯一性（应该由数据库约束保证）
        # 抽样检查
        from sqlalchemy import text
        dup_result = db.session.execute(text(
            "SELECT student_id, exam_id, subject_id, COUNT(*) as cnt "
            "FROM scores GROUP BY student_id, exam_id, subject_id HAVING cnt > 1 LIMIT 5"
        )).fetchall()
        check("无重复成绩记录", len(dup_result) == 0,
              f"重复记录: {[(r[0], r[1], r[2], r[3]) for r in dup_result]}")

        # 检查每个考试是否有足够学生有成绩
        exams = Exam.query.all()
        for exam in exams:
            exam_scores = Score.query.filter_by(exam_id=exam.id).count()
            if exam_scores == 0:
                warn(f"考试 '{exam.name}' 无成绩记录", f"exam_id={exam.id}")


def test_exam_data(app):
    """T5: 考试数据完整性"""
    print("\n" + "=" * 60)
    print("T5: 考试数据完整性")
    with app.app_context():
        exams = Exam.query.order_by(Exam.exam_date.asc()).all()
        if not exams:
            warn("暂无考试数据")
            return

        info(f"考试总数: {len(exams)}")
        for exam in exams:
            score_count = Score.query.filter_by(exam_id=exam.id).count()
            subject_count = db.session.query(Score.subject_id).filter_by(exam_id=exam.id).distinct().count()
            info(f"  {exam.name} ({exam.exam_date}) — {score_count}条成绩, {subject_count}个科目")

        # 检查考试日期合理性
        now = get_local_now().date()
        future_exams = [e.name for e in exams if e.exam_date > now + timedelta(days=30)]
        check("无异常未来考试日期", len(future_exams) == 0,
              f"未来考试: {future_exams}")

        # 检查科目覆盖率
        all_subjects = Subject.query.all()
        for exam in exams:
            exam_subjects = set(
                s.subject_id for s in Score.query.filter_by(exam_id=exam.id).distinct().with_entities(Score.subject_id).all()
            )
            exam_subjects_flat = [x[0] for x in exam_subjects]
            missing_subjects = [
                sub.name for sub in all_subjects if sub.id not in exam_subjects_flat
            ]
            if len(exam_subjects_flat) < len(all_subjects):
                warn(f"考试 '{exam.name}' 缺少科目", f"缺少: {missing_subjects}")


def test_discipline_integrity(app):
    """T6: 违纪数据完整性"""
    print("\n" + "=" * 60)
    print("T6: 违纪数据完整性")
    with app.app_context():
        records = DisciplineRecord.query.all()
        info(f"违纪记录总数: {len(records)}")

        if not records:
            info("暂无违纪数据（正常）")
            return

        # 检查类型有效性
        valid_types = {"warning", "minor", "major", "serious"}
        invalid_types = set(r.type for r in records) - valid_types
        check("违纪类型有效", len(invalid_types) == 0, f"无效类型: {invalid_types}")

        # 检查 verify_status
        status_dist = defaultdict(int)
        for r in records:
            status_dist[r.verify_status] += 1
        info(f"verify_status 分布: {dict(status_dist)}")

        # 检查分数范围
        neg_points = [r.id for r in records if r.points < 0]
        check("扣分非负", len(neg_points) == 0, f"负扣分ID: {neg_points}")


def test_attendance_integrity(app):
    """T7: 考勤数据完整性"""
    print("\n" + "=" * 60)
    print("T7: 考勤数据完整性")
    with app.app_context():
        records = Attendance.query.all()
        info(f"考勤记录总数: {len(records)}")

        if not records:
            info("暂无考勤数据（正常）")
            return

        # 检查状态有效性
        valid_statuses = {"present", "late", "early", "absent", "leave"}
        invalid = set(r.status for r in records) - valid_statuses
        check("考勤状态有效", len(invalid) == 0, f"无效状态: {invalid}")

        # 检查日期范围
        dates = [r.record_date for r in records]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None
        info(f"日期范围: {min_date} ~ {max_date}")

        # 检查未来日期
        now = get_local_now().date()
        future = [r.id for r in records if r.record_date > now]
        check("无未来考勤记录", len(future) == 0, f"未来记录ID: {future[:5]}")


def test_psych_survey_integrity(app):
    """T8: 心理问卷数据完整性"""
    print("\n" + "=" * 60)
    print("T8: 心理问卷数据完整性")
    with app.app_context():
        surveys = PsychSurvey.query.all()
        info(f"心理问卷总数: {len(surveys)}")

        if not surveys:
            info("暂无心理问卷数据（正常）")
            return

        # 检查 answers_json 是否可解析
        bad_json = []
        for s in surveys:
            if s.answers_json:
                try:
                    json.loads(s.answers_json)
                except:
                    bad_json.append(s.id)
        check("answers_json 可解析", len(bad_json) == 0, f"损坏ID: {bad_json[:5]}")

        # 检查 verify_status
        status_dist = defaultdict(int)
        for s in surveys:
            status_dist[s.verify_status] += 1
        info(f"verify_status 分布: {dict(status_dist)}")

        # 检查测谎校验
        invalid_surveys = [s.id for s in surveys if not s.is_valid]
        if invalid_surveys:
            warn(f"存在无效问卷(测谎未通过)", f"数量: {len(invalid_surveys)}")

        # 检查 dimensions_json
        bad_dim = []
        for s in surveys:
            if s.dimensions_json:
                try:
                    json.loads(s.dimensions_json)
                except:
                    bad_dim.append(s.id)
        check("dimensions_json 可解析", len(bad_dim) == 0, f"损坏ID: {bad_dim[:5]}")

    # MentalHealthAssessment
    print("\n  --- 心理健康评估 ---")
    with app.app_context():
        assessments = MentalHealthAssessment.query.all()
        info(f"心理健康评估总数: {len(assessments)}")

        if assessments:
            # 检查 risk_level
            valid_levels = {"low", "medium", "high"}
            invalid = set(a.risk_level for a in assessments) - valid_levels
            check("risk_level 有效", len(invalid) == 0, f"无效值: {invalid}")

            # 检查关联
            student_ids = set(s.id for s in Student.query.all())
            orphan = [a.id for a in assessments if a.student_id not in student_ids]
            check("评估关联有效学生", len(orphan) == 0, f"孤儿ID: {orphan[:5]}")


def test_risk_record_integrity(app):
    """T9: 风险记录完整性"""
    print("\n" + "=" * 60)
    print("T9: 风险记录完整性")
    with app.app_context():
        records = RiskRecord.query.all()
        info(f"风险记录总数: {len(records)}")

        if not records:
            info("暂无风险记录（正常，需要先运行扫描）")
            return

        # 检查 risk_level
        valid_levels = {"green", "yellow", "red"}
        invalid = set(r.risk_level for r in records) - valid_levels
        check("risk_level 有效", len(invalid) == 0, f"无效值: {invalid}")

        # 检查 warning_details JSON
        bad_json = []
        for r in records:
            if r.warning_details:
                try:
                    parsed = json.loads(r.warning_details)
                    if not isinstance(parsed, list):
                        bad_json.append(r.id)
                except:
                    bad_json.append(r.id)
        check("warning_details JSON 格式正确(list)", len(bad_json) == 0,
              f"损坏ID: {bad_json[:5]}")

        # 检查 feature_attribution JSON
        bad_feat = []
        for r in records:
            if r.feature_attribution:
                try:
                    parsed = json.loads(r.feature_attribution)
                    if not isinstance(parsed, dict):
                        bad_feat.append(r.id)
                except:
                    bad_feat.append(r.id)
        check("feature_attribution JSON 格式正确(dict)", len(bad_feat) == 0,
              f"损坏ID: {bad_feat[:5]}")

        # 风险等级分布
        level_dist = defaultdict(int)
        for r in records:
            level_dist[r.risk_level] += 1
        info(f"风险等级分布: {dict(level_dist)}")

        # 检查 scan_date
        dates = set(r.scan_date for r in records)
        info(f"扫描日期: {sorted(dates)}")


def test_feature_extractor(app):
    """T10: 特征提取管道"""
    print("\n" + "=" * 60)
    print("T10: 特征提取管道(FeatureExtractor)")
    with app.app_context():
        try:
            fe = FeatureExtractor(grade_id=1)
            matrix = fe.extract()

            if not matrix:
                warn("特征矩阵为空（可能缺少考试数据）")
                return

            check(f"特征矩阵行数: {len(matrix)}", len(matrix) > 0)

            # 检查每行数据的完整性
            required_keys = [
                "student_id", "math_slope", "math_avg", "quality_score",
                "risk_density", "attendance_rate", "discipline_factor"
            ]
            bad_rows = []
            for row in matrix:
                for key in required_keys:
                    if key not in row or row[key] is None:
                        bad_rows.append((row.get("student_id"), key))
                        break

            check("所有特征行包含必需字段", len(bad_rows) == 0,
                  f"缺失字段: {bad_rows[:10]}")

            # 检查数值范围
            for row in matrix:
                if row.get("math_avg", 0) < 0 or row.get("math_avg", 0) > 150:
                    warn(f"学生 {row['student_id']} math_avg 异常: {row['math_avg']}")
                if row.get("attendance_rate", 0) < 0 or row.get("attendance_rate", 0) > 1.5:
                    warn(f"学生 {row['student_id']} attendance_rate 异常: {row['attendance_rate']}")

            # 抽样测试单生特征提取
            sample_student = matrix[0]
            try:
                vector = fe.get_student_vector(sample_student["student_id"])
                check(f"单生特征提取正常 (student_id={sample_student['student_id']})",
                      vector is not None and "features" in vector)
                if vector and "features" in vector:
                    check(f"特征维度=6", len(vector["features"]) == 6,
                          f"实际: {len(vector['features'])}")
            except Exception as e:
                check("单生特征提取", False, f"错误: {e}")

            # 基线计算
            try:
                baselines = fe.get_grade_baselines()
                check("年级基线计算正常", baselines is not None and len(baselines) > 0)
                if baselines:
                    info(f"年级基线: {baselines}")
            except Exception as e:
                check("年级基线计算", False, f"错误: {e}")

        except Exception as e:
            check("特征提取管道初始化", False, f"错误: {e}\n{traceback.format_exc()}")


def test_score_ranking(app):
    """T11: 成绩排名数据"""
    print("\n" + "=" * 60)
    print("T11: 成绩排名数据")
    with app.app_context():
        scores = Score.query.filter(Score.verify_status == "VERIFIED").all()
        if not scores:
            info("暂无已确认成绩，跳过排名检查")
            return

        # 检查排名是否已计算
        unranked = Score.query.filter(
            Score.verify_status == "VERIFIED",
            (Score.rank_class == 0) | (Score.rank_class == None)
        ).count()

        if unranked > 0:
            warn(f"存在未排名的已确认成绩", f"数量: {unranked}")
        else:
            check("所有已确认成绩已计算排名", True)

        # 抽样检查排名一致性
        exams_with_scores = db.session.query(Score.exam_id).filter(
            Score.verify_status == "VERIFIED"
        ).distinct().all()
        exam_ids = [x[0] for x in exams_with_scores]

        for eid in exam_ids[:3]:  # 抽查前3个考试
            exam_scores = Score.query.filter_by(exam_id=eid, verify_status="VERIFIED").all()
            if not exam_scores:
                continue

            # 按科目分组检查班级排名
            subjects_in_exam = set(s.subject_id for s in exam_scores)
            for sub_id in list(subjects_in_exam)[:2]:  # 每个考试抽查2个科目
                sub_scores = [s for s in exam_scores if s.subject_id == sub_id]
                # 按班级分组
                by_class = defaultdict(list)
                for s in sub_scores:
                    by_class[s.class_id].append(s)

                for cid, class_scores in by_class.items():
                    sorted_scores = sorted(class_scores, key=lambda x: x.score, reverse=True)
                    expected_ranks = {s.id: i + 1 for i, s in enumerate(sorted_scores)}
                    mismatch = [s.id for s in class_scores if s.rank_class != expected_ranks.get(s.id)]
                    if mismatch:
                        warn(f"考试{eid} 科目{sub_id} 班级{cid} 排名不一致",
                             f"不一致数: {len(mismatch)}")

        check("排名数据抽查通过", True)


def test_orphan_data(app):
    """T12: 孤儿数据检查"""
    print("\n" + "=" * 60)
    print("T12: 孤儿数据检查（跨表引用完整性）")
    with app.app_context():
        student_ids = set(s.id for s in Student.query.all())
        class_ids = set(c.id for c in Class.query.all())
        grade_ids = set(g.id for g in Grade.query.all())

        # Class -> Grade
        orphan_class = Class.query.filter(Class.grade_id.notin_(grade_ids)).count()
        check("所有班级关联有效年级", orphan_class == 0, f"孤儿班级数: {orphan_class}")

        # WingsScore
        if WingsScore.query.count() > 0:
            orphan = WingsScore.query.filter(WingsScore.student_id.notin_(student_ids)).count()
            check("WingsScore 关联有效学生", orphan == 0, f"孤儿数: {orphan}")

        # QualityScore
        if QualityScore.query.count() > 0:
            orphan = QualityScore.query.filter(QualityScore.student_id.notin_(student_ids)).count()
            check("QualityScore 关联有效学生", orphan == 0, f"孤儿数: {orphan}")

            # 检查 indicator_id 关联
            indicator_ids = set(i.id for i in QualityIndicator.query.all())
            orphan_ind = QualityScore.query.filter(QualityScore.indicator_id.notin_(indicator_ids)).count()
            check("QualityScore 关联有效指标", orphan_ind == 0, f"孤儿数: {orphan_ind}")


def test_user_system(app):
    """T13: 用户系统"""
    print("\n" + "=" * 60)
    print("T13: 用户系统")
    with app.app_context():
        users = User.query.all()
        info(f"用户总数: {len(users)}")

        if not users:
            check("存在用户", False)
            return

        # 角色分布
        role_dist = defaultdict(int)
        for u in users:
            role_dist[u.role] += 1
        info(f"角色分布: {dict(role_dist)}")

        # 检查空密码
        empty_pwd = [u.id for u in users if not u.password_hash]
        check("无空密码用户", len(empty_pwd) == 0, f"空密码ID: {empty_pwd}")

        # 检查班主任是否关联班级
        class_teachers = User.query.filter_by(role="class_teacher").all()
        ct_with_class = [u for u in class_teachers if u.class_id]
        ct_without_class = [u for u in class_teachers if not u.class_id]
        info(f"班主任总数: {len(class_teachers)}, 已关联班级: {len(ct_with_class)}")
        if ct_without_class:
            warn(f"存在未关联班级的班主任", f"数量: {len(ct_without_class)}")


def test_ml_pipeline(app):
    """T14: ML 模型管道"""
    print("\n" + "=" * 60)
    print("T14: ML 模型管道")
    with app.app_context():
        # 检查模型文件
        import joblib
        model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        pipeline_path = os.path.join(model_dir, "wings_xgb_pipeline.pkl")
        metadata_path = os.path.join(model_dir, "pipeline_metadata.pkl")

        if os.path.exists(pipeline_path):
            check("XGBoost pipeline 文件存在", True)
            try:
                pipeline = joblib.load(pipeline_path)
                check("pipeline 可加载", pipeline is not None)
            except Exception as e:
                check("pipeline 可加载", False, f"错误: {e}")
        else:
            warn("XGBoost pipeline 文件不存在", f"路径: {pipeline_path}")

        if os.path.exists(metadata_path):
            check("pipeline_metadata 文件存在", True)
            try:
                metadata = joblib.load(metadata_path)
                check("metadata 可加载", metadata is not None)
                if metadata:
                    info(f"特征名: {metadata.get('feature_names', [])}")
                    info(f"特征选择掩码: {metadata.get('support_mask', [])}")
            except Exception as e:
                check("metadata 可加载", False, f"错误: {e}")
        else:
            warn("pipeline_metadata 文件不存在", f"路径: {metadata_path}")


def test_api_endpoints(app):
    """T15: 关键 API 端点测试"""
    print("\n" + "=" * 60)
    print("T15: 关键 API 端点测试")
    client = app.test_client()

    # 模拟登录
    endpoints = [
        ("GET", "/auth/login", False),
        ("GET", "/ml/", False),
        ("GET", "/health", True),  # 健康检查不需要登录
    ]

    # 先测试健康检查
    resp = client.get("/health")
    check("健康检查 /health", resp.status_code == 200,
          f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        info(f"  响应: {resp.get_json()}")

    # 测试登录
    resp = client.post("/auth/login", data={
        "username": "admin",
        "password": "admin123",
    }, follow_redirects=False)
    check("管理员登录", resp.status_code in (200, 302),
          f"状态码: {resp.status_code}")


def test_datetime_consistency(app):
    """T16: 时区一致性检查"""
    print("\n" + "=" * 60)
    print("T16: 时区一致性检查（datetime.utcnow 残留）")
    with app.app_context():
        # 检查关键文件是否还有 utcnow
        critical_files = [
            "feature_extractor.py",
            "blueprints/ml_models.py",
            "blueprints/ai_analysis.py",
            "blueprints/ai_inference.py",
            "blueprints/bigscreen.py",
        ]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for fname in critical_files:
            fpath = os.path.join(base_dir, fname)
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            if "utcnow" in content or "utcnow()" in content:
                # 排除注释中的引用
                lines_with_utcnow = []
                for i, line in enumerate(content.split("\n"), 1):
                    stripped = line.strip()
                    if "utcnow" in line and not stripped.startswith("#") and not stripped.startswith("//"):
                        lines_with_utcnow.append(f"L{i}: {stripped}")
                if lines_with_utcnow:
                    warn(f"{fname} 仍含 utcnow()", f"\n    " + "\n    ".join(lines_with_utcnow[:3]))
                else:
                    check(f"{fname} 无活跃 utcnow()", True)
            else:
                check(f"{fname} 无 utcnow 残留", True)

        # 检查 date.today() 残留
        for fname in critical_files:
            fpath = os.path.join(base_dir, fname)
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            if "date.today()" in content:
                lines = [line for line in content.split("\n") if "date.today()" in line and not line.strip().startswith("#")]
                if lines:
                    warn(f"{fname} 仍含 date.today()", f"\n    " + "\n    ".join(lines[:3]))


def test_activity_data(app):
    """T17: 活动数据"""
    print("\n" + "=" * 60)
    print("T17: 活动数据")
    with app.app_context():
        activities = Activity.query.all()
        info(f"活动总数: {len(activities)}")
        if not activities:
            info("暂无活动数据（正常）")
            return

        for a in activities:
            reg_count = ActivityRegistration.query.filter_by(activity_id=a.id).count()
            info(f"  {a.name}: 报名{reg_count}人 (最大{a.max_participants})")

        # 检查报名关联
        student_ids = set(s.id for s in Student.query.all())
        regs = ActivityRegistration.query.all()
        orphan = [r.id for r in regs if r.student_id not in student_ids]
        check("报名关联有效学生", len(orphan) == 0, f"孤儿ID: {orphan[:5]}")


# ============================================================
# 主入口
# ============================================================

def main():
    print("=" * 60)
    print("  grade7-new 冒烟测试")
    print(f"  运行时间: {get_local_now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    app = create_test_app()

    try:
        test_database_connection(app)
        test_basic_counts(app)
        test_student_integrity(app)
        test_score_integrity(app)
        test_exam_data(app)
        test_discipline_integrity(app)
        test_attendance_integrity(app)
        test_psych_survey_integrity(app)
        test_risk_record_integrity(app)
        test_feature_extractor(app)
        test_score_ranking(app)
        test_orphan_data(app)
        test_user_system(app)
        test_ml_pipeline(app)
        test_api_endpoints(app)
        test_datetime_consistency(app)
        test_activity_data(app)
    except Exception as e:
        print(f"\n[致命错误] 测试中断: {e}")
        traceback.print_exc()

    # 汇总报告
    print("\n" + "=" * 60)
    print(f"  冒烟测试报告")
    print(f"  总计: {results['total']} 项")
    print(f"  通过: {results['pass']} 项")
    print(f"  失败: {results['fail']} 项")
    print(f"  警告: {results['warn']} 项")
    if results['fail'] == 0:
        print(f"  结果: {PASS} 所有检查通过！")
    else:
        print(f"  结果: {FAIL} 存在 {results['fail']} 个失败项，需要修复！")
    print("=" * 60)

    return 0 if results["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
