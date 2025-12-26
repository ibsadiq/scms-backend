"""
Notifications API URLs - Phase 1.5
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from notifications.views import (
    NotificationViewSet,
    NotificationPreferenceViewSet,
    NotificationTemplateViewSet
)

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'notification-preferences', NotificationPreferenceViewSet, basename='notification-preferences')
router.register(r'notification-templates', NotificationTemplateViewSet, basename='notification-templates')

urlpatterns = [
    path('', include(router.urls)),
]
