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
    class Meta:
        model = MarkedScript
        fields = [
            "id", "exam", "student", "subject", "assessment_entry",
            "script_file", "file_name", "file_size", "uploaded_by", "uploaded_at",
            "notes", "visible_to_student", "visible_to_parent",
        ]
        read_only_fields = ["file_name", "file_size", "uploaded_by", "uploaded_at"]