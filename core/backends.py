# core/backends.py
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Allows users to log in using either their email address or their username.
    This seamlessly bridges CLI-created users and API-created users.
    """
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
            return user
            
        return None
