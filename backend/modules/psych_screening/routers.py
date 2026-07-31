"""
Psych Screening 路由层 — 18 个 API 端点

端点分组:
  📋 问卷筛查:   GET/POST /surveys + /dimension-data + /ai-analysis + /sync
  📊 评估管理:   GET/POST/PUT/DELETE /assessments
  🩺 干预追踪:   GET/POST /interventions + /followup + /timeline
  📖 辅助:       /questions /students/search /dashboard + /seed
"""

from core.models import Student, User, UserRole
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from modules.psych_screening.models import (
    InterventionRecord,
    MentalHealthAnswer,
    MentalHealthAssessment,
    MentalHealthQuestion,
    PsychSurvey,
)
from modules.psych_screening.schemas import (
    ASSESSMENT_TYPE_CHOICES,
    EFFECT_RATING_CHOICES,
    INTERVENTION_TYPE_CHOICES,
    MSSMHS_DIMENSIONS,
    RISK_LEVEL_CHOICES,
    AIAnalysisRequest,
    AIAnalysisResponse,
    AssessmentCreateRequest,
    AssessmentDetailOut,
    AssessmentListResponse,
    AssessmentOut,
    AssessmentUpdateRequest,
    DimensionDataResponse,
    InterventionCreateRequest,
    InterventionFollowupRequest,
    InterventionListResponse,
    InterventionOut,
    InterventionTimelineResponse,
    PsychDashboardResponse,
    PsychSurveyListResponse,
    PsychSurveyOut,
    QuestionListResponse,
    QuestionOut,
    StudentSearchItem,
    StudentSearchResponse,
    SurveySubmitRequest,
    SurveySubmitResponse,
    SyncToAssessmentResponse,
)
from modules.psych_screening.services import (
    create_assessment,
    create_intervention,
    delete_assessment,
    followup_intervention,
    get_dashboard_stats,
    get_dimension_aggregation,
    get_intervention_timeline,
    list_assessments,
    list_interventions,
    run_ai_analysis,
    search_students,
    seed_mssmhs_questions,
    submit_survey,
    sync_surveys_to_assessments,
    update_assessment,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["psych-screening"])


# ═══════════════════════════════════════════════════════════════
# 辅助 Dependency — 角色权限
# ═══════════════════════════════════════════════════════════════


def _verify_student_scope(
    user: User,
    target_class_id: int | None = None,
    target_grade_id: int | None = None,
):
    """验证用户权限 scope：班主任只能看自己班，年级组长只能看自己年级"""
    if user.role == UserRole.MS_ADMIN:
        return  # 德育处管理员放行
    if user.role == UserRole.GRADE_LEADER:
        if target_grade_id and user.grade_id != target_grade_id:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "年级组长只能查看本年级数据")
    if user.role in (UserRole.CLASS_TEACHER, UserRole.TEACHER):
        if target_class_id and user.class_id != target_class_id:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "班主任只能查看本班数据")


def _get_scope_params(user: User):
    """根据角色返回 grade_id / class_id 过滤参数"""
    params = {}
    if user.role == UserRole.GRADE_LEADER and user.grade_id:
        params["grade_id"] = user.grade_id
    elif user.role in (UserRole.CLASS_TEACHER, UserRole.TEACHER) and user.class_id:
        params["class_id"] = user.class_id
    return params


# ═══════════════════════════════════════════════════════════════
# 元数据端点 — 常量列表
# ═══════════════════════════════════════════════════════════════


