"""
SCORM URL Configuration for Enterprise LMS
Provides URL routes for SCORM 1.2 runtime API, launch endpoints, and SCORM Cloud webhooks.
"""

from django.urls import path

from . import views


urlpatterns = [
    # Launch endpoints
    path('launch/', views.LaunchView.as_view(), name='scorm-launch'),
    path('launch/<str:registration_id>/', views.LaunchDetailView.as_view(), name='scorm-launch-detail'),
    
    # SCORM 1.2 Runtime API endpoints
    path('runtime/init/', views.RuntimeAPIView.as_view(), name='scorm-runtime-init'),
    path('runtime/finish/', views.RuntimeAPIView.as_view(), name='scorm-runtime-finish'),
    path('runtime/getvalue/', views.RuntimeAPIView.as_view(), name='scorm-runtime-getvalue'),
    path('runtime/setvalue/', views.RuntimeAPIView.as_view(), name='scorm-runtime-setvalue'),
    path('runtime/commit/', views.RuntimeAPIView.as_view(), name='scorm-runtime-commit'),
    path('runtime/getlasterror/', views.RuntimeAPIView.as_view(), name='scorm-runtime-getlasterror'),
    path('runtime/geterrorstring/', views.RuntimeAPIView.as_view(), name='scorm-runtime-geterrorstring'),
    path('runtime/getdiagnostic/', views.RuntimeAPIView.as_view(), name='scorm-runtime-getdiagnostic'),
    
    # Alternative: Single runtime endpoint with action parameter
    path('runtime/<str:action>/', views.RuntimeAPIView.as_view(), name='scorm-runtime-action'),
    
    # Registration management
    path('registrations/', views.RegistrationListView.as_view(), name='scorm-registration-list'),
    path('registrations/<str:registration_id>/', views.RegistrationDetailView.as_view(), name='scorm-registration-detail'),
    path('registrations/<str:registration_id>/progress/', views.RegistrationProgressView.as_view(), name='scorm-registration-progress'),
    path('registrations/<str:registration_id>/sync/', views.SyncCloudProgressView.as_view(), name='scorm-registration-sync'),
    
    # Legacy function-based views (for backward compatibility)
    path('legacy/launch/', views.scorm_launch, name='scorm-legacy-launch'),
    path('config/', views.scorm_runtime_config, name='scorm-runtime-config'),
]


# Webhook URLs (typically mounted at root level in main urls.py)
# These are included here for reference but should be mounted at /webhooks/scorm/
webhook_urlpatterns = [
    path('', views.SCORMCloudWebhookView.as_view(), name='scorm-cloud-webhook'),
]
