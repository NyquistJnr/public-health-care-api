# core/exceptions.py
from rest_framework.views import exception_handler
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

def custom_api_exception_handler(exc, context):
    """
    Catches raw Django errors and converts them to DRF errors before 
    passing them to our custom UniformJSONRenderer.
    """
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict'):
            exc = DRFValidationError(detail=exc.message_dict)
        else:
            exc = DRFValidationError(detail={"non_field_errors": exc.messages})
            
    response = exception_handler(exc, context)
    
    return response
