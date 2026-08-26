from rest_framework import serializers

from academic.models import ClassRoom, GradeLevel, Student
from administration.models import AcademicYear, Term


class ReportFilterSerializer(serializers.Serializer):
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(), required=False,
    )
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all(), required=False)
    grade_level = serializers.PrimaryKeyRelatedField(
        queryset=GradeLevel.objects.all(), required=False,
    )
    classroom = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all(), required=False,
    )
    class_level = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all(), required=False,
    )
    student = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(), required=False,
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    status = serializers.ChoiceField(
        choices=("Active", "Inactive", "Graduated", "Withdrawn"), required=False,
    )
    payment_method = serializers.CharField(required=False, max_length=50)

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        term, year = attrs.get("term"), attrs.get("academic_year")
        if term and year and term.academic_year_id != year.pk:
            raise serializers.ValidationError({
                "term": "The selected term does not belong to the academic year."
            })
        return attrs


def validated_filters(request, *, body=False):
    serializer = ReportFilterSerializer(data=request.data if body else request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
