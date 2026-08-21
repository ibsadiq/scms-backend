# results/urls.py  (or examination/urls.py — match your actual app name)
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from examination.views.grading import (
    GradingSchemeViewSet, AssessmentComponentViewSet,
    GradeRuleViewSet, PromotionRuleViewSet,
)
from examination.views.assessment import (
    AssessmentSessionViewSet, AssessmentEntryViewSet, MarkedScriptViewSet,
)
from examination.views.result import (
    TermResultViewSet, AnnualResultViewSet, ReportCardViewSet, ResultAuditLogViewSet
)
from examination.views.cumulative import (
    CumulativeResultViewSet, AcademicTranscriptViewSet, ResultAmendmentViewSet
)

router = DefaultRouter()

# Grading setup
router.register(r"grading-schemes", GradingSchemeViewSet, basename="grading-scheme")
router.register(r"assessment-components", AssessmentComponentViewSet, basename="assessment-component")
router.register(r"grade-rules", GradeRuleViewSet, basename="grade-rule")
router.register(r"promotion-rules", PromotionRuleViewSet, basename="promotion-rule")

# Assessment / score entry
router.register(r"assessment-sessions", AssessmentSessionViewSet, basename="assessment-session")
router.register(r"assessment-entries", AssessmentEntryViewSet, basename="assessment-entry")
router.register(r"marked-scripts", MarkedScriptViewSet, basename="marked-script")

# Results
router.register(r"term-results", TermResultViewSet, basename="term-result")
router.register(r"annual-results", AnnualResultViewSet, basename="annual-result")
router.register(r"report-cards", ReportCardViewSet, basename="report-card")
router.register(r"cumulative-results", CumulativeResultViewSet, basename="cumulative-result")
router.register(r"transcripts", AcademicTranscriptViewSet, basename="transcript")
router.register(r"amendments", ResultAmendmentViewSet, basename="result-amendment")
router.register(r"audit-logs", ResultAuditLogViewSet, basename="result-audit-log")

urlpatterns = [
    path("", include(router.urls)),
]