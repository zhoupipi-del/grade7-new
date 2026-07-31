"""
modules/reports/schemas.py — Pydantic 请求/响应模型

双轨架构:
  PDF异步轨: ExportMoralReportRequest + TaskAcceptedResponse + TaskStatusResponse (原有)
  RDI白皮书轨: RiskStudentSummary + SchoolWideReportResponse + ClassTeacherReportResponse (新增)
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# PDF 异步轨 — 原有 Schema (不动)
# ═══════════════════════════════════════════════════════════════

class ExportMoralReportRequest(BaseModel):
    """触发德育报告导出请求"""
    class_id: int = Field(..., ge=1, description="班级 ID")
    semester: Optional[str] = Field(None, description="学期标识，如 2025-2026-2")
    report_type: str = Field("class_moral", description="报告类型: class_moral / student_individual")
    student_id: Optional[int] = Field(None, ge=1, description="指定学生 ID（student_individual 时必填）")


class TaskAcceptedResponse(BaseModel):
    """202 Accepted — 任务已提交"""
    task_id: str
    status: str = "PENDING"
    message: str = "报告生成任务已提交，请持 task_id 轮询状态"


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    state: str  # PENDING / PROGRESS / SUCCESS / FAILURE
    progress: Optional[int] = Field(None, ge=0, le=100, description="进度百分比 0-100")
    status_text: Optional[str] = Field(None, description="当前步骤描述")
    result: Optional[Dict[str, Any]] = Field(None, description="成功时返回 {filename, download_url, ...}")
    error: Optional[str] = Field(None, description="失败时的错误信息")


class ExportGradeReportRequest(BaseModel):
    """触发全年级德育报告批量导出请求"""
    grade_id: int = Field(..., ge=1, description="年级 ID")
    semester: Optional[str] = Field(None, description="学期标识，如 2025-2026-2")
    include_classes: Optional[list[int]] = Field(None, description="指定班级 ID 列表（为空则导出全年级）")


class GradeTaskAcceptedResponse(BaseModel):
    """202 Accepted — 全年级批量导出任务已提交"""
    task_ids: list[str] = Field(..., description="所有班级任务 ID 列表")
    total_classes: int = Field(..., description="总班级数")
    status: str = "PENDING"
    message: str = "全年级报告生成任务已提交，请持 task_ids 轮询状态"


# ═══════════════════════════════════════════════════════════════
# RDI 白皮书轨 — BOSS 亲定数据契约 (新增)
# ═══════════════════════════════════════════════════════════════

class RiskStudentSummary(BaseModel):
    """高危学生花名册条目 — 四维 breakdown + AI 处方摘要"""
    student_id: int = Field(..., description="学生 ID")
    student_name: str = Field(..., description="学生姓名")
    class_name: str = Field(..., description="班级名称")
    current_rdi: float = Field(..., description="当前 RDI 综合风险指数")
    risk_level: str = Field(..., description="风险层级: red_intervention / yellow_attention / green_normal")
    breakdown: Dict[str, float] = Field(
        ..., description="四维偏离分解: {behavior, attendance, score, psych}"
    )
    latest_warning_reason: str = Field("", description="最近一次预警原因")
    ai_prescription_snippet: str = Field("", description="AI 处方摘要（前200字）")


class SchoolWideReportResponse(BaseModel):
    """全校德育/风险态势白皮书 — 四大维度宏观热力图"""
    generated_at: str = Field(..., description="报告生成时间 ISO8601")
    total_students_scanned: int = Field(..., description="全校扫描学生总数")
    risk_distribution: Dict[str, int] = Field(
        ..., description="风险分布: {red_intervention, yellow_attention, green_normal}"
    )
    department_heat_ranking: List[Dict[str, Any]] = Field(
        ..., description="各班级风险均值排行 [{class_id, class_name, grade_name, avg_rdi, warned_count}]"
    )
    top_critical_list: List[RiskStudentSummary] = Field(
        ..., description="高危学生花名册（intervention 级）"
    )


class HighRiskExportResponse(BaseModel):
    """高危学生花名册导出响应"""
    generated_at: str = Field(..., description="生成时间")
    total_high_risk: int = Field(..., description="高危学生总数")
    risk_levels_filtered: List[str] = Field(..., description="筛选的风险等级")
    students: List[RiskStudentSummary] = Field(..., description="高危学生列表")
    export_format: str = Field("json", description="导出格式: json / excel / pdf")


class ClassTeacherReportResponse(BaseModel):
    """班主任一键班级报告 — 本班德育工作图表数据"""
    generated_at: str = Field(..., description="生成时间")
    class_id: int = Field(..., description="班级 ID")
    class_name: str = Field(..., description="班级名称")
    student_count: int = Field(..., description="本班学生总数")
    risk_distribution: Dict[str, int] = Field(
        ..., description="本班风险分布: {red_intervention, yellow_attention, green_normal}"
    )
    high_risk_students: List[RiskStudentSummary] = Field(
        ..., description="本班高危+关注学生清单"
    )
    attendance_summary: Dict[str, Any] = Field(
        ..., description="考勤概览: {attendance_rate, present_count, late_count, absent_count, ...}"
    )
    discipline_summary: Dict[str, Any] = Field(
        ..., description="违纪概览: {total_incidents, involved_students, total_penalty_points, ...}"
    )
    academic_summary: Dict[str, Any] = Field(
        ..., description="学业概览: {covered_students, avg_std_value, below_avg_count, ...}"
    )
