#serializers/assessments.py
from rest_framework import serializers
from ..models import AssessmentSession, AssessmentEntry, MarkedScript


class AssessmentSessionSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = AssessmentSession
        fields = [
            "id", "assessment_type", "name", "start_date", "ends_date",
            "out_of", "classrooms", "comments", "created_by", "created_on", "status",
        ]
        read_only_fields = ["created_by", "created_on"]

    def validate(self, attrs):
        instance = AssessmentSession(**{**(self.instance.__dict__ if self.instance else {}), **attrs})
        instance.pk = self.instance.pk if self.instance else None
        instance.full_clean(exclude=["id", "classrooms"])  # M2M excluded, same reason as above
        return attrs


class AssessmentEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentEntry
        fields = [
            "id", "component", "student", "subject", "score",
            "entered_by", "entered_at", "remarks",
        ]
        # entered_by is set by the view from request.user.teacher, never accepted
        # from the client — otherwise a teacher could submit scores as someone else.
        read_only_fields = ["entered_by", "entered_at"]

    def validate(self, attrs):
        instance = AssessmentEntry(
            component=attrs.get("component", getattr(self.instance, "component", None)),
            student=attrs.get("student", getattr(self.instance, "student", None)),
            subject=attrs.get("subject", getattr(self.instance, "subject", None)),
            score=attrs.get("score", getattr(self.instance, "score", None)),
            entered_by=self.context["request"].user.teacher,
        )
        instance.pk = self.instance.pk if self.instance else None
        instance.full_clean(exclude=["id", "entered_by"])  # entered_by allocation check runs separately in clean()
        return attrs


class MarkedScriptSerializer(serializers.ModelSerializer):
    exam_name = serializers.CharField(source="exam.name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MarkedScript
        fields = [
            "id", "exam", "exam_name", "student", "student_name", "student_admission_number",
            "subject", "subject_name", "assessment_entry",
            "script_file", "file_name", "file_size", "uploaded_by", "uploaded_by_name", "uploaded_at",
            "notes", "visible_to_student", "visible_to_parent",
        ]
        read_only_fields = ["file_name", "file_size", "uploaded_by", "uploaded_at"]

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.full_name
        return "System Admin"

    def create(self, validated_data):
        exam = validated_data.get("exam")
        student = validated_data.get("student")
        subject = validated_data.get("subject")

        existing = MarkedScript.objects.filter(exam=exam, student=student, subject=subject).first()
        if existing:
            for attr, val in validated_data.items():
                setattr(existing, attr, val)
            existing.save()
            return existing
        return super().create(validated_data)