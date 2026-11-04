"""
Core URL Configuration for Enterprise LMS
Provides healthcheck and system status endpoints.
"""

from django.urls import path
from .views import HealthCheckView, SystemInfoView


app_name = 'core'

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('info/', SystemInfoView.as_view(), name='system-info'),
]
