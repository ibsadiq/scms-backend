from django.core.exceptions import ValidationError
from django.utils import timezone
from ..models import LifecycleState

class ResultLifecycleService:
    """
    Central service for managing result lifecycle transitions.
    Enforces workflow rules for TermResult and AnnualResult.
    """

    ALLOWED_TRANSITIONS = {
        LifecycleState.DRAFT: [LifecycleState.COMPUTED],
        LifecycleState.COMPUTED: [LifecycleState.LOCKED],
        LifecycleState.LOCKED: [LifecycleState.HOMEROOM_APPROVED, LifecycleState.COMPUTED], # COMPUTED is allowed for recomputation after unlock
        LifecycleState.HOMEROOM_APPROVED: [LifecycleState.ADMIN_APPROVED, LifecycleState.COMPUTED],
        LifecycleState.ADMIN_APPROVED: [LifecycleState.PUBLISHED, LifecycleState.COMPUTED],
        LifecycleState.PUBLISHED: [LifecycleState.COMPUTED],
    }

    @staticmethod
    def _validate_transition(result, new_state):
        current_state = result.lifecycle_state
        if new_state not in ResultLifecycleService.ALLOWED_TRANSITIONS.get(current_state, []):
            raise ValidationError(
                f"Invalid transition from {current_state} to {new_state}."
            )

    @staticmethod
    def mark_computed(result, user=None):
        ResultLifecycleService._validate_transition(result, LifecycleState.COMPUTED)
        result.lifecycle_state = LifecycleState.COMPUTED
        result.is_locked = False
        result.homeroom_approved = False
        result.homeroom_approved_by = None
        result.homeroom_approved_at = None
        result.admin_approved = False
        result.admin_approved_by = None
        result.admin_approved_at = None
        result.is_published = False
        result.published_by = None
        result.published_date = None
        result.save()
        return result

    @staticmethod
    def lock(result, user):
        ResultLifecycleService._validate_transition(result, LifecycleState.LOCKED)
        result.lifecycle_state = LifecycleState.LOCKED
        result.is_locked = True
        result.locked_by = user
        result.locked_at = timezone.now()
        result.save()
        return result

    @staticmethod
    def homeroom_approve(result, user, delegated=False):
        ResultLifecycleService._validate_transition(result, LifecycleState.HOMEROOM_APPROVED)
        result.lifecycle_state = LifecycleState.HOMEROOM_APPROVED
        result.homeroom_approved = True
        result.homeroom_approved_by = user
        result.homeroom_approved_at = timezone.now()
        result.homeroom_approval_delegated = delegated
        result.save()
        return result

    @staticmethod
    def admin_approve(result, user):
        ResultLifecycleService._validate_transition(result, LifecycleState.ADMIN_APPROVED)
        result.lifecycle_state = LifecycleState.ADMIN_APPROVED
        result.admin_approved = True
        result.admin_approved_by = user
        result.admin_approved_at = timezone.now()
        result.save()
        return result

    @staticmethod
    def publish(result, user):
        ResultLifecycleService._validate_transition(result, LifecycleState.PUBLISHED)
        result.lifecycle_state = LifecycleState.PUBLISHED
        result.is_published = True
        result.published_by = user
        result.published_date = timezone.now()
        result.save()
        return result

    @staticmethod
    def unpublish(result, user):
        # We allow reverting from PUBLISHED back to ADMIN_APPROVED
        if result.lifecycle_state != LifecycleState.PUBLISHED:
            raise ValidationError("Result is not published.")
        result.lifecycle_state = LifecycleState.ADMIN_APPROVED
        result.is_published = False
        result.published_by = None
        result.published_date = None
        result.save()
        return result

    @staticmethod
    def unlock_for_amendment(result, user, amendment_request, reason):
        """
        Special transition that handles approved amendments.
        """
        # Unlock logic delegates to mark_computed which cleans up approvals
        ResultLifecycleService.mark_computed(result, user)
        
        result.unlocked_by = user
        result.unlocked_at = timezone.now()
        result.unlock_reason = reason
        result.save()
        return result
