"""蓝图集中注册 — 新增蓝图只需在此文件加一行"""
from blueprints.auth import auth_bp
from blueprints.ms import ms_bp
from blueprints.grade import grade_bp
from blueprints.class_ import class_bp
from blueprints.wings import wings_bp
from blueprints.common import common_bp
from blueprints.survey import survey_bp
from blueprints.api_miniapp import miniapp_bp
from blueprints.notices import notices_bp
from blueprints.backup import backup_bp
from blueprints.ai_comment import ai_comment_bp
from blueprints.parent_meeting import parent_meeting_bp
from blueprints.scores import scores_bp
from blueprints.home_visit import home_visit_bp
from blueprints.tags import tags_bp
from blueprints.workload import workload_bp
from blueprints.bigscreen import bigscreen_bp
from blueprints.audit import audit_bp
from blueprints.export_summary import export_summary_bp
from blueprints.parent_portal import parent_portal_bp
from blueprints.quality import quality_bp
from blueprints.activity import activity_bp
from blueprints.attendance_stats import attendance_stats_bp
from blueprints.message_templates import message_templates_bp
from blueprints.report_generator import report_generator_bp
from blueprints.search import search_bp
from blueprints.system_config import system_config_bp
from blueprints.semester_archive import semester_archive_bp
from blueprints.ai_analysis import ai_analysis_bp
from blueprints.mental_health import mental_health_bp
from blueprints.communication import communication_bp
from blueprints.cockpit import cockpit_bp
from blueprints.student_profile import student_profile_bp
from blueprints.ml_models import ml_models_bp
from blueprints.growth_report import growth_bp
from blueprints.comparison import comparison_bp
from blueprints.ai_inference import bp as ai_inference_bp
from blueprints.markov import bp as markov_bp
from blueprints.fission import bp as fission_bp
from blueprints.causal import causal_bp
from blueprints.ms_flag_report import ms_flag_report_bp
from blueprints.ai_prescription import ai_prescription_bp
from blueprints.report_pdf import report_pdf_bp
from blueprints.dashboard_teacher import dashboard_teacher_bp

