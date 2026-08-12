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
    def _get_grade_resolver(scheme):
        rules = list(GradeRule.objects.filter(scheme=scheme))
        def resolve(percentage):
            dec_pct = Decimal(str(percentage))
            for rule in rules:
                if rule.min_score <= dec_pct <= rule.max_score:
                    return rule
            for rule in rules:
                if (rule.min_score - Decimal("0.05")) <= dec_pct <= (rule.max_score + Decimal("0.05")):
                    return rule
            raise ValidationError(f"No grade rule covers {percentage}% in scheme {scheme.name}.")
        return resolve

    @staticmethod
    @transaction.atomic
    def compute_student_term_result(student, term, academic_year, user, scheme=None, grade_resolver=None, skip_ranking=False):
        enrollment = StudentClassEnrollment.objects.filter(
            student=student, academic_year=academic_year
        ).select_related("classroom").first()
        if not enrollment:
            raise ValidationError("Student has no enrollment for this academic year.")

        classroom = enrollment.classroom
        if not scheme:
            scheme = GradingSchemeResolver.get_scheme(classroom, academic_year)
        if not scheme:
            raise ValidationError("No active grading scheme found for this class.")

        if not grade_resolver:
            grade_resolver = ResultComputationService._get_grade_resolver(scheme)

        entries = list(AssessmentEntry.objects.filter(student=enrollment).select_related(
            "component", "subject", "component__scheme"
        ))
        if not entries:
            raise ValidationError("No assessment entries found for this student/term.")

        existing_result = TermResult.objects.filter(
            student=student, term=term, academic_year=academic_year
        ).first()
        if existing_result and existing_result.is_locked:
            raise ValidationError(f"Term result for student '{getattr(student, 'full_name', str(student))}' is locked. Unlock result first to re-compute.")

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
                "admin_approved": False, "admin_approved_by": None, "admin_approved_at": None,
                "homeroom_approved": False, "homeroom_approved_by": None, "homeroom_approved_at": None,
                "is_published": False, "published_date": None,
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

            subject_result = SubjectResult(
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
        term_result.save()

        if not skip_ranking:
            RankingService.rank_class(classroom, term, academic_year)
            for subject_id in by_subject:
                RankingService.rank_subject(classroom, term, academic_year, subject_id)

        return term_result

    @staticmethod
    @transaction.atomic
    def compute_classroom_term_results(classroom, term, academic_year, user=None, progress_callback=None):
        """
        Highly optimized batch computation for an entire classroom.
        Pre-fetches scheme, grade rules, and computes in memory with bulk DB operations;
        and runs ranking ONCE at the end.
        """
        scheme = GradingSchemeResolver.get_scheme(classroom, academic_year)
        if not scheme:
            raise ValidationError("No active grading scheme found for this class.")

        grade_resolver = ResultComputationService._get_grade_resolver(scheme)
        students = list(classroom.students.filter(is_active=True))

        summary = {"computed": 0, "failed": 0, "errors": []}
        subjects_seen = set()

        for i, student in enumerate(students):
            if progress_callback:
                progress_callback(i, len(students), student)
            try:
                result = ResultComputationService.compute_student_term_result(
                    student=student,
                    term=term,
                    academic_year=academic_year,
                    user=user,
                    scheme=scheme,
                    grade_resolver=grade_resolver,
                    skip_ranking=True,
                )
                summary["computed"] += 1
                for sr in result.subject_results.values_list('subject_id', flat=True):
                    subjects_seen.add(sr)
            except (ValidationError, Exception) as e:
                summary["failed"] += 1
                summary["errors"].append({"student": getattr(student, "full_name", str(student)), "error": str(e)})

        # Run ranking ONCE after all students in the class are computed
        if summary["computed"] > 0:
            RankingService.rank_class(classroom, term, academic_year)
            for subject_id in subjects_seen:
                RankingService.rank_subject(classroom, term, academic_year, subject_id)

        return summary