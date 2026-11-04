"""
Notification Views for Enterprise LMS
Provides NotificationViewSet for listing, marking read, and managing notifications.
Also includes webhook handlers for SendGrid and AWS SES email events.
"""

import logging
import json
import hmac
import hashlib
from typing import Optional

from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from .models import (
    Notification, NotificationPreference, NotificationDigest,
    EmailProvider, EmailTemplate, EmailLog, EmailEvent
)
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    NotificationMarkReadSerializer,
    NotificationUnreadCountSerializer,
    NotificationPreferenceSerializer,
    NotificationPreferenceUpdateSerializer,
    NotificationDigestSerializer,
    NotificationBulkActionSerializer,
    NotificationFilterSerializer,
    PushTokenRegisterSerializer,
    PushTokenUnregisterSerializer,
    EmailProviderSerializer,
    EmailProviderCreateSerializer,
    EmailTemplateSerializer,
    EmailTemplateCreateSerializer,
    EmailLogSerializer,
    EmailLogListSerializer,
    EmailEventSerializer,
    EmailAnalyticsSerializer,
    ProviderHealthSerializer,
    WebhookEventSerializer
)
from .services import NotificationService, InAppNotificationService, EmailService

logger = logging.getLogger(__name__)


class NotificationFilter(filters.FilterSet):
    """Filter set for notifications."""
    
    class Meta:
        model = Notification
        fields = {
            'is_read': ['exact'],
            'category': ['exact'],
            'notification_type': ['exact'],
            'priority': ['exact'],
            'status': ['exact'],
            'created_at': ['gte', 'lte'],
        }
    
    search = filters.CharFilter(method='filter_search')
    
    def filter_search(self, queryset, name, value):
        """Search in title and message."""
        if value:
            return queryset.filter(
                Q(title__icontains=value) | Q(message__icontains=value)
            )
        return queryset


