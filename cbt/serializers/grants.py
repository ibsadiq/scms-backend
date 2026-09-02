from rest_framework import serializers

from cbt.models import AttemptGrant


class AttemptGrantStudentSerializer(serializers.ModelSerializer):
    grant_token = serializers.CharField(read_only=True)
    published_revision_id = serializers.UUIDField(
        source="published_revision.public_id", read_only=True
    )
    revision_hash = serializers.CharField(
        source="published_revision.content_hash", read_only=True
    )
    server_time = serializers.DateTimeField(read_only=True)

    class Meta:
        model = AttemptGrant
        fields = [
            "public_id",
            "published_revision_id",
            "revision_hash",
            "status",
            "valid_from",
            "valid_until",
            "issued_at",
            "grant_token",
            "server_time",
        ]