# ── 所有蓝图注册表 ──
# 格式: (blueprint, url_prefix, 说明)
BLUEPRINTS = [
    (auth_bp,      "",           "认证模块 /login /logout /accounts"),
    (ms_bp,        "/ms",        "德育处工作台 — 规则配置/任务下发/问题学生建档/全校总览"),
    (grade_bp,     "/grade",     "年级组工作台 — 接收任务/分配班主任/年级数据/审批"),
    (class_bp,     "/class",     "班主任工作台 — 本班纪律/考勤/评分/重点关注/通知"),
    (wings_bp,     "/wings",     "五翼→素质兼容重定向（Phase 3 合流，仅302跳转）"),
    (common_bp,    "/common",    "公共模块 — 消息中心/系统公告/文件上传"),
    (survey_bp,    "/survey",    "问卷与心理 — 心理筛查/家长问卷"),
    (miniapp_bp,   "/api/v1",    "小程序专用API"),
    (notices_bp,   "/notices",   "通知公告 — 发布通知/回执追踪"),
    (backup_bp,    "/backup",    "数据备份 — 备份/恢复/下载/删除"),
    (ai_comment_bp, "/ai-comment", "AI评语引擎 — 期末评语(正式+AI生成)/增值评价(隐形好学生+温暖评语)"),
    (parent_meeting_bp, "/parent-meeting", "家长会 — 创建/签到/统计/批量签到"),
    (scores_bp,    "/scores",     "成绩管理 — 考试/科目/成绩录入/排名/分析"),
    (home_visit_bp, "/home-visits", "家访记录 — 记录/筛选/导出"),
    (tags_bp,      "/tags",       "学生标签 — 标签管理/批量操作"),
    (workload_bp,  "/workload",   "教师工作量 — 统计/图表/导出"),
    (bigscreen_bp, "/bigscreen",  "数据大屏 — 全校德育数据可视化"),
    (audit_bp,     "/audit",      "审计日志 — 操作记录/筛选/追溯"),
    (export_summary_bp, "/export-summary", "导出汇总 — 各模块Excel一键导出"),
    (parent_portal_bp, "/parent", "家长端门户 — 查看孩子考勤/违纪/成绩/通知/评语"),
    (quality_bp,     "/quality",  "综合素质评价 — 指标管理/多角色评分/五维报告"),
    (activity_bp,    "/activity", "活动管理 — 创建/报名/签到/统计（德育处/年级/班主任/学生/家长）"),
    (attendance_stats_bp, "/attendance-stats", "考勤统计看板 — 仪表盘/班级对比/每日趋势/异常预警/学生详情"),
    (message_templates_bp,  "/message-templates",  "消息模板系统 — 模板CRUD/变量替换/预览发送"),
    (report_generator_bp, "/reports", "报表自动生成 — 使用openpyxl生成Excel报表"),
    (search_bp,    "/search",   "全局搜索 — 跨表搜索学生/违纪/通知/消息/活动"),
    (system_config_bp, "/system", "系统配置 — 学期管理/参数配置（德育处/年级组长）"),
    (semester_archive_bp, "/archive", "学期归档 — 学期数据快照/查看/恢复/对比"),
    (ai_analysis_bp, "/ai-analysis", "AI辅助分析 — 学生行为预测/风险预警/趋势分析"),
    (mental_health_bp, "/mental-health", "心理健康评估 — 问卷/评估/预警/干预"),
    (communication_bp, "/communication", "家校沟通追踪 — 统计/分析/提醒"),
    (cockpit_bp,  "/cockpit",  "数据驾驶舱 — 全景仪表盘/成绩/德育/考勤/导出"),
    (student_profile_bp, "/student-profile", "学生画像 — 统一档案页/多维聚合/时间轴/手记/Chart.js趋势"),
    (ml_models_bp, "/ml", "ML数学模型 — 成绩预测/心理风险/违纪预测/综合素质预测"),
    (growth_bp, "/growth", "综合成长报告 — 6维度数据整合/周报月报/PDF导出"),
    (comparison_bp, "/comparison", "班级/年级对比分析 — 多维度对比/图表可视化"),
    (ai_inference_bp, "/ai-api", "AI 线上推理 — 学生风险实时预测 API"),
    (markov_bp,      "/api/markov", "数学学力事件视界 — Markov链状态转移/教学熔断预警"),
    (fission_bp,     "/api/fission", "群体违纪链式核裂变溯源引擎"),
    (causal_bp,      "/causal",      "因果链诊断 — 成绩下滑跨表归因/AI干预方案"),
    (ms_flag_report_bp, "/ms/leaderboard", "流动红旗归档 — 物理快照/趋势分析/历史回溯"),
    (ai_prescription_bp, "/ai-prescription", "AI德育大秘 — 班级月度德育处方/考前心理安抚话术"),
    (report_pdf_bp, "/report-pdf", "德育报告单PDF — 单生报告(评语+成绩走势+五维雷达)/班级批量导出"),
    (dashboard_teacher_bp, "/teacher", "班主任四维工作台 — 学业趋势/纪律红黄牌/考勤预警/心理风险雷达"),
]


def register_all(app):
    """一键注册所有蓝图"""
    for bp, prefix, _desc in BLUEPRINTS:
        app.register_blueprint(bp, url_prefix=prefix)

    # ── 启动时打印所有路由（调试用） ──
    print("\n" + "=" * 70)
    print("  梨江中学德育管理平台 · 已注册蓝图")
    print("=" * 70)
    for bp, prefix, desc in BLUEPRINTS:
        print(f"  {prefix:>12s}  →  {desc}")
    print("=" * 70)
    print(f"  共 {len(BLUEPRINTS)} 个蓝图\n")
