"""
Django App Configuration for Courses app
"""

from django.apps import AppConfig


class CoursesConfig(AppConfig):
    """
    Configuration class for the Courses Django application.
    Provides course content management and catalog functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.courses'
    verbose_name = 'Courses'
    verbose_name_plural = 'Courses'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
