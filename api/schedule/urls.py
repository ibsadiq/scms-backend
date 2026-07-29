from django.urls import path, include
from rest_framework.routers import DefaultRouter

from schedule.views import (
    RoomViewSet,
    PeriodSlotViewSet,
    TeacherAvailabilityViewSet,
    TimetableEntryViewSet,
    GenerateTimetableView,
)

router = DefaultRouter()
router.register(r"rooms", RoomViewSet, basename="rooms")
router.register(r"period-slots", PeriodSlotViewSet, basename="period-slots")
router.register(r"teacher-availability", TeacherAvailabilityViewSet, basename="teacher-availability")
router.register(r"timetable", TimetableEntryViewSet, basename="timetable")

urlpatterns = [
    path("", include(router.urls)),
    path("generate-timetable/", GenerateTimetableView.as_view(), name="generate_timetable"),
]