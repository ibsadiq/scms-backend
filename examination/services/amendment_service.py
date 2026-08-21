from django.db import transaction
from django.utils import timezone
from ..models import (
    TermResult, AnnualResult, ResultAmendmentRequest,
    LifecycleState
)

class AmendmentService:

    @staticmethod
    def request_amendment(result, user, reason):
        if result.lifecycle_state not in [LifecycleState.LOCKED, LifecycleState.PUBLISHED]:
            raise ValueError("Only locked or published results can be amended.")
            
        if isinstance(result, TermResult):
            return ResultAmendmentRequest.objects.create(
                term_result=result,
                requested_by=user,
                reason=reason
            )
        elif isinstance(result, AnnualResult):
            return ResultAmendmentRequest.objects.create(
                annual_result=result,
                requested_by=user,
                reason=reason
            )
        else:
            raise ValueError("Invalid result type for amendment.")

    @staticmethod
    @transaction.atomic
    def resolve_amendment(request, user, status, notes=""):
        if request.status != ResultAmendmentRequest.Status.PENDING:
            raise ValueError("Amendment request is not pending.")
            
        request.status = status
        request.resolved_by = user
        request.resolved_at = timezone.now()
        request.resolution_notes = notes
        request.save()
        
        if status == ResultAmendmentRequest.Status.APPROVED:
            # Unlock the result atomically via LifecycleService
            result = request.term_result or request.annual_result
            if result:
                from .result_lifecycle_service import ResultLifecycleService
                ResultLifecycleService.unlock_for_amendment(
                    result=result,
                    user=user,
                    amendment_request=request,
                    reason=request.reason
                )
                
        return request
