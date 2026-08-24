from rest_framework.throttling import ScopedRateThrottle


class BackgroundJobCreateThrottle(ScopedRateThrottle):
    def allow_request(self, request, view):
        view.throttle_scope = "background_job_create"
        return super().allow_request(request, view)
