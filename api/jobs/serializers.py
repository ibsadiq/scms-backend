from rest_framework import serializers

from .models import BackgroundJob


class BackgroundJobSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    result = serializers.JSONField(source="safe_result", read_only=True)

    class Meta:
        model = BackgroundJob
        fields = (
            "id",
            "job_type",
            "status",
            "progress",
            "result",
            "error_code",
            "created_at",
            "started_at",
            "completed_at",
        )