@router.get("/metadata")
async def get_metadata(
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """返回模块所用的常量列表 (供前端渲染表单)"""
    return {
        "mssmhs_dimensions": MSSMHS_DIMENSIONS,
        "assessment_types": [{"value": v, "label": l} for v, l in ASSESSMENT_TYPE_CHOICES],
        "risk_levels": [{"value": v, "label": l} for v, l in RISK_LEVEL_CHOICES],
        "intervention_types": [{"value": v, "label": l} for v, l in INTERVENTION_TYPE_CHOICES],
        "effect_ratings": [{"value": v, "label": l} for v, l in EFFECT_RATING_CHOICES],
        "max_per_dim": 30,
        "max_total": 275,
    }


# ═══════════════════════════════════════════════════════════════
# 📋 问卷筛查
# ═══════════════════════════════════════════════════════════════


@router.get("/surveys", response_model=PsychSurveyListResponse)
async def list_surveys(
    grade_id: int | None = Query(None),
    class_id: int | None = Query(None),
    survey_type: str | None = Query(None, description="MSSMHS-55 / PCE-55"),
    limit: int = Query(200, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """心理筛查问卷列表 (含统计)"""
    # 权限 scope 覆盖
    scope = _get_scope_params(current_user)
    if scope.get("grade_id"):
        grade_id = scope["grade_id"]
    if scope.get("class_id"):
        class_id = scope["class_id"]

    conditions = [
        PsychSurvey.school_id == current_user.school_id,
        PsychSurvey.is_valid == True,
    ]
    if grade_id:
        conditions.append(PsychSurvey.grade_id == grade_id)
    if class_id:
        conditions.append(PsychSurvey.class_id == class_id)
    if survey_type:
        conditions.append(PsychSurvey.survey_type == survey_type)

    # 列表
    from sqlalchemy import func

    count_stmt = select(func.count(PsychSurvey.id)).where(*conditions)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(PsychSurvey)
        .where(*conditions)
        .order_by(PsychSurvey.total_score.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    surveys = result.scalars().all()

    # 批量加载学生信息
    student_ids = [s.student_id for s in surveys]
    if student_ids:
        students_result = await db.execute(select(Student).where(Student.id.in_(student_ids)))
        student_map = {s.id: s for s in students_result.scalars().all()}
    else:
        student_map = {}

    # 统计
    stats_stmt = select(
        func.sum(func.if_(PsychSurvey.total_score >= 160, 1, 0)),
        func.sum(
            func.if_(
                PsychSurvey.total_score >= 120,
                func.if_(PsychSurvey.total_score < 160, 1, 0),
                0,
            )
        ),
        func.sum(func.if_(PsychSurvey.total_score < 120, 1, 0)),
    ).where(*conditions, PsychSurvey.survey_type == "MSSMHS-55")
    stats_result = await db.execute(stats_stmt)
    stats_row = stats_result.one()

    # 序列化
    from modules.psych_screening.services import _parse_dimensions

    survey_outs = []
    for s in surveys:
        stu = student_map.get(s.student_id)
        dims = _parse_dimensions(s.dimension_scores)
        survey_outs.append(
            PsychSurveyOut(
                id=s.id,
                student_id=s.student_id,
                student_name=stu.name if stu else None,
                class_name=stu.class_.name if stu and stu.class_ else None,
                grade_name=None,
                survey_type=s.survey_type,
                total_score=s.total_score,
                verify_status=s.verify_status,
                completed_at=s.completed_at,
                dimensions=dims,
            )
        )

    return PsychSurveyListResponse(
        surveys=survey_outs,
        total=total,
        stats={
            "high": stats_row[0] or 0,
            "medium": stats_row[1] or 0,
            "low": stats_row[2] or 0,
        },
    )


@router.post("/surveys/submit", response_model=SurveySubmitResponse)
async def submit_psych_survey(
    req: SurveySubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """
    提交 MSSMHS-55 心理筛查问卷。
    自动评分 → 风险定级 → 中高风险自动创建评估档案。
    """
    result = await submit_survey(
        db=db,
        student_id=req.student_id,
        school_id=current_user.school_id,
        answers=[a.model_dump() for a in req.answers],
        survey_type=req.survey_type,
    )
    return SurveySubmitResponse(**result)


@router.get("/surveys/dimension-data", response_model=DimensionDataResponse)
async def get_dimension_data(
    class_id: int | None = Query(None),
    grade_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """
    MSSMHS-55 十维度聚合数据 (ECharts 雷达图)。
    支持按班级/年级筛选，兼容角色 scope。
    """
    scope = _get_scope_params(current_user)
    if scope.get("grade_id"):
        grade_id = scope["grade_id"]
    if scope.get("class_id"):
        class_id = scope["class_id"]

    data = await get_dimension_aggregation(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        class_id=class_id,
    )
    return DimensionDataResponse(**data)


@router.post("/surveys/ai-analysis", response_model=AIAnalysisResponse)
async def ai_analysis(
    req: AIAnalysisRequest = AIAnalysisRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    DeepSeek AI 宏观分析 → 心理健康白皮书 (仅管理员/年级组长)。
    """
    scope = _get_scope_params(current_user)
    grade_id = req.grade_id or scope.get("grade_id")
    class_id = req.class_id

    result = await run_ai_analysis(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        class_id=class_id,
    )
    return AIAnalysisResponse(**result)


@router.post("/surveys/sync-to-assessment", response_model=SyncToAssessmentResponse)
async def sync_surveys(
    grade_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """
    一键同步: 扫描中高风险问卷 → 批量创建/更新评估记录 (幂等)。
    """
    scope = _get_scope_params(current_user)
    if scope.get("grade_id"):
        grade_id = scope["grade_id"]

    result = await sync_surveys_to_assessments(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
    )
    return SyncToAssessmentResponse(**result)


# ═══════════════════════════════════════════════════════════════
# 📊 心理健康评估
# ═══════════════════════════════════════════════════════════════


@router.get("/assessments", response_model=AssessmentListResponse)
async def list_psych_assessments(
    grade_id: int | None = Query(None),
    class_id: int | None = Query(None),
    student_id: int | None = Query(None),
    risk_level: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """心理健康评估列表"""
    scope = _get_scope_params(current_user)
    if scope.get("grade_id"):
        grade_id = scope["grade_id"]
    if scope.get("class_id"):
        class_id = scope["class_id"]

    result = await list_assessments(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        class_id=class_id,
        student_id=student_id,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )

    # 序列化
    assessment_student_ids = [a.student_id for a in result["assessments"]]
    student_map = {}
    if assessment_student_ids:
        students_result = await db.execute(
            select(Student).where(Student.id.in_(assessment_student_ids))
        )
        student_map = {s.id: s for s in students_result.scalars().all()}

    outs = []
    for a in result["assessments"]:
        stu = student_map.get(a.student_id)
        outs.append(
            AssessmentOut(
                id=a.id,
                student_id=a.student_id,
                student_name=stu.name if stu else None,
                class_name=stu.class_.name if stu and stu.class_ else None,
                assessment_type=a.assessment_type,
                assessment_date=a.assessment_date,
                scale_name=a.scale_name,
                total_score=a.total_score,
                risk_level=a.risk_level,
                conclusion=a.conclusion,
                recommendations=a.recommendations,
                need_intervention=a.need_intervention,
                intervention_plan=a.intervention_plan,
                assessed_by=a.assessed_by,
                assessor_name=None,  # risk_models 不提供 assessor relationship
                status=a.status,
                reviewed_by=a.reviewed_by,
                reviewed_at=a.reviewed_at,
                review_comment=a.review_comment,
                created_at=a.created_at,
            )
        )

    return AssessmentListResponse(
        assessments=outs,
        total=result["total"],
        stats=result["stats"],
    )


@router.post("/assessments", response_model=AssessmentOut)
async def create_psych_assessment(
    req: AssessmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """手动创建心理健康评估"""
    student = await db.execute(
        select(Student).where(
            Student.id == req.student_id,
            Student.school_id == current_user.school_id,
        )
    )
    student = student.scalar_one_or_none()
    if not student:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "学生不存在")

    # 班主任只能评估自己班
    if current_user.role == UserRole.CLASS_TEACHER and student.class_id != current_user.class_id:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "只能评估本班学生")

    assessment = await create_assessment(
        db=db,
        school_id=current_user.school_id,
        assessed_by=current_user.id,
        data=req.model_dump(exclude_none=True),
    )

    return AssessmentOut(
        id=assessment.id,
        student_id=assessment.student_id,
        student_name=student.name,
        class_name=student.class_.name if student.class_ else None,
        assessment_type=assessment.assessment_type,
        assessment_date=assessment.assessment_date,
        scale_name=assessment.scale_name,
        total_score=assessment.total_score,
        risk_level=assessment.risk_level,
        conclusion=assessment.conclusion,
        recommendations=assessment.recommendations,
        need_intervention=assessment.need_intervention,
        intervention_plan=assessment.intervention_plan,
        assessed_by=assessment.assessed_by,
        status=assessment.status,
        created_at=assessment.created_at,
    )


@router.get("/assessments/{assessment_id}", response_model=AssessmentDetailOut)
async def get_assessment_detail(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """心理健康评估详情 (含答题明细+干预记录+辅助数据)"""
    assessment = await db.execute(
        select(MentalHealthAssessment).where(
            MentalHealthAssessment.id == assessment_id,
            MentalHealthAssessment.school_id == current_user.school_id,
        )
    )
    assessment = assessment.scalar_one_or_none()
    if not assessment:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "评估记录不存在")

    # 权限检查
    _verify_student_scope(current_user, assessment.class_id, assessment.grade_id)

    stu = assessment.student
    student_name = stu.name if stu else None
    class_name = stu.class_.name if stu and stu.class_ else None

    # 答题明细
    answers_result = await db.execute(
        select(MentalHealthAnswer).where(MentalHealthAnswer.assessment_id == assessment_id)
    )
    answers = answers_result.scalars().all()
    answer_detail = []
    for a in answers:
        q = a.question
        answer_detail.append(
            {
                "question_id": a.question_id,
                "answer_value": a.answer_value,
                "dimension": q.dimension if q else None,
                "question_text": q.question_text if q else None,
                "question_no": q.question_no if q else None,
            }
        )

    # 干预记录
    interventions_result = await db.execute(
        select(InterventionRecord)
        .where(
            InterventionRecord.assessment_id == assessment_id,
            InterventionRecord.school_id == current_user.school_id,
        )
        .order_by(InterventionRecord.intervention_date.desc())
    )
    interventions = interventions_result.scalars().all()
    intervention_summary = []
    for ir in interventions:
        intervention_summary.append(
            {
                "id": ir.id,
                "type": ir.intervention_type,
                "date": str(ir.intervention_date) if ir.intervention_date else None,
                "effect": ir.effect_rating,
                "status": ir.status,
            }
        )

    return AssessmentDetailOut(
        id=assessment.id,
        student_id=assessment.student_id,
        student_name=student_name,
        class_name=class_name,
        assessment_type=assessment.assessment_type,
        assessment_date=assessment.assessment_date,
        scale_name=assessment.scale_name,
        total_score=assessment.total_score,
        risk_level=assessment.risk_level,
        conclusion=assessment.conclusion,
        recommendations=assessment.recommendations,
        need_intervention=assessment.need_intervention,
        intervention_plan=assessment.intervention_plan,
        assessed_by=assessment.assessed_by,
        assessor_name=None,
        status=assessment.status,
        reviewed_by=assessment.reviewed_by,
        reviewed_at=assessment.reviewed_at,
        review_comment=assessment.review_comment,
        created_at=assessment.created_at,
        answers=answer_detail,
        intervention_records=intervention_summary,
    )


@router.put("/assessments/{assessment_id}", response_model=AssessmentOut)
async def update_psych_assessment(
    assessment_id: int,
    req: AssessmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """编辑评估记录"""
    assessment = await db.execute(
        select(MentalHealthAssessment).where(
            MentalHealthAssessment.id == assessment_id,
            MentalHealthAssessment.school_id == current_user.school_id,
        )
    )
    assessment = assessment.scalar_one_or_none()
    if not assessment:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "评估记录不存在")

    _verify_student_scope(current_user, assessment.class_id, assessment.grade_id)

    assessment = await update_assessment(
        db=db,
        assessment_id=assessment_id,
        data=req.model_dump(exclude_none=True),
    )

    stu = assessment.student
    return AssessmentOut(
        id=assessment.id,
        student_id=assessment.student_id,
        student_name=stu.name if stu else None,
        class_name=stu.class_.name if stu and stu.class_ else None,
        assessment_type=assessment.assessment_type,
        assessment_date=assessment.assessment_date,
        scale_name=assessment.scale_name,
        total_score=assessment.total_score,
        risk_level=assessment.risk_level,
        conclusion=assessment.conclusion,
        recommendations=assessment.recommendations,
        need_intervention=assessment.need_intervention,
        intervention_plan=assessment.intervention_plan,
        assessed_by=assessment.assessed_by,
        status=assessment.status,
        created_at=assessment.created_at,
    )


@router.delete("/assessments/{assessment_id}")
async def delete_psych_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    """删除评估记录 (仅管理员/年级组长)"""
    assessment = await db.execute(
        select(MentalHealthAssessment).where(
            MentalHealthAssessment.id == assessment_id,
            MentalHealthAssessment.school_id == current_user.school_id,
        )
    )
    assessment = assessment.scalar_one_or_none()
    if not assessment:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "评估记录不存在")

    _verify_student_scope(current_user, assessment.class_id, assessment.grade_id)

    await delete_assessment(db, assessment_id)
    return {"status": "ok", "message": "评估记录已删除"}


# ═══════════════════════════════════════════════════════════════
# 🩺 绿洲干预追踪
# ═══════════════════════════════════════════════════════════════


@router.get("/interventions", response_model=InterventionListResponse)
async def list_psych_interventions(
    grade_id: int | None = Query(None),
    class_id: int | None = Query(None),
    student_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """干预追踪列表"""
    scope = _get_scope_params(current_user)
    if scope.get("grade_id"):
        grade_id = scope["grade_id"]
    if scope.get("class_id"):
        class_id = scope["class_id"]

    result = await list_interventions(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        class_id=class_id,
        student_id=student_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    # 批量学生信息
    rec_student_ids = list({r.student_id for r in result["records"]})
    student_map = {}
    if rec_student_ids:
        students_result = await db.execute(select(Student).where(Student.id.in_(rec_student_ids)))
        student_map = {s.id: s for s in students_result.scalars().all()}

    outs = []
    for r in result["records"]:
        stu = student_map.get(r.student_id)
        outs.append(
            InterventionOut(
                id=r.id,
                student_id=r.student_id,
                student_name=stu.name if stu else None,
                class_name=stu.class_.name if stu and stu.class_ else None,
                teacher_id=r.teacher_id,
                teacher_name=r.teacher.name if r.teacher else None,
                assessment_id=r.assessment_id,
                mh_risk_before=r.mh_risk_before,
                mh_risk_after=r.mh_risk_after,
                intervention_type=r.intervention_type,
                notes=r.notes,
                parent_feedback=r.parent_feedback,
                effect_rating=r.effect_rating,
                intervention_date=r.intervention_date,
                follow_up_date=r.follow_up_date,
                follow_up_done=r.follow_up_done,
                follow_up_notes=r.follow_up_notes,
                status=r.status,
                is_effective=r.is_effective,
                mh_risk_improved=r.mh_risk_improved,
                created_at=r.created_at,
            )
        )

    return InterventionListResponse(
        records=outs,
        total=result["total"],
        stats=result["stats"],
    )


@router.post("/interventions", response_model=InterventionOut)
async def create_psych_intervention(
    req: InterventionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """创建心理健康干预记录"""
    student = await db.execute(
        select(Student).where(
            Student.id == req.student_id,
            Student.school_id == current_user.school_id,
        )
    )
    student = student.scalar_one_or_none()
    if not student:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "学生不存在")

    # 班主任只能干预自己班
    if current_user.role == UserRole.CLASS_TEACHER and student.class_id != current_user.class_id:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "只能干预本班学生")

    rec = await create_intervention(
        db=db,
        school_id=current_user.school_id,
        teacher_id=current_user.id,
        data=req.model_dump(exclude_none=True),
    )

    return InterventionOut(
        id=rec.id,
        student_id=rec.student_id,
        student_name=student.name,
        class_name=student.class_.name if student.class_ else None,
        teacher_id=rec.teacher_id,
        assessment_id=rec.assessment_id,
        mh_risk_before=rec.mh_risk_before,
        intervention_type=rec.intervention_type,
        notes=rec.notes,
        intervention_date=rec.intervention_date,
        follow_up_date=rec.follow_up_date,
        follow_up_done=rec.follow_up_done,
        status=rec.status,
        is_effective=rec.is_effective,
        mh_risk_improved=rec.mh_risk_improved,
        created_at=rec.created_at,
    )


@router.post("/interventions/{intervention_id}/followup", response_model=InterventionOut)
async def followup_psych_intervention(
    intervention_id: int,
    req: InterventionFollowupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """随访更新干预记录"""
    rec = await db.execute(
        select(InterventionRecord).where(
            InterventionRecord.id == intervention_id,
            InterventionRecord.school_id == current_user.school_id,
        )
    )
    rec = rec.scalar_one_or_none()
    if not rec:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "干预记录不存在")

    # 权限: 创建者或管理员
    if current_user.role not in (UserRole.MS_ADMIN, UserRole.GRADE_LEADER):
        if rec.teacher_id != current_user.id:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "只能更新自己创建的干预记录")

    rec = await followup_intervention(
        db=db,
        intervention_id=intervention_id,
        data=req.model_dump(exclude_none=True),
    )

    stu = rec.student
    return InterventionOut(
        id=rec.id,
        student_id=rec.student_id,
        student_name=stu.name if stu else None,
        class_name=stu.class_.name if stu and stu.class_ else None,
        teacher_id=rec.teacher_id,
        assessment_id=rec.assessment_id,
        mh_risk_before=rec.mh_risk_before,
        mh_risk_after=rec.mh_risk_after,
        intervention_type=rec.intervention_type,
        notes=rec.notes,
        parent_feedback=rec.parent_feedback,
        effect_rating=rec.effect_rating,
        intervention_date=rec.intervention_date,
        follow_up_date=rec.follow_up_date,
        follow_up_done=rec.follow_up_done,
        follow_up_notes=rec.follow_up_notes,
        status=rec.status,
        is_effective=rec.is_effective,
        mh_risk_improved=rec.mh_risk_improved,
        created_at=rec.created_at,
    )


@router.get("/interventions/timeline/{student_id}", response_model=InterventionTimelineResponse)
async def intervention_timeline(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """学生干预时间轴 (含风险变化趋势)"""
    student = await db.execute(
        select(Student).where(
            Student.id == student_id,
            Student.school_id == current_user.school_id,
        )
    )
    student = student.scalar_one_or_none()
    if not student:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "学生不存在")

    _verify_student_scope(current_user, student.class_id, student.grade_id)

    result = await get_intervention_timeline(
        db=db,
        student_id=student_id,
        school_id=current_user.school_id,
    )

    # 序列化 latest_assessment
    latest = result.get("latest_assessment")
    latest_out = None
    if latest:
        latest_out = AssessmentOut(
            id=latest.id,
            student_id=latest.student_id,
            assessment_type=latest.assessment_type,
            assessment_date=latest.assessment_date,
            scale_name=latest.scale_name,
            total_score=latest.total_score,
            risk_level=latest.risk_level,
            conclusion=latest.conclusion,
            need_intervention=latest.need_intervention,
            intervention_plan=latest.intervention_plan,
            status=latest.status,
            created_at=latest.created_at,
        )

    # 序列化 records
    record_outs = []
    for r in result["records"]:
        record_outs.append(
            InterventionOut(
                id=r.id,
                student_id=r.student_id,
                teacher_id=r.teacher_id,
                assessment_id=r.assessment_id,
                mh_risk_before=r.mh_risk_before,
                mh_risk_after=r.mh_risk_after,
                intervention_type=r.intervention_type,
                notes=r.notes,
                parent_feedback=r.parent_feedback,
                effect_rating=r.effect_rating,
                intervention_date=r.intervention_date,
                follow_up_date=r.follow_up_date,
                follow_up_done=r.follow_up_done,
                follow_up_notes=r.follow_up_notes,
                status=r.status,
                is_effective=r.is_effective,
                mh_risk_improved=r.mh_risk_improved,
                created_at=r.created_at,
            )
        )

    return InterventionTimelineResponse(
        student_id=result["student_id"],
        student_name=result["student_name"],
        records=record_outs,
        risk_trend=result["risk_trend"],
        latest_assessment=latest_out,
    )


# ═══════════════════════════════════════════════════════════════
# 📖 学生搜索
# ═══════════════════════════════════════════════════════════════


@router.get("/students/search", response_model=StudentSearchResponse)
async def search_psych_students(
    q: str | None = Query(None, alias="q", description="姓名关键词"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """
    搜索学生 (按姓名+权限 scope)，用于干预创建 Modal。
    返回结果含最新 MH 风险等级。
    """
    scope = _get_scope_params(current_user)
    results = await search_students(
        db=db,
        school_id=current_user.school_id,
        grade_id=scope.get("grade_id"),
        class_id=scope.get("class_id"),
        keyword=q,
        limit=limit,
    )

    items = [StudentSearchItem(**s) for s in results]
    return StudentSearchResponse(students=items, total=len(items))


# ═══════════════════════════════════════════════════════════════
# 📖 问题库
# ═══════════════════════════════════════════════════════════════


@router.get("/questions", response_model=QuestionListResponse)
async def list_questions(
    scale_name: str | None = Query(None, description="MSSMHS-55 / SCL-90"),
    is_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.COUNSELOR, UserRole.GRADE_LEADER)),
):
    """问题库列表 (管理员+心理教师可读)"""
    conditions = [
        MentalHealthQuestion.school_id == current_user.school_id,
    ]
    if scale_name:
        conditions.append(MentalHealthQuestion.scale_name == scale_name)
    if is_active is not None:
        conditions.append(MentalHealthQuestion.is_active == is_active)

    stmt = (
        select(MentalHealthQuestion)
        .where(*conditions)
        .order_by(
            MentalHealthQuestion.scale_name,
            MentalHealthQuestion.dimension,
            MentalHealthQuestion.question_no,
        )
    )
    result = await db.execute(stmt)
    questions = result.scalars().all()

    # 获取所有量表名
    scale_names_result = await db.execute(
        select(MentalHealthQuestion.scale_name.distinct()).where(
            MentalHealthQuestion.school_id == current_user.school_id,
            MentalHealthQuestion.is_active == True,
        )
    )
    scale_names = [row[0] for row in scale_names_result.all() if row[0]]

    outs = [
        QuestionOut(
            id=q.id,
            scale_name=q.scale_name,
            dimension=q.dimension,
            question_no=q.question_no,
            question_text=q.question_text,
            option_type=q.option_type,
            reverse_scoring=q.reverse_scoring,
            is_active=q.is_active,
        )
        for q in questions
    ]

    return QuestionListResponse(
        questions=outs,
        scale_names=scale_names,
        total=len(outs),
    )


@router.post("/questions/seed")
async def seed_questions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    幂等初始化 MSSMHS-55 题目库 (仅管理员)。
    首次调用会插入 55 道标准题，后续调用跳过已有题。
    """
    count = await seed_mssmhs_questions(db, current_user.school_id)
    return {
        "status": "ok",
        "seeded": count,
        "message": f"已初始化 {count} 道 MSSMHS-55 题目"
        if count > 0
        else "题目库已存在，无需重复初始化",
    }


# ═══════════════════════════════════════════════════════════════
# 📊 统计仪表盘
# ═══════════════════════════════════════════════════════════════


@router.get("/dashboard", response_model=PsychDashboardResponse)
async def get_dashboard(
    grade_id: int | None = Query(None),
    class_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)
    ),
):
    """心理筛查仪表盘聚合统计"""
    scope = _get_scope_params(current_user)
    if scope.get("grade_id"):
        grade_id = scope["grade_id"]
    if scope.get("class_id"):
        class_id = scope["class_id"]

    stats = await get_dashboard_stats(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        class_id=class_id,
    )
    return PsychDashboardResponse(**stats)
