from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from academic.models import StudentClassEnrollment
from ..models import (
    AssessmentEntry, AssessmentComponent, AssessmentScore,
    TermResult, SubjectResult, GradeRule,
)
from .ranking_service import RankingService
from .grading_engine import GradingSchemeResolver


class ResultComputationService:

    @staticmethod
    def _resolve_grade(scheme, percentage):
        rule = GradeRule.objects.filter(
            scheme=scheme, min_score__lte=percentage, max_score__gte=percentage
        ).first()
        if not rule:
            raise ValidationError(f"No grade rule covers {percentage}% in scheme {scheme}.")
        return rule

    @staticmethod
    @transaction.atomic
    def compute_student_term_result(student, term, academic_year, user):
        enrollment = StudentClassEnrollment.objects.filter(
            student=student, academic_year=academic_year
        ).select_related("classroom").first()
        if not enrollment:
            raise ValidationError("Student has no enrollment for this academic year.")

        classroom = enrollment.classroom
        scheme = GradingSchemeResolver.get_scheme(classroom, academic_year)
        if not scheme:
            raise ValidationError("No active grading scheme found for this class.")

        entries = AssessmentEntry.objects.filter(student=enrollment).select_related(
            "component", "subject", "component__scheme"
        )
        if not entries.exists():
            raise ValidationError("No assessment entries found for this student/term.")

        # Group entries by subject
        by_subject = {}
        for entry in entries:
            by_subject.setdefault(entry.subject_id, []).append(entry)

        term_result, _ = TermResult.objects.update_or_create(
            student=student, term=term, academic_year=academic_year,
            defaults={
                "grading_scheme": scheme,
                "scheme_name": scheme.name,
                "classroom": classroom,
                "total_marks": Decimal("0"),
                "average_percentage": Decimal("0"),
                "grade": "N/A",
                "gpa": Decimal("0"),
                "computed_date": timezone.now(),
                "computed_by": user,
                # reset approval/publish state on recompute — safer than leaving stale approvals
                "is_approved": False, "approved_by": None, "approved_at": None,
                "homeroom_approved": False, "homeroom_approved_by": None, "homeroom_approved_at": None,
                "is_published": False, "published_date": None,
            },
        )
        term_result.subject_results.all().delete()

        subject_totals = []
        overall_pass = True
        promotion_rule = getattr(scheme, "promotion_rule", None)

        for subject_id, subject_entries in by_subject.items():
            components = AssessmentComponent.objects.filter(
                id__in=[e.component_id for e in subject_entries]
            )
            weight_total = sum(c.weight for c in components)
            if weight_total == 0:
                continue

            weighted_score = Decimal("0")
            for entry in subject_entries:
                component = entry.component
                normalized = (entry.score / component.max_score) * component.weight
                weighted_score += normalized

            percentage = round((weighted_score / weight_total) * 100, 2)
            grade_rule = ResultComputationService._resolve_grade(scheme, percentage)
            is_pass = percentage >= (promotion_rule.minimum_subject_pass if promotion_rule else 40)
            overall_pass = overall_pass and is_pass

            subject_result = SubjectResult.objects.create(
                term_result=term_result,
                subject_id=subject_id,
                total_score=weighted_score,
                percentage=percentage,
                grade=grade_rule.grade,
                grade_point=grade_rule.grade_point,
                is_pass=is_pass,
                grading_scheme_name=scheme.name,
                grading_rule_snapshot={
                    "min_score": str(grade_rule.min_score),
                    "max_score": str(grade_rule.max_score),
                    "remark": grade_rule.remark,
                },
            )

            for entry in subject_entries:
                AssessmentScore.objects.create(
                    subject_result=subject_result,
                    component=entry.component,
                    score=entry.score,
                )
            subject_totals.append(percentage)

        if not subject_totals:
            raise ValidationError("No valid subject scores to compute a term result.")

        average = round(sum(subject_totals) / len(subject_totals), 2)
        overall_grade_rule = ResultComputationService._resolve_grade(scheme, average)

        term_result.total_marks = sum(subject_totals)
        term_result.average_percentage = average
        term_result.grade = overall_grade_rule.grade
        term_result.gpa = overall_grade_rule.grade_point
        term_result.is_pass = overall_pass
        term_result.save()

        RankingService.rank_class(classroom, term, academic_year)
        for subject_id in by_subject:
            RankingService.rank_subject(classroom, term, academic_year, subject_id)

        return term_result