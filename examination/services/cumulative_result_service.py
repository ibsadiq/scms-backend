from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import (
    AnnualResult, CumulativeResult, CumulativeSubjectResult,
    CumulativePolicy, LifecycleState
)
from .grade_resolver import GradeResolver
from .term_result_service import TermResultService

class CumulativeResultService:

    @staticmethod
    @transaction.atomic
    def compute_cumulative_result(student, target_academic_year, user):
        """
        Computes the cumulative academic record up to the target academic year.
        """
        # Consume ONLY finalized annual results
        annual_results = list(
            AnnualResult.objects.filter(
                student=student,
                academic_year__start_date__lte=target_academic_year.start_date,
                lifecycle_state__in=[LifecycleState.LOCKED, LifecycleState.PUBLISHED]
            ).select_related("academic_year", "grading_scheme", "classroom")
        )

        if not annual_results:
            return None
            
        latest_annual = next((r for r in annual_results if r.academic_year == target_academic_year), None)
        if not latest_annual:
            latest_annual = max(annual_results, key=lambda r: r.academic_year.start_date)

        # Check if cumulative result exists and is locked
        existing_cumulative = CumulativeResult.objects.filter(
            student=student, academic_year=latest_annual.academic_year
        ).first()
        
        if existing_cumulative and existing_cumulative.lifecycle_state in [LifecycleState.LOCKED, LifecycleState.PUBLISHED]:
            raise ValidationError("Cannot recompute a locked or published cumulative result.")

        scheme = latest_annual.grading_scheme
        policy = getattr(scheme, "cumulative_policy", None)

        # Fallback defaults if no policy configured
        method = CumulativePolicy.CumulativeComputationMethod.AVERAGE_ANNUAL_RESULTS
        include_failed = True
        include_repeated = False
        
        policy_snapshot = {
            "computation_method": method,
            "include_failed_years": include_failed,
            "include_repeated_years": include_repeated,
            "weights": {}
        }

        if policy:
            method = policy.computation_method
            include_failed = policy.include_failed_years
            include_repeated = policy.include_repeated_years
            
            policy_snapshot = {
                "computation_method": method,
                "include_failed_years": include_failed,
                "include_repeated_years": include_repeated,
                "weights": {w.grade_level.name: float(w.weight) for w in policy.annual_weights.all()}
            }

        # Sort annual results chronologically
        annual_results.sort(key=lambda r: r.academic_year.start_date)

        # Group by grade level to identify repeated years
        by_grade_level = {}
        for ar in annual_results:
            by_grade_level.setdefault(ar.classroom.grade_level_id, []).append(ar)

        valid_annual_results = []
        for grade_level_id, ars in by_grade_level.items():
            if not include_repeated:
                # Discard older repeated years, keep only the latest attempt for this grade level
                ars = [ars[-1]]
                
            for ar in ars:
                decision_status = getattr(ar.promotion_decision, 'status', None) if hasattr(ar, 'promotion_decision') else None
                
                # If a result is PENDING_REVIEW, it's incomplete and shouldn't bleed into cumulative records
                if decision_status == "PENDING_REVIEW":
                    continue
                    
                if not include_failed and decision_status in ["NOT_PROMOTED", "REPEAT_CLASS"]:
                    continue
                    
                valid_annual_results.append(ar)

        if not valid_annual_results:
            return None

        cumulative, _ = CumulativeResult.objects.update_or_create(
            student=student, academic_year=latest_annual.academic_year,
            defaults={
                "grading_scheme": scheme,
                "computed_by": user,
                "policy_snapshot": policy_snapshot
            }
        )
        
        CumulativeResultService._compute_subject_cumulatives(cumulative, valid_annual_results, method, policy)
        CumulativeResultService._aggregate_cumulative(cumulative, scheme)
        
        return cumulative

    @staticmethod
    def _compute_subject_cumulatives(cumulative, annual_results, method, policy):
        weights = {}
        if policy and method == CumulativePolicy.CumulativeComputationMethod.WEIGHTED_ANNUAL_RESULTS:
            weights = {w.grade_level_id: Decimal(str(w.weight)) for w in policy.annual_weights.all()}

        by_subject = {}
        for ar in annual_results:
            for sr in ar.subjects.select_related("subject", "annual_result__classroom", "annual_result__academic_year"):
                by_subject.setdefault(sr.subject_id, []).append(sr)

        for subject_id, srs in by_subject.items():
            if not srs:
                continue
                
            if method == CumulativePolicy.CumulativeComputationMethod.FINAL_YEAR_ONLY:
                latest_sr = sorted(srs, key=lambda s: s.annual_result.academic_year.start_date)[-1]
                cum_avg = latest_sr.annual_average
            elif method == CumulativePolicy.CumulativeComputationMethod.WEIGHTED_ANNUAL_RESULTS:
                total_weight = Decimal("0")
                weighted_sum = Decimal("0")
                for sr in srs:
                    gl_id = sr.annual_result.classroom.grade_level_id
                    weight = weights.get(gl_id, Decimal("0"))
                    if weight > Decimal("0"):
                        weighted_sum += (sr.annual_average * weight / Decimal("100"))
                        total_weight += weight
                if total_weight > Decimal("0"):
                    cum_avg = round(weighted_sum * (Decimal("100") / total_weight), 2)
                else:
                    cum_avg = round(sum(sr.annual_average for sr in srs) / len(srs), 2)
            else:
                # AVERAGE_ANNUAL_RESULTS
                cum_avg = round(sum(sr.annual_average for sr in srs) / len(srs), 2)
                
            grade_resolver = GradeResolver(cumulative.grading_scheme).resolve
            rule = grade_resolver(cum_avg)
            grade = rule.grade
            grade_point = rule.grade_point

            csr, _ = CumulativeSubjectResult.objects.update_or_create(
                cumulative_result=cumulative, subject_id=subject_id,
                defaults={
                    "cumulative_average": cum_avg,
                    "grade": grade,
                    "grade_point": grade_point,
                }
            )
            # Add traceable links to the exact annual subject results used
            csr.annual_subject_results.set(srs)

    @staticmethod
    def _aggregate_cumulative(cumulative, scheme):
        subjects = cumulative.subjects.all()
        if not subjects:
            return

        total = sum(sr.cumulative_average for sr in subjects)
        avg = round(total / len(subjects), 2)
        
        grade_resolver = GradeResolver(scheme).resolve
        rule = grade_resolver(avg)
        cumulative.grade = rule.grade
        cumulative.cumulative_gpa = rule.grade_point

        cumulative.total_marks = total
        cumulative.cumulative_average = avg
        cumulative.save()
