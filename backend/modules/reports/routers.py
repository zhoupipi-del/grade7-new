"""
modules/reports/routers.py — 报告引擎 HTTP 双轨分流

PDF异步轨 (原有):
  端点 1: POST /export/moral-report → 202 Accepted + task_id
  端点 2: GET  /tasks/{task_id}     → 任务状态轮询
  端点 3: POST /export/grade-report → 全年级批量导出
  端点 4: GET  /batch-export        → 批量导出前端工作台

RDI白皮书轨 (新增):
  端点 5: GET  /rdi-summary         → 全校德育/风险态势白皮书
  端点 6: POST /export/high-risk    → 高危学生花名册导出
  端点 7: GET  /class-report/{cid}  → 班主任一键班级报告
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, status, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from celery.result import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from core.routers import get_current_user, get_db, require_role
from core.models import User, UserRole
from modules.reports.schemas import (
    ExportMoralReportRequest,
    TaskAcceptedResponse,
    TaskStatusResponse,
    ExportGradeReportRequest,
    GradeTaskAcceptedResponse,
    SchoolWideReportResponse,
    HighRiskExportResponse,
    ClassTeacherReportResponse,
)
from modules.reports.tasks import generate_class_moral_report, _get_sync_session
from modules.reports.services import (
    get_school_wide_rdi_summary,
    get_high_risk_students,
    get_class_teacher_report,
)

router = APIRouter(tags=["Reports 德育报告引擎"])

# 🛡️ 核心修复：基于当前文件位置，动态逆向推导 backend 绝对根目录
# 当前路径: backend/modules/reports/routers.py
# 向上跳两级到达 backend 根目录
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent.parent
HTML_FILE_PATH = BACKEND_ROOT / "static" / "ms" / "batch_export.html"


@router.post(
    "/export/moral-report",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskAcceptedResponse,
)
async def export_moral_report(
    body: ExportMoralReportRequest,
    current_user: User = Depends(get_current_user),
):
    """
    【端点 1】触发异步导出

    派发任务到 Redis 队列，立刻返回 task_id。
    耗时仅 2ms，0 线程阻塞 — 彻底终结 502 超时死结！
    """
    task = generate_class_moral_report.delay(
        school_id=current_user.school_id,
        class_id=body.class_id,
        semester=body.semester or _default_semester(),
        created_by=current_user.id,
    )

    return TaskAcceptedResponse(
        task_id=task.id,
        status="PENDING",
        message="德育报告异步生成任务已提交，请持 task_id 轮询状态",
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    【端点 2】状态雷达

    供前端定时轮询（如每 2 秒一次），获取当前百分比进度或最终下载链接。

    状态:
      - PENDING:  任务排队中
      - PROGRESS: 生成中 → {progress: 0-100, status_text: "正在..."}
      - SUCCESS:  完成   → {result: {filename, download_url, file_size_kb}}
      - FAILURE:  失败   → {error: "错误信息"}
    """
    task_result = AsyncResult(task_id, app=None)

    response = {
        "task_id": task_id,
        "state": task_result.state,
    }

    if task_result.state == "PROGRESS" and task_result.info:
        info = task_result.info if isinstance(task_result.info, dict) else {}
        response["progress"] = info.get("progress", 0)
        response["status_text"] = info.get("status_text", "")

    elif task_result.state == "SUCCESS":
        result = task_result.result if isinstance(task_result.result, dict) else {}
        response["progress"] = 100
        response["status_text"] = "报告生成完成"
        response["result"] = result

    elif task_result.state == "FAILURE":
        response["progress"] = 0
        response["error"] = str(task_result.info) if task_result.info else "未知错误"

    return response


def _default_semester() -> str:
    """根据当前日期推算默认学期"""
    from core.models import get_local_now
    now = get_local_now()
    if now.month >= 2 and now.month <= 7:
        return f"{now.year - 1}-{now.year}-2"
    else:
        return f"{now.year}-{now.year + 1}-1"


@router.post(
    "/export/grade-report",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GradeTaskAcceptedResponse,
)
async def export_grade_moral_report(
    body: ExportGradeReportRequest,
    current_user: User = Depends(get_current_user),
):
    """
    【端点 3】触发全年级异步批量导出

    派发任务到 Redis 队列，为每个班级创建一个独立任务，立刻返回 task_ids 列表。
    耗时仅 2ms，0 线程阻塞！

    权限:
      - ms_admin:   可导出全校任意年级
      - grade_leader: 只能导出本年级
    """
    from core.routers import require_role
    from core.models import UserRole

    # 权限检查
    if current_user.role == UserRole.GRADE_LEADER:
        from core.models import Grade

        db = _get_sync_session()

        try:
            grade = db.query(Grade).filter(Grade.id == body.grade_id).first()
            if not grade or grade.school_id != current_user.school_id:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "无权访问该年级"}
                )
            # 检查年级组长是否负责管理该年级
            if grade.leader_id != current_user.id:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "仅能导出您负责的年级"}
                )
        finally:
            db.close()

    # 查询该年级的所有班级
    from core.models import Class

    db = _get_sync_session()

    try:
        if body.include_classes:
            # 指定班级导出
            classes = db.query(Class).filter(
                Class.id.in_(body.include_classes),
                Class.school_id == current_user.school_id,
                Class.grade_id == body.grade_id,
            ).all()
        else:
            # 全年级导出
            classes = db.query(Class).filter(
                Class.grade_id == body.grade_id,
                Class.school_id == current_user.school_id,
            ).all()

        if not classes:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "该年级无班级"}
            )

        # 为每个班级派发任务
        task_ids = []
        semester = body.semester or _default_semester()

        for cls in classes:
            task = generate_class_moral_report.delay(
                school_id=current_user.school_id,
                class_id=cls.id,
                semester=semester,
                created_by=current_user.id,
            )
            task_ids.append(task.id)

        return GradeTaskAcceptedResponse(
            task_ids=task_ids,
            total_classes=len(classes),
            status="PENDING",
            message=f"全年级报告生成任务已提交（共 {len(classes)} 个班级），请持 task_ids 轮询状态",
        )

    finally:
        db.close()

