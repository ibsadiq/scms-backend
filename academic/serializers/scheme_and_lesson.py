from rest_framework import serializers
from administration.models import AcademicYear, Term
from academic.models import (
    SchemeOfWork,
    SchemeOfWorkItem,
    LessonPlan,
    LessonDelivery,
    LessonPlanMaterial,
    PublishedScheme,
    CurriculumResource,
    AllocatedSubject,
)


class RejectionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=True, allow_blank=False)


class PublishedSchemeAdoptionSerializer(serializers.Serializer):
    published_scheme = serializers.PrimaryKeyRelatedField(
        queryset=PublishedScheme.objects.filter(is_active=True)
    )
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all()
    )
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all()
    )


class LessonPlanFromSchemeItemSerializer(serializers.Serializer):
    scheme_item = serializers.PrimaryKeyRelatedField(queryset=SchemeOfWorkItem.objects.all())
    allocation = serializers.PrimaryKeyRelatedField(queryset=AllocatedSubject.objects.all())
    lesson_date = serializers.DateField()
    duration_minutes = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class CurriculumResourceMaterialSerializer(serializers.Serializer):
    curriculum_resource = serializers.PrimaryKeyRelatedField(
        queryset=CurriculumResource.objects.filter(is_active=True)
    )


class SchemeOfWorkItemSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(
        source="curriculum_topic.topic.name", read_only=True, allow_null=True
    )
    subtopic_details = serializers.SerializerMethodField()
    objective_details = serializers.SerializerMethodField()
    official_source = serializers.SerializerMethodField()
    lesson_planning = serializers.SerializerMethodField()

    def get_subtopic_details(self, obj):
        return [{"id": item.id, "name": item.name} for item in obj.subtopics.all()]

    def get_objective_details(self, obj):
        return [
            {"id": item.id, "description": item.description, "order": item.order}
            for item in obj.learning_objectives.all()
        ]

    def get_official_source(self, obj):
        entry = obj.published_scheme_entry
        if not entry:
            return None
        published = entry.published_scheme
        return {
            "published_scheme_id": published.id,
            "published_scheme_name": published.name,
            "published_scheme_version": published.version,
            "published_entry_id": entry.id,
            "entry_type": entry.entry_type,
            "week_start": entry.week_start,
            "week_end": entry.week_end,
            "curriculum_topic": entry.curriculum_topic_id,
            "title": entry.title,
            "content_summary": entry.content_summary,
            "teacher_activities": entry.teacher_activities,
            "learner_activities": entry.pupil_activities,
            "learning_resources": entry.learning_resources,
            "order": entry.order,
        }

    def get_lesson_planning(self, obj):
        from academic.services.lesson_plan_service import LessonPlanService
        permitted = obj.entry_type in LessonPlanService.PLANNABLE_ENTRY_TYPES
        return {
            "permitted": permitted,
            "multiple_plans_permitted": permitted,
            "reason": "" if permitted else (
                f"{obj.get_entry_type_display()} entries do not create conventional lesson plans."
            ),
            "lesson_plan_count": obj.lesson_plans.count(),
        }

    class Meta:
        model = SchemeOfWorkItem
        fields = [
            "id",
            "scheme",
            "published_scheme_entry",
            "entry_type",
            "week_start",
            "week_end",
            "curriculum_topic",
            "topic_name",
            "subtopics",
            "subtopic_details",
            "learning_objectives",
            "objective_details",
            "title",
            "notes",
            "content_summary",
            "teacher_activities",
            "learner_activities",
            "learning_resources",
            "order",
            "official_source",
            "lesson_planning",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["published_scheme_entry", "created_at", "updated_at"]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from academic.services.scheme_of_work_service import SchemeOfWorkService

        scheme = attrs.get("scheme") or getattr(self.instance, "scheme", None)
        topic = (
            attrs["curriculum_topic"]
            if "curriculum_topic" in attrs
            else getattr(self.instance, "curriculum_topic", None)
        )
        subtopics = attrs.get("subtopics", None)
        objectives = attrs.get("learning_objectives", None)
        if self.instance:
            if subtopics is None:
                subtopics = self.instance.subtopics.all()
            if objectives is None:
                objectives = self.instance.learning_objectives.all()
        try:
            candidate = self.instance or SchemeOfWorkItem()
            for field, value in attrs.items():
                if field not in {"subtopics", "learning_objectives"}:
                    setattr(candidate, field, value)
            candidate.full_clean(exclude=["id"])
            SchemeOfWorkService.validate_item(
                scheme=scheme,
                curriculum_topic=topic,
                subtopics=subtopics or [],
                learning_objectives=objectives or [],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                getattr(exc, "message_dict", None) or exc.messages
            ) from exc
        return attrs


class SchemeOfWorkSerializer(serializers.ModelSerializer):
    items = SchemeOfWorkItemSerializer(many=True, read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    subject_name = serializers.CharField(source="curriculum_subject.subject.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.__str__", read_only=True)
    responsible_teacher_name = serializers.CharField(source="responsible_teacher.__str__", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.__str__", read_only=True)
    curriculum_name = serializers.CharField(source="curriculum_subject.curriculum.name", read_only=True)
    grade_level_name = serializers.SerializerMethodField()
    section_name = serializers.SerializerMethodField()
    published_sources = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_grade_level_name(self, obj):
        return str(obj.curriculum_subject.grade_level)

    def get_section_name(self, obj):
        return obj.curriculum_subject.grade_level.get_section_display()

    def get_published_sources(self, obj):
        sources = {}
        for item in obj.items.all():
            entry = item.published_scheme_entry
            if entry:
                published = entry.published_scheme
                sources[published.id] = {
                    "id": published.id,
                    "name": published.name,
                    "version": published.version,
                }
        return list(sources.values())

    def get_permissions(self, obj):
        from academic.models import AcademicWorkflow, SchemeOfWorkStatus
        from academic.services.academic_authority_service import AcademicAuthorityService
        from academic.services.academic_planning_access_service import AcademicPlanningAccessService

        request = self.context.get("request")
        actor = getattr(request, "user", None)
        can_manage = bool(actor and AcademicPlanningAccessService.can_manage_scheme(actor, obj))
        can_review = bool(actor and AcademicAuthorityService.can_approve(
            actor=actor,
            workflow=AcademicWorkflow.SCHEME_OF_WORK,
            subject=obj.curriculum_subject.subject,
            section=obj.curriculum_subject.grade_level.section,
            academic_year=obj.academic_year,
            creator=obj.responsible_teacher,
        ))
        return {
            "can_edit": can_manage and obj.status == SchemeOfWorkStatus.DRAFT,
            "can_submit": can_manage and obj.status == SchemeOfWorkStatus.DRAFT,
            "can_review": can_review and obj.status == SchemeOfWorkStatus.SUBMITTED,
            "can_reopen": can_manage and obj.status == SchemeOfWorkStatus.REJECTED,
        }

    class Meta:
        model = SchemeOfWork
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "term",
            "term_name",
            "curriculum_subject",
            "curriculum_name",
            "subject_name",
            "grade_level_name",
            "section_name",
            "created_by",
            "created_by_name",
            "responsible_teacher",
            "responsible_teacher_name",
            "status",
            "submitted_at",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "rejection_reason",
            "is_active",
            "items",
            "published_sources",
            "permissions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_by",
            "responsible_teacher",
            "status",
            "submitted_at",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            candidate = self.instance or SchemeOfWork()
            for field, value in attrs.items():
                setattr(candidate, field, value)
            candidate.full_clean(exclude=["id", "created_by", "responsible_teacher"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                getattr(exc, "message_dict", None) or exc.messages
            ) from exc
        return attrs


class LessonPlanMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonPlanMaterial
        fields = [
            "id",
            "lesson_plan",
            "title",
            "description",
            "file",
            "external_url",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from academic.services.lesson_material_service import LessonPlanMaterialService

        lesson_plan = attrs.get("lesson_plan") or getattr(self.instance, "lesson_plan", None)
        file = attrs.get("file", getattr(self.instance, "file", None))
        external_url = attrs.get(
            "external_url", getattr(self.instance, "external_url", "")
        )
        try:
            LessonPlanMaterialService.validate_material(
                lesson_plan=lesson_plan,
                file=file,
                external_url=external_url,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return attrs


class LessonPlanSerializer(serializers.ModelSerializer):
    materials = LessonPlanMaterialSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source="allocation.subject.name", read_only=True)
    classroom_name = serializers.CharField(source="allocation.class_room.__str__", read_only=True)
    teacher_name = serializers.CharField(source="allocation.teacher_name.__str__", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.__str__", read_only=True)
    scheme_context = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_scheme_context(self, obj):
        item = obj.scheme_item
        official = item.published_scheme_entry
        return {
            "scheme_id": item.scheme_id,
            "scheme_item_id": item.id,
            "entry_type": item.entry_type,
            "week_start": item.week_start,
            "week_end": item.week_end,
            "topic_name": item.curriculum_topic.topic.name if item.curriculum_topic_id else None,
            "school_title": item.title,
            "official_scheme_name": official.published_scheme.name if official else None,
            "official_scheme_version": official.published_scheme.version if official else None,
            "available_subtopics": [
                {"id": item.id, "name": item.name} for item in item.subtopics.all()
            ],
            "available_objectives": [
                {"id": objective.id, "description": objective.description, "order": objective.order}
                for objective in item.learning_objectives.all()
            ],
        }

    def get_permissions(self, obj):
        from academic.models import AcademicWorkflow
        from academic.services.academic_authority_service import AcademicAuthorityService
        from academic.services.academic_planning_access_service import AcademicPlanningAccessService
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        can_manage = bool(actor and AcademicPlanningAccessService.can_manage_plan(actor, obj))
        can_review = bool(actor and AcademicAuthorityService.can_approve(
            actor=actor, workflow=AcademicWorkflow.LESSON_PLAN,
            subject=obj.allocation.subject,
            section=obj.allocation.class_room.grade_level.section,
            academic_year=obj.allocation.academic_year,
            creator=obj.allocation.teacher_name,
        ))
        return {
            "can_edit": can_manage and obj.status == "DRAFT",
            "can_manage_materials": can_manage and obj.status in {"DRAFT", "REJECTED"},
            "can_submit": can_manage and obj.status == "DRAFT",
            "can_review": can_review and obj.status == "SUBMITTED",
            "can_reopen": can_manage and obj.status == "REJECTED",
        }

    class Meta:
        model = LessonPlan
        fields = [
            "id",
            "scheme_item",
            "allocation",
            "subject_name",
            "classroom_name",
            "teacher_name",
            "lesson_date",
            "title",
            "duration_minutes",
            "learning_objectives",
            "subtopics",
            "previous_knowledge",
            "introduction",
            "lesson_content",
            "teacher_activities",
            "learner_activities",
            "teaching_materials",
            "evaluation",
            "assignment_notes",
            "references",
            "status",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "reviewed_by_name",
            "materials",
            "scheme_context",
            "permissions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from academic.services.lesson_plan_service import LessonPlanService

        scheme_item = attrs.get("scheme_item") or getattr(self.instance, "scheme_item", None)
        allocation = attrs.get("allocation") or getattr(self.instance, "allocation", None)
        objectives = attrs.get("learning_objectives", None)
        subtopics = attrs.get("subtopics", None)
        if self.instance:
            if objectives is None:
                objectives = self.instance.learning_objectives.all()
            if subtopics is None:
                subtopics = self.instance.subtopics.all()
        try:
            if self.instance is None:
                LessonPlanService.require_plannable_entry(scheme_item)
            candidate = self.instance or LessonPlan()
            for field, value in attrs.items():
                if field not in {"learning_objectives", "subtopics"}:
                    setattr(candidate, field, value)
            candidate.full_clean(exclude=["id"])
            LessonPlanService.validate_context(
                scheme_item=scheme_item, allocation=allocation
            )
            LessonPlanService.validate_objectives(
                scheme_item=scheme_item, objectives=objectives or []
            )
            LessonPlanService.validate_subtopics(
                scheme_item=scheme_item, subtopics=subtopics or []
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                getattr(exc, "message_dict", None) or exc.messages
            ) from exc
        return attrs


class LessonDeliverySerializer(serializers.ModelSerializer):
    lesson_plan_title = serializers.CharField(source="lesson_plan.__str__", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.__str__", read_only=True)

    class Meta:
        model = LessonDelivery
        fields = [
            "id",
            "lesson_plan",
            "lesson_plan_title",
            "status",
            "taught_at",
            "objectives_covered",
            "subtopics_covered",
            "teacher_notes",
            "learner_response",
            "follow_up_required",
            "follow_up_notes",
            "next_lesson_notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["recorded_by", "created_at", "updated_at"]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from academic.services.lesson_delivery_service import LessonDeliveryService

        plan = attrs.get("lesson_plan") or getattr(self.instance, "lesson_plan", None)
        objectives = attrs.get("objectives_covered", None)
        subtopics = attrs.get("subtopics_covered", None)
        if self.instance:
            if objectives is None:
                objectives = self.instance.objectives_covered.all()
            if subtopics is None:
                subtopics = self.instance.subtopics_covered.all()
        status_value = attrs.get("status", getattr(self.instance, "status", None))
        try:
            LessonDeliveryService.validate_coverage(
                lesson_plan=plan,
                objectives_covered=objectives or [],
                subtopics_covered=subtopics or [],
            )
            LessonDeliveryService.validate_status(
                status=status_value,
                objectives_covered=objectives or [],
                subtopics_covered=subtopics or [],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return attrs
