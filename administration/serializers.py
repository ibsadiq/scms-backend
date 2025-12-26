from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import AcademicYear, Term, Article, CarouselImage, SchoolEvent


from users.serializers import UserSerializer


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


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = "__all__"


class TermSerializer(serializers.ModelSerializer):
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(), write_only=True
    )
    academic_year_name = serializers.StringRelatedField(
        source="academic_year", read_only=True
    )

    class Meta:
        model = Term
        fields = [
            "id",
            "name",
            "academic_year",
            "academic_year_name",
            "start_date",
            "end_date",
        ]


class SchoolEventSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source="term.name", read_only=True)
    academic_year = serializers.CharField(
        source="term.academic_year.name", read_only=True
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
            "start_date",
            "end_date",
            "description",
        ]


class SchoolEventBulkUploadSerializer(serializers.Serializer):
    file = serializers.FileField()