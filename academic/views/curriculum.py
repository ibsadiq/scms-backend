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
    queryset = CurriculumSubject.objects.all()
    serializer_class = CurriculumSubjectSerializer
    permission_classes = [IsAuthenticated]

class CurriculumTopicViewSet(viewsets.ModelViewSet):
    queryset = CurriculumTopic.objects.all()
    serializer_class = CurriculumTopicSerializer
    permission_classes = [IsAuthenticated]

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated]

class SubTopicViewSet(viewsets.ModelViewSet):
    queryset = SubTopic.objects.all()
    serializer_class = SubTopicSerializer
    permission_classes = [IsAuthenticated]

class LearningObjectiveViewSet(viewsets.ModelViewSet):
    queryset = LearningObjective.objects.all()
    serializer_class = LearningObjectiveSerializer
    permission_classes = [IsAuthenticated]
