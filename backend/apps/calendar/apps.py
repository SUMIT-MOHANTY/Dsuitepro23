"""
Django App Configuration for Calendar app
"""

from django.apps import AppConfig


class CalendarConfig(AppConfig):
    """
    Configuration class for the Calendar Django application.
    Provides calendar and scheduling functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.calendar'
    verbose_name = 'Calendar'
    verbose_name_plural = 'Calendars'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
