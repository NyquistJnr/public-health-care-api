# core/renderers.py
from rest_framework.renderers import JSONRenderer

class UniformJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            data = {}

        status_code = renderer_context['response'].status_code

        response_dict = {
            'status': 'success' if status_code < 400 else 'error',
            'message': 'Request processed successfully' if status_code < 400 else 'An error occurred',
            'data': None,
            'errors': None
        }

        if status_code >= 400:
            response_dict['errors'] = data
            
            if isinstance(data, dict):
                if 'detail' in data:
                    response_dict['message'] = str(data['detail'])
                
                elif len(data) > 0:
                    first_field = next(iter(data))
                    first_error = data[first_field]
                    
                    if isinstance(first_error, list) and len(first_error) > 0:
                        error_text = str(first_error[0])
                    else:
                        error_text = str(first_error)

                    if first_field == 'non_field_errors':
                        response_dict['message'] = error_text
                    else:
                        clean_field_name = first_field.replace('_', ' ').capitalize()
                        response_dict['message'] = f"{clean_field_name}: {error_text}"
        else:
            response_dict['data'] = data

        return super().render(response_dict, accepted_media_type, renderer_context)
