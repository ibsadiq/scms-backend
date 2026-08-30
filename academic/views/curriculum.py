from django.db.models import BooleanField, Count, Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from academic.models import GradeLevel
from academic.permissions import IsAcademicAdminOrReadOnly
from academic.models.curriculum import (
    Curriculum,
    CurriculumSubject,
    CurriculumTopic,
    Topic,
    SubTopic,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    CurriculumResource,
)
from academic.serializers.curriculum import (
    CurriculumClassSerializer,
    CurriculumSerializer,
    CurriculumSubjectSummarySerializer,
    CurriculumSubjectSerializer,
    CurriculumTopicDetailSerializer,
    CurriculumTopicSummarySerializer,
    CurriculumTopicSerializer,
    TopicSerializer,
    SubTopicSerializer,
    LearningObjectiveSerializer,
    PublishedSchemeSerializer,
    PublishedSchemeEntrySerializer,
    CurriculumResourceSerializer,
)


class CurriculumViewSet(viewsets.ModelViewSet):
    queryset = Curriculum.objects.prefetch_related("subjects__grade_level").all()
    serializer_class = CurriculumSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]

    def get_queryset(self):
        queryset = Curriculum.objects.all()
        if self.action in {"list", "retrieve"}:
            return queryset.prefetch_related("subjects__grade_level")
        return queryset

    @action(detail=True, methods=["get"], url_path="classes")
    def classes(self, request, pk=None):
        curriculum = self.get_object()
        queryset = (
            GradeLevel.objects.filter(curriculum_subjects__curriculum=curriculum)
            .annotate(
                subjects_count=Count(
                    "curriculum_subjects",
                    filter=Q(curriculum_subjects__curriculum=curriculum, curriculum_subjects__is_active=True),
                    distinct=True,
                )
            )
            .distinct()
            .order_by("sequence_order")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CurriculumClassSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = CurriculumClassSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get"],
        url_path=r"classes/(?P<class_id>[^/.]+)/subjects",
    )
    def class_subjects(self, request, pk=None, class_id=None):
        """Return lightweight subject summaries for one curriculum grade level."""

        curriculum = self.get_object()
        grade_level = get_object_or_404(
            GradeLevel.objects.filter(
                curriculum_subjects__curriculum=curriculum,
            ).distinct(),
            pk=class_id,
        )
        queryset = (
            CurriculumSubject.objects.filter(
                curriculum=curriculum,
                grade_level=grade_level,
                is_active=True,
            )
            .select_related("subject")
            .annotate(
                themes_count=Count(
                    "curriculum_topics__theme",
                    filter=(
                        Q(curriculum_topics__is_active=True)
                        & ~Q(curriculum_topics__theme="")
                    ),
                    distinct=True,
                ),
                topics_count=Count(
                    "curriculum_topics",
                    filter=Q(curriculum_topics__is_active=True),
                    distinct=True,
                ),
                objectives_count=Count(
                    "curriculum_topics__learning_objectives",
                    filter=(
                        Q(curriculum_topics__is_active=True)
                        & Q(curriculum_topics__learning_objectives__is_active=True)
                    ),
                    distinct=True,
                ),
            )
            .order_by("subject__name")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CurriculumSubjectSummarySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = CurriculumSubjectSummarySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get"],
        url_path=(
            r"classes/(?P<class_id>[^/.]+)/subjects/"
            r"(?P<subject_id>[^/.]+)/content"
        ),
    )
    def subject_content(self, request, pk=None, class_id=None, subject_id=None):
        """Return lightweight theme/topic summaries for one subject mapping."""

        curriculum = self.get_object()
        curriculum_subject = get_object_or_404(
            CurriculumSubject.objects.select_related("subject", "grade_level"),
            pk=subject_id,
            curriculum=curriculum,
            grade_level_id=class_id,
            is_active=True,
        )
        queryset = (
            CurriculumTopic.objects.filter(
                curriculum_subject=curriculum_subject,
                is_active=True,
            )
            .select_related("topic")
            .annotate(
                subtopics_count=Count(
                    "topic__subtopics",
                    filter=Q(topic__subtopics__is_active=True),
                    distinct=True,
                ),
                objectives_count=Count(
                    "learning_objectives",
                    filter=Q(learning_objectives__is_active=True),
                    distinct=True,
                ),
                has_guidance=Exists(
                    CurriculumTopic.objects.filter(
                        pk=OuterRef("pk"),
                        guidance__isnull=False,
                    ),
                    output_field=BooleanField(),
                ),
            )
            .order_by("order", "topic__name")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CurriculumTopicSummarySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = CurriculumTopicSummarySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get"],
        url_path=(
            r"classes/(?P<class_id>[^/.]+)/subjects/"
            r"(?P<subject_id>[^/.]+)/topics/(?P<topic_id>[^/.]+)"
        ),
    )
    def topic_detail(self, request, pk=None, class_id=None, subject_id=None, topic_id=None):
        curriculum = self.get_object()
        topic = get_object_or_404(
            CurriculumTopic.objects.select_related(
                "topic", "source", "last_import_batch", "guidance",
            ).prefetch_related(
                "topic__subtopics",
                "learning_objectives__subtopic",
            ),
            pk=topic_id,
            curriculum_subject_id=subject_id,
            curriculum_subject__curriculum=curriculum,
            curriculum_subject__grade_level_id=class_id,
        )
        return Response(CurriculumTopicDetailSerializer(topic).data)

class CurriculumSubjectViewSet(viewsets.ModelViewSet):
    queryset = CurriculumSubject.objects.select_related("subject", "grade_level")
    serializer_class = CurriculumSubjectSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum", "grade_level"]

class CurriculumTopicViewSet(viewsets.ModelViewSet):
    queryset = CurriculumTopic.objects.select_related("topic", "guidance").prefetch_related(
        "learning_objectives"
    )
    serializer_class = CurriculumTopicSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum_subject"]

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.select_related("grade_level", "subject").prefetch_related(
        "subtopics"
    )
    serializer_class = TopicSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["grade_level", "subject"]

class SubTopicViewSet(viewsets.ModelViewSet):
    queryset = SubTopic.objects.all()
    serializer_class = SubTopicSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["topic"]

class LearningObjectiveViewSet(viewsets.ModelViewSet):
    queryset = LearningObjective.objects.all()
    serializer_class = LearningObjectiveSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum_topic", "subtopic"]


class PublishedSchemeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PublishedScheme.objects.select_related(
        "curriculum_subject__subject", "curriculum_subject__grade_level", "source"
    ).prefetch_related("entries")
    serializer_class = PublishedSchemeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["curriculum_subject", "version", "is_active"]


class PublishedSchemeEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PublishedSchemeEntry.objects.select_related(
        "published_scheme__curriculum_subject", "curriculum_topic__topic", "source", "import_batch"
    ).prefetch_related("subtopics", "learning_objectives")
    serializer_class = PublishedSchemeEntrySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = [
        "published_scheme", "term_number", "week_start", "entry_type", "curriculum_topic", "is_active"
    ]


class CurriculumResourceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CurriculumResource.objects.select_related(
        "curriculum_subject__subject", "curriculum_subject__grade_level",
        "curriculum_topic__topic", "published_scheme_entry", "source", "import_batch",
    )
    serializer_class = CurriculumResourceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = [
        "curriculum_subject", "curriculum_topic", "published_scheme_entry",
        "resource_type", "is_active",
    ]
