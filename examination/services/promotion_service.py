from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from ..models import PromotionDecision, LifecycleState

class PromotionService:

    @staticmethod
    @transaction.atomic
    def evaluate_promotion(annual_result, rule):
        from administration.models import Term
        expected_terms = Term.objects.filter(academic_year=annual_result.academic_year).count()
        actual_terms = annual_result.student.term_results.filter(academic_year=annual_result.academic_year).count()
        total_subjects = annual_result.subjects.count()
        
        required_subject_ids = set(rule.required_pass_subjects.values_list("id", flat=True))

        structured_reasons = {
            "minimum_average": float(rule.minimum_average),
            "actual_average": float(annual_result.average_percentage),
            "minimum_subject_pass": float(rule.minimum_subject_pass),
            "max_failed_subjects": rule.max_failed_subjects,
            "required_subject_ids": list(required_subject_ids),
            "expected_terms": expected_terms,
            "actual_terms": actual_terms,
            "total_subjects": total_subjects,
        }
        
        # 1. Completeness Check
        is_incomplete = False
        incompleteness_reasons = []
        
        if actual_terms < expected_terms and expected_terms > 0:
            is_incomplete = True
            incompleteness_reasons.append(f"Expected {expected_terms} term(s), but only found {actual_terms}.")
            
        if total_subjects == 0:
            is_incomplete = True
            incompleteness_reasons.append("No subject results found for this annual record.")
            
        from django.db import models
        missing_terms_filter = models.Q()
        if expected_terms >= 1:
            missing_terms_filter |= models.Q(first_term_status="MISSING")
        if expected_terms >= 2:
            missing_terms_filter |= models.Q(second_term_status="MISSING")
        if expected_terms >= 3:
            missing_terms_filter |= models.Q(third_term_status="MISSING")

        missing_terms_count = annual_result.subjects.filter(missing_terms_filter).count() if missing_terms_filter else 0
        
        structured_reasons["missing_terms_in_subjects"] = missing_terms_count
        if missing_terms_count > 0:
            # Depending on school strictness, they might want this to trigger PENDING_REVIEW
            # We flag it here for safety.
            is_incomplete = True
            incompleteness_reasons.append(f"Found {missing_terms_count} subject(s) with missing term data.")
            
        structured_reasons["completeness_status"] = "INCOMPLETE" if is_incomplete else "COMPLETE"
        
        if is_incomplete:
            status = PromotionDecision.Status.PENDING_REVIEW
            reasons = ["Result is incomplete:"] + incompleteness_reasons
            failed_subjects = 0
            structured_reasons["failed_subjects_count"] = 0
            structured_reasons["failed_subject_ids"] = []
            structured_reasons["required_subject_failures"] = []
        else:
            failed_subjects_qs = annual_result.subjects.filter(is_pass=False)
            failed_subjects = failed_subjects_qs.count()
            failed_subject_ids = list(failed_subjects_qs.values_list("subject_id", flat=True))
            failed_subject_names = list(failed_subjects_qs.values_list("subject__name", flat=True))
            
            meets_average = annual_result.average_percentage >= rule.minimum_average
            within_fail_limit = failed_subjects <= rule.max_failed_subjects
    
            missing_required_names = []
            missing_required_ids = []
            if required_subject_ids:
                passed_required = set(
                    annual_result.subjects.filter(
                        subject_id__in=required_subject_ids, is_pass=True
                    ).values_list("subject_id", flat=True)
                )
                missing_required_ids = list(required_subject_ids - passed_required)
                if missing_required_ids:
                    from academic.models import Subject
                    missing_required_names = list(Subject.objects.filter(id__in=missing_required_ids).values_list('name', flat=True))
                    within_fail_limit = False
                    
            structured_reasons["failed_subjects_count"] = failed_subjects
            structured_reasons["failed_subject_ids"] = failed_subject_ids
            structured_reasons["failed_subject_names"] = failed_subject_names
            structured_reasons["required_subject_failures"] = missing_required_names

            status = PromotionDecision.Status.PROMOTED if (meets_average and within_fail_limit) else PromotionDecision.Status.NOT_PROMOTED
            
            reasons = []
            if status != PromotionDecision.Status.PROMOTED:
                reasons.append(f"Average {annual_result.average_percentage}% (min {rule.minimum_average}%)")
                if failed_subjects > rule.max_failed_subjects:
                    reasons.append(f"Failed {failed_subjects} subjects (max allowed: {rule.max_failed_subjects})")
                if missing_required_names:
                    reasons.append(f"Failed required subjects: {', '.join(missing_required_names)}")
            else:
                reasons.append("Met all promotion criteria.")

        decision, created = PromotionDecision.objects.update_or_create(
            annual_result=annual_result,
            defaults={
                "status": status,
                "reasons": "\n".join(reasons),
                "structured_reasons": structured_reasons,
                "failed_subjects_count": failed_subjects,
            }
        )
        
        return decision

    @staticmethod
    @transaction.atomic
    def override_promotion(annual_result, user, new_status, reason, promoted_to=None):
        if not hasattr(annual_result, "promotion_decision"):
            raise ValidationError("No promotion decision exists to override.")
            
        decision = annual_result.promotion_decision
        
        # Only allow overrides if the result is not yet completely published/locked
        if annual_result.lifecycle_state in [LifecycleState.LOCKED, LifecycleState.PUBLISHED]:
            raise ValidationError("Cannot override promotion for a locked or published result. Request an amendment first.")
            
        decision.status = new_status
        decision.is_overridden = True
        decision.overridden_by = user
        decision.overridden_at = timezone.now()
        decision.override_reason = reason
        decision.promoted_to = promoted_to
        decision.save()
        
        # In a full system, you would also create a ResultAuditLog here.
        # e.g., ResultAuditLog.objects.create(annual_result=annual_result, action="PROMOTION_OVERRIDDEN", ...)
        
        return decision