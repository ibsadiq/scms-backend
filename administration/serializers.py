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


class TermSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        required=False
    )
    academic_year_name = serializers.StringRelatedField(
        source="academic_year",
        read_only=True
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
        validators = []   # IMPORTANT
        

    def validate(self, data):
        start_date = (
            data.get("start_date")
            or getattr(self.instance, "start_date", None)
        )

        end_date = (
            data.get("end_date")
            or getattr(self.instance, "end_date", None)
        )

        academic_year = (
            data.get("academic_year")
            or getattr(self.instance, "academic_year", None)
        )

        name = (
            data.get("name")
            or getattr(self.instance, "name", None)
        )

        term_id = (
            data.get("id")
            or getattr(self.instance, "id", None)
        )

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                "end_date":
                    "Term end date must be after start date."
            })

        if academic_year and start_date:
            if start_date < academic_year.start_date:
                raise serializers.ValidationError({
                    "start_date":
                        f"Term dates must be within the academic year "
                        f"({academic_year.start_date} "
                        f"to {academic_year.end_date})."
                })

        if academic_year and end_date:
            if (
                academic_year.end_date
                and end_date > academic_year.end_date
            ):
                raise serializers.ValidationError({
                    "end_date":
                        f"Term dates must be within the academic year "
                        f"({academic_year.start_date} "
                        f"to {academic_year.end_date})."
                })

        # Custom uniqueness check
        if academic_year and name:
            qs = Term.objects.filter(
                academic_year=academic_year,
                name=name,
            )

            if term_id:
                qs = qs.exclude(pk=term_id)

            if qs.exists():
                raise serializers.ValidationError({
                    "name":
                        "A term with this name already exists in this academic year."
                })

        return data

class AcademicYearSerializer(serializers.ModelSerializer):
    terms = TermSerializer(many=True, required=False)

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "active_year", "terms"]

    def validate(self, data):
        start_date = data.get("start_date") or (self.instance.start_date if self.instance else None)
        end_date = data.get("end_date") or (self.instance.end_date if self.instance else None)

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})

        terms_data = data.get("terms", [])
        for term_data in terms_data:
            term_start = term_data.get("start_date")
            term_end = term_data.get("end_date")
            term_name = term_data.get("name", "Term")

            if term_start and term_end:
                if term_start > term_end:
                    raise serializers.ValidationError(
                        {"terms": f"For {term_name}, end date must be after start date."}
                    )
                if start_date and term_start < start_date:
                    raise serializers.ValidationError(
                        {"terms": f"For {term_name}, start date ({term_start}) cannot be before the academic year start date ({start_date})."}
                    )
                if end_date and term_end > end_date:
                    raise serializers.ValidationError(
                        {"terms": f"For {term_name}, end date ({term_end}) cannot be after the academic year end date ({end_date})."}
                    )
        return data

    def create(self, validated_data):
        terms_data = validated_data.pop('terms', [])
        academic_year = AcademicYear.objects.create(**validated_data)
        for term_data in terms_data:
            term_data.pop('id', None)
            Term.objects.create(academic_year=academic_year, **term_data)
        return academic_year

    def update(self, instance, validated_data):
        terms_data = validated_data.pop("terms", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if terms_data is not None:
            keep_term_ids = []

            for term_data in terms_data:
                term_id = term_data.pop("id", None)
                term_data.pop("academic_year", None)

                if term_id:
                    try:
                        term = instance.terms.get(id=term_id)

                        for attr, value in term_data.items():
                            setattr(term, attr, value)

                        term.save()

                    except Term.DoesNotExist:
                        term = Term.objects.create(
                            academic_year=instance,
                            **term_data
                        )
                else:
                    term = Term.objects.create(
                        academic_year=instance,
                        **term_data
                    )

                keep_term_ids.append(term.id)

            instance.terms.exclude(
                id__in=keep_term_ids
            ).delete()

        return instance

class SchoolEventSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source="term.name", read_only=True)
    academic_year_name = serializers.CharField(
        source="academic_year.name", read_only=True
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
            "academic_year_name",
            "start_date",
            "end_date",
            "description",
        ]


class SchoolEventBulkUploadSerializer(serializers.Serializer):
    file = serializers.FileField()