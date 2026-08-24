from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import AcademicYear, Term, Article, CarouselImage, SchoolEvent


from users.serializers import UserSerializer


class DashboardStatsCoreSerializer(serializers.Serializer):
    totalStudents = serializers.IntegerField()
    totalTeachers = serializers.IntegerField()
    activeSubjects = serializers.IntegerField()
    attendanceRate = serializers.FloatField()
    attendancePresent = serializers.IntegerField()
    attendanceAbsent = serializers.IntegerField()
    newStudentsThisMonth = serializers.IntegerField()
    revenueCollected = serializers.FloatField()
    pendingFees = serializers.FloatField()
    revenueSeries = serializers.ListField(child=serializers.FloatField())


class EnrollmentTrendSerializer(serializers.Serializer):
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    label = serializers.CharField()
    shortLabel = serializers.CharField()
    count = serializers.IntegerField()


class RecentStudentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    admission_number = serializers.CharField()
    class_name = serializers.CharField()
    admission_date = serializers.DateField(allow_null=True)


class StudentsByLevelSerializer(serializers.Serializer):
    name = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()
    icon = serializers.CharField()


class DashboardFinanceSerializer(serializers.Serializer):
    collected = serializers.FloatField()
    outstanding = serializers.FloatField()
    expected = serializers.FloatField()
    collectionRate = serializers.FloatField()
    studentsWithDebt = serializers.IntegerField()
    totalStudents = serializers.IntegerField()


class DashboardAttendanceDaySerializer(serializers.Serializer):
    dayName = serializers.CharField()
    date = serializers.DateField()
    rate = serializers.FloatField()
    present = serializers.IntegerField()
    total = serializers.IntegerField()


class RecentAdmissionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    grade_level = serializers.CharField()
    admission_date = serializers.DateField(allow_null=True)


class RecentPaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    receipt_number = serializers.CharField(allow_null=True)
    student_name = serializers.CharField()
    amount = serializers.FloatField()
    method = serializers.CharField(allow_null=True)
    paid_on = serializers.DateField()
    term_name = serializers.CharField()


class GradeDistributionSerializer(serializers.Serializer):
    a = serializers.IntegerField()
    b = serializers.IntegerField()
    c = serializers.IntegerField()
    df = serializers.IntegerField()


class DashboardPerformanceSerializer(serializers.Serializer):
    averageGrade = serializers.CharField()
    passRate = serializers.IntegerField()
    grades = GradeDistributionSerializer()


class AdministrationDashboardSerializer(serializers.Serializer):
    stats = DashboardStatsCoreSerializer()
    enrollmentTrends = EnrollmentTrendSerializer(many=True)
    recentStudents = RecentStudentSerializer(many=True)
    studentsByLevel = StudentsByLevelSerializer(many=True)
    financial = DashboardFinanceSerializer()
    attendance = DashboardAttendanceDaySerializer(many=True)
    recentAdmissions = RecentAdmissionSerializer(many=True)
    recentPayments = RecentPaymentSerializer(many=True)
    performance = DashboardPerformanceSerializer()


class ArticleSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField(read_only=True)
    # created_at = serializers.SerializerMethodField(read_only=True)
    short_content = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "content",
            "short_content",
            "picture",
            "created_at",
            "created_by",
        ]

    @extend_schema_field(serializers.CharField)
    def get_created_by(self, obj):
        user = obj.created_by
        serializer = UserSerializer(user, many=False)
        if serializer.data["first_name"]:
            return serializer.data["first_name"]
        return serializer.data["email"]

    @extend_schema_field(serializers.CharField)
    def get_short_content(self, obj):
        content = obj.content
        return content[:200]


class CarouselImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarouselImage
        fields = ["id", "title", "description", "picture"]


class TermSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        required=False
    )
    academic_year_name = serializers.StringRelatedField(
        source="academic_year",
        read_only=True
    )

    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Term
        fields = [
            "id",
            "name",
            "academic_year",
            "academic_year_name",
            "start_date",
            "end_date",
            "is_active",
        ]
        validators = []   # IMPORTANT
        
    @extend_schema_field(serializers.BooleanField)
    def get_is_active(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        return obj.start_date <= today <= obj.end_date
        

    def validate(self, data):
        start_date = (
            data.get("start_date")
            or getattr(self.instance, "start_date", None)
        )

        end_date = (
            data.get("end_date")
            or getattr(self.instance, "end_date", None)
        )

        academic_year = (
            data.get("academic_year")
            or getattr(self.instance, "academic_year", None)
        )

        name = (
            data.get("name")
            or getattr(self.instance, "name", None)
        )

        term_id = (
            data.get("id")
            or getattr(self.instance, "id", None)
        )

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                "end_date":
                    "Term end date must be after start date."
            })

        if academic_year and start_date:
            if start_date < academic_year.start_date:
                raise serializers.ValidationError({
                    "start_date":
                        f"Term dates must be within the academic year "
                        f"({academic_year.start_date} "
                        f"to {academic_year.end_date})."
                })

        if academic_year and end_date:
            if (
                academic_year.end_date
                and end_date > academic_year.end_date
            ):
                raise serializers.ValidationError({
                    "end_date":
                        f"Term dates must be within the academic year "
                        f"({academic_year.start_date} "
                        f"to {academic_year.end_date})."
                })

        # Custom uniqueness check
        if academic_year and name:
            qs = Term.objects.filter(
                academic_year=academic_year,
                name=name,
            )

            if term_id:
                qs = qs.exclude(pk=term_id)

            if qs.exists():
                raise serializers.ValidationError({
                    "name":
                        "A term with this name already exists in this academic year."
                })

        return data

class AcademicYearSerializer(serializers.ModelSerializer):
    terms = TermSerializer(many=True, required=False)

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "active_year", "terms"]

    def validate(self, data):
        start_date = data.get("start_date") or (self.instance.start_date if self.instance else None)
        end_date = data.get("end_date") or (self.instance.end_date if self.instance else None)

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})

        terms_data = data.get("terms", [])
        for term_data in terms_data:
            term_start = term_data.get("start_date")
            term_end = term_data.get("end_date")
            term_name = term_data.get("name", "Term")

            if term_start and term_end:
                if term_start > term_end:
                    raise serializers.ValidationError(
                        {"terms": f"For {term_name}, end date must be after start date."}
                    )
                if start_date and term_start < start_date:
                    raise serializers.ValidationError(
                        {"terms": f"For {term_name}, start date ({term_start}) cannot be before the academic year start date ({start_date})."}
                    )
                if end_date and term_end > end_date:
                    raise serializers.ValidationError(
                        {"terms": f"For {term_name}, end date ({term_end}) cannot be after the academic year end date ({end_date})."}
                    )
        return data

    def create(self, validated_data):
        terms_data = validated_data.pop('terms', [])
        academic_year = AcademicYear.objects.create(**validated_data)
        for term_data in terms_data:
            term_data.pop('id', None)
            Term.objects.create(academic_year=academic_year, **term_data)
        return academic_year

    def update(self, instance, validated_data):
        terms_data = validated_data.pop("terms", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if terms_data is not None:
            keep_term_ids = []

            for term_data in terms_data:
                term_id = term_data.pop("id", None)
                term_data.pop("academic_year", None)

                if term_id:
                    try:
                        term = instance.terms.get(id=term_id)

                        for attr, value in term_data.items():
                            setattr(term, attr, value)

                        term.save()

                    except Term.DoesNotExist:
                        term = Term.objects.create(
                            academic_year=instance,
                            **term_data
                        )
                else:
                    term = Term.objects.create(
                        academic_year=instance,
                        **term_data
                    )

                keep_term_ids.append(term.id)

            instance.terms.exclude(
                id__in=keep_term_ids
            ).delete()

        return instance

class SchoolEventSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source="term.name", read_only=True)
    academic_year_name = serializers.CharField(
        source="academic_year.name", read_only=True
    )

    class Meta:
        model = SchoolEvent
        fields = [
            "id",
            "name",
            "event_type",
            "term",
            "term_name",
            "academic_year",
            "academic_year_name",
            "start_date",
            "end_date",
            "description",
        ]


class SchoolEventBulkUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
