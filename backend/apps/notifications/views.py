"""
Notification Views for Enterprise LMS
Provides NotificationViewSet for listing, marking read, and managing notifications.
"""

import logging
from typing import Optional

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from .models import Notification, NotificationPreference, NotificationDigest
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
    PushTokenUnregisterSerializer
)
from .services import NotificationService, InAppNotificationService

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


# Legacy alias for backward compatibility
NotificationPreferencesViewSet = NotificationPreferenceViewSet
