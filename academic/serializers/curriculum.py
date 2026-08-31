from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from academic.models import (
    Curriculum,
    CurriculumSubject,
    GradeLevel,
    Topic,
    CurriculumTopic,
    CurriculumGuidance,
    SubTopic,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    CurriculumResource,
    CurriculumAssignment,
    Subject,
)


class CurriculumClassSerializer(serializers.ModelSerializer):
    section_display = serializers.CharField(source="get_section_display", read_only=True)
    subjects_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = GradeLevel
        fields = [
            "id",
            "system_code",
            "default_name",
            "alias",
            "section",
            "section_display",
            "sequence_order",
            "min_age",
            "max_age",
            "graduation_note",
            "subjects_count",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class CurriculumSubjectSummarySerializer(serializers.ModelSerializer):
    """Lightweight subject navigation data for one curriculum grade level."""

    description = serializers.SerializerMethodField()
    themes_count = serializers.IntegerField(read_only=True, default=0)
    topics_count = serializers.IntegerField(read_only=True, default=0)
    objectives_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = CurriculumSubject
        fields = [
            "id",
            "name",
            "code",
            "description",
            "themes_count",
            "topics_count",
            "objectives_count",
            "is_active",
        ]

    def get_description(self, obj) -> str:
        return obj.description or (obj.subject.description if obj.subject else "")


class CurriculumTopicSummarySerializer(serializers.ModelSerializer):
    """Lightweight topic navigation data without nested curriculum content."""

    topic_id = serializers.IntegerField(source="topic.id", read_only=True, allow_null=True)
    subtopics_count = serializers.IntegerField(read_only=True, default=0)
    objectives_count = serializers.IntegerField(read_only=True, default=0)
    has_guidance = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = CurriculumTopic
        fields = [
            "id",
            "topic_id",
            "name",
            "theme",
            "order",
            "subtopics_count",
            "objectives_count",
            "has_guidance",
            "is_active",
        ]


class SubTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTopic
        fields = ["id", "topic", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class TopicSerializer(serializers.ModelSerializer):
    subtopics = SubTopicSerializer(many=True, read_only=True)
    grade_level_name = serializers.CharField(source="grade_level.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, allow_null=True)

    class Meta:
        model = Topic
        fields = [
            "id",
            "name",
            "grade_level",
            "grade_level_name",
            "subject",
            "subject_name",
            "subtopics",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class LearningObjectiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningObjective
        fields = [
            "id",
            "curriculum_topic",
            "subtopic",
            "description",
            "order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CurriculumGuidanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumGuidance
        fields = [
            "id",
            "curriculum_topic",
            "teacher_activities",
            "learner_activities",
            "teaching_learning_materials",
            "evaluation_guide",
            "notes",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class LearningObjectiveDetailSerializer(serializers.ModelSerializer):
    subtopic_name = serializers.CharField(source="subtopic.name", read_only=True, allow_null=True)
    import_batch_id = serializers.IntegerField(source="last_import_batch_id", read_only=True)

    class Meta:
        model = LearningObjective
        fields = [
            "id", "description", "order", "is_active", "subtopic",
            "subtopic_name", "source_page", "source_reference",
            "import_batch_id", "created_at", "updated_at",
        ]


class CurriculumTopicDetailSerializer(serializers.ModelSerializer):
    topic_id = serializers.IntegerField(source="topic.id", read_only=True, allow_null=True)
    subtopics = SubTopicSerializer(many=True, read_only=True)
    learning_objectives = LearningObjectiveDetailSerializer(many=True, read_only=True)
    guidance = CurriculumGuidanceSerializer(read_only=True)
    source_title = serializers.CharField(source="source.title", read_only=True)
    source_filename = serializers.CharField(source="source.original_filename", read_only=True)
    source_type = serializers.CharField(source="source.source_type", read_only=True)
    source_checksum = serializers.CharField(source="source.checksum_sha256", read_only=True)
    import_batch_id = serializers.IntegerField(source="last_import_batch_id", read_only=True)
    import_batch_status = serializers.CharField(source="last_import_batch.status", read_only=True)

    class Meta:
        model = CurriculumTopic
        fields = [
            "id", "topic_id", "name", "theme", "content_summary", "order",
            "is_active", "subtopics", "learning_objectives", "guidance",
            "source_title", "source_filename", "source_type", "source_checksum",
            "source_page_start", "source_page_end", "source_reference",
            "import_batch_id", "import_batch_status", "created_at", "updated_at",
        ]


class CurriculumTopicSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="name", read_only=True)
    guidance = CurriculumGuidanceSerializer(read_only=True)
    learning_objectives = LearningObjectiveSerializer(many=True, read_only=True)

    class Meta:
        model = CurriculumTopic
        fields = [
            "id",
            "curriculum_subject",
            "name",
            "topic",
            "topic_name",
            "theme",
            "content_summary",
            "order",
            "is_active",
            "guidance",
            "learning_objectives",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CurriculumSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True, allow_null=True)
    grade_level_name = serializers.CharField(source="grade_level.__str__", read_only=True)
    curriculum_name = serializers.CharField(source="curriculum.name", read_only=True)
    curriculum_id = serializers.IntegerField(read_only=True)
    grade_level_id = serializers.IntegerField(read_only=True)
    subject_id = serializers.IntegerField(read_only=True, allow_null=True)
    is_mapped = serializers.SerializerMethodField()

    def get_is_mapped(self, obj):
        return obj.subject_id is not None

    class Meta:
        model = CurriculumSubject
        fields = [
            "id",
            "curriculum",
            "curriculum_id",
            "curriculum_name",
            "name",
            "code",
            "subject",
            "subject_id",
            "subject_name",
            "grade_level",
            "grade_level_id",
            "grade_level_name",
            "is_mapped",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CurriculumSubjectMappingSerializer(serializers.Serializer):
    subject_id = serializers.PrimaryKeyRelatedField(
        source="subject",
        queryset=Subject.objects.all(),
        allow_null=True,
    )


class CurriculumSerializer(serializers.ModelSerializer):
    grade_levels = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Curriculum
        fields = [
            "id",
            "name",
            "authority_type",
            "authority_name",
            "version",
            "description",
            "effective_from",
            "effective_to",
            "is_active",
            "grade_levels",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_grade_levels(self, obj) -> list[str]:
        if (
            hasattr(obj, "_prefetched_objects_cache")
            and "subjects" in obj._prefetched_objects_cache
        ):
            levels = []
            seen = set()
            sorted_subjects = sorted(
                obj.subjects.all(),
                key=lambda s: (s.grade_level.sequence_order if s.grade_level else 0),
            )
            for s in sorted_subjects:
                if s.grade_level_id and s.grade_level_id not in seen:
                    seen.add(s.grade_level_id)
                    levels.append(s.grade_level.alias or s.grade_level.default_name)
            return levels

        grade_levels = (
            GradeLevel.objects.filter(curriculum_subjects__curriculum=obj)
            .distinct()
            .order_by("sequence_order")
        )
        return [gl.alias or gl.default_name for gl in grade_levels]


class PublishedSchemeEntrySerializer(serializers.ModelSerializer):
    entry_type_display = serializers.CharField(source="get_entry_type_display", read_only=True)
    topic_name = serializers.CharField(source="curriculum_topic.name", read_only=True)
    subtopic_details = SubTopicSerializer(source="subtopics", many=True, read_only=True)
    objective_details = LearningObjectiveDetailSerializer(
        source="learning_objectives", many=True, read_only=True
    )
    source_title = serializers.CharField(source="source.title", read_only=True)
    source_type = serializers.CharField(source="source.source_type", read_only=True)

    class Meta:
        model = PublishedSchemeEntry
        fields = [
            "id", "published_scheme", "term_number", "week_start", "week_end",
            "entry_type", "entry_type_display", "curriculum_topic", "topic_name",
            "subtopics", "learning_objectives", "title", "content_summary", "order",
            "subtopic_details", "objective_details",
            "teacher_activities", "pupil_activities", "learning_resources", "source",
            "source_page_start", "source_page_end", "source_reference", "import_batch",
            "source_title", "source_type",
            "is_active", "created_at", "updated_at",
        ]


class PublishedSchemeSerializer(serializers.ModelSerializer):
    entries = PublishedSchemeEntrySerializer(many=True, read_only=True)
    source_title = serializers.CharField(source="source.title", read_only=True)
    source_type = serializers.CharField(source="source.source_type", read_only=True)
    curriculum_id = serializers.IntegerField(
        source="curriculum_subject.curriculum_id", read_only=True
    )
    curriculum_name = serializers.CharField(
        source="curriculum_subject.curriculum.name", read_only=True
    )
    curriculum_subject_name = serializers.CharField(
        source="curriculum_subject.name", read_only=True
    )
    grade_level_name = serializers.CharField(
        source="curriculum_subject.grade_level.__str__", read_only=True
    )
    grade_level_id = serializers.IntegerField(
        source="curriculum_subject.grade_level_id", read_only=True
    )
    subject_id = serializers.IntegerField(
        source="curriculum_subject.subject_id", read_only=True, allow_null=True
    )
    subject_name = serializers.CharField(
        source="curriculum_subject.subject.name", read_only=True, allow_null=True
    )
    is_mapped = serializers.SerializerMethodField()
    entry_count = serializers.SerializerMethodField()
    terms_covered = serializers.SerializerMethodField()

    def get_is_mapped(self, obj):
        return obj.curriculum_subject.subject_id is not None

    def get_entry_count(self, obj):
        return len(obj.entries.all())

    def get_terms_covered(self, obj):
        return sorted({entry.term_number for entry in obj.entries.all()})

    class Meta:
        model = PublishedScheme
        fields = [
            "id", "curriculum_subject", "curriculum_subject_name", "curriculum_id",
            "curriculum_name", "grade_level_id", "grade_level_name", "subject_id", "subject_name",
            "is_mapped", "entry_count", "terms_covered",
            "name", "version", "description", "source",
            "source_title", "source_type", "is_active", "entries", "created_at", "updated_at",
        ]


class CurriculumResourceSerializer(serializers.ModelSerializer):
    resource_type_display = serializers.CharField(source="get_resource_type_display", read_only=True)
    topic_name = serializers.CharField(source="curriculum_topic.name", read_only=True)
    published_entry_title = serializers.CharField(
        source="published_scheme_entry.title", read_only=True
    )
    published_entry_week_start = serializers.IntegerField(
        source="published_scheme_entry.week_start", read_only=True
    )
    published_entry_week_end = serializers.IntegerField(
        source="published_scheme_entry.week_end", read_only=True
    )
    source_title = serializers.CharField(source="source.title", read_only=True)
    source_type = serializers.CharField(source="source.source_type", read_only=True)

    class Meta:
        model = CurriculumResource
        fields = [
            "id", "curriculum_subject", "curriculum_topic", "published_scheme_entry",
            "resource_type", "resource_type_display", "title", "content", "metadata",
            "topic_name", "published_entry_title", "published_entry_week_start",
            "published_entry_week_end",
            "order", "source", "source_page_start", "source_page_end", "source_reference",
            "source_title", "source_type", "import_batch", "is_active", "created_at", "updated_at",
        ]


class CurriculumAssignmentSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    curriculum_name = serializers.CharField(source="curriculum.name", read_only=True)
    curriculum_version = serializers.CharField(source="curriculum.version", read_only=True)
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    grade_level_name = serializers.CharField(source="grade_level.__str__", read_only=True)
    classroom_name = serializers.CharField(source="classroom.__str__", read_only=True)
    scope_type = serializers.CharField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.__str__", read_only=True)

    section = serializers.PrimaryKeyRelatedField(
        queryset=CurriculumAssignment._meta.get_field("section").remote_field.model.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    grade_level = serializers.PrimaryKeyRelatedField(
        queryset=CurriculumAssignment._meta.get_field("grade_level").remote_field.model.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    classroom = serializers.PrimaryKeyRelatedField(
        queryset=CurriculumAssignment._meta.get_field("classroom").remote_field.model.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = CurriculumAssignment
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "curriculum",
            "curriculum_name",
            "curriculum_version",
            "section",
            "section_name",
            "grade_level",
            "grade_level_name",
            "classroom",
            "classroom_name",
            "scope_type",
            "is_active",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]
        extra_kwargs = {
            "section": {"required": False, "allow_null": True},
            "grade_level": {"required": False, "allow_null": True},
            "classroom": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        instance = self.instance or CurriculumAssignment()
        for field, value in attrs.items():
            setattr(instance, field, value)

        # Clear scopes if not present in attrs and instance is new
        if not self.instance:
            if "section" not in attrs:
                instance.section = None
            if "grade_level" not in attrs:
                instance.grade_level = None
            if "classroom" not in attrs:
                instance.classroom = None

        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                getattr(exc, "message_dict", None) or exc.messages
            ) from exc

        return attrs
