"""
Django App Configuration for Assessment app
"""

from django.apps import AppConfig


class AssessmentConfig(AppConfig):
    """
    Configuration class for the Assessment Django application.
    Provides quiz, assignment, and grading functionality for the LMS.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.assessment'
    verbose_name = 'Assessment'
    verbose_name_plural = 'Assessments'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
