"""
Certificates URL Configuration for Enterprise LMS
Provides URL routing for certificate API endpoints and public verification.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.certificates.views import (
    CertificateTemplateViewSet,
    CertificateViewSet,
    VerifyCertificateView,
    PublicCertificateVerificationView,
)

app_name = 'certificates'

# Create router for ViewSets
router = DefaultRouter()

# Register ViewSets
router.register(r'templates', CertificateTemplateViewSet, basename='certificate-template')
router.register(r'', CertificateViewSet, basename='certificate')

# URL patterns
urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Public verification endpoint
    # GET /api/v1/certificates/verify/{number}/{hash}/
    path(
        'verify/<str:number>/<str:hash>/',
        VerifyCertificateView.as_view({'get': 'retrieve'}),
        name='verify-certificate'
    ),
    
    # Public verification via POST
    # POST /api/v1/certificates/verify/
    path(
        'verify/',
        VerifyCertificateView.as_view({'post': 'verify_post'}),
        name='verify-certificate-post'
    ),
    
    # Alternative public verification endpoint (for web view)
    # GET /api/v1/certificates/public-verify/{number}/{hash}/
    path(
        'public-verify/<str:number>/<str:hash>/',
        PublicCertificateVerificationView.as_view({'get': 'retrieve'}),
        name='public-verify-certificate'
    ),
]
