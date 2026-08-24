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
            logger.warning("Database integrity conflict", exc_info=True)
            return JsonResponse(
                {
                    "error": "Conflict",
                    "detail": "The request conflicts with an existing record or data constraint.",
                },
                status=409,
            )

        except DatabaseError as e:
            logger.error("Unexpected database error", exc_info=True)
            return JsonResponse(
                {"error": "Database Error", "detail": "The database operation could not be completed."},
                status=500,
            )

        # DRF exceptions (optional, for future use if you integrate DRF globally)
        except APIException as e:
            return JsonResponse(
                {"error": "API Error", "detail": str(e.detail)},
                status=e.status_code,
            )

        # Catch-all for other exceptions
        except Exception:
            logger.error("Unhandled exception: %s", traceback.format_exc())
            return JsonResponse(
                {"error": "Internal Server Error", "detail": "The request could not be completed."},
                status=500,
            )