@router.get("/batch-export", response_class=HTMLResponse)
async def get_batch_export_page(current_user: User = Depends(get_current_user)):
    """
    期末德育大账本批量导出前端工作台
    路径将被挂载在: /api/v1/reports/batch-export
    """
    # 严格锁死越权越界行为
    if current_user.role not in ["ms_admin", "grade_leader"]:
        raise HTTPException(status_code=403, detail="没有访问行政大账本工作台的权限！")

    try:
        # 使用 utf-8 编码安全读取绝对路径下的 HTML
        with open(HTML_FILE_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        # 即使报错，也将绝对路径打印在日志中，便于前线一秒排障
        raise HTTPException(
            status_code=404,
            detail=f"🚧 前端战术模板丢失！预设绝对路径未命中: {HTML_FILE_PATH}"
        )


# ═══════════════════════════════════════════════════════════════
# RDI 白皮书轨 — 同步实时聚合端点 (新增)
# ═══════════════════════════════════════════════════════════════

@router.get("/rdi-summary", response_model=SchoolWideReportResponse)
async def get_rdi_summary(
    grade_id: Optional[int] = Query(None, description="年级ID过滤（为空则全校）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【端点 5】全校德育/风险态势白皮书

    从 risk_warnings 聚合全校四维偏离 → risk_distribution + 班级热力排行 + 高危花名册

    权限:
      - ms_admin:   全校态势
      - grade_leader: 本年级态势（grade_id 强制覆盖为本人负责的年级）
    """
    # 权限守卫: 班主任/家长禁止访问全校态势
    if current_user.role in (UserRole.CLASS_TEACHER, UserRole.PARENT, UserRole.STUDENT):
        raise HTTPException(status_code=403, detail="无权访问全校态势白皮书")

    # grade_leader 强制只能看自己负责的年级
    effective_grade_id = grade_id
    if current_user.role == UserRole.GRADE_LEADER:
        effective_grade_id = current_user.grade_id
        if grade_id and grade_id != effective_grade_id:
            raise HTTPException(status_code=403, detail="仅可查看您负责的年级")

    result = await get_school_wide_rdi_summary(
        db=db,
        school_id=current_user.school_id,
        grade_id=effective_grade_id,
    )
    return result


@router.post("/export/high-risk", response_model=HighRiskExportResponse)
async def export_high_risk(
    grade_id: Optional[int] = Query(None, description="年级ID过滤"),
    risk_levels: Optional[List[str]] = Query(None, description="风险等级过滤，默认 intervention"),
    export_format: str = Query("json", description="导出格式: json / excel / pdf"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【端点 6】高危学生花名册导出（暑期靶向家访指南）

    精准导出 intervention 级学生，四维 breakdown + AI 处方摘要

    权限:
      - ms_admin:   全校高危花名册
      - grade_leader: 本年级高危花名册
    """
    if current_user.role in (UserRole.CLASS_TEACHER, UserRole.PARENT, UserRole.STUDENT):
        raise HTTPException(status_code=403, detail="无权导出高危花名册")

    effective_grade_id = grade_id
    if current_user.role == UserRole.GRADE_LEADER:
        effective_grade_id = current_user.grade_id
        if grade_id and grade_id != effective_grade_id:
            raise HTTPException(status_code=403, detail="仅可导出您负责的年级")

    result = await get_high_risk_students(
        db=db,
        school_id=current_user.school_id,
        grade_id=effective_grade_id,
        risk_levels=risk_levels or ["intervention"],
        export_format=export_format,
    )
    return result


@router.get("/class-report/{class_id}", response_model=ClassTeacherReportResponse)
async def get_class_report(
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【端点 7】班主任一键班级报告

    本班RDI分布 + 高危清单 + 考勤/违纪/学业概览

    权限:
      - ms_admin:   可查看任意班级
      - grade_leader: 可查看本年级任意班级
      - class_teacher: 仅可查看本班 (class_id == user.class_id)
    """
    # 班主任铁闸: class_id 强制覆盖
    if current_user.role == UserRole.CLASS_TEACHER:
        if class_id != current_user.class_id:
            raise HTTPException(status_code=403, detail="仅可查看本班德育报告")

    # 家长/学生禁止
    if current_user.role in (UserRole.PARENT, UserRole.STUDENT):
        raise HTTPException(status_code=403, detail="无权访问班级报告")

    try:
        result = await get_class_teacher_report(
            db=db,
            school_id=current_user.school_id,
            class_id=class_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
