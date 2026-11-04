"""
Certificates Views for Enterprise LMS
Provides ViewSets for CertificateTemplate and Certificate models,
plus public verification endpoint.
"""

import logging
from typing import Optional

from django.http import FileResponse, Http404
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.exceptions import PermissionDenied, ValidationError

from django_filters.rest_framework import DjangoFilterBackend

from apps.certificates.models import Certificate, CertificateTemplate, CertificateIssueEvent
from apps.certificates.serializers import (
    CertificateSerializer,
    CertificateListSerializer,
    CertificateCreateSerializer,
    CertificateUpdateSerializer,
    CertificateRegenerateSerializer,
    CertificateRevokeSerializer,
    CertificateTemplateSerializer,
    CertificateTemplateListSerializer,
    CertificateIssueEventSerializer,
    CertificateStatsSerializer,
    CertificateVerifyResponseSerializer,
)
from apps.certificates.services import CertificateService
from apps.certificates.tasks import generate_certificate_task, regenerate_certificate_task
from apps.core.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class CertificateTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CertificateTemplate CRUD operations.
    
    list: Get all certificate templates (admin only)
    create: Create a new certificate template (admin only)
    retrieve: Get a specific template (admin only)
    update: Update a template (admin only)
    partial_update: Partially update a template (admin only)
    destroy: Delete a template (admin only)
    """
    queryset = CertificateTemplate.objects.all()
    serializer_class = CertificateTemplateSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['is_active', 'created_at']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-created_at']
    search_fields = ['name', 'description']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return CertificateTemplateListSerializer
        return CertificateTemplateSerializer
    
    def get_queryset(self):
        """Filter templates based on query params."""
        queryset = CertificateTemplate.objects.all()
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a certificate template."""
        template = self.get_object()
        template.is_active = True
        template.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'activated'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a certificate template."""
        template = self.get_object()
        template.is_active = False
        template.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'deactivated'})
    
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """Get a preview of the template with sample data."""
        template = self.get_object()
        
        # Sample data for preview
        sample_data = {
            'student_name': 'John Doe',
            'student_email': 'john.doe@example.com',
            'course_name': 'Sample Course',
            'course_slug': 'sample-course',
            'course_duration': '10h 30m',
            'completion_date': timezone.now().strftime("%B %d, %Y"),
            'certificate_number': 'CERT-20240101-ABCD1234',
            'verification_hash': 'samplehash123456789',
            'instructor_name': 'Jane Smith',
            'organization_name': 'Enterprise LMS',
            'organization_logo': '',
            'issued_at': timezone.now().isoformat(),
            'current_date': timezone.now().strftime("%B %d, %Y"),
        }
        
        return Response({
            'template': template.html_template,
            'css_styles': template.css_styles,
            'sample_variables': sample_data,
            'available_variables': template.available_variables
        })


class CertificateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Certificate operations.
    
    list: List user's certificates (or all for admin)
    create: Create a new certificate (admin only)
    retrieve: Get certificate details
    update: Update certificate (admin only)
    partial_update: Partially update certificate (admin only)
    destroy: Delete certificate (admin only)
    """
    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['generation_status', 'is_revoked', 'issued_at', 'course']
    ordering_fields = ['issued_at', 'created_at', 'certificate_number']
    ordering = ['-issued_at']
    search_fields = ['certificate_number', 'user__email', 'user__first_name', 'user__last_name']
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'revoke']:
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return CertificateListSerializer
        elif self.action == 'create':
            return CertificateCreateSerializer
        elif self.action == 'update' or self.action == 'partial_update':
            return CertificateUpdateSerializer
        elif self.action == 'regenerate':
            return CertificateRegenerateSerializer
        elif self.action == 'revoke':
            return CertificateRevokeSerializer
        return CertificateSerializer
    
    def get_queryset(self):
        """
        Filter certificates based on user role.
        - Admins see all certificates
        - Regular users see only their own
        """
        user = self.request.user
        
        if user.is_staff or user.is_superuser:
            queryset = Certificate.objects.all()
        else:
            queryset = Certificate.objects.filter(user=user)
        
        # Apply additional filters from query params
        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter == 'valid':
                queryset = queryset.filter(
                    is_revoked=False,
                    generation_status='completed'
                ).filter(
                    Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
                )
            elif status_filter == 'revoked':
                queryset = queryset.filter(is_revoked=True)
            elif status_filter == 'expired':
                queryset = queryset.filter(
                    is_revoked=False,
                    expires_at__lt=timezone.now()
                )
            elif status_filter == 'pending':
                queryset = queryset.filter(generation_status='pending')
            elif status_filter == 'failed':
                queryset = queryset.filter(generation_status='failed')
        
        return queryset.select_related('user', 'course', 'template')
    
    def perform_create(self, serializer):
        """Create certificate and queue PDF generation."""
        certificate = serializer.save()
        
        # Queue async PDF generation
        generate_certificate_task.delay(
            certificate_id=str(certificate.id),
            triggered_by_user_id=str(self.request.user.id)
        )
        
        logger.info(f"Certificate created and queued for generation: {certificate.certificate_number}")
        return certificate
    
    @action(detail=False, methods=['get'])
    def my(self, request):
        """
        Get current user's certificates.
        Returns list of certificates with download URLs.
        """
        certificates = Certificate.objects.filter(
            user=request.user
        ).select_related('course', 'template').order_by('-issued_at')
        
        # Apply pagination
        page = self.paginate_queryset(certificates)
        if page is not None:
            serializer = CertificateListSerializer(
                page,
                many=True,
                context={'request': request}
            )
            return self.get_paginated_response(serializer.data)
        
        serializer = CertificateListSerializer(
            certificates,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download certificate PDF.
        Returns the PDF file if available.
        """
        certificate = self.get_object()
        
        # Check permissions - users can only download their own
        if not request.user.is_staff and certificate.user != request.user:
            raise PermissionDenied("You can only download your own certificates.")
        
        # Check if PDF exists
        if not certificate.pdf_file:
            return Response(
                {
                    'error': 'PDF not yet generated',
                    'generation_status': certificate.generation_status,
                    'message': 'The certificate PDF is still being generated. Please try again later.'
                },
                status=status.HTTP_202_ACCEPTED
            )
        
        # Log download event
        CertificateIssueEvent.objects.create(
            certificate=certificate,
            event_type=CertificateIssueEvent.EVENT_TYPE_DOWNLOADED,
            performed_by=request.user if request.user != certificate.user else None,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Return PDF file
        try:
            response = FileResponse(
                certificate.pdf_file.open('rb'),
                content_type='application/pdf',
                as_attachment=True,
                filename=f"{certificate.certificate_number}.pdf"
            )
            return response
        except Exception as e:
            logger.error(f"Error serving certificate PDF: {e}")
            return Response(
                {'error': 'Failed to serve PDF file'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """
        Regenerate certificate PDF.
        Queues async regeneration task.
        """
        certificate = self.get_object()
        
        # Validate request data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        template_id = serializer.validated_data.get('template_id')
        notify_user = serializer.validated_data.get('notify_user', True)
        
        # Queue regeneration task
        regenerate_certificate_task.delay(
            certificate_id=str(certificate.id),
            template_id=str(template_id) if template_id else None,
            triggered_by_user_id=str(request.user.id)
        )
        
        return Response({
            'status': 'queued',
            'message': 'Certificate regeneration has been queued.',
            'certificate_id': str(certificate.id),
            'certificate_number': certificate.certificate_number
        })
    
    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """
        Revoke a certificate.
        Only admins can revoke certificates.
        """
        certificate = self.get_object()
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        reason = serializer.validated_data.get('reason', '')
        
        # Use service to revoke
        service = CertificateService()
        success = service.revoke_certificate(
            certificate=certificate,
            reason=reason,
            revoked_by=request.user,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        if success:
            return Response({
                'status': 'revoked',
                'message': 'Certificate has been revoked successfully.',
                'certificate_number': certificate.certificate_number,
                'revoked_at': certificate.revoked_at
            })
        
        return Response(
            {'error': 'Failed to revoke certificate'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        """
        Get certificate event history.
        """
        certificate = self.get_object()
        
        # Check permissions
        if not request.user.is_staff and certificate.user != request.user:
            raise PermissionDenied("You can only view your own certificate events.")
        
        events = certificate.events.all().select_related('performed_by')
        serializer = CertificateIssueEventSerializer(events, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def stats(self, request):
        """
        Get certificate statistics (admin only).
        """
        service = CertificateService()
        stats = service.get_certificate_stats()
        serializer = CertificateStatsSerializer(data=stats)
        serializer.is_valid()
        return Response(serializer.data)
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class VerifyCertificateView(viewsets.ViewSet):
    """
    Public endpoint for certificate verification.
    No authentication required.
    """
    permission_classes = [AllowAny]
    
    def retrieve(self, request, number=None, hash=None):
        """
        Verify a certificate by number and hash.
        
        URL pattern: /verify/{number}/{hash}/
        """
        if not number or not hash:
            return Response(
                {
                    'valid': False,
                    'message': 'Certificate number and verification hash are required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = CertificateService()
        result = service.verify_certificate(
            certificate_number=number,
            verification_hash=hash
        )
        
        serializer = CertificateVerifyResponseSerializer(data=result)
        serializer.is_valid()
        
        if result['valid']:
            return Response(serializer.data)
        else:
            return Response(
                serializer.data,
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'], url_path='verify')
    def verify_post(self, request):
        """
        Verify certificate via POST request.
        Accepts certificate_number and verification_hash in request body.
        """
        certificate_number = request.data.get('certificate_number')
        verification_hash = request.data.get('verification_hash')
        
        if not certificate_number or not verification_hash:
            return Response(
                {
                    'valid': False,
                    'message': 'certificate_number and verification_hash are required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = CertificateService()
        result = service.verify_certificate(
            certificate_number=certificate_number,
            verification_hash=verification_hash
        )
        
        serializer = CertificateVerifyResponseSerializer(data=result)
        serializer.is_valid()
        
        if result['valid']:
            return Response(serializer.data)
        else:
            return Response(
                serializer.data,
                status=status.HTTP_404_NOT_FOUND
            )


class PublicCertificateVerificationView(viewsets.ViewSet):
    """
    Alternative public verification view with HTML response support.
    """
    permission_classes = [AllowAny]
    
    def retrieve(self, request, number=None, hash=None):
        """
        Verify certificate and return HTML page or JSON based on Accept header.
        """
        service = CertificateService()
        result = service.verify_certificate(
            certificate_number=number,
            verification_hash=hash
        )
        
        # Check if HTML response is requested
        accept_header = request.headers.get('Accept', '')
        if 'text/html' in accept_header:
            from django.template.response import TemplateResponse
            
            return TemplateResponse(
                request,
                'certificates/verification_result.html',
                result
            )
        
        # Return JSON response
        serializer = CertificateVerifyResponseSerializer(data=result)
        serializer.is_valid()
        
        if result['valid']:
            return Response(serializer.data)
        else:
            return Response(
                serializer.data,
                status=status.HTTP_404_NOT_FOUND
            )
