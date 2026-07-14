"""
Data Adapter 路由层

端点:
  GET  /templates       — 获取所有清洗模板
  POST /upload-scores   — 上传成绩 Excel 并清洗
  POST /preview         — 预览清洗结果 (不写库)
  GET  /health          — 健康检查
"""

import json

from core.models import User
from core.routers import get_current_user, get_db
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import StudentRiskAlert, StudentWeaknessPrescription
from .schemas import (
    CleanErrorOut,
    PreviewResponse,
    TaskListResponse,
    TaskOut,
    TemplateListResponse,
    TemplateOut,
    TemplateSubjectOut,
    UploadScoresResponse,
)
from .services import (
    calculate_exam_zscore_matrix,
    execute_rdi_risk_analysis_pipeline,
    get_all_templates,
    process_and_save_senior_scores_pipeline,
    process_scores,
    serialize_errors,
)

router = APIRouter(tags=["data-adapter"])


# ============================================================
# 健康检查
# ============================================================


@router.get("/health")
async def health():
    return {"status": "ok", "module": "data_adapter"}


# ============================================================
# 模板列表
# ============================================================


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    current_user: User = Depends(get_current_user),
):
    """获取所有可用的清洗模板"""
    templates = get_all_templates()
    template_outs = []
    for t in templates:
        subjects = []
        for raw_name, standard_name in t.get("field_mapping", {}).get("subjects", {}).items():
            subjects.append(
                TemplateSubjectOut(
                    raw_name=raw_name,
                    standard_name=standard_name,
                )
            )
        template_outs.append(
            TemplateOut(
                code=t.get("code", ""),
                name=t.get("name", ""),
                source_type=t.get("source_type", ""),
                phase=t.get("phase", ""),
                subjects=subjects,
            )
        )
    return TemplateListResponse(
        templates=template_outs,
        total=len(template_outs),
    )


# ============================================================
# 上传成绩 — 核心端点
# ============================================================


