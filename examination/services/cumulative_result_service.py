from decimal import Decimal
from django.db import transaction
from ..models import (
    AnnualResult, CumulativeResult, CumulativeSubjectResult,
    CumulativePolicy
)
from .term_result_service import TermResultService

class CumulativeResultService:

    @staticmethod
    @transaction.atomic
    def compute_cumulative_result(student, target_academic_year, user):
        """
        Computes the cumulative academic record up to the target academic year.
        """
        # Fetch all annual results for the student up to and including the target year
        annual_results = list(
            AnnualResult.objects.filter(
                student=student,
                academic_year__start_date__lte=target_academic_year.start_date
            ).select_related("academic_year", "grading_scheme")
        )

        if not annual_results:
            return None
            
        latest_annual = next((r for r in annual_results if r.academic_year == target_academic_year), None)
        if not latest_annual:
            latest_annual = max(annual_results, key=lambda r: r.academic_year.start_date)

        scheme = latest_annual.grading_scheme
        policy = getattr(scheme, "cumulative_policy", None)

        # Fallback defaults if no policy configured
        method = CumulativePolicy.CumulativeComputationMethod.AVERAGE_ANNUAL_RESULTS
        include_failed = True
        
        if policy:
            method = policy.computation_method
            include_failed = policy.include_failed_years
            
        valid_annual_results = []
        for ar in annual_results:
            if not include_failed and getattr(ar, 'promotion_decision', None) and ar.promotion_decision.status != "PROMOTED":
                continue
            valid_annual_results.append(ar)

        if not valid_annual_results:
            return None

        cumulative, _ = CumulativeResult.objects.update_or_create(
            student=student, academic_year=latest_annual.academic_year,
            defaults={
                "grading_scheme": scheme,
                "computed_by": user,
            }
        )
        
        CumulativeResultService._compute_subject_cumulatives(cumulative, valid_annual_results, method)
        CumulativeResultService._aggregate_cumulative(cumulative, scheme)
        
        return cumulative

    @staticmethod
    def _compute_subject_cumulatives(cumulative, annual_results, method):
        by_subject = {}
        for ar in annual_results:
            for sr in ar.subjects.select_related("subject"):
                by_subject.setdefault(sr.subject_id, []).append(sr)

        for subject_id, srs in by_subject.items():
            if not srs:
                continue
                
            if method == CumulativePolicy.CumulativeComputationMethod.FINAL_YEAR_ONLY:
                latest_sr = srs[-1]
                cum_avg = latest_sr.annual_average
            else:
                # AVERAGE_ANNUAL_RESULTS
                cum_avg = round(sum(sr.annual_average for sr in srs) / len(srs), 2)
                
            grade_resolver = TermResultService._get_grade_resolver(cumulative.grading_scheme)
            try:
                rule = grade_resolver(cum_avg)
                grade = rule.grade
                grade_point = rule.grade_point
            except Exception:
                grade = srs[-1].grade
                grade_point = srs[-1].grade_point

            CumulativeSubjectResult.objects.update_or_create(
                cumulative_result=cumulative, subject_id=subject_id,
                defaults={
                    "cumulative_average": cum_avg,
                    "grade": grade,
                    "grade_point": grade_point,
                }
            )

    @staticmethod
    def _aggregate_cumulative(cumulative, scheme):
        subjects = cumulative.subjects.all()
        if not subjects:
            return

        total = sum(sr.cumulative_average for sr in subjects)
        avg = round(total / len(subjects), 2)
        
        grade_resolver = TermResultService._get_grade_resolver(scheme)
        try:
            rule = grade_resolver(avg)
            cumulative.grade = rule.grade
            cumulative.cumulative_gpa = rule.grade_point
        except Exception:
            pass

        cumulative.total_marks = total
        cumulative.cumulative_average = avg
        cumulative.save()
