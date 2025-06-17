from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from rest_framework import status
import traceback


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None:
        return Response(
            {"error": response.status_code, "detail": response.data},
            status=response.status_code,
        )

    # Handle non-DRF errors (500 errors)
    return Response(
        {"error": "Server Error", "detail": str(exc)},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
