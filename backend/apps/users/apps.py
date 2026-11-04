"""
Django App Configuration for Users app
"""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """
    Configuration class for the Users Django application.
    Provides user management and authentication functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    verbose_name = 'Users'
    verbose_name_plural = 'Users'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
