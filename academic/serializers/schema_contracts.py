from rest_framework import serializers


class TeacherHomeroomClassSerializer(serializers.Serializer):
    id = serializers.CharField()
    classroom_id = serializers.IntegerField()
    classroom_name = serializers.CharField()
    grade_level_name = serializers.CharField()
    student_count = serializers.IntegerField()


class CurriculumContextSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["RESOLVED", "NO_CURRICULUM_ASSIGNED", "SUBJECT_UNMAPPED", "CONFIGURATION_CONFLICT"])
    curriculum_assignment_id = serializers.IntegerField(allow_null=True)
    assignment_scope = serializers.CharField(allow_null=True)
    curriculum_subject_id = serializers.IntegerField(allow_null=True)
    curriculum_subject_name = serializers.CharField(allow_null=True)
    curriculum_id = serializers.IntegerField(allow_null=True)
    curriculum_name = serializers.CharField(allow_null=True)
    candidate_count = serializers.IntegerField()


class TeacherAssignmentSerializer(TeacherHomeroomClassSerializer):
    id = serializers.IntegerField()
    allocation_id = serializers.IntegerField()
    subject_id = serializers.IntegerField(allow_null=True)
    subject_name = serializers.CharField()
    grade_level_id = serializers.IntegerField(allow_null=True)
    academic_year_id = serializers.IntegerField(allow_null=True)
    academic_year_name = serializers.CharField(allow_null=True)
    term_id = serializers.IntegerField(allow_null=True)
    term_name = serializers.CharField(allow_null=True)
    is_class_teacher = serializers.BooleanField()
    schedule = serializers.ListField(child=serializers.JSONField())
    curriculum_context = CurriculumContextSerializer()


class TeacherClassesResponseSerializer(serializers.Serializer):
    homeroom_classes = TeacherHomeroomClassSerializer(many=True)
    teaching_assignments = TeacherAssignmentSerializer(many=True)


class ClassroomStudentResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    admission_number = serializers.CharField(allow_null=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    photo = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=("active",))
    grade_level_name = serializers.CharField()
    classroom_name = serializers.CharField()
    score = serializers.FloatField(allow_null=True)
    remarks = serializers.CharField(allow_blank=True)


class TeacherScheduleEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    day_of_week = serializers.CharField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    subject_name = serializers.CharField()
    classroom_name = serializers.CharField()
    grade_level_name = serializers.CharField()
    room_number = serializers.CharField()
    is_active = serializers.BooleanField()


class TeacherAllocationSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject_id = serializers.IntegerField(allow_null=True)
    subject_name = serializers.CharField()
    classroom_id = serializers.IntegerField()
    classroom_name = serializers.CharField()
    grade_level_id = serializers.IntegerField(allow_null=True)
    grade_level_name = serializers.CharField()
    academic_year_id = serializers.IntegerField(allow_null=True)
    academic_year_name = serializers.CharField(allow_null=True)
    term_id = serializers.IntegerField(allow_null=True)
    term_name = serializers.CharField(allow_null=True)


class TeacherCurriculumInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    version = serializers.CharField(allow_blank=True)
    authority_name = serializers.CharField(allow_blank=True, allow_null=True)
    authority_type = serializers.CharField(allow_blank=True, allow_null=True)
    description = serializers.CharField(allow_blank=True)


class TeacherCurriculumSubjectInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField(allow_blank=True)
    grade_level_id = serializers.IntegerField()
    grade_level_name = serializers.CharField()


class TeacherCurriculumSubTopicSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class TeacherLearningObjectiveSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    description = serializers.CharField()
    order = serializers.IntegerField()
    subtopic_id = serializers.IntegerField(allow_null=True)
    subtopic_name = serializers.CharField(allow_null=True)


class TeacherCurriculumGuidanceSerializer(serializers.Serializer):
    teacher_activities = serializers.CharField(allow_blank=True)
    learner_activities = serializers.CharField(allow_blank=True)
    teaching_learning_materials = serializers.CharField(allow_blank=True)
    evaluation_guide = serializers.CharField(allow_blank=True)
    notes = serializers.CharField(allow_blank=True)


class TeacherCurriculumTopicSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    theme = serializers.CharField(allow_blank=True)
    content_summary = serializers.CharField(allow_blank=True)
    order = serializers.IntegerField()
    subtopics = TeacherCurriculumSubTopicSerializer(many=True)
    learning_objectives = TeacherLearningObjectiveSerializer(many=True)
    guidance = TeacherCurriculumGuidanceSerializer(allow_null=True)
    resource_count = serializers.IntegerField()


class TeacherPublishedSchemeSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    version = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    term_coverage = serializers.ListField(child=serializers.IntegerField())
    entry_count = serializers.IntegerField()


class TeacherCurriculumResourceSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    resource_type = serializers.CharField()
    resource_type_display = serializers.CharField()
    content = serializers.CharField(allow_blank=True)
    topic_id = serializers.IntegerField(allow_null=True)
    topic_name = serializers.CharField(allow_null=True)
    published_scheme_entry_id = serializers.IntegerField(allow_null=True)
    metadata = serializers.JSONField()


class TeacherCurriculumWorkspaceResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["RESOLVED", "NO_CURRICULUM_ASSIGNED", "SUBJECT_UNMAPPED", "CONFIGURATION_CONFLICT"]
    )
    message = serializers.CharField(allow_null=True)
    allocation = TeacherAllocationSummarySerializer(allow_null=True)
    curriculum = TeacherCurriculumInfoSerializer(allow_null=True)
    curriculum_subject = TeacherCurriculumSubjectInfoSerializer(allow_null=True)
    topics = TeacherCurriculumTopicSerializer(many=True)
    published_schemes = TeacherPublishedSchemeSummarySerializer(many=True)
    resources = TeacherCurriculumResourceSummarySerializer(many=True)
