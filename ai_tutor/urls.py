from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LessonTopicViewSet, TutorSessionViewSet, TeacherAvatarSettingViewSet

router = DefaultRouter()
router.register(r'topics', LessonTopicViewSet, basename='lesson-topic')
router.register(r'sessions', TutorSessionViewSet, basename='tutor-session')
router.register(r'avatar-settings', TeacherAvatarSettingViewSet, basename='avatar-setting')

urlpatterns = [
    path('', include(router.urls)),
]
