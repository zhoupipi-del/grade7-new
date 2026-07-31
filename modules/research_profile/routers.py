"""
research_profile/routers.py — 教师教研全息画像 API 网关 (V3)

端点:
  GET  /teachers                       教研活跃教师列表(下拉选择)
  GET  /teachers/{teacher_id}/profile  教师四维教研全息画像(含评分)
"""

import logging

from core.models import User, UserRole
from core.routers import get_db, require_role
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from . import schemas, services

logger = logging.getLogger(__name__)
router = APIRouter(tags=["教师教研全息画像"])

# 教研画像对所有校内角色开放
PROFILE_ROLES = (UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.TEACHER)


@router.get("/teachers", response_model=list[schemas.ActiveTeacherResponse])
async def list_teachers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PROFILE_ROLES)),
):
    """获取全校活跃教师列表（支持画像面板快速筛选）"""
    if not current_user.school_id:
        raise HTTPException(status_code=400, detail="用户不属于任何有效学校租户")
    try:
        return await services.list_teachers(db, current_user.school_id)
    except Exception as e:
        logger.error(f"获取教师列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检索教师列表错误")


@router.get("/teachers/{teacher_id}/profile", response_model=schemas.TeacherResearchProfile)
async def get_teacher_profile(
    teacher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PROFILE_ROLES)),
):
    """获取指定教师在集体备课、监理听课及AI偏方应用层面的四维效能画像"""
    school_id = current_user.school_id
    if not school_id:
        raise HTTPException(status_code=400, detail="用户无合法多租户隔离标识")

    try:
        profile = await services.get_teacher_profile(db, teacher_id, school_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="教师不存在或不属于本校")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取教师教研画像失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="计算教师教研画像失败")


@router.get("/ranking", response_model=schemas.ResearchRankingResponse)
async def get_ranking(
    metric: str = "composite",
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PROFILE_ROLES)),
):
    """
    全校教研效能排行榜（领导视图）。

    按综合分(composite)或单维度(intensity/social/rigor/ai_integration)降序排序，
    返回 Top-N 教师。综合分 = intensity*0.30 + social*0.25 + rigor*0.30 + ai_integration*0.15。
    纯聚合查询，复用现有四维画像引擎，不写库。
    """
    school_id = current_user.school_id
    if not school_id:
        raise HTTPException(status_code=400, detail="用户无合法多租户隔离标识")
    # 防手滑：limit 收敛到合理区间
    limit = max(1, min(int(limit), 100))
    try:
        return await services.get_ranking(db, school_id, metric=metric, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取教研排行榜失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="计算教研排行榜失败")


@router.get(
    "/teachers/{teacher_id}/error-gap",
    response_model=schemas.TeacherErrorGapResponse,
)
async def get_teacher_error_gap(
    teacher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PROFILE_ROLES)),
):
    """
    教师任教范围学生错题断层归因（独立诊断维度，不计入四维综合分）。

    归因桥：精确优先(timetable_schedule_instances 锁具体任课老师) + 回退(teacher_subjects 年级学科组)。
    纯只读聚合，跨 error_funnel/teacher_mgmt/timetable/grades 模块，不写库。
    返回教学盲区关注度(0-100) —— 诊断信号，非教师考核惩罚分。
    """
    school_id = current_user.school_id
    if not school_id:
        raise HTTPException(status_code=400, detail="用户无合法多租户隔离标识")
    try:
        return await services.get_teacher_error_gap(db, teacher_id, school_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取教师错题断层归因失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="计算教师错题断层归因失败")
