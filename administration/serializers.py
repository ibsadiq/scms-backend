from rest_framework import serializers
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

    def get_created_by(self, obj):
        user = obj.created_by
        serializer = UserSerializer(user, many=False)
        if serializer.data["first_name"]:
            return serializer.data["first_name"]
        return serializer.data["email"]

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
    academic_year = (
        serializers.StringRelatedField()
    )  # Display AcademicYear name in term details

    class Meta:
        model = Term
        fields = "__all__"


class SchoolEventSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source='term.name', read_only=True)
    academic_year = serializers.CharField(source='term.academic_year.name', read_only=True)

    class Meta:
        model = SchoolEvent
        fields = [
            'id',
            'name',
            'event_type',
            'term',
            'term_name',
            'academic_year',
            'start_date',
            'end_date',
            'description',
        ]
