from rest_framework import serializers
from .models import SchoolSettings


class SchoolSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for school settings
    """
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = SchoolSettings
        fields = [
            'id',
            'school_name',
            'address',
            'city',
            'state',
            'contact_phone',
            'contact_email',
            'website',
            'logo',
            'logo_url',
            'primary_color',
            'secondary_color',
            'academic_year_start_month',
            'terms_per_year',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'logo_url']

    def get_logo_url(self, obj):
        """
        Get the full URL for the school logo
        """
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None

    def validate_primary_color(self, value):
        """
        Validate hex color format
        """
        if not value.startswith('#'):
            raise serializers.ValidationError('Color must start with #')
        if len(value) not in [4, 7]:
            raise serializers.ValidationError('Invalid hex color format (use #RGB or #RRGGBB)')
        return value
