# core/exceptions.py

import logging
from rest_framework.views import exception_handler
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework import status

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
        
        return Response({
            "detail": str(exc)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    return response
