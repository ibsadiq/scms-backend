from rest_framework import serializers


class OfflinePackageRequestSerializer(serializers.Serializer):
    grant_token = serializers.CharField(trim_whitespace=False)
