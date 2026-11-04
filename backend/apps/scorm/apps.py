"""
Django App Configuration for SCORM app
"""

from django.apps import AppConfig


class ScormConfig(AppConfig):
    """
    Configuration class for the SCORM Django application.
    Provides SCORM 1.2/xAPI runtime functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scorm'
    verbose_name = 'SCORM'
    verbose_name_plural = 'SCORM'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
