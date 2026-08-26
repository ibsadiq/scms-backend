from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from academic.models import GradeLevel
from academic.models.curriculum import (
    Curriculum,
    CurriculumSubject,
    CurriculumTopic,
    Topic,
    SubTopic,
    LearningObjective,
)
from academic.serializers.curriculum import (
    CurriculumSerializer,
    CurriculumSubjectSerializer,
    CurriculumTopicSerializer,
    TopicSerializer,
    SubTopicSerializer,
    LearningObjectiveSerializer,
)
from academic.serializers import GradeLevelSerializer

class CurriculumViewSet(viewsets.ModelViewSet):
    queryset = Curriculum.objects.all()
    serializer_class = CurriculumSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["get"], url_path="classes")
    def classes(self, request, pk=None):
        curriculum = self.get_object()
        queryset = GradeLevel.objects.filter(
            curriculum_subjects__curriculum=curriculum
        ).distinct()
        page = self.paginate_queryset(queryset)
        serializer = GradeLevelSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

class CurriculumSubjectViewSet(viewsets.ModelViewSet):
    queryset = CurriculumSubject.objects.select_related("subject", "grade_level")
    serializer_class = CurriculumSubjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum", "grade_level"]

class CurriculumTopicViewSet(viewsets.ModelViewSet):
    queryset = CurriculumTopic.objects.select_related("topic", "guidance").prefetch_related(
        "learning_objectives"
    )
    serializer_class = CurriculumTopicSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum_subject"]

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.select_related("grade_level", "subject").prefetch_related(
        "subtopics"
    )
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["grade_level", "subject"]

class SubTopicViewSet(viewsets.ModelViewSet):
    queryset = SubTopic.objects.all()
    serializer_class = SubTopicSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["topic"]

class LearningObjectiveViewSet(viewsets.ModelViewSet):
    queryset = LearningObjective.objects.all()
    serializer_class = LearningObjectiveSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum_topic", "subtopic"]
