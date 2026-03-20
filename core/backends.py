# core/backends.py
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        login_identifier = kwargs.get('email', username)
        
        if not login_identifier:
            return None

        try:
            user = User.objects.get(
                Q(username__iexact=login_identifier) | Q(email__iexact=login_identifier)
            )
        except User.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            if user.facility and not user.facility.is_active:
                raise AuthenticationFailed("Access Denied: Your facility has been suspended by the State. Please contact administration.")
                
            return user
            
        return None
