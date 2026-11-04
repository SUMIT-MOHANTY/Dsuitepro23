"""
Django App Configuration for Core app
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """
    Configuration class for the Core Django application.
    Provides abstract base models and shared utilities for all LMS apps.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'
    verbose_name_plural = 'Core'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
