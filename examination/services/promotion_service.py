from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from ..models import PromotionDecision, LifecycleState

class PromotionService:

    @staticmethod
    @transaction.atomic
    def evaluate_promotion(annual_result, rule):
        failed_subjects = annual_result.subjects.filter(is_pass=False).count()
        meets_average = annual_result.average_percentage >= rule.minimum_average
        within_fail_limit = failed_subjects <= rule.max_failed_subjects

        required_subject_ids = set(rule.required_pass_subjects.values_list("id", flat=True))
        missing_required = set()
        if required_subject_ids:
            passed_required = set(
                annual_result.subjects.filter(
                    subject_id__in=required_subject_ids, is_pass=True
                ).values_list("subject_id", flat=True)
            )
            missing_required = required_subject_ids - passed_required
            within_fail_limit = within_fail_limit and not missing_required

        status = PromotionDecision.Status.PROMOTED if (meets_average and within_fail_limit) else PromotionDecision.Status.NOT_PROMOTED
        
        reasons = []
        if status != PromotionDecision.Status.PROMOTED:
            reasons.append(f"Average {annual_result.average_percentage}% (min {rule.minimum_average}%)")
            if failed_subjects:
                reasons.append(f"Failed {failed_subjects} subjects (max allowed: {rule.max_failed_subjects})")
            if missing_required:
                from academic.models import Subject
                missing_names = Subject.objects.filter(id__in=missing_required).values_list('name', flat=True)
                reasons.append(f"Failed required subjects: {', '.join(missing_names)}")

        decision, created = PromotionDecision.objects.update_or_create(
            annual_result=annual_result,
            defaults={
                "status": status,
                "reasons": "\n".join(reasons),
                "failed_subjects_count": failed_subjects,
            }
        )
        
        # Legacy fallback
        annual_result.is_promoted = (status == PromotionDecision.Status.PROMOTED)
        annual_result.promotion_reason = decision.reasons
        annual_result.save(update_fields=["is_promoted", "promotion_reason"])

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
        
        # Update legacy fallback
        annual_result.is_promoted = (new_status == PromotionDecision.Status.PROMOTED)
        annual_result.promoted_to = promoted_to
        annual_result.save(update_fields=["is_promoted", "promoted_to"])
        
        # In a full system, you would also create a ResultAuditLog here.
        # e.g., ResultAuditLog.objects.create(annual_result=annual_result, action="PROMOTION_OVERRIDDEN", ...)
        
        return decision