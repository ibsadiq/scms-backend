from django.http import JsonResponse
from django.core.exceptions import (
    ValidationError,
    ObjectDoesNotExist,
    PermissionDenied,
)
from django.db import IntegrityError, DatabaseError
from rest_framework.exceptions import APIException
import logging
import traceback

logger = logging.getLogger(__name__)


class CustomExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)

        # Common Django errors
        except ValidationError as e:
            return JsonResponse(
                {
                    "error": "Validation Error",
                    "detail": (
                        e.message_dict if hasattr(e, "message_dict") else e.messages
                    ),
                },
                status=400,
            )

        except ObjectDoesNotExist as e:
            return JsonResponse(
                {"error": "Not Found", "detail": str(e)},
                status=404,
            )

        except PermissionDenied as e:
            return JsonResponse(
                {"error": "Permission Denied", "detail": str(e)},
                status=403,
            )

        except IntegrityError as e:
            return JsonResponse(
                {"error": "Integrity Error", "detail": str(e)},
                status=400,
            )

        except DatabaseError as e:
            return JsonResponse(
                {"error": "Database Error", "detail": str(e)},
                status=500,
            )

        # DRF exceptions (optional, for future use if you integrate DRF globally)
        except APIException as e:
            return JsonResponse(
                {"error": "API Error", "detail": str(e.detail)},
                status=e.status_code,
            )

        # Catch-all for other exceptions
        except Exception as e:
            logger.error("Unhandled exception: %s", traceback.format_exc())
            return JsonResponse(
                {"error": "Internal Server Error", "detail": str(e)},
                status=500,
            )
