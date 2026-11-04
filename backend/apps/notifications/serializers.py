"""
Notification Serializers for Enterprise LMS
Provides serializers for notifications, preferences, and digests.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Notification, NotificationPreference, NotificationDigest

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification model.
    Used for listing and retrieving notifications.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_email', 'user_name',
            'notification_type', 'category', 'priority',
            'title', 'message', 'data', 'action_url',
            'status', 'is_read', 'sent_at', 'delivered_at', 'read_at',
            'created_at', 'updated_at', 'time_ago',
            'error_message', 'retry_count'
        ]
        read_only_fields = [
            'id', 'user', 'sent_at', 'delivered_at', 'read_at',
            'created_at', 'updated_at', 'error_message', 'retry_count'
        ]
    
    def get_user_name(self, obj):
        """Get the user's full name."""
        return obj.user.get_full_name()
    
    def get_time_ago(self, obj):
        """Get human-readable time ago."""
        from django.utils.timesince import timesince
        from django.utils import timezone
        
        if obj.created_at:
            return timesince(obj.created_at) + ' ago'
        return ''


class NotificationListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for notification lists.
    Excludes heavy fields for better performance.
    """
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'category', 'priority',
            'title', 'message', 'action_url', 'is_read',
            'created_at', 'time_ago'
        ]
    
    def get_time_ago(self, obj):
        """Get human-readable time ago."""
        from django.utils.timesince import timesince
        if obj.created_at:
            return timesince(obj.created_at) + ' ago'
        return ''


class NotificationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating notifications.
    Used by admin/system processes to create notifications.
    """
    user_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'user_id', 'notification_type', 'category', 'priority',
            'title', 'message', 'data', 'action_url'
        ]
    
    def create(self, validated_data):
        user_id = validated_data.pop('user_id')
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {'user_id': 'User not found.'}
            )
        
        return Notification.objects.create(user=user, **validated_data)


class NotificationMarkReadSerializer(serializers.Serializer):
    """
    Serializer for marking notifications as read.
    """
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="List of notification IDs to mark as read. If empty, marks all as read."
    )
    mark_all = serializers.BooleanField(
        default=False,
        help_text="If true, marks all notifications as read"
    )


class NotificationUnreadCountSerializer(serializers.Serializer):
    """
    Serializer for unread count response.
    """
    unread_count = serializers.IntegerField()
    has_unread = serializers.BooleanField()


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationPreference model.
    Used for retrieving and updating user notification preferences.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    is_in_quiet_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'user_email',
            'email_enabled', 'email_digest_frequency',
            'in_app_enabled', 'push_enabled', 'push_device_tokens',
            'notify_on_course_updates', 'notify_on_assignments',
            'notify_on_forum_replies', 'notify_on_certificates',
            'notify_on_enrollments',
            'quiet_hours_enabled', 'quiet_hours_start',
            'quiet_hours_end', 'quiet_hours_timezone',
            'is_in_quiet_hours',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'user_email', 'created_at', 'updated_at']
    
    def get_is_in_quiet_hours(self, obj):
        """Check if currently in quiet hours."""
        return obj.is_quiet_hours()


class NotificationPreferenceUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating notification preferences.
    All fields are optional for partial updates.
    """
    class Meta:
        model = NotificationPreference
        fields = [
            'email_enabled', 'email_digest_frequency',
            'in_app_enabled', 'push_enabled', 'push_device_tokens',
            'notify_on_course_updates', 'notify_on_assignments',
            'notify_on_forum_replies', 'notify_on_certificates',
            'notify_on_enrollments',
            'quiet_hours_enabled', 'quiet_hours_start',
            'quiet_hours_end', 'quiet_hours_timezone'
        ]
    
    def validate_email_digest_frequency(self, value):
        """Validate digest frequency."""
        valid_frequencies = ['immediate', 'hourly', 'daily', 'weekly', 'never']
        if value not in valid_frequencies:
            raise serializers.ValidationError(
                f"Invalid frequency. Must be one of: {', '.join(valid_frequencies)}"
            )
        return value
    
    def validate_push_device_tokens(self, value):
        """Validate device tokens is a list."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Device tokens must be a list.")
        return value


class NotificationDigestSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationDigest model.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = NotificationDigest
        fields = [
            'id', 'user', 'user_email', 'digest_type',
            'notification_count', 'notification_ids',
            'sent_at', 'opened_at', 'created_at'
        ]
        read_only_fields = fields


class NotificationBulkActionSerializer(serializers.Serializer):
    """
    Serializer for bulk actions on notifications.
    """
    ACTION_CHOICES = [
        ('mark_read', 'Mark as Read'),
        ('mark_unread', 'Mark as Unread'),
        ('delete', 'Delete'),
    ]
    
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        min_length=1,
        help_text="List of notification IDs to perform action on"
    )
    
    def validate_notification_ids(self, value):
        """Validate that all notification IDs exist and belong to the user."""
        if not value:
            raise serializers.ValidationError("At least one notification ID is required.")
        return value


class NotificationFilterSerializer(serializers.Serializer):
    """
    Serializer for filtering notifications.
    """
    is_read = serializers.BooleanField(required=False)
    category = serializers.ChoiceField(
        choices=Notification.CATEGORY_CHOICES,
        required=False
    )
    notification_type = serializers.ChoiceField(
        choices=Notification.NOTIFICATION_TYPES,
        required=False
    )
    priority = serializers.ChoiceField(
        choices=Notification.PRIORITY_CHOICES,
        required=False
    )
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    search = serializers.CharField(required=False, max_length=100)


class NotificationSettingsSerializer(serializers.Serializer):
    """
    Serializer for global notification settings.
    Used for admin configuration.
    """
    default_from_email = serializers.EmailField(required=False)
    site_name = serializers.CharField(max_length=100, required=False)
    site_url = serializers.URLField(required=False)
    email_backend = serializers.CharField(max_length=50, required=False)
    enable_push_notifications = serializers.BooleanField(required=False)
    digest_schedule = serializers.DictField(required=False)


class PushTokenRegisterSerializer(serializers.Serializer):
    """
    Serializer for registering push notification device tokens.
    """
    device_token = serializers.CharField(max_length=500, required=True)
    device_type = serializers.ChoiceField(
        choices=[('ios', 'iOS'), ('android', 'Android'), ('web', 'Web')],
        required=True
    )
    device_name = serializers.CharField(max_length=100, required=False, allow_blank=True)


class PushTokenUnregisterSerializer(serializers.Serializer):
    """
    Serializer for unregistering push notification device tokens.
    """
    device_token = serializers.CharField(max_length=500, required=True)
