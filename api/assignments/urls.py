"""
Assignment URL Configuration - Phase 1.7
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from assignments.views import (
    TeacherAssignmentViewSet,
    StudentAssignmentViewSet,
    ParentAssignmentViewSet
)

router = DefaultRouter()

# Teacher endpoints
router.register(
    r'teacher/assignments',
    TeacherAssignmentViewSet,
    basename='teacher-assignment'
)

# Student endpoints
router.register(
    r'student/assignments',
    StudentAssignmentViewSet,
    basename='student-assignment'
)

# Parent endpoints
router.register(
    r'parent/assignments',
    ParentAssignmentViewSet,
    basename='parent-assignment'
)

urlpatterns = [
    path('', include(router.urls)),
]
