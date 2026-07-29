from rest_framework import viewsets
from ..models import GradingScheme, AssessmentComponent, GradeRule, PromotionRule
from ..serializers.grading import (
    GradingSchemeSerializer, AssessmentComponentSerializer,
    GradeRuleSerializer, PromotionRuleSerializer,
)
from ..permissions import CanManageGradingScheme


class GradingSchemeViewSet(viewsets.ModelViewSet):
    serializer_class = GradingSchemeSerializer
    permission_classes = [CanManageGradingScheme]
    queryset = GradingScheme.objects.select_related(
        "grade_level", "classroom", "academic_year"
    ).prefetch_related("components", "grade_rules")


class AssessmentComponentViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentComponentSerializer
    permission_classes = [CanManageGradingScheme]
    queryset = AssessmentComponent.objects.select_related("scheme")

    def get_queryset(self):
        qs = super().get_queryset()
        scheme_id = self.request.query_params.get("scheme")
        if scheme_id:
            return qs.filter(scheme_id=scheme_id)

        classroom_id = self.request.query_params.get("classroom")
        if classroom_id:
            from academic.models import ClassRoom
            try:
                classroom = ClassRoom.objects.get(id=classroom_id)
                # 1. Classroom level
                scheme = None
                # Wait, grading scheme doesn't import well this way, but we can use self.queryset
                from ..models import GradingScheme
                scheme = GradingScheme.objects.filter(classroom=classroom).first()
                if not scheme and classroom.name and classroom.name.grade_level:
                    # 2. Grade level
                    scheme = GradingScheme.objects.filter(grade_level=classroom.name.grade_level).first()
                if not scheme and classroom.name and classroom.name.grade_level and hasattr(classroom.name.grade_level, 'section') and classroom.name.grade_level.section:
                    # 3. Section level
                    scheme = GradingScheme.objects.filter(section=classroom.name.grade_level.section).first()
                
                if scheme:
                    return qs.filter(scheme=scheme)
                else:
                    return qs.none()
            except ClassRoom.DoesNotExist:
                return qs.none()

        return qs


class GradeRuleViewSet(viewsets.ModelViewSet):
    serializer_class = GradeRuleSerializer
    permission_classes = [CanManageGradingScheme]
    queryset = GradeRule.objects.select_related("scheme")

    def get_queryset(self):
        qs = super().get_queryset()
        scheme_id = self.request.query_params.get("scheme")
        return qs.filter(scheme_id=scheme_id) if scheme_id else qs


class PromotionRuleViewSet(viewsets.ModelViewSet):
    serializer_class = PromotionRuleSerializer
    permission_classes = [CanManageGradingScheme]
    queryset = PromotionRule.objects.select_related("scheme").prefetch_related("required_pass_subjects")