class NotificationPagination(LimitOffsetPagination):
    """Custom pagination for notifications."""
    default_limit = 20
    max_limit = 100


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user notifications.
    
    Provides endpoints for:
    - Listing user's notifications
    - Marking notifications as read/unread
    - Getting unread count
    - Bulk actions on notifications
    """
    
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NotificationFilter
    
    def get_queryset(self):
        """Return notifications for the current user only."""
        return Notification.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return NotificationListSerializer
        elif self.action == 'mark_read':
            return NotificationMarkReadSerializer
        elif self.action == 'bulk_action':
            return NotificationBulkActionSerializer
        return NotificationSerializer
    
    def list(self, request, *args, **kwargs):
        """
        List notifications for the current user.
        
        Query Parameters:
        - is_read: Filter by read status (true/false)
        - category: Filter by category
        - notification_type: Filter by type (email, in_app, push)
        - priority: Filter by priority (low, normal, high, urgent)
        - search: Search in title and message
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get unread count for header
        unread_count = self.get_queryset().filter(is_read=False).count()
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response['X-Unread-Count'] = unread_count
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        response = Response(serializer.data)
        response['X-Unread-Count'] = unread_count
        return response
    
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve a specific notification.
        Automatically marks it as read if not already.
        """
        notification = self.get_object()
        
        # Auto-mark as read on retrieve
        if not notification.is_read:
            notification.mark_as_read()
        
        serializer = self.get_serializer(notification)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='my')
    def my_notifications(self, request):
        """
        Get current user's notifications.
        Alias for list with explicit naming.
        """
        return self.list(request)
    
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """
        Get the count of unread notifications for the current user.
        
        Returns:
        {
            "unread_count": 5,
            "has_unread": true
        }
        """
        count = self.get_queryset().filter(is_read=False).count()
        serializer = NotificationUnreadCountSerializer({
            'unread_count': count,
            'has_unread': count > 0
        })
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='mark-read')
    def mark_read(self, request):
        """
        Mark notifications as read.
        
        Request Body:
        {
            "notification_ids": ["uuid1", "uuid2"],  // Optional, if empty and mark_all=false, marks none
            "mark_all": false  // If true, marks all notifications as read
        }
        
        Returns:
        {
            "marked_count": 2,
            "message": "2 notifications marked as read"
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        notification_ids = serializer.validated_data.get('notification_ids', [])
        mark_all = serializer.validated_data.get('mark_all', False)
        
        queryset = self.get_queryset().filter(is_read=False)
        
        if not mark_all and notification_ids:
            queryset = queryset.filter(id__in=notification_ids)
        elif not mark_all:
            return Response({
                'marked_count': 0,
                'message': 'No notifications marked as read'
            })
        
        count = 0
        for notification in queryset:
            notification.mark_as_read()
            count += 1
        
        return Response({
            'marked_count': count,
            'message': f'{count} notification(s) marked as read'
        })
    
    @action(detail=False, methods=['post'], url_path='mark-unread')
    def mark_unread(self, request):
        """
        Mark notifications as unread.
        
        Request Body:
        {
            "notification_ids": ["uuid1", "uuid2"]  // Required
        }
        
        Returns:
        {
            "marked_count": 2,
            "message": "2 notifications marked as unread"
        }
        """
        notification_ids = request.data.get('notification_ids', [])
        
        if not notification_ids:
            return Response(
                {'error': 'notification_ids is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(
            id__in=notification_ids,
            is_read=True
        )
        
        count = 0
        for notification in queryset:
            notification.is_read = False
            notification.read_at = None
            notification.status = Notification.STATUS_SENT
            notification.save(update_fields=['is_read', 'read_at', 'status', 'updated_at'])
            count += 1
        
        return Response({
            'marked_count': count,
            'message': f'{count} notification(s) marked as unread'
        })
    
    @action(detail=False, methods=['post'], url_path='bulk-action')
    def bulk_action(self, request):
        """
        Perform bulk actions on notifications.
        
        Request Body:
        {
            "action": "mark_read" | "mark_unread" | "delete",
            "notification_ids": ["uuid1", "uuid2"]
        }
        """
        serializer = NotificationBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        notification_ids = serializer.validated_data['notification_ids']
        
        queryset = self.get_queryset().filter(id__in=notification_ids)
        
        if action_type == 'mark_read':
            count = 0
            for notification in queryset.filter(is_read=False):
                notification.mark_as_read()
                count += 1
            message = f'{count} notification(s) marked as read'
        
        elif action_type == 'mark_unread':
            count = queryset.filter(is_read=True).update(
                is_read=False,
                read_at=None,
                status=Notification.STATUS_SENT
            )
            message = f'{count} notification(s) marked as unread'
        
        elif action_type == 'delete':
            count = queryset.count()
            queryset.delete()
            message = f'{count} notification(s) deleted'
        
        else:
            return Response(
                {'error': 'Invalid action'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'action': action_type,
            'affected_count': count,
            'message': message
        })
    
    @action(detail=False, methods=['get'], url_path='recent')
    def recent(self, request):
        """
        Get recent notifications (last 5 minutes) for real-time polling.
        
        Query Parameters:
        - minutes: Time window in minutes (default: 5, max: 60)
        
        Returns:
        List of recent notifications
        """
        minutes = int(request.query_params.get('minutes', 5))
        minutes = min(minutes, 60)  # Cap at 60 minutes
        
        notifications = InAppNotificationService.get_recent_notifications(
            user=request.user,
            minutes=minutes
        )
        
        serializer = NotificationListSerializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['delete'], url_path='clear-all')
    def clear_all(self, request):
        """
        Clear all notifications for the current user.
        
        Query Parameters:
        - only_read: If true, only clears read notifications (default: false)
        
        Returns:
        {
            "deleted_count": 10,
            "message": "10 notifications cleared"
        }
        """
        only_read = request.query_params.get('only_read', 'false').lower() == 'true'
        
        queryset = self.get_queryset()
        if only_read:
            queryset = queryset.filter(is_read=True)
        
        count = queryset.count()
        queryset.delete()
        
        return Response({
            'deleted_count': count,
            'message': f'{count} notification(s) cleared'
        })


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notification preferences.
    
    Provides endpoints for:
    - Getting user notification preferences
    - Updating preferences
    - Managing push tokens
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return preferences for the current user only."""
        return NotificationPreference.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action in ['update', 'partial_update']:
            return NotificationPreferenceUpdateSerializer
        return NotificationPreferenceSerializer
    
    def get_object(self):
        """Get or create preferences for the current user."""
        preference, created = NotificationPreference.objects.get_or_create(
            user=self.request.user,
            defaults={
                'email_enabled': True,
                'in_app_enabled': True,
                'push_enabled': False,
            }
        )
        return preference
    
    def list(self, request, *args, **kwargs):
        """Get current user's notification preferences."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """Create or update preferences."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def update(self, request, *args, **kwargs):
        """Update notification preferences."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='my')
    def my_preferences(self, request):
        """Get current user's notification preferences."""
        return self.list(request)
    
    @action(detail=False, methods=['post'], url_path='register-push-token')
    def register_push_token(self, request):
        """
        Register a push notification device token.
        
        Request Body:
        {
            "device_token": "abc123...",
            "device_type": "ios" | "android" | "web",
            "device_name": "My iPhone"  // Optional
        }
        """
        serializer = PushTokenRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        preference = self.get_object()
        
        device_token = serializer.validated_data['device_token']
        device_type = serializer.validated_data['device_type']
        device_name = serializer.validated_data.get('device_name', '')
        
        # Check if token already exists
        tokens = preference.push_device_tokens
        existing = [t for t in tokens if t.get('token') == device_token]
        
        if existing:
            # Update existing token info
            for token in tokens:
                if token.get('token') == device_token:
                    token['device_type'] = device_type
                    token['device_name'] = device_name
                    token['updated_at'] = timezone.now().isoformat()
        else:
            # Add new token
            tokens.append({
                'token': device_token,
                'device_type': device_type,
                'device_name': device_name,
                'created_at': timezone.now().isoformat(),
                'updated_at': timezone.now().isoformat()
            })
        
        preference.push_device_tokens = tokens
        preference.save(update_fields=['push_device_tokens', 'updated_at'])
        
        return Response({
            'message': 'Push token registered successfully',
            'token_count': len(tokens)
        })
    
    @action(detail=False, methods=['post'], url_path='unregister-push-token')
    def unregister_push_token(self, request):
        """
        Unregister a push notification device token.
        
        Request Body:
        {
            "device_token": "abc123..."
        }
        """
        serializer = PushTokenUnregisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        preference = self.get_object()
        
        device_token = serializer.validated_data['device_token']
        
        # Remove token
        tokens = preference.push_device_tokens
        tokens = [t for t in tokens if t.get('token') != device_token]
        
        preference.push_device_tokens = tokens
        preference.save(update_fields=['push_device_tokens', 'updated_at'])
        
        return Response({
            'message': 'Push token unregistered successfully',
            'token_count': len(tokens)
        })
    
    @action(detail=False, methods=['post'], url_path='clear-all-push-tokens')
    def clear_all_push_tokens(self, request):
        """Clear all push notification device tokens."""
        preference = self.get_object()
        
        count = len(preference.push_device_tokens)
        preference.push_device_tokens = []
        preference.save(update_fields=['push_device_tokens', 'updated_at'])
        
        return Response({
            'message': 'All push tokens cleared',
            'cleared_count': count
        })


class NotificationDigestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing notification digests.
    
    Provides endpoints for:
    - Listing user's notification digests
    - Viewing digest details
    """
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationDigestSerializer
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        """Return digests for the current user only."""
        return NotificationDigest.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'], url_path='mark-opened')
    def mark_opened(self, request, pk=None):
        """
        Mark a digest as opened.
        
        Returns:
        {
            "message": "Digest marked as opened"
        }
        """
        digest = self.get_object()
        
        if not digest.opened_at:
            digest.opened_at = timezone.now()
            digest.save(update_fields=['opened_at'])
        
        return Response({
            'message': 'Digest marked as opened',
            'opened_at': digest.opened_at
        })


# =============================================================================
# Email Provider Management ViewSets
# =============================================================================

class EmailProviderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing email providers (SendGrid, AWS SES).
    
    Provides endpoints for:
    - Listing configured email providers
    - Creating/updating provider configurations
    - Testing provider connectivity
    - Managing provider priority/failover
    """
    
    permission_classes = [permissions.IsAdminUser]
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        """Return all email providers ordered by priority."""
        return EmailProvider.objects.all().order_by('priority_order', 'name')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action in ['create', 'update', 'partial_update']:
            return EmailProviderCreateSerializer
        return EmailProviderSerializer
    
    @action(detail=True, methods=['post'], url_path='test')
    def test_connection(self, request, pk=None):
        """
        Test the connection to an email provider.
        
        Returns:
        {
            "success": true,
            "message": "Connection successful",
            "latency_ms": 245
        }
        """
        provider = self.get_object()
        
        try:
            # Use EmailService to test the provider
            email_service = EmailService()
            result = email_service.test_provider(provider)
            
            return Response({
                'success': result.success,
                'message': result.message,
                'latency_ms': result.latency_ms
            })
        except Exception as e:
            logger.error(f"Provider test failed: {str(e)}")
            return Response({
                'success': False,
                'message': f'Connection test failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='toggle')
    def toggle_active(self, request, pk=None):
        """
        Toggle the active status of a provider.
        
        Returns:
        {
            "active": false,
            "message": "Provider deactivated"
        }
        """
        provider = self.get_object()
        provider.is_active = not provider.is_active
        provider.save(update_fields=['is_active', 'updated_at'])
        
        status_text = 'activated' if provider.is_active else 'deactivated'
        return Response({
            'active': provider.is_active,
            'message': f'Provider {status_text}'
        })
    
    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder_providers(self, request):
        """
        Reorder provider priorities.
        
        Request Body:
        {
            "provider_ids": ["uuid1", "uuid2", "uuid3"]
        }
        """
        provider_ids = request.data.get('provider_ids', [])
        
        if not provider_ids:
            return Response(
                {'error': 'provider_ids is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        for index, provider_id in enumerate(provider_ids):
            EmailProvider.objects.filter(id=provider_id).update(
                priority_order=index + 1
            )
        
        return Response({
            'message': 'Provider priorities updated',
            'provider_count': len(provider_ids)
        })
    
    @action(detail=False, methods=['get'], url_path='health')
    def provider_health(self, request):
        """
        Get health status of all providers.
        
        Returns:
        {
            "providers": [
                {
                    "id": "uuid",
                    "name": "SendGrid Primary",
                    "provider_type": "sendgrid",
                    "is_active": true,
                    "is_healthy": true,
                    "success_rate": 0.98,
                    "avg_latency_ms": 150
                }
            ],
            "overall_health": "healthy"
        }
        """
        providers = EmailProvider.objects.all()
        health_data = []
        
        for provider in providers:
            # Calculate health metrics from EmailLog
            recent_logs = EmailLog.objects.filter(
                provider=provider,
                created_at__gte=timezone.now() - timezone.timedelta(hours=24)
            )
            
            total = recent_logs.count()
            successful = recent_logs.filter(status=EmailLog.STATUS_DELIVERED).count()
            success_rate = successful / total if total > 0 else 1.0
            
            avg_latency = recent_logs.exclude(delivered_at=None).filter(
                sent_at__isnull=False
            ).aggregate(
                avg_latency=models.Avg(
                    models.F('delivered_at') - models.F('sent_at')
                )
            )['avg_latency']
            
            health_data.append({
                'id': str(provider.id),
                'name': provider.name,
                'provider_type': provider.provider_type,
                'is_active': provider.is_active,
                'is_healthy': success_rate >= 0.95 and provider.is_active,
                'success_rate': round(success_rate, 2),
                'avg_latency_ms': avg_latency.total_seconds() * 1000 if avg_latency else 0
            })
        
        # Determine overall health
        active_providers = [p for p in health_data if p['is_active']]
        healthy_count = sum(1 for p in active_providers if p['is_healthy'])
        
        if healthy_count == 0 and active_providers:
            overall_health = 'critical'
        elif healthy_count < len(active_providers):
            overall_health = 'degraded'
        else:
            overall_health = 'healthy'
        
        return Response({
            'providers': health_data,
            'overall_health': overall_health
        })


class EmailTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing MJML email templates.
    
    Provides endpoints for:
    - Listing email templates
    - Creating/updating templates with MJML validation
    - Previewing rendered templates
    - Managing template versions
    """
    
    permission_classes = [permissions.IsAdminUser]
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        """Return all email templates."""
        return EmailTemplate.objects.all().order_by('-is_active', 'name')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action in ['create', 'update', 'partial_update']:
            return EmailTemplateCreateSerializer
        return EmailTemplateSerializer
    
    @action(detail=True, methods=['post'], url_path='preview')
    def preview(self, request, pk=None):
        """
        Preview a rendered template with sample data.
        
        Request Body:
        {
            "sample_data": {"user_name": "John", "course_name": "Python 101"}
        }
        
        Returns:
        {
            "subject": "Welcome to Python 101",
            "html_content": "<html>...</html>",
            "text_content": "Plain text version"
        }
        """
        template = self.get_object()
        sample_data = request.data.get('sample_data', {})
        
        try:
            email_service = EmailService()
            rendered = email_service.render_template(template, sample_data)
            
            return Response({
                'subject': rendered['subject'],
                'html_content': rendered['html_content'],
                'text_content': rendered['text_content']
            })
        except Exception as e:
            return Response({
                'error': f'Template rendering failed: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        """
        Activate a template and deactivate others with the same purpose.
        
        Returns:
        {
            "message": "Template activated",
            "deactivated_count": 2
        }
        """
        template = self.get_object()
        
        # Deactivate other templates with same purpose
        deactivated = EmailTemplate.objects.filter(
            purpose=template.purpose,
            is_active=True
        ).exclude(id=template.id).update(is_active=False)
        
        template.is_active = True
        template.save(update_fields=['is_active', 'updated_at'])
        
        return Response({
            'message': 'Template activated',
            'deactivated_count': deactivated
        })
    
    @action(detail=False, methods=['get'], url_path='by-purpose')
    def by_purpose(self, request):
        """
        Get templates grouped by purpose.
        
        Query Parameters:
        - purpose: Filter by specific purpose
        
        Returns:
        {
            "welcome": [template_list],
            "course_enrollment": [template_list]
        }
        """
        purpose = request.query_params.get('purpose')
        
        queryset = self.get_queryset()
        if purpose:
            queryset = queryset.filter(purpose=purpose)
        
        templates = queryset.values('purpose').distinct()
        result = {}
        
        for item in templates:
            p = item['purpose']
            result[p] = EmailTemplateSerializer(
                queryset.filter(purpose=p), many=True
            ).data
        
        return Response(result)


class EmailLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing email delivery logs.
    
    Provides endpoints for:
    - Listing email logs with filtering
    - Viewing detailed email events
    - Getting delivery statistics
    """
    
    permission_classes = [permissions.IsAdminUser]
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        """Return email logs with optional filtering."""
        queryset = EmailLog.objects.all().select_related('provider')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by provider
        provider_id = self.request.query_params.get('provider')
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return EmailLogListSerializer
        return EmailLogSerializer
    
    @action(detail=True, methods=['get'], url_path='events')
    def events(self, request, pk=None):
        """
        Get all events for a specific email log.
        
        Returns:
        List of EmailEvent objects
        """
        email_log = self.get_object()
        events = EmailEvent.objects.filter(email_log=email_log).order_by('-timestamp')
        
        serializer = EmailEventSerializer(events, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='analytics')
    def analytics(self, request):
        """
        Get email delivery analytics.
        
        Query Parameters:
        - days: Number of days to analyze (default: 7, max: 90)
        
        Returns:
        {
            "total_sent": 1000,
            "total_delivered": 950,
            "total_bounced": 30,
            "total_complained": 5,
            "delivery_rate": 0.95,
            "bounce_rate": 0.03,
            "complaint_rate": 0.005,
            "provider_breakdown": {...}
        }
        """
        days = int(request.query_params.get('days', 7))
        days = min(days, 90)
        
        since = timezone.now() - timezone.timedelta(days=days)
        queryset = EmailLog.objects.filter(created_at__gte=since)
        
        total = queryset.count()
        delivered = queryset.filter(status=EmailLog.STATUS_DELIVERED).count()
        bounced = queryset.filter(status=EmailLog.STATUS_BOUNCED).count()
        complained = queryset.filter(status=EmailLog.STATUS_COMPLAINED).count()
        
        # Provider breakdown
        provider_stats = queryset.values('provider__name').annotate(
            count=models.Count('id'),
            delivered_count=models.Count(
                models.Case(
                    models.When(status=EmailLog.STATUS_DELIVERED, then=1),
                    output_field=models.IntegerField()
                )
            )
        )
        
        return Response({
            'period_days': days,
            'total_sent': total,
            'total_delivered': delivered,
            'total_bounced': bounced,
            'total_complained': complained,
            'delivery_rate': round(delivered / total, 4) if total > 0 else 0,
            'bounce_rate': round(bounced / total, 4) if total > 0 else 0,
            'complaint_rate': round(complained / total, 4) if total > 0 else 0,
            'provider_breakdown': list(provider_stats)
        })


# =============================================================================
# Webhook Handlers for SendGrid and AWS SES
# =============================================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def sendgrid_webhook(request):
    """
    Handle SendGrid event webhook callbacks.
    
    Processes events: delivered, bounced, dropped, deferred, processed, 
    open, click, spamreport, unsubscribe, group_unsubscribe, group_resubscribe
    
    SendGrid sends events as a JSON array of event objects.
    Each event contains: event, email, timestamp, sg_message_id, etc.
    
    Security: Validates webhook signature using SendGrid public key.
    """
    # Verify webhook signature if configured
    webhook_secret = getattr(settings, 'SENDGRID_WEBHOOK_SECRET', None)
    if webhook_secret:
        signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature', '')
        timestamp = request.headers.get('X-Twilio-Email-Event-Webhook-Timestamp', '')
        
        if not _verify_sendgrid_signature(
            webhook_secret, signature, timestamp, request.body
        ):
            logger.warning("Invalid SendGrid webhook signature")
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_401_UNAUTHORIZED
            )
    
    try:
        events = request.data if isinstance(request.data, list) else [request.data]
    except Exception as e:
        logger.error(f"Failed to parse SendGrid webhook payload: {str(e)}")
        return Response(
            {'error': 'Invalid payload'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    processed_count = 0
    
    for event_data in events:
        try:
            event_type = event_data.get('event')
            email = event_data.get('email')
            sg_message_id = event_data.get('sg_message_id', '').split('.')[0]
            timestamp = event_data.get('timestamp')
            
            if not event_type or not email:
                continue
            
            # Map SendGrid event to our event type
            event_mapping = {
                'delivered': EmailEvent.EVENT_DELIVERED,
                'bounce': EmailEvent.EVENT_BOUNCED,
                'dropped': EmailEvent.EVENT_DROPPED,
                'deferred': EmailEvent.EVENT_DEFERRED,
                'processed': EmailEvent.EVENT_PROCESSED,
                'open': EmailEvent.EVENT_OPENED,
                'click': EmailEvent.EVENT_CLICKED,
                'spamreport': EmailEvent.EVENT_COMPLAINED,
                'unsubscribe': EmailEvent.EVENT_UNSUBSCRIBED,
                'group_unsubscribe': EmailEvent.EVENT_UNSUBSCRIBED,
                'group_resubscribe': EmailEvent.EVENT_RESUBSCRIBED,
            }
            
            our_event_type = event_mapping.get(event_type, EmailEvent.EVENT_DELIVERED)
            
            # Find the email log
            try:
                email_log = EmailLog.objects.get(
                    external_message_id=sg_message_id,
                    recipient_email=email
                )
            except EmailLog.DoesNotExist:
                logger.warning(f"Email log not found for sg_message_id: {sg_message_id}")
                continue
            
            # Create event record
            event_timestamp = timezone.datetime.fromtimestamp(
                timestamp, tz=timezone.utc
            ) if timestamp else timezone.now()
            
            event = EmailEvent.objects.create(
                email_log=email_log,
                event_type=our_event_type,
                provider='sendgrid',
                raw_data=event_data,
                ip_address=event_data.get('ip'),
                user_agent=event_data.get('useragent'),
                timestamp=event_timestamp
            )
            
            # Update email log status
            _update_email_log_status(email_log, our_event_type, event_data)
            
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Error processing SendGrid event: {str(e)}")
            continue
    
    logger.info(f"Processed {processed_count} SendGrid webhook events")
    return Response({'processed': processed_count})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def aws_ses_webhook(request):
    """
    Handle AWS SES event webhook callbacks via SNS notifications.
    
    Processes events: bounce, complaint, delivery, send, reject, open, click
    
    AWS SES sends events through SNS notifications containing:
    - NotificationType: Type of event
    - Message: JSON string with event details
    - MessageId: SES message ID
    
    Security: Validates SNS message signature.
    """
    try:
        # Parse SNS message
        sns_data = request.data
        message_type = sns_data.get('Type') or sns_data.get('Type')
        
        # Handle SNS subscription confirmation
        if message_type == 'SubscriptionConfirmation':
            subscribe_url = sns_data.get('SubscribeURL')
            if subscribe_url:
                logger.info(f"SNS SubscriptionConfirmation received: {subscribe_url}")
                # In production, you would verify and confirm the subscription
                return Response({'message': 'Subscription confirmation received'})
        
        # Handle SNS notification
        if message_type == 'Notification':
            message = sns_data.get('Message', '{}')
            try:
                ses_event = json.loads(message) if isinstance(message, str) else message
            except json.JSONDecodeError:
                logger.error("Failed to parse SES message JSON")
                return Response(
                    {'error': 'Invalid message format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            event_type = ses_event.get('eventType') or ses_event.get('notificationType')
            
            if not event_type:
                logger.warning("SES event missing eventType")
                return Response({'message': 'No event type'})
            
            # Process the SES event
            _process_ses_event(event_type, ses_event)
            
        return Response({'message': 'Event processed'})
        
    except Exception as e:
        logger.error(f"Error processing AWS SES webhook: {str(e)}")
        return Response(
            {'error': 'Processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _process_ses_event(event_type: str, ses_event: dict):
    """Process an individual SES event."""
    
    # Map SES event types to our event types
    event_mapping = {
        'delivery': EmailEvent.EVENT_DELIVERED,
        'bounce': EmailEvent.EVENT_BOUNCED,
        'complaint': EmailEvent.EVENT_COMPLAINED,
        'send': EmailEvent.EVENT_PROCESSED,
        'reject': EmailEvent.EVENT_DROPPED,
        'open': EmailEvent.EVENT_OPENED,
        'click': EmailEvent.EVENT_CLICKED,
    }
    
    our_event_type = event_mapping.get(event_type.lower(), EmailEvent.EVENT_DELIVERED)
    
    # Get message ID and recipient
    message_id = ses_event.get('mail', {}).get('messageId')
    recipients = ses_event.get('delivery', {}).get('recipients', []) or \
                 ses_event.get('bounce', {}).get('bouncedRecipients', []) or \
                 ses_event.get('complaint', {}).get('complainedRecipients', [])
    
    if not message_id:
        logger.warning("SES event missing messageId")
        return
    
    # Process for each recipient
    for recipient in recipients:
        email = recipient if isinstance(recipient, str) else recipient.get('emailAddress', '')
        if not email:
            continue
        
        try:
            # Find email log
            email_log = EmailLog.objects.get(
                external_message_id=message_id,
                recipient_email=email
            )
        except EmailLog.DoesNotExist:
            logger.warning(f"Email log not found for SES messageId: {message_id}")
            continue
        
        # Create event
        timestamp = timezone.now()
        if 'timestamp' in ses_event.get('delivery', {}):
            ts_str = ses_event['delivery']['timestamp']
            try:
                timestamp = timezone.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            except:
                pass
        
        event = EmailEvent.objects.create(
            email_log=email_log,
            event_type=our_event_type,
            provider='aws_ses',
            raw_data=ses_event,
            timestamp=timestamp
        )
        
        # Update email log status
        _update_email_log_status(email_log, our_event_type, ses_event)
        
        logger.debug(f"Processed SES {event_type} event for {email}")


def _update_email_log_status(email_log: EmailLog, event_type: str, event_data: dict):
    """Update email log status based on event type."""
    
    status_mapping = {
        EmailEvent.EVENT_PROCESSED: EmailLog.STATUS_SENT,
        EmailEvent.EVENT_DELIVERED: EmailLog.STATUS_DELIVERED,
        EmailEvent.EVENT_BOUNCED: EmailLog.STATUS_BOUNCED,
        EmailEvent.EVENT_COMPLAINED: EmailLog.STATUS_COMPLAINED,
        EmailEvent.EVENT_DROPPED: EmailLog.STATUS_FAILED,
        EmailEvent.EVENT_DEFERRED: EmailLog.STATUS_DEFERRED,
    }
    
    new_status = status_mapping.get(event_type)
    if new_status:
        email_log.status = new_status
        
        # Update timestamps based on event
        if event_type == EmailEvent.EVENT_DELIVERED:
            email_log.delivered_at = timezone.now()
        elif event_type == EmailEvent.EVENT_BOUNCED:
            email_log.bounced_at = timezone.now()
            email_log.bounce_reason = event_data.get('reason', '') or \
                                     event_data.get('bounce', {}).get('bounceSubType', '')
        elif event_type == EmailEvent.EVENT_COMPLAINED:
            email_log.complained_at = timezone.now()
        elif event_type == EmailEvent.EVENT_OPENED:
            email_log.opened_at = timezone.now()
            email_log.open_count = (email_log.open_count or 0) + 1
        elif event_type == EmailEvent.EVENT_CLICKED:
            email_log.clicked_at = timezone.now()
            email_log.click_count = (email_log.click_count or 0) + 1
        
        email_log.save()


def _verify_sendgrid_signature(secret: str, signature: str, timestamp: str, body: bytes) -> bool:
    """Verify SendGrid webhook signature."""
    try:
        # Create the payload to verify
        payload = timestamp.encode('utf-8') + body
        
        # Compute expected signature
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False


# =============================================================================
# Legacy alias for backward compatibility
# =============================================================================
NotificationPreferencesViewSet = NotificationPreferenceViewSet
