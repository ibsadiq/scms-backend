from django.urls import path, include
from rest_framework.routers import DefaultRouter
from examination.views import (
    ExaminationViewSet,
    MarksViewSet,
    ResultViewSet,
    GradeScaleViewSet
)
from examination.views_result_computation import (
    TermResultViewSet,
    SubjectResultViewSet
)
from examination.views_report_cards import ReportCardViewSet
from examination.views_teacher import (
    TeacherDashboardViewSet,
    TeacherMarksViewSet,
    TeacherResultsViewSet
)
from examination.views_parent import (
    ParentDashboardViewSet,
    ParentResultsViewSet,
    ParentAttendanceViewSet,
    ParentFeeViewSet,
    ParentTimetableViewSet
)

router = DefaultRouter()
router.register(r'assessments', ExaminationViewSet, basename='assessments')
router.register(r'marks', MarksViewSet, basename='marks')
router.register(r'results', ResultViewSet, basename='results')
router.register(r'grade-scales', GradeScaleViewSet, basename='grade-scales')

# Result Computation endpoints (Phase 1.1)
router.register(r'term-results', TermResultViewSet, basename='term-results')
router.register(r'subject-results', SubjectResultViewSet, basename='subject-results')

# Report Card endpoints (Phase 1.2)
router.register(r'report-cards', ReportCardViewSet, basename='report-cards')

# Teacher-specific endpoints (Phase 1.3)
router.register(r'teacher', TeacherDashboardViewSet, basename='teacher')
router.register(r'teacher/marks', TeacherMarksViewSet, basename='teacher-marks')
router.register(r'teacher/results', TeacherResultsViewSet, basename='teacher-results')

# Parent-specific endpoints (Phase 1.4)
router.register(r'parent', ParentDashboardViewSet, basename='parent')
router.register(r'parent/results', ParentResultsViewSet, basename='parent-results')
router.register(r'parent/attendance', ParentAttendanceViewSet, basename='parent-attendance')
router.register(r'parent/fees', ParentFeeViewSet, basename='parent-fees')
router.register(r'parent/timetable', ParentTimetableViewSet, basename='parent-timetable')

urlpatterns = [
    path('', include(router.urls)),
]
