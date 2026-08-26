from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
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

class CurriculumViewSet(viewsets.ModelViewSet):
    queryset = Curriculum.objects.all()
    serializer_class = CurriculumSerializer
    permission_classes = [IsAuthenticated]

class CurriculumSubjectViewSet(viewsets.ModelViewSet):
    queryset = CurriculumSubject.objects.select_related("subject", "grade_level")
    serializer_class = CurriculumSubjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum"]

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
