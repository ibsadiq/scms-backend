from rest_framework import serializers

from .models import (
    GradeScale,
    GradeScaleRule,
    ExaminationListHandler,
    MarksManagement,
    Result,
    TermResult,
    SubjectResult,
    ReportCard
)


class GradeScaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeScale
        fields = "__all__"


class GradeScaleRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeScaleRule
        fields = "__all__"


class ExaminationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing examinations/assessments with nested data.
    """
    classroom_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    status = serializers.ReadOnlyField()

    class Meta:
        model = ExaminationListHandler
        fields = [
            'id',
            'name',
            'start_date',
            'ends_date',
            'out_of',
            'classrooms',
            'classroom_names',
            'comments',
            'created_by',
            'created_by_name',
            'created_on',
            'status'
        ]
        read_only_fields = ['id', 'created_on', 'status']

    def get_classroom_names(self, obj):
        """
        Get classroom names as a list.
        ClassRoom model has 'name' (ClassLevel FK) and optional 'stream' (Stream FK).
        Display format: "ClassLevel Stream" or just "ClassLevel" if no stream.
        """
        classrooms = []
        for classroom in obj.classrooms.all():
            class_name = str(classroom.name.name) if classroom.name else "Unknown"
            if classroom.stream:
                classrooms.append(f"{class_name} {classroom.stream.name}")
            else:
                classrooms.append(class_name)
        return classrooms

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}"
        return None


class ExaminationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating examinations.
    """
    class Meta:
        model = ExaminationListHandler
        fields = [
            'id',
            'name',
            'start_date',
            'ends_date',
            'out_of',
            'classrooms',
            'comments',
            'created_by'
        ]
        read_only_fields = ['id']

    def validate(self, data):
        """
        Validate that start_date is before ends_date.
        """
        if data.get('start_date') and data.get('ends_date'):
            if data['start_date'] > data['ends_date']:
                raise serializers.ValidationError({
                    'ends_date': 'End date must be after start date.'
                })
        return data


class MarksListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing marks with nested data.
    """
    exam_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = MarksManagement
        fields = [
            'id',
            'exam_name',
            'points_scored',
            'subject',
            'subject_name',
            'student',
            'student_name',
            'created_by',
            'teacher_name',
            'date_time',
            'percentage'
        ]
        read_only_fields = ['id', 'date_time']

    def get_exam_name(self, obj):
        return obj.exam_name.name if obj.exam_name else None

    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None

    def get_student_name(self, obj):
        if obj.student and obj.student.student:
            student = obj.student.student
            return f"{student.first_name} {student.last_name}"
        return None

    def get_teacher_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}"
        return None

    def get_percentage(self, obj):
        if obj.exam_name and obj.exam_name.out_of > 0:
            return round((obj.points_scored / obj.exam_name.out_of) * 100, 2)
        return 0


class MarksCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating marks.
    """
    class Meta:
        model = MarksManagement
        fields = [
            'id',
            'exam_name',
            'points_scored',
            'subject',
            'student',
            'created_by'
        ]
        read_only_fields = ['id']

    def validate_points_scored(self, value):
        """
        Validate points scored is not negative.
        """
        if value < 0:
            raise serializers.ValidationError("Points scored cannot be negative.")
        return value


class ResultSerializer(serializers.ModelSerializer):
    """
    Serializer for student results/GPA.
    """
    student_name = serializers.SerializerMethodField()
    academic_year_name = serializers.SerializerMethodField()
    term_name = serializers.SerializerMethodField()

    class Meta:
        model = Result
        fields = [
            'id',
            'student',
            'student_name',
            'gpa',
            'cat_gpa',
            'academic_year',
            'academic_year_name',
            'term',
            'term_name'
        ]
        read_only_fields = ['id']

    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.first_name} {obj.student.last_name}"
        return None

    def get_academic_year_name(self, obj):
        return obj.academic_year.name if obj.academic_year else None

    def get_term_name(self, obj):
        return obj.term.name if obj.term else None


# ============================================================================
# RESULT COMPUTATION SERIALIZERS (Phase 1.1)
# ============================================================================

class SubjectResultSerializer(serializers.ModelSerializer):
    """
    Serializer for individual subject results.
    """
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.subject_code', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    status = serializers.ReadOnlyField()

    class Meta:
        model = SubjectResult
        fields = [
            'id',
            'subject',
            'subject_name',
            'subject_code',
            'teacher',
            'teacher_name',
            'ca_score',
            'ca_max',
            'exam_score',
            'exam_max',
            'total_score',
            'total_possible',
            'percentage',
            'grade',
            'grade_point',
            'position_in_subject',
            'total_students',
            'highest_score',
            'lowest_score',
            'class_average',
            'teacher_remarks',
            'status'
        ]
        read_only_fields = [
            'id',
            'total_score',
            'percentage',
            'status'
        ]

    def get_teacher_name(self, obj):
        if obj.teacher:
            return f"{obj.teacher.first_name} {obj.teacher.last_name}"
        return None


class TermResultListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing term results (without subject breakdown).
    """
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    classroom_name = serializers.SerializerMethodField()
    status = serializers.ReadOnlyField()
    percentage_str = serializers.ReadOnlyField()

    class Meta:
        model = TermResult
        fields = [
            'id',
            'student',
            'student_name',
            'student_admission_number',
            'term',
            'term_name',
            'academic_year',
            'academic_year_name',
            'classroom',
            'classroom_name',
            'total_marks',
            'total_possible',
            'average_percentage',
            'percentage_str',
            'grade',
            'gpa',
            'position_in_class',
            'total_students',
            'is_published',
            'published_date',
            'computed_date',
            'status'
        ]
        read_only_fields = [
            'id',
            'total_marks',
            'total_possible',
            'average_percentage',
            'grade',
            'gpa',
            'position_in_class',
            'total_students',
            'computed_date'
        ]

    def get_classroom_name(self, obj):
        if obj.classroom:
            classroom_name = str(obj.classroom.name.name)
            if obj.classroom.stream:
                return f"{classroom_name} {obj.classroom.stream.name}"
            return classroom_name
        return None


class TermResultDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed term result (with subject breakdown).
    """
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    classroom_name = serializers.SerializerMethodField()
    subject_results = SubjectResultSerializer(many=True, read_only=True)
    status = serializers.ReadOnlyField()
    percentage_str = serializers.ReadOnlyField()
    computed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TermResult
        fields = [
            'id',
            'student',
            'student_name',
            'student_admission_number',
            'term',
            'term_name',
            'academic_year',
            'academic_year_name',
            'classroom',
            'classroom_name',
            'total_marks',
            'total_possible',
            'average_percentage',
            'percentage_str',
            'grade',
            'gpa',
            'position_in_class',
            'total_students',
            'class_teacher_remarks',
            'principal_remarks',
            'computed_date',
            'computed_by',
            'computed_by_name',
            'is_published',
            'published_date',
            'subject_results',
            'status'
        ]
        read_only_fields = [
            'id',
            'total_marks',
            'total_possible',
            'average_percentage',
            'grade',
            'gpa',
            'position_in_class',
            'total_students',
            'computed_date',
            'computed_by'
        ]

    def get_classroom_name(self, obj):
        if obj.classroom:
            classroom_name = str(obj.classroom.name.name)
            if obj.classroom.stream:
                return f"{classroom_name} {obj.classroom.stream.name}"
            return classroom_name
        return None

    def get_computed_by_name(self, obj):
        if obj.computed_by:
            return f"{obj.computed_by.first_name} {obj.computed_by.last_name}"
        return None


class ResultComputationRequestSerializer(serializers.Serializer):
    """
    Serializer for result computation request.
    """
    term_id = serializers.IntegerField(required=True)
    classroom_id = serializers.IntegerField(required=True)
    grade_scale_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Optional: Specify which grading scale to use. If not provided, uses default."
    )
    recompute = serializers.BooleanField(
        default=False,
        help_text="Set to true to recompute existing results"
    )

    def validate(self, data):
        """Validate that term, classroom, and optional grade_scale exist"""
        from administration.models import Term
        from academic.models import ClassRoom

        try:
            data['term'] = Term.objects.get(id=data['term_id'])
        except Term.DoesNotExist:
            raise serializers.ValidationError({
                'term_id': 'Term not found.'
            })

        try:
            data['classroom'] = ClassRoom.objects.get(id=data['classroom_id'])
        except ClassRoom.DoesNotExist:
            raise serializers.ValidationError({
                'classroom_id': 'Classroom not found.'
            })

        # Validate grade scale if provided
        grade_scale_id = data.get('grade_scale_id')
        if grade_scale_id:
            try:
                data['grade_scale'] = GradeScale.objects.get(id=grade_scale_id)
            except GradeScale.DoesNotExist:
                raise serializers.ValidationError({
                    'grade_scale_id': 'Grade scale not found.'
                })
        else:
            data['grade_scale'] = None

        return data


class PublishResultsSerializer(serializers.Serializer):
    """
    Serializer for publishing/unpublishing results.
    """
    term_id = serializers.IntegerField(required=True)
    classroom_id = serializers.IntegerField(required=True)
    action = serializers.ChoiceField(
        choices=['publish', 'unpublish'],
        required=True
    )

    def validate(self, data):
        """Validate that term and classroom exist"""
        from administration.models import Term
        from academic.models import ClassRoom

        try:
            data['term'] = Term.objects.get(id=data['term_id'])
        except Term.DoesNotExist:
            raise serializers.ValidationError({
                'term_id': 'Term not found.'
            })

        try:
            data['classroom'] = ClassRoom.objects.get(id=data['classroom_id'])
        except ClassRoom.DoesNotExist:
            raise serializers.ValidationError({
                'classroom_id': 'Classroom not found.'
            })

        return data

# ============================================================================
# REPORT CARD SERIALIZERS
# ============================================================================

class ReportCardSerializer(serializers.ModelSerializer):
    """
    Serializer for Report Cards.
    """
    student = serializers.IntegerField(source='term_result.student.id', read_only=True)
    student_name = serializers.CharField(source='term_result.student.full_name', read_only=True)
    admission_number = serializers.CharField(source='term_result.student.admission_number', read_only=True)
    term = serializers.IntegerField(source='term_result.term.id', read_only=True)
    term_name = serializers.CharField(source='term_result.term.name', read_only=True)
    academic_year = serializers.IntegerField(source='term_result.academic_year.id', read_only=True)
    academic_year_name = serializers.CharField(source='term_result.academic_year.name', read_only=True)
    download_url = serializers.SerializerMethodField()
    generated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportCard
        fields = [
            'id',
            'student',
            'student_name',
            'admission_number',
            'term',
            'term_name',
            'academic_year',
            'academic_year_name',
            'generated_date',
            'generated_by',
            'generated_by_name',
            'download_url',
            'download_count',
            'last_downloaded'
        ]

    def get_download_url(self, obj):
        """Get download URL for the report card PDF"""
        if obj.pdf_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(f'/api/examination/report-cards/{obj.id}/download/')
        return None

    def get_generated_by_name(self, obj):
        """Get name of user who generated the report card"""
        if obj.generated_by:
            return f"{obj.generated_by.first_name} {obj.generated_by.last_name}"
        return None
