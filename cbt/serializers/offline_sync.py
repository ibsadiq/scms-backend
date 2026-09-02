from rest_framework import serializers


class OfflineCredentialsSerializer(serializers.Serializer):
    protocol_version = serializers.IntegerField(default=1)
    package_id = serializers.UUIDField()
    package_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    package_signature = serializers.CharField(trim_whitespace=False)
    grant_token = serializers.CharField(trim_whitespace=False)
    client_id = serializers.UUIDField()


class OfflineAttemptStartSerializer(OfflineCredentialsSerializer):
    offline_started_at = serializers.DateTimeField()
    client_timestamp = serializers.DateTimeField(required=False)


class OfflineAnswerEventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    client_id = serializers.UUIDField()
    client_sequence = serializers.IntegerField(min_value=1)
    base_revision = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    question_id = serializers.UUIDField()
    operation = serializers.ChoiceField(choices=("SET", "CLEAR"))
    payload = serializers.DictField(required=False)
    client_timestamp = serializers.DateTimeField()


class OfflineSyncSerializer(OfflineCredentialsSerializer):
    known_server_revision = serializers.IntegerField(min_value=0)
    events = serializers.ListField(
        child=OfflineAnswerEventSerializer(),
        allow_empty=True,
    )

    def validate_events(self, value):
        # Envelope validation is deliberately independent from the configurable
        # service limit so oversized input receives a stable protocol error.
        return value


class OfflineSubmitSerializer(OfflineSyncSerializer):
    submission_id = serializers.UUIDField()
    client_submitted_at = serializers.DateTimeField()
