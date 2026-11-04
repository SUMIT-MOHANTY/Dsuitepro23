"""
Django App Configuration for Analytics app
"""

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """
    Configuration class for the Analytics Django application.
    Provides reporting and analytics functionality for the LMS.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.analytics'
    verbose_name = 'Analytics'
    verbose_name_plural = 'Analytics'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
