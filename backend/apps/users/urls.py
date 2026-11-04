"""
Users URL Configuration for Enterprise LMS
Provides URL routing for authentication and user management endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AuthViewSet,
    UserManagementViewSet,
    RoleViewSet,
    SessionViewSet,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
)

# Create router for viewsets
router = DefaultRouter()

# Auth endpoints
router.register(r'auth', AuthViewSet, basename='auth')

# User management endpoints
router.register(r'users', UserManagementViewSet, basename='users')

# Role management endpoints
router.register(r'roles', RoleViewSet, basename='roles')

# Session management endpoints
router.register(r'sessions', SessionViewSet, basename='sessions')

# URL patterns
urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # JWT Token endpoints (not part of viewset)
    path('auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
]
