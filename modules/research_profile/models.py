"""
research_profile/models.py — 模型层

纯聚合模块，不建新表。
导入关联模块模型供 service 层跨表聚合使用。
"""

from modules.error_funnel.models import ErrorBookItem, KnowledgeGap
from modules.research_activities.models import (
    ResearchActivity,
    ResearchActivityAgenda,
    ResearchActivityParticipant,
)
from modules.research_lesson_prep.models import (
    ResearchLessonPlan,
    ResearchPlanReview,
    ResearchPlanVersion,
)
from modules.research_observation.models import (
    ResearchClassObservation,
    ResearchObservationAppeal,
    ResearchObservationRubric,
)

__all__ = [
    # research_lesson_prep
    "ResearchLessonPlan",
    "ResearchPlanVersion",
    "ResearchPlanReview",
    # research_observation
    "ResearchClassObservation",
    "ResearchObservationRubric",
    "ResearchObservationAppeal",
    # research_activities
    "ResearchActivity",
    "ResearchActivityParticipant",
    "ResearchActivityAgenda",
    # error_funnel
    "ErrorBookItem",
    "KnowledgeGap",
]
