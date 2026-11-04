"""
Django App Configuration for Enrollment app
"""

from django.apps import AppConfig


class EnrollmentConfig(AppConfig):
    """
    Configuration class for the Enrollment Django application.
    Provides enrollment and progress tracking functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.enrollment'
    verbose_name = 'Enrollment'
    verbose_name_plural = 'Enrollments'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
