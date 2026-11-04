"""
Django App Configuration for Forum app
"""

from django.apps import AppConfig


class ForumConfig(AppConfig):
    """
    Configuration class for the Forum Django application.
    Provides discussion forum functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.forum'
    verbose_name = 'Forum'
    verbose_name_plural = 'Forums'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
