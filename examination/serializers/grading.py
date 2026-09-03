#serializers/grading.py
from rest_framework import serializers
from ..models import GradingScheme, AssessmentComponent, GradeRule, PromotionRule


class AssessmentComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentComponent
        fields = ["id", "scheme", "name", "max_score", "weight", "order"]

    def validate(self, attrs):
        attrs_copy = attrs.copy()
        instance_dict = {}
        if self.instance:
            for field in self.instance._meta.fields:
                instance_dict[field.name] = getattr(self.instance, field.name)
        instance_dict.update(attrs_copy)

        instance = AssessmentComponent(**instance_dict)
        instance.pk = self.instance.pk if self.instance else None
        instance.full_clean(exclude=["id"])
        return attrs


class GradeRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeRule
        fields = ["id", "scheme", "min_score", "max_score", "grade", "remark", "grade_point"]

    def validate(self, attrs):
        attrs_copy = attrs.copy()
        instance_dict = {}
        if self.instance:
            for field in self.instance._meta.fields:
                instance_dict[field.name] = getattr(self.instance, field.name)
        instance_dict.update(attrs_copy)

        instance = GradeRule(**instance_dict)
        instance.pk = self.instance.pk if self.instance else None
        instance.full_clean(exclude=["id"])
        return attrs


class PromotionRuleSerializer(serializers.ModelSerializer):
    required_pass_subjects_display = serializers.StringRelatedField(
        source="required_pass_subjects", many=True, read_only=True
    )

    class Meta:
        model = PromotionRule
        fields = [
            "id", "scheme", "annual_computation_method",
            "minimum_average", "minimum_subject_pass", "max_failed_subjects",
            "auto_promote", "required_pass_subjects", "required_pass_subjects_display",
        ]

    def validate(self, attrs):
        attrs_copy = attrs.copy()
        attrs_copy.pop("required_pass_subjects", None)  # M2M can't go through the unsaved-instance constructor

        instance_dict = {}
        if self.instance:
            for field in self.instance._meta.fields:
                instance_dict[field.name] = getattr(self.instance, field.name)
        instance_dict.update(attrs_copy)

        instance = PromotionRule(**instance_dict)
        instance.pk = self.instance.pk if self.instance else None
        instance.full_clean(exclude=["id", "required_pass_subjects"])
        return attrs


class GradingSchemeSerializer(serializers.ModelSerializer):
    components = AssessmentComponentSerializer(many=True, read_only=True)
    grade_rules = GradeRuleSerializer(many=True, read_only=True)
    promotion_rule = PromotionRuleSerializer(read_only=True)

    class Meta:
        model = GradingScheme
        fields = [
            "id", "name", "description", "section", "grade_level", "classroom",
            "academic_year", "is_active", "components", "grade_rules", "promotion_rule",
        ]

    def validate(self, attrs):
        attrs_copy = attrs.copy()
        instance_dict = {}
        if self.instance:
            for field in self.instance._meta.fields:
                instance_dict[field.name] = getattr(self.instance, field.name)
        instance_dict.update(attrs_copy)

        instance = GradingScheme(**instance_dict)
        instance.pk = self.instance.pk if self.instance else None
        instance.full_clean(exclude=["id"])
        return attrs