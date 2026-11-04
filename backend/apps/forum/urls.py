"""
Forum URLs for Enterprise LMS
Provides URL routing for forum endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ForumViewSet, PostViewSet

# Create router for forum endpoints
router = DefaultRouter()

# Forum endpoints
router.register(r'', ForumViewSet, basename='forum')

# Post endpoints (nested under forums)
router.register(r'posts', PostViewSet, basename='post')

urlpatterns = [
    path('', include(router.urls)),
]
