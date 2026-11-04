"""
Root URL Configuration for Enterprise LMS
Provides the main URL router with healthcheck and /api/v1/ namespace.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Import spectacular views for OpenAPI schema
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),
    
    # API Version 1 - Main API namespace
    path('api/v1/', include([
        # Core endpoints (healthcheck, system info)
        path('', include('apps.core.urls', namespace='core')),
        
        # Users app endpoints (authentication and user management)
        path('', include('apps.users.urls')),
        
        # Courses app endpoints (course catalog and content management)
        path('', include('apps.courses.urls')),
        
        # Assessment app endpoints (quizzes, assignments, grading)
        path('assessments/', include('apps.assessment.urls', namespace='assessment')),
        
        # Forum app endpoints (discussion forums and posts)
        path('forums/', include('apps.forum.urls', namespace='forum')),
        
        # Notifications app endpoints (notifications and preferences)
        path('notifications/', include('apps.notifications.urls', namespace='notifications')),
        
        # Domain app endpoints (to be implemented by domain agents)
        # path('enrollments/', include('apps.enrollment.urls', namespace='enrollment')),
        # path('certificates/', include('apps.certificates.urls', namespace='certificates')),
        # path('scorm/', include('apps.scorm.urls', namespace='scorm')),
        # path('analytics/', include('apps.analytics.urls', namespace='analytics')),
        # path('calendar/', include('apps.calendar.urls', namespace='calendar')),
    ])),
    
    # API Schema endpoints (OpenAPI/Swagger)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
