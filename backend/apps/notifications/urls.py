"""
Notification URLs for Enterprise LMS
Provides URL routing for notification endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationViewSet,
    NotificationPreferenceViewSet,
    NotificationDigestViewSet
)

# Create router for notification endpoints
router = DefaultRouter()

# Main notification endpoints
router.register(r'', NotificationViewSet, basename='notification')

# Preference endpoints
router.register(r'preferences', NotificationPreferenceViewSet, basename='notification-preference')

# Digest endpoints
router.register(r'digests', NotificationDigestViewSet, basename='notification-digest')

urlpatterns = [
    path('', include(router.urls)),
]
