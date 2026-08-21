from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from ..models import (
    TermResult, AnnualResult, AnnualSubjectResult, PromotionRule,
    TermWeightConfig
)
from .grade_resolver import GradeResolver
from .term_result_service import TermResultService


class AnnualResultService:

    @staticmethod
    @transaction.atomic
    def compute_annual_result(student, academic_year, user):
        term_results = list(
            TermResult.objects.filter(student=student, academic_year=academic_year)
            .select_related("term", "grading_scheme", "classroom")
        )
        if not term_results:
            raise ValidationError("No term results found for this academic year.")

        latest = max(term_results, key=lambda r: r.term.start_date)
        scheme = latest.grading_scheme
        rule = getattr(scheme, "promotion_rule", None)
        if not rule:
            raise ValidationError("No promotion rule configured for this grading scheme.")

        existing_result = AnnualResult.objects.filter(
            student=student, academic_year=academic_year
        ).first()
        
        if existing_result and existing_result.is_locked:
            raise ValidationError(f"Annual result for student '{getattr(student, 'full_name', str(student))}' is locked. Unlock result first to re-compute.")

        annual_result, _ = AnnualResult.objects.update_or_create(
            student=student, academic_year=academic_year,
            defaults={
                "classroom": latest.classroom,
                "grading_scheme": latest.grading_scheme,
                "computed_by": user,
            },
        )
        
        AnnualResultService._compute_subject_results(annual_result, term_results, rule)
        AnnualResultService._aggregate_annual_result(annual_result, scheme)

        # Call promotion service to evaluate the result
        from .promotion_service import PromotionService
        PromotionService.evaluate_promotion(annual_result, rule)

        return annual_result

    @staticmethod
    def _compute_subject_results(annual_result, term_results, rule):
        by_subject = {}
        sorted_term_results = sorted(term_results, key=lambda r: r.term.start_date)
        # Group by subject
        for idx, term_result in enumerate(sorted_term_results):
            term_num = getattr(term_result.term, "term_number", idx + 1)
            for sr in term_result.subject_results.select_related("subject"):
                bucket = by_subject.setdefault(sr.subject_id, {})
                if term_num == 1:
                    bucket["first_term"] = sr
                elif term_num == 2:
                    bucket["second_term"] = sr
                elif term_num == 3:
                    bucket["third_term"] = sr
                bucket["latest"] = sr

        method = rule.annual_computation_method
        missing_policy = rule.missing_term_policy
        
        term_weights = {}
        if method == PromotionRule.AnnualComputationMethod.WEIGHTED_TERMS:
            weights = TermWeightConfig.objects.filter(promotion_rule=rule)
            term_weights = {w.term_number: w.weight for w in weights}

        for subject_id, bucket in by_subject.items():
            t1 = bucket.get("first_term")
            t2 = bucket.get("second_term")
            t3 = bucket.get("third_term")
            
            annual_avg = Decimal("0.00")
            is_pass = bucket["latest"].is_pass
            grade = bucket["latest"].grade
            grade_point = bucket["latest"].grade_point
            
            # Helper to handle missing
            def handle_missing(sr_obj):
                if sr_obj is not None:
                    if hasattr(sr_obj, 'status') and sr_obj.status == "EXCUSED":
                        # Excused terms are unconditionally dropped from the annual average
                        return None, False
                    return sr_obj.percentage, True
                if missing_policy == PromotionRule.MissingTermPolicy.TREAT_AS_ZERO:
                    return Decimal("0.00"), True
                return None, False

            if method == PromotionRule.AnnualComputationMethod.FINAL_TERM_ONLY:
                annual_avg = t3.percentage if t3 is not None else Decimal("0.00")
            
            elif method == PromotionRule.AnnualComputationMethod.WEIGHTED_TERMS:
                total_weight = Decimal("0")
                weighted_sum = Decimal("0")
                
                s1, use1 = handle_missing(t1)
                if use1 and 1 in term_weights:
                    weighted_sum += (s1 * term_weights[1] / Decimal("100"))
                    total_weight += term_weights[1]
                    
                s2, use2 = handle_missing(t2)
                if use2 and 2 in term_weights:
                    weighted_sum += (s2 * term_weights[2] / Decimal("100"))
                    total_weight += term_weights[2]
                    
                s3, use3 = handle_missing(t3)
                if use3 and 3 in term_weights:
                    weighted_sum += (s3 * term_weights[3] / Decimal("100"))
                    total_weight += term_weights[3]
                    
                if total_weight > Decimal("0"):
                    # Normalize if total weight < 100
                    annual_avg = round(weighted_sum * (Decimal("100") / total_weight), 2)
            
            else: # AVERAGE_ALL_TERMS
                scores = []
                for s in (t1, t2, t3):
                    val, use = handle_missing(s)
                    if use:
                        scores.append(val)
                if scores:
                    annual_avg = round(sum(scores) / len(scores), 2)
            
            # Re-resolve grade for annual average
            grade_resolver = GradeResolver(annual_result.grading_scheme).resolve
            annual_grade_rule = grade_resolver(annual_avg)
            grade = annual_grade_rule.grade
            grade_point = annual_grade_rule.grade_point
            is_pass = annual_avg >= Decimal(str(rule.minimum_subject_pass))
                
            if missing_policy == PromotionRule.MissingTermPolicy.FAIL_SUBJECT:
                # If any of the expected terms are None OR explicitly marked MISSING, then fail
                has_missing = False
                for term_sr in [t1, t2, t3]:
                    if term_sr is None:
                        has_missing = True
                    elif hasattr(term_sr, 'status') and term_sr.status == "MISSING":
                        has_missing = True
                
                if has_missing:
                    is_pass = False

            AnnualSubjectResult.objects.update_or_create(
                annual_result=annual_result, subject_id=subject_id,
                defaults={
                    "first_term": t1.percentage if t1 else Decimal("0"),
                    "second_term": t2.percentage if t2 else Decimal("0"),
                    "third_term": t3.percentage if t3 else Decimal("0"),
                    "first_term_status": t1.status if hasattr(t1, 'status') and t1 else ("MISSING" if t1 is None else "AVAILABLE"),
                    "second_term_status": t2.status if hasattr(t2, 'status') and t2 else ("MISSING" if t2 is None else "AVAILABLE"),
                    "third_term_status": t3.status if hasattr(t3, 'status') and t3 else ("MISSING" if t3 is None else "AVAILABLE"),
                    "annual_average": annual_avg,
                    "grade": grade,
                    "grade_point": grade_point,
                    "is_pass": is_pass,
                },
            )

    @staticmethod
    def _aggregate_annual_result(annual_result, scheme):
        subject_results = annual_result.subjects.all()
        if not subject_results:
            return

        total_marks = sum(sr.annual_average for sr in subject_results)
        average = round(total_marks / len(subject_results), 2)
        
        grade_resolver = GradeResolver(scheme).resolve
        overall_rule = grade_resolver(average)
        annual_result.grade = overall_rule.grade
        annual_result.gpa = overall_rule.grade_point

        annual_result.total_marks = total_marks
        annual_result.average_percentage = average
        annual_result.save()
