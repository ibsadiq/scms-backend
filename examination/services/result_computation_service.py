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
from .term_result_service import TermResultService


class ResultComputationService:

    @staticmethod
    def _get_grade_resolver(scheme):
        return TermResultService._get_grade_resolver(scheme)

    @staticmethod
    def compute_student_term_result(
        student, term, academic_year, user,
        scheme=None, grade_resolver=None, skip_ranking=False,
        pre_fetched_enrollment=None, pre_fetched_entries=None, pre_fetched_existing_result=None
    ):
        return TermResultService.compute_student_term_result(
            student=student, term=term, academic_year=academic_year, user=user,
            scheme=scheme, grade_resolver=grade_resolver, skip_ranking=skip_ranking,
            pre_fetched_enrollment=pre_fetched_enrollment,
            pre_fetched_entries=pre_fetched_entries,
            pre_fetched_existing_result=pre_fetched_existing_result
        )

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

        # Pre-fetch enrollments for all students
        enrollments = list(StudentClassEnrollment.objects.filter(
            student__in=students, academic_year=academic_year, classroom=classroom
        ).select_related("classroom"))
        enrollments_by_student = {e.student_id: e for e in enrollments}

        # Pre-fetch existing results for all students
        existing_results = list(TermResult.objects.filter(
            student__in=students, term=term, academic_year=academic_year
        ))
        existing_results_by_student = {r.student_id: r for r in existing_results}

        # Pre-fetch assessment entries for all enrollments
        entries = list(AssessmentEntry.objects.filter(
            student__in=enrollments
        ).select_related("component", "subject", "component__scheme"))
        entries_by_enrollment = {}
        for entry in entries:
            entries_by_enrollment.setdefault(entry.student_id, []).append(entry)

        summary = {"computed": 0, "failed": 0, "errors": []}
        subjects_seen = set()

        for i, student in enumerate(students):
            if progress_callback:
                progress_callback(i, len(students), student)
                
            enrollment = enrollments_by_student.get(student.id)
            student_entries = entries_by_enrollment.get(enrollment.id, []) if enrollment else []
            existing_result = existing_results_by_student.get(student.id)
            
            try:
                result = ResultComputationService.compute_student_term_result(
                    student=student,
                    term=term,
                    academic_year=academic_year,
                    user=user,
                    scheme=scheme,
                    grade_resolver=grade_resolver,
                    skip_ranking=True,
                    pre_fetched_enrollment=enrollment,
                    pre_fetched_entries=student_entries,
                    pre_fetched_existing_result=existing_result
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