# core/exceptions.py

import logging
from rest_framework.views import exception_handler
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework import status

from core.audit_context import get_client_ip

logger = logging.getLogger(__name__)

def custom_api_exception_handler(exc, context):
    """
    Catches raw Django errors and converts them to DRF errors before
    passing them to our custom UniformJSONRenderer. Also catches unhandled
    500 server crashes to return JSON instead of HTML.
    """
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict'):
            exc = DRFValidationError(detail=exc.message_dict)
        else:
            exc = DRFValidationError(detail={"non_field_errors": exc.messages})

    response = exception_handler(exc, context)

    if response is None:
        logger.error(f"Unhandled Server Error: {exc}", exc_info=True)
        _log_error(exc, context, status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "detail": str(exc)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response


def _log_error(exc, context, status_code):
    # Local import avoids a hard import-time dependency on core.models from this module.
    from core.models import ErrorLog

    request = context.get('request')
    try:
        ErrorLog.objects.create(
            error_message=str(exc),
            endpoint=getattr(request, 'path', None),
            status_code=status_code,
            ip_address=get_client_ip(request) if request else None,
            user=request.user if request and getattr(request, 'user', None) and request.user.is_authenticated else None,
        )
    except Exception:
        # Never let logging failure mask the original error response.
        logger.error("Failed to persist ErrorLog", exc_info=True)
