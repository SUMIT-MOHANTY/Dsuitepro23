"""
Django App Configuration for Notifications app
"""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """
    Configuration class for the Notifications Django application.
    Provides email and in-app notification functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'
    verbose_name = 'Notifications'
    verbose_name_plural = 'Notifications'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
