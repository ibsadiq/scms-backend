import logging
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from academic.models import StudentClassEnrollment
from ..models import (
    AssessmentEntry, AssessmentScore,
    TermResult, SubjectResult, GradeRule, LifecycleState
)
from .grading_engine import GradingSchemeResolver

logger = logging.getLogger(__name__)

from .grade_resolver import GradeResolver

class TermResultService:


    @staticmethod
    @transaction.atomic
    def compute_student_term_result(
        student, term, academic_year, user,
        scheme=None, grade_resolver=None, skip_ranking=False,
        pre_fetched_enrollment=None, pre_fetched_entries=None, pre_fetched_existing_result=None
    ):
        enrollment = pre_fetched_enrollment
        if not enrollment:
            enrollment = StudentClassEnrollment.objects.select_for_update().filter(
                student=student, academic_year=academic_year
            ).select_related("classroom").first()
        else:
            enrollment = StudentClassEnrollment.objects.select_for_update().select_related(
                "classroom"
            ).get(pk=enrollment.pk)
            
        if not enrollment:
            raise ValidationError("Student has no enrollment for this academic year.")

        classroom = enrollment.classroom
        if not scheme:
            scheme = GradingSchemeResolver.get_scheme(classroom, academic_year)
        if not scheme:
            raise ValidationError("No active grading scheme found for this class.")

        if not grade_resolver:
            grade_resolver = GradeResolver(scheme).resolve

        entries = pre_fetched_entries
        if entries is None:
            entries = list(AssessmentEntry.objects.filter(
                student=enrollment, term=term
            ).select_related(
                "component", "subject", "component__scheme"
            ))
            
        if not entries:
            raise ValidationError("No assessment entries found for this student/term.")

        existing_result = pre_fetched_existing_result
        if existing_result is None:
            existing_result = TermResult.objects.select_for_update().filter(
                student=student, term=term, academic_year=academic_year
            ).first()
        elif existing_result.pk:
            existing_result = TermResult.objects.select_for_update().get(pk=existing_result.pk)
            
        if existing_result and existing_result.is_locked:
            raise ValidationError(f"Term result for student '{getattr(student, 'full_name', str(student))}' is locked. Unlock result first to re-compute.")

        # Group entries by subject
        by_subject = {}
        for entry in entries:
            by_subject.setdefault(entry.subject_id, []).append(entry)

        scale_snapshot = [
            {
                "grade": rule.grade,
                "min_score": str(rule.min_score),
                "max_score": str(rule.max_score),
                "remark": rule.remark or "",
                "grade_point": str(rule.grade_point) if rule.grade_point is not None else "",
            }
            for rule in scheme.grade_rules.all().order_by("-min_score")
        ] if scheme else []

        term_result, _ = TermResult.objects.update_or_create(
            student=student, term=term, academic_year=academic_year,
            defaults={
                "grading_scheme": scheme,
                "scheme_name": scheme.name if scheme else "",
                "grading_scale_snapshot": scale_snapshot,
                "classroom": classroom,
                "total_marks": Decimal("0"),
                "average_percentage": Decimal("0"),
                "grade": "N/A",
                "gpa": Decimal("0"),
                "computed_date": timezone.now(),
                "computed_by": user,
                "lifecycle_state": LifecycleState.COMPUTED,
            },
        )
        term_result.subject_results.all().delete()

        subject_totals = []
        overall_pass = True
        promotion_rule = getattr(scheme, "promotion_rule", None)

        subject_results_to_create = []

        for subject_id, subject_entries in by_subject.items():
            components = {e.component for e in subject_entries}
            weight_total = sum(c.weight for c in components)
            if weight_total == 0:
                continue

            weighted_score = Decimal("0")
            for entry in subject_entries:
                component = entry.component
                normalized = (Decimal(str(entry.score)) / Decimal(str(component.max_score))) * Decimal(str(component.weight))
                weighted_score += normalized

            percentage = round((weighted_score / Decimal(str(weight_total))) * Decimal("100"), 2)
            grade_rule = grade_resolver(percentage)
            is_pass = percentage >= Decimal(str(promotion_rule.minimum_subject_pass if promotion_rule else 40))
            overall_pass = overall_pass and is_pass

            statuses = [e.status for e in subject_entries]
            if all(s == AssessmentEntry.EntryStatus.EXEMPTED for s in statuses):
                subject_status = SubjectResult.SubjectResultStatus.EXCUSED
            elif all(s in [AssessmentEntry.EntryStatus.MISSING, AssessmentEntry.EntryStatus.ABSENT] for s in statuses):
                subject_status = SubjectResult.SubjectResultStatus.MISSING
            else:
                subject_status = SubjectResult.SubjectResultStatus.COMPLETE

            subject_result = SubjectResult(
                term_result=term_result,
                subject_id=subject_id,
                total_score=weighted_score,
                percentage=percentage,
                grade=grade_rule.grade,
                grade_point=grade_rule.grade_point,
                is_pass=is_pass,
                status=subject_status,
                grading_scheme_name=scheme.name,
                grading_rule_snapshot={
                    "min_score": str(grade_rule.min_score),
                    "max_score": str(grade_rule.max_score),
                    "remark": grade_rule.remark,
                },
            )
            subject_results_to_create.append((subject_result, subject_entries))
            subject_totals.append(percentage)

        if not subject_totals:
            raise ValidationError("No valid subject scores to compute a term result.")

        created_subject_results = SubjectResult.objects.bulk_create([sr[0] for sr in subject_results_to_create])
        
        assessment_scores_to_create = []
        for subject_result, subject_entries in zip(created_subject_results, [sr[1] for sr in subject_results_to_create]):
            for entry in subject_entries:
                assessment_scores_to_create.append(
                    AssessmentScore(
                        subject_result=subject_result,
                        component=entry.component,
                        score=entry.score,
                    )
                )
        if assessment_scores_to_create:
            AssessmentScore.objects.bulk_create(assessment_scores_to_create)

        average = round(sum(subject_totals) / len(subject_totals), 2)
        overall_grade_rule = grade_resolver(average)

        term_result.total_marks = sum(subject_totals)
        term_result.average_percentage = average
        term_result.grade = overall_grade_rule.grade
        term_result.gpa = overall_grade_rule.grade_point
        term_result.is_pass = overall_pass
        term_result.grading_scale_snapshot = scale_snapshot
        term_result.save()

        if not skip_ranking:
            from .ranking_service import RankingService
            RankingService.rank_class(classroom, term, academic_year)
            for subject_id in by_subject:
                RankingService.rank_subject(classroom, term, academic_year, subject_id)

        return term_result
