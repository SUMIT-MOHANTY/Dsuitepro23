"""
Django App Configuration for Certificates app
"""

from django.apps import AppConfig


class CertificatesConfig(AppConfig):
    """
    Configuration class for the Certificates Django application.
    Provides certificate generation and verification functionality.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.certificates'
    verbose_name = 'Certificates'
    verbose_name_plural = 'Certificates'

    def ready(self):
        """
        Called when the app is ready. Import signal handlers here.
        """
        # Import signal handlers
        pass
