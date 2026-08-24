from rest_framework import serializers
from academic.models import (
    AcademicLeadershipAssignment,
    AcademicApprovalPolicy,
)


class AcademicLeadershipAssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.user.get_full_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = AcademicLeadershipAssignment
        fields = [
            "id",
            "teacher",
            "teacher_name",
            "role",
            "department",
            "department_name",
            "section",
            "academic_year",
            "academic_year_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AcademicApprovalPolicySerializer(serializers.ModelSerializer):
    workflow_display = serializers.CharField(source="get_workflow_display", read_only=True)
    approval_route_display = serializers.CharField(source="get_approval_route_display", read_only=True)

    class Meta:
        model = AcademicApprovalPolicy
        fields = [
            "id",
            "workflow",
            "workflow_display",
            "approval_route",
            "approval_route_display",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
