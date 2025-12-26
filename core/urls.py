from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SchoolSettingsViewSet

router = DefaultRouter()
router.register(r'settings', SchoolSettingsViewSet, basename='settings')

urlpatterns = [
    path('', include(router.urls)),
]