@router.post("/upload-scores", response_model=UploadScoresResponse)
async def upload_scores(
    file: UploadFile = File(...),
    template_code: str | None = Form(None),
    selected_subjects: str | None = Form(None),
    exam_id: int | None = Form(None, description="关联的大考ID (高中赋分管道必填)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    成绩 Excel 上传并清洗

    - 自动根据当前用户学校学段 (phase) 选择清洗模板
    - **junior / primary**: 标准清洗 (全科必考)
    - **senior**: 选科模式, 可通过 `selected_subjects` 传入选科映射
    - `selected_subjects` 格式: JSON 字符串
      `{"张三": ["物理", "化学", "生物"], "李四": ["历史", "地理", "政治"]}`
    - 返回清洗结果 + 前 20 条预览数据

    学段隔离: 模块级 MODULE_PHASES=["junior","senior","integrated"] 自动拦截
    """
    # 学段由模块级隔离闸统一管控，此处直接从 current_user 读取
    phase = current_user.school.school_phase if current_user.school else "junior"
    # ---- 1. 读取文件 ----
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="文件为空")

    # ---- 2. 解析选科映射 (高中学段) ----
    parsed_selected = None
    if selected_subjects:
        try:
            parsed_selected = json.loads(selected_subjects)
            if not isinstance(parsed_selected, dict):
                raise ValueError("selected_subjects 必须是 JSON 对象")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"selected_subjects 格式错误: {e}",
            )

    # ---- 3. 执行清洗 ----
    try:
        code, template, result = process_scores(
            file_content=file_content,
            filename=file.filename or "upload.xlsx",
            phase=phase,
            template_code=template_code,
            selected_subjects=parsed_selected,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清洗失败: {e}")

    # ---- 4. 序列化错误 ----
    errors_out = [
        CleanErrorOut(
            row=e.get("row", 0) if isinstance(e, dict) else e.row,
            column=e.get("column", "") if isinstance(e, dict) else e.column,
            raw_value=str(e.get("raw_value", "") if isinstance(e, dict) else e.raw_value)[:100],
            error_type=(
                e.get("error_type", "")
                if isinstance(e, dict)
                else (e.error_type.value if hasattr(e.error_type, "value") else str(e.error_type))
            ),
            message=e.get("message", "") if isinstance(e, dict) else e.message,
        )
        for e in result.errors[:20]
    ]

    preview_data = result.cleaned_data[:20]

    # ---- 5. 持久化导入记录 (失败不阻塞响应) ----
    task_id = None
    try:
        from .models import ImportTask

        task = ImportTask(
            school_id=current_user.school_id,
            filename=file.filename or "upload.xlsx",
            status=("completed" if result.failed_rows == 0 else "completed_with_errors"),
            phase=phase,
            template_code=code,
            total_rows=result.total_rows,
            success_rows=result.success_rows,
            failed_rows=result.failed_rows,
            skipped_rows=result.skipped_rows,
            errors_summary=serialize_errors(result.errors, 20),
            sync_status="imported",
            created_by=current_user.id,
        )
        db.add(task)
        await db.commit()
        task_id = task.id
    except Exception:
        await db.rollback()

    # ---- 5.5 高中学段: 赋分落盘管道 ----
    pipeline_summary = None
    if phase == "senior":
        if not exam_id:
            raise HTTPException(
                status_code=400,
                detail="高中学段上传成绩必须提供 exam_id 参数",
            )
        try:
            pipeline_summary = await process_and_save_senior_scores_pipeline(
                db=db,
                exam_id=exam_id,
                school_id=current_user.school_id,
                cleaned_data=result.cleaned_data,
            )
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"赋分落盘管道溃缩: {e}",
            )

        # 🚀 成绩落盘成功后, 顺流点火 RDI 风险血缘追溯引擎
        try:
            rdi_result = await execute_rdi_risk_analysis_pipeline(
                db=db,
                exam_id=exam_id,
                school_id=current_user.school_id,
            )
            if pipeline_summary and isinstance(pipeline_summary, dict):
                pipeline_summary["rdi_alerts"] = rdi_result

            # 🚀 RDI 预警落盘后, 顺流启动 AI 诊断处方自动机
            if rdi_result.get("alerts_triggered", 0) > 0:
                try:
                    from modules.data_adapter.ai_prescription_engine import (
                        run_ai_prescription_pipeline,
                    )

                    ai_result = await run_ai_prescription_pipeline(
                        db=db,
                        exam_id=exam_id,
                        school_id=current_user.school_id,
                    )
                    if pipeline_summary and isinstance(pipeline_summary, dict):
                        pipeline_summary["ai_prescriptions"] = ai_result
                except Exception as ai_err:
                    if pipeline_summary and isinstance(pipeline_summary, dict):
                        pipeline_summary["ai_prescriptions"] = {
                            "status": "error",
                            "msg": str(ai_err),
                        }

        except Exception as e:
            # RDI 失败不阻塞上传响应, 仅记录
            if pipeline_summary and isinstance(pipeline_summary, dict):
                pipeline_summary["rdi_alerts"] = {
                    "status": "error",
                    "msg": str(e),
                }

    # ---- 6. 构建响应 ----
    message = (
        f"清洗完成: {result.success_rows} 成功 / "
        f"{result.failed_rows} 失败 / "
        f"{result.skipped_rows} 跳过"
    )
    if phase == "senior":
        message += " (高中选科模式)"
        if parsed_selected:
            message += f" — 已按 {len(parsed_selected)} 人选科映射过滤"

    return UploadScoresResponse(
        status=("completed" if result.failed_rows == 0 else "completed_with_errors"),
        phase=phase,
        template_code=code,
        template_name=template.get("name", ""),
        total_rows=result.total_rows,
        success_rows=result.success_rows,
        failed_rows=result.failed_rows,
        skipped_rows=result.skipped_rows,
        errors=errors_out,
        preview_data=preview_data,
        message=message,
        task_id=task_id,
        pipeline_summary=pipeline_summary,
        sync_status="imported",
    )


# ============================================================
# 导入任务列表
# ============================================================


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sync_status: str | None = Query(None, description="按数据来源筛选: native/legacy/imported"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查询数据导入任务列表，支持按 sync_status 过滤：
    - native:   系统原生创建
    - legacy:   旧系统迁移
    - imported: 批量Excel导入
    """
    from .models import ImportTask

    conditions = [ImportTask.school_id == current_user.school_id]
    if sync_status:
        conditions.append(ImportTask.sync_status == sync_status)

    count_q = select(func.count()).select_from(
        select(ImportTask).where(and_(*conditions)).subquery()
    )
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    result = await db.execute(
        select(ImportTask)
        .where(and_(*conditions))
        .order_by(ImportTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tasks = result.scalars().all()

    return TaskListResponse(
        tasks=[TaskOut.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================
# 预览清洗 (不写库)
# ============================================================


@router.post("/preview", response_model=PreviewResponse)
async def preview_cleaning(
    file: UploadFile = File(...),
    template_code: str | None = Form(None),
    preview_rows: int = Form(5),
    current_user: User = Depends(get_current_user),
):
    """
    预览清洗结果 (不写入数据库)

    - 只处理前 N 行, 快速验证字段映射是否正确
    - 默认预览 5 行

    学段隔离: 模块级 MODULE_PHASES=["junior","senior","integrated"] 自动拦截
    """
    phase = current_user.school.school_phase if current_user.school else "junior"
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="文件为空")

    try:
        code, template, result = process_scores(
            file_content=file_content,
            filename=file.filename or "upload.xlsx",
            phase=phase,
            template_code=template_code,
            preview_only=True,
            preview_rows=preview_rows,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {e}")

    errors_out = [
        CleanErrorOut(
            row=e.get("row", 0) if isinstance(e, dict) else e.row,
            column=e.get("column", "") if isinstance(e, dict) else e.column,
            raw_value=str(e.get("raw_value", "") if isinstance(e, dict) else e.raw_value)[:100],
            error_type=(
                e.get("error_type", "")
                if isinstance(e, dict)
                else (e.error_type.value if hasattr(e.error_type, "value") else str(e.error_type))
            ),
            message=e.get("message", "") if isinstance(e, dict) else e.message,
        )
        for e in result.errors[:20]
    ]

    return PreviewResponse(
        phase=phase,
        template_code=code,
        template_name=template.get("name", ""),
        total_previewed=result.total_rows,
        success_count=result.success_rows,
        failed_count=result.failed_rows,
        skipped_count=result.skipped_rows,
        rows=result.cleaned_data,
        errors=errors_out,
    )


# ============================================================
# Z-Score 热力图矩阵 — 全校学科强弱分布大盘
# ============================================================


@router.get("/exams/{exam_id}/zscore-matrix")
async def get_exam_zscore_heatmap_matrix(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【大盘热力图接口】获取单场大考全校行政班级×学科的 Z-Score 强弱热力图

    返回 ECharts Heatmap 所需的三元组矩阵:
      - classes:     班级名称列表 (Y轴)
      - subjects:    学科代码列表 (X轴)
      - matrix_data: [[class_idx, subject_idx, z_score], ...]
      - global_subject_stats: 全校大盘各学科均值与标准差
    """
    school_id = current_user.school_id

    try:
        matrix_res = await calculate_exam_zscore_matrix(db, exam_id, school_id)
        return {
            "status": "success",
            "exam_id": exam_id,
            "data": matrix_res,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Z-Score 矩阵热力图引擎中断: {e}",
        )


# ============================================================
# RDI 风险血缘追溯 — 手动触发分析端点
# ============================================================


@router.post("/exams/{exam_id}/rdi-analysis")
async def trigger_rdi_analysis(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【RDI 血缘追溯引擎】手动触发单场大考的风险分析

    扫描该校该场大考的所有有效成绩:
      - 计算个人 Z-Score
      - Z ≤ -1.5 → 红灯, -1.5 < Z ≤ -1.0 → 黄灯
      - 为每个危重样本组装 3 层血缘 DAG 并落盘

    幂等: 重复调用会清除旧的 active 预警后重新计算
    """
    school_id = current_user.school_id

    try:
        result = await execute_rdi_risk_analysis_pipeline(
            db=db,
            exam_id=exam_id,
            school_id=school_id,
        )

        # 🚀 预警落盘后, 立刻顺流启动 AI 诊断处方自动机
        ai_result = None
        try:
            from modules.data_adapter.ai_prescription_engine import (
                run_ai_prescription_pipeline,
            )

            ai_result = await run_ai_prescription_pipeline(
                db=db,
                exam_id=exam_id,
                school_id=school_id,
            )
        except Exception as ai_err:
            # AI 处方失败不阻塞 RDI 响应, 仅记录
            ai_result = {
                "status": "error",
                "msg": f"AI 处方引擎中断: {ai_err}",
            }

        return {
            "status": "success",
            "exam_id": exam_id,
            "data": result,
            "ai_prescriptions": ai_result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RDI 血缘追溯引擎中断: {e}",
        )


# ============================================================
# RDI 预警流水盘 — 拉取当前考试的所有活动预警
# ============================================================


@router.get("/exams/{exam_id}/alerts")
async def get_exam_alerts(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【预警大盘接口】获取单场大考的所有活动红黄灯预警

    返回该考试下该校所有 status='active' 的预警记录,
    每条记录携带完整的 lineage_graph JSON 供前端渲染三层 DAG.
    """
    school_id = current_user.school_id

    stmt = (
        select(StudentRiskAlert)
        .where(
            StudentRiskAlert.exam_id == exam_id,
            StudentRiskAlert.school_id == school_id,
            StudentRiskAlert.status == "active",
        )
        .order_by(StudentRiskAlert.risk_level.desc(), StudentRiskAlert.created_at.desc())
    )
    res = await db.execute(stmt)
    alerts = res.scalars().all()

    return {
        "status": "success",
        "exam_id": exam_id,
        "total": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "student_id": a.student_id,
                "exam_id": a.exam_id,
                "risk_type": a.risk_type,
                "risk_level": a.risk_level,
                "trigger_reason": a.trigger_reason,
                "lineage_graph": a.lineage_graph,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ],
    }


# ============================================================
# AI 弱科处方 — 按预警 ID 拉取关联的 AI 诊断处方
# ============================================================


@router.get("/alerts/{alert_id}/prescriptions")
async def get_alert_prescriptions(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    【AI 处方调阅接口】获取某条预警关联的所有 AI 定向弱科诊断处方

    返回该预警下每个弱势学科 (Z ≤ -1.0) 的 DeepSeek 诊断报告与行动处方.
    """
    school_id = current_user.school_id

    stmt = (
        select(StudentWeaknessPrescription)
        .where(
            StudentWeaknessPrescription.alert_id == alert_id,
            StudentWeaknessPrescription.school_id == school_id,
        )
        .order_by(StudentWeaknessPrescription.z_score.asc())
    )
    res = await db.execute(stmt)
    prescriptions = res.scalars().all()

    return {
        "status": "success",
        "alert_id": alert_id,
        "total": len(prescriptions),
        "prescriptions": [
            {
                "id": p.id,
                "alert_id": p.alert_id,
                "student_id": p.student_id,
                "subject_code": p.subject_code,
                "raw_score": float(p.raw_score) if p.raw_score is not None else None,
                "scaled_score": float(p.scaled_score) if p.scaled_score is not None else None,
                "z_score": float(p.z_score) if p.z_score is not None else None,
                "weakness_analysis": p.weakness_analysis,
                "action_prescription": p.action_prescription,
                "model_metadata": p.model_metadata,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in prescriptions
        ],
    }
