"""
Notifications Models for Enterprise LMS
Provides Notification model for email and in-app notifications.
"""

import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel

User = get_user_model()


class Notification(TimestampedModel):
    """
    Model representing a notification for a user.
    Supports email, in-app, and push notification types with delivery tracking.
    """
    
    # Notification Type Choices
    TYPE_EMAIL = 'email'
    TYPE_IN_APP = 'in_app'
    TYPE_PUSH = 'push'
    
    NOTIFICATION_TYPES = [
        (TYPE_EMAIL, _('Email')),
        (TYPE_IN_APP, _('In-App')),
        (TYPE_PUSH, _('Push')),
    ]
    
    # Notification Category Choices
    CATEGORY_GENERAL = 'general'
    CATEGORY_COURSE = 'course'
    CATEGORY_ASSIGNMENT = 'assignment'
    CATEGORY_FORUM = 'forum'
    CERTIFICATE = 'certificate'
    CATEGORY_ENROLLMENT = 'enrollment'
    CATEGORY_REMINDER = 'reminder'
    CATEGORY_SYSTEM = 'system'
    
    CATEGORY_CHOICES = [
        (CATEGORY_GENERAL, _('General')),
        (CATEGORY_COURSE, _('Course')),
        (CATEGORY_ASSIGNMENT, _('Assignment')),
        (CATEGORY_FORUM, _('Forum')),
        (CERTIFICATE, _('Certificate')),
        (CATEGORY_ENROLLMENT, _('Enrollment')),
        (CATEGORY_REMINDER, _('Reminder')),
        (CATEGORY_SYSTEM, _('System')),
    ]
    
    # Status Choices
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_FAILED = 'failed'
    STATUS_READ = 'read'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, _('Pending')),
        (STATUS_SENT, _('Sent')),
        (STATUS_DELIVERED, _('Delivered')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_READ, _('Read')),
    ]
    
    # Priority Choices
    PRIORITY_LOW = 'low'
    PRIORITY_NORMAL = 'normal'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, _('Low')),
        (PRIORITY_NORMAL, _('Normal')),
        (PRIORITY_HIGH, _('High')),
        (PRIORITY_URGENT, _('Urgent')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text=_("User who receives the notification")
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default=TYPE_IN_APP,
        db_index=True,
        help_text=_("Type of notification")
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GENERAL,
        db_index=True,
        help_text=_("Category of notification")
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
        db_index=True,
        help_text=_("Priority level of notification")
    )
    title = models.CharField(
        max_length=255,
        help_text=_("Notification title")
    )
    message = models.TextField(
        help_text=_("Notification message")
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Additional data as JSON (e.g., action URLs, entity IDs)")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text=_("Current delivery status")
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether the notification has been read")
    )
    action_url = models.URLField(
        blank=True,
        help_text=_("URL to navigate to when notification is clicked")
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("When the notification was sent")
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the notification was delivered")
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the notification was read")
    )
    error_message = models.TextField(
        blank=True,
        help_text=_("Error message if delivery failed")
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of retry attempts for failed notifications")
    )
    
    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['notification_type', 'status']),
        ]
    
    def __str__(self):
        return f"{self.notification_type} - {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read."""
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.status = self.STATUS_READ
            self.save(update_fields=['is_read', 'read_at', 'status', 'updated_at'])
    
    def mark_as_sent(self):
        """Mark notification as sent."""
        from django.utils import timezone
        self.status = self.STATUS_SENT
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at', 'updated_at'])
    
    def mark_as_delivered(self):
        """Mark notification as delivered."""
        from django.utils import timezone
        self.status = self.STATUS_DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])
    
    def mark_as_failed(self, error_message=''):
        """Mark notification as failed with error message."""
        self.status = self.STATUS_FAILED
        self.error_message = error_message
        self.save(update_fields=['status', 'error_message', 'updated_at'])
    
    def increment_retry(self):
        """Increment retry count."""
        self.retry_count += 1
        self.save(update_fields=['retry_count', 'updated_at'])


class NotificationPreference(TimestampedModel):
    """
    User notification preferences for controlling notification delivery.
    Enhanced with granular channel and topic controls for push notifications.
    """
    
    # Platform Choices
    PLATFORM_WEB = 'web'
    PLATFORM_ANDROID = 'android'
    PLATFORM_IOS = 'ios'
    
    PLATFORM_CHOICES = [
        (PLATFORM_WEB, _('Web')),
        (PLATFORM_ANDROID, _('Android')),
        (PLATFORM_IOS, _('iOS')),
    ]
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        help_text=_("User these preferences belong to")
    )
    
    # Email preferences
    email_enabled = models.BooleanField(
        default=True,
        help_text=_("Whether email notifications are enabled")
    )
    email_digest_frequency = models.CharField(
        max_length=20,
        choices=[
            ('immediate', _('Immediate')),
            ('hourly', _('Hourly')),
            ('daily', _('Daily')),
            ('weekly', _('Weekly')),
            ('never', _('Never')),
        ],
        default='immediate',
        help_text=_("Frequency of email digests")
    )
    
    # In-app preferences
    in_app_enabled = models.BooleanField(
        default=True,
        help_text=_("Whether in-app notifications are enabled")
    )
    
    # Push preferences - Legacy field for backward compatibility
    push_enabled = models.BooleanField(
        default=False,
        help_text=_("Whether push notifications are enabled")
    )
    push_device_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of push notification device tokens (legacy)")
    )
    
    # Category-specific preferences
    notify_on_course_updates = models.BooleanField(
        default=True,
        help_text=_("Notify on course updates")
    )
    notify_on_assignments = models.BooleanField(
        default=True,
        help_text=_("Notify on assignment deadlines and grades")
    )
    notify_on_forum_replies = models.BooleanField(
        default=True,
        help_text=_("Notify on forum replies")
    )
    notify_on_certificates = models.BooleanField(
        default=True,
        help_text=_("Notify on certificate issuance")
    )
    notify_on_enrollments = models.BooleanField(
        default=True,
        help_text=_("Notify on enrollment changes")
    )
    
    # Quiet hours
    quiet_hours_enabled = models.BooleanField(
        default=False,
        help_text=_("Whether quiet hours are enabled")
    )
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        help_text=_("Start time for quiet hours")
    )
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        help_text=_("End time for quiet hours")
    )
    quiet_hours_timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text=_("Timezone for quiet hours")
    )
    
    # Topic subscriptions for push notifications
    subscribed_topics = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of topic names the user is subscribed to")
    )
    
    # Rich media preferences
    rich_media_enabled = models.BooleanField(
        default=True,
        help_text=_("Whether rich media attachments are enabled")
    )
    
    # Action buttons preferences
    action_buttons_enabled = models.BooleanField(
        default=True,
        help_text=_("Whether action buttons are enabled in notifications")
    )
    
    class Meta:
        verbose_name = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")
    
    def __str__(self):
        return f"Preferences for {self.user.email}"
    
    def is_quiet_hours(self):
        """Check if current time is within quiet hours."""
        from datetime import datetime
        import pytz
        
        if not self.quiet_hours_enabled or not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        try:
            tz = pytz.timezone(self.quiet_hours_timezone)
        except:
            tz = pytz.UTC
        
        now = datetime.now(tz).time()
        
        if self.quiet_hours_start < self.quiet_hours_end:
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Quiet hours span midnight
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end
    
    def should_send_email(self, category=CATEGORY_GENERAL):
        """Check if email should be sent based on preferences."""
        if not self.email_enabled:
            return False
        
        category_map = {
            Notification.CATEGORY_COURSE: self.notify_on_course_updates,
            Notification.CATEGORY_ASSIGNMENT: self.notify_on_assignments,
            Notification.CATEGORY_FORUM: self.notify_on_forum_replies,
            Notification.CERTIFICATE: self.notify_on_certificates,
            Notification.CATEGORY_ENROLLMENT: self.notify_on_enrollments,
        }
        
        return category_map.get(category, True)
    
    def should_send_in_app(self, category=CATEGORY_GENERAL):
        """Check if in-app notification should be sent."""
        return self.in_app_enabled
    
    def should_send_push(self, category=CATEGORY_GENERAL):
        """Check if push notification should be sent."""
        return self.push_enabled and len(self.push_device_tokens) > 0
    
    def is_subscribed_to_topic(self, topic):
        """Check if user is subscribed to a specific topic."""
        return topic in self.subscribed_topics
    
    def subscribe_to_topic(self, topic):
        """Subscribe user to a topic."""
        if topic not in self.subscribed_topics:
            self.subscribed_topics.append(topic)
            self.save(update_fields=['subscribed_topics', 'updated_at'])
    
    def unsubscribe_from_topic(self, topic):
        """Unsubscribe user from a topic."""
        if topic in self.subscribed_topics:
            self.subscribed_topics.remove(topic)
            self.save(update_fields=['subscribed_topics', 'updated_at'])


class PushSubscription(TimestampedModel):
    """
    Model representing a push notification subscription for a user device.
    Supports Web Push API, FCM (Android), and APNs (iOS).
    """
    
    # Platform Choices
    PLATFORM_WEB = 'web'
    PLATFORM_ANDROID = 'android'
    PLATFORM_IOS = 'ios'
    
    PLATFORM_CHOICES = [
        (PLATFORM_WEB, _('Web')),
        (PLATFORM_ANDROID, _('Android')),
        (PLATFORM_IOS, _('iOS')),
    ]
    
    # Status Choices
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_EXPIRED = 'expired'
    STATUS_REVOKED = 'revoked'
    
    STATUS_CHOICES = [
        (STATUS_ACTIVE, _('Active')),
        (STATUS_INACTIVE, _('Inactive')),
        (STATUS_EXPIRED, _('Expired')),
        (STATUS_REVOKED, _('Revoked')),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='push_subscriptions',
        help_text=_("User who owns this subscription")
    )
    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        db_index=True,
        help_text=_("Platform type (web, android, ios)")
    )
    
    # Device identification
    device_token = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Device token for FCM (Android) or APNs (iOS)")
    )
    device_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Human-readable device name")
    )
    device_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Unique device identifier")
    )
    
    # Web Push API fields
    endpoint = models.URLField(
        max_length=500,
        blank=True,
        help_text=_("Web Push endpoint URL")
    )
    p256dh = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("P256DH key for Web Push encryption")
    )
    auth = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Auth key for Web Push encryption")
    )
    
    # VAPID key reference for Web Push
    vapid_key_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Reference to VAPID key used for this subscription")
    )
    
    # Status and expiration
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text=_("Current subscription status")
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the subscription expires")
    )
    
    # User agent and IP for tracking
    user_agent = models.TextField(
        blank=True,
        help_text=_("User agent string of the subscribing device")
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_("IP address when subscription was created")
    )
    
    # Last used timestamp
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When this subscription was last used to send a notification")
    )
    
    class Meta:
        verbose_name = _("Push Subscription")
        verbose_name_plural = _("Push Subscriptions")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'platform', 'status']),
            models.Index(fields=['device_token', 'platform']),
            models.Index(fields=['status', 'expires_at']),
        ]
        unique_together = [
            ['user', 'device_token', 'platform'],
        ]
    
    def __str__(self):
        return f"{self.platform} - {self.device_name or self.device_id[:20]}"
    
    def is_valid(self):
        """Check if subscription is valid and not expired."""
        from django.utils import timezone
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True
    
    def mark_as_used(self):
        """Update last_used_at timestamp."""
        from django.utils import timezone
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at', 'updated_at'])
    
    def revoke(self):
        """Revoke this subscription."""
        self.status = self.STATUS_REVOKED
        self.save(update_fields=['status', 'updated_at'])
    
    def expire(self):
        """Mark subscription as expired."""
        self.status = self.STATUS_EXPIRED
        self.save(update_fields=['status', 'updated_at'])


class NotificationLog(TimestampedModel):
    """
    Comprehensive delivery tracking for push notifications.
    Tracks delivery status, platform responses, and confirmation tracking.
    """
    
    # Platform Choices
    PLATFORM_WEB = 'web'
    PLATFORM_ANDROID = 'android'
    PLATFORM_IOS = 'ios'
    
    PLATFORM_CHOICES = [
        (PLATFORM_WEB, _('Web')),
        (PLATFORM_ANDROID, _('Android')),
        (PLATFORM_IOS, _('iOS')),
    ]
    
    # Status Choices
    STATUS_SCHEDULED = 'scheduled'
    STATUS_QUEUED = 'queued'
    STATUS_SENDING = 'sending'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_FAILED = 'failed'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_BOUNCED = 'bounced'
    STATUS_EXPIRED = 'expired'
    
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, _('Scheduled')),
        (STATUS_QUEUED, _('Queued')),
        (STATUS_SENDING, _('Sending')),
        (STATUS_SENT, _('Sent')),
        (STATUS_DELIVERED, _('Delivered')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_CONFIRMED, _('Confirmed')),
        (STATUS_BOUNCED, _('Bounced')),
        (STATUS_EXPIRED, _('Expired')),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='delivery_logs',
        help_text=_("Associated notification")
    )
    subscription = models.ForeignKey(
        PushSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_logs',
        help_text=_("Push subscription used for delivery")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_logs',
        help_text=_("Recipient user")
    )
    
    # Platform information
    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        db_index=True,
        help_text=_("Target platform")
    )
    
    # Delivery status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
        help_text=_("Current delivery status")
    )
    
    # Scheduling
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("When notification is scheduled to be sent")
    )
    
    # Delivery timestamps
    queued_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When notification was queued")
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When notification was sent to provider")
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When delivery was confirmed by provider")
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When delivery was confirmed by device/app")
    )
    
    # Platform response
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Message ID from push provider (FCM, APNs)")
    )
    platform_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw response from push provider")
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text=_("Error message if delivery failed")
    )
    error_code = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Error code from provider")
    )
    
    # Retry tracking
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of retry attempts")
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Next scheduled retry time")
    )
    
    # Confirmation tracking
    confirmation_token = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Token for delivery confirmation")
    )
    confirmation_received = models.BooleanField(
        default=False,
        help_text=_("Whether delivery confirmation was received")
    )
    
    # Rich media tracking
    has_attachment = models.BooleanField(
        default=False,
        help_text=_("Whether notification has rich media attachment")
    )
    attachment_url = models.URLField(
        blank=True,
        help_text=_("URL of rich media attachment")
    )
    
    # Action buttons tracking
    action_buttons = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Action buttons included in notification")
    )
    action_clicked = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Which action button was clicked")
    )
    
    class Meta:
        verbose_name = _("Notification Log")
        verbose_name_plural = _("Notification Logs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['notification', 'platform']),
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['confirmation_token']),
            models.Index(fields=['provider_message_id']),
        ]
    
    def __str__(self):
        return f"{self.platform} - {self.status} - {self.user.email}"
    
    def mark_as_sent(self, provider_message_id='', platform_response=None):
        """Mark notification as sent."""
        from django.utils import timezone
        self.status = self.STATUS_SENT
        self.sent_at = timezone.now()
        if provider_message_id:
            self.provider_message_id = provider_message_id
        if platform_response:
            self.platform_response = platform_response
        self.save(update_fields=['status', 'sent_at', 'provider_message_id', 
                                  'platform_response', 'updated_at'])
    
    def mark_as_delivered(self):
        """Mark notification as delivered."""
        from django.utils import timezone
        self.status = self.STATUS_DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])
    
    def mark_as_confirmed(self):
        """Mark notification as confirmed by device/app."""
        from django.utils import timezone
        self.status = self.STATUS_CONFIRMED
        self.confirmed_at = timezone.now()
        self.confirmation_received = True
        self.save(update_fields=['status', 'confirmed_at', 'confirmation_received', 'updated_at'])
    
    def mark_as_failed(self, error_message='', error_code=''):
        """Mark notification as failed."""
        self.status = self.STATUS_FAILED
        self.error_message = error_message
        self.error_code = error_code
        self.save(update_fields=['status', 'error_message', 'error_code', 'updated_at'])
    
    def schedule_retry(self, next_retry_at):
        """Schedule a retry attempt."""
        self.retry_count += 1
        self.next_retry_at = next_retry_at
        self.status = self.STATUS_SCHEDULED
        self.save(update_fields=['retry_count', 'next_retry_at', 'status', 'updated_at'])


class NotificationDigest(TimestampedModel):
    """
    Digest notification settings and tracking.
    """
    
    # Frequency Choices
    FREQUENCY_HOURLY = 'hourly'
    FREQUENCY_DAILY = 'daily'
    FREQUENCY_WEEKLY = 'weekly'
    
    FREQUENCY_CHOICES = [
        (FREQUENCY_HOURLY, _('Hourly')),
        (FREQUENCY_DAILY, _('Daily')),
        (FREQUENCY_WEEKLY, _('Weekly')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_digests',
        help_text=_("User who receives the digest")
    )
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        help_text=_("Digest frequency")
    )
    notifications = models.ManyToManyField(
        Notification,
        related_name='digests',
        help_text=_("Notifications included in this digest")
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the digest was sent")
    )
    
    class Meta:
        verbose_name = _("Notification Digest")
        verbose_name_plural = _("Notification Digests")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.frequency} digest for {self.user.email}"


class EmailProvider(TimestampedModel):
    """
    Email provider configuration (SendGrid, AWS SES, etc.)
    """
    
    # Provider Type Choices
    TYPE_SENDGRID = 'sendgrid'
    TYPE_AWS_SES = 'aws_ses'
    TYPE_SMTP = 'smtp'
    TYPE_MAILGUN = 'mailgun'
    
    TYPE_CHOICES = [
        (TYPE_SENDGRID, _('SendGrid')),
        (TYPE_AWS_SES, _('AWS SES')),
        (TYPE_SMTP, _('SMTP')),
        (TYPE_MAILGUN, _('Mailgun')),
    ]
    
    # Status Choices
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_ERROR = 'error'
    
    STATUS_CHOICES = [
        (STATUS_ACTIVE, _('Active')),
        (STATUS_INACTIVE, _('Inactive')),
        (STATUS_ERROR, _('Error')),
    ]
    
    name = models.CharField(
        max_length=100,
        help_text=_("Provider name")
    )
    provider_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        help_text=_("Type of email provider")
    )
    is_default = models.BooleanField(
        default=False,
        help_text=_("Whether this is the default provider")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        help_text=_("Provider status")
    )
    
    # Configuration (encrypted at application level)
    api_key = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("API key for the provider")
    )
    api_secret = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("API secret for the provider")
    )
    region = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Region for AWS SES")
    )
    smtp_host = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("SMTP host")
    )
    smtp_port = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("SMTP port")
    )
    smtp_username = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("SMTP username")
    )
    smtp_password = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("SMTP password")
    )
    smtp_use_tls = models.BooleanField(
        default=True,
        help_text=_("Use TLS for SMTP")
    )
    
    # Rate limiting
    rate_limit = models.PositiveIntegerField(
        default=100,
        help_text=_("Emails per minute rate limit")
    )
    
    # Webhook settings
    webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Secret for webhook signature verification")
    )
    
    class Meta:
        verbose_name = _("Email Provider")
        verbose_name_plural = _("Email Providers")
        ordering = ['-is_default', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.provider_type})"
    
    def save(self, *args, **kwargs):
        if self.is_default:
            # Ensure only one default provider
            EmailProvider.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class EmailTemplate(TimestampedModel):
    """
    Email template for notifications.
    """
    
    # Status Choices
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, _('Draft')),
        (STATUS_ACTIVE, _('Active')),
        (STATUS_ARCHIVED, _('Archived')),
    ]
    
    # Template Type Choices
    TYPE_NOTIFICATION = 'notification'
    TYPE_DIGEST = 'digest'
    TYPE_WELCOME = 'welcome'
    TYPE_PASSWORD_RESET = 'password_reset'
    TYPE_VERIFICATION = 'verification'
    TYPE_CERTIFICATE = 'certificate'
    TYPE_MARKETING = 'marketing'
    
    TYPE_CHOICES = [
        (TYPE_NOTIFICATION, _('Notification')),
        (TYPE_DIGEST, _('Digest')),
        (TYPE_WELCOME, _('Welcome')),
        (TYPE_PASSWORD_RESET, _('Password Reset')),
        (TYPE_VERIFICATION, _('Verification')),
        (TYPE_CERTIFICATE, _('Certificate')),
        (TYPE_MARKETING, _('Marketing')),
    ]
    
    name = models.CharField(
        max_length=100,
        help_text=_("Template name")
    )
    slug = models.SlugField(
        unique=True,
        help_text=_("Unique template slug")
    )
    template_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default=TYPE_NOTIFICATION,
        help_text=_("Type of template")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        help_text=_("Template status")
    )
    is_default = models.BooleanField(
        default=False,
        help_text=_("Whether this is the default template for its type")
    )
    
    # Content
    subject = models.CharField(
        max_length=255,
        help_text=_("Email subject line")
    )
    html_content = models.TextField(
        help_text=_("HTML email content")
    )
    text_content = models.TextField(
        help_text=_("Plain text email content")
    )
    mjml_content = models.TextField(
        blank=True,
        help_text=_("MJML source content")
    )
    
    # Styling
    primary_color = models.CharField(
        max_length=7,
        default='#007bff',
        help_text=_("Primary brand color")
    )
    logo_url = models.URLField(
        blank=True,
        help_text=_("URL to logo image")
    )
    footer_text = models.TextField(
        blank=True,
        help_text=_("Custom footer text")
    )
    
    # Variables
    variables_schema = models.JSONField(
        default=dict,
        help_text=_("JSON schema for template variables")
    )
    
    # Versioning
    version = models.PositiveIntegerField(
        default=1,
        help_text=_("Template version")
    )
    parent_template = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='versions',
        help_text=_("Parent template for versioning")
    )
    
    # Usage statistics
    send_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Total emails sent using this template")
    )
    open_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Total opens")
    )
    click_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Total clicks")
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When template was last used")
    )
    
    class Meta:
        verbose_name = _("Email Template")
        verbose_name_plural = _("Email Templates")
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['slug', 'status', 'is_default']),
            models.Index(fields=['template_type', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    def save(self, *args, **kwargs):
        # Compile MJML to HTML if mjml_content changed
        if self.mjml_content and not self.html_content:
            self.compile_mjml()
        super().save(*args, **kwargs)
    
    def compile_mjml(self):
        """Compile MJML content to HTML."""
        # This will be implemented in the service layer
        # For now, just store MJML as-is
        self.html_content = self.mjml_content
    
    def increment_send_count(self):
        """Increment send count and update last used timestamp."""
        from django.utils import timezone
        self.send_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['send_count', 'last_used_at', 'updated_at'])


class EmailLog(TimestampedModel):
    """
    Comprehensive email delivery tracking and logging.
    """
    
    # Status Choices
    STATUS_QUEUED = 'queued'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_OPENED = 'opened'
    STATUS_CLICKED = 'clicked'
    STATUS_BOUNCED = 'bounced'
    STATUS_COMPLAINED = 'complained'
    STATUS_FAILED = 'failed'
    STATUS_DEFERRED = 'deferred'
    STATUS_DROPPED = 'dropped'
    STATUS_UNSUBSCRIBED = 'unsubscribed'
    STATUS_GROUP_UNSUBSCRIBED = 'group_unsubscribed'
    STATUS_BLOCKED = 'blocked'
    STATUS_RENDERING_FAILED = 'rendering_failed'
    
    STATUS_CHOICES = [
        (STATUS_QUEUED, _('Queued')),
        (STATUS_SENT, _('Sent')),
        (STATUS_DELIVERED, _('Delivered')),
        (STATUS_OPENED, _('Opened')),
        (STATUS_CLICKED, _('Clicked')),
        (STATUS_BOUNCED, _('Bounced')),
        (STATUS_COMPLAINED, _('Complained')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_DEFERRED, _('Deferred')),
        (STATUS_DROPPED, _('Dropped')),
        (STATUS_UNSUBSCRIBED, _('Unsubscribed')),
        (STATUS_GROUP_UNSUBSCRIBED, _('Group Unsubscribed')),
        (STATUS_BLOCKED, _('Blocked')),
        (STATUS_RENDERING_FAILED, _('Rendering Failed')),
    ]
    
    # Bounce Types
    BOUNCE_TYPE_HARD = 'hard'
    BOUNCE_TYPE_SOFT = 'soft'
    BOUNCE_TYPE_BLOCK = 'block'
    
    BOUNCE_TYPE_CHOICES = [
        (BOUNCE_TYPE_HARD, _('Hard Bounce')),
        (BOUNCE_TYPE_SOFT, _('Soft Bounce')),
        (BOUNCE_TYPE_BLOCK, _('Block')),
    ]
    
    # Core Fields
    message_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Unique message ID from provider")
    )
    provider = models.ForeignKey(
        EmailProvider,
        on_delete=models.SET_NULL,
        null=True,
        related_name='email_logs',
        help_text=_("Email provider used")
    )
    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
        help_text=_("Template used for this email")
    )
    
    # Recipient Information
    recipient_email = models.EmailField(
        db_index=True,
        help_text=_("Recipient email address")
    )
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
        help_text=_("User recipient if applicable")
    )
    
    # Sender Information
    from_email = models.EmailField(
        help_text=_("From email address")
    )
    from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("From name")
    )
    reply_to = models.EmailField(
        blank=True,
        help_text=_("Reply-to email address")
    )
    
    # Content
    subject = models.CharField(
        max_length=255,
        help_text=_("Email subject")
    )
    html_body = models.TextField(
        blank=True,
        help_text=_("HTML email body")
    )
    text_body = models.TextField(
        blank=True,
        help_text=_("Plain text email body")
    )
    template_variables = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Variables used in template rendering")
    )
    
    # Status Tracking
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
        help_text=_("Current delivery status")
    )
    
    # Timestamps
    queued_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When email was queued")
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When email was sent")
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When email was delivered")
    )
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When email was first opened")
    )
    clicked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When first link was clicked")
    )
    
    # Engagement Tracking
    open_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of times opened")
    )
    click_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of times clicked")
    )
    last_opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Last open timestamp")
    )
    last_clicked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Last click timestamp")
    )
    
    # Bounce/Complaint Information
    bounce_type = models.CharField(
        max_length=20,
        choices=BOUNCE_TYPE_CHOICES,
        blank=True,
        help_text=_("Type of bounce")
    )
    bounce_reason = models.TextField(
        blank=True,
        help_text=_("Bounce reason/description")
    )
    bounce_diagnostic = models.TextField(
        blank=True,
        help_text=_("Diagnostic information")
    )
    
    # Error Information
    error_message = models.TextField(
        blank=True,
        help_text=_("Error message if failed")
    )
    error_code = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Provider error code")
    )
    
    # Provider Response
    provider_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw provider API response")
    )
    
    # IP & User Agent
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_("IP address for opens/clicks")
    )
    user_agent = models.TextField(
        blank=True,
        help_text=_("User agent for opens/clicks")
    )
    
    # Retry Information
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of retry attempts")
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Next scheduled retry time")
    )
    
    # Campaign/Category
    campaign_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_("Campaign identifier")
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text=_("Email category")
    )
    
    class Meta:
        verbose_name = _("Email Log")
        verbose_name_plural = _("Email Logs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient_email', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['provider', '-created_at']),
            models.Index(fields=['template', '-created_at']),
            models.Index(fields=['campaign_id', '-created_at']),
            models.Index(fields=['recipient_user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.message_id} - {self.recipient_email}"
    
    def mark_as_sent(self):
        """Mark email as sent."""
        from django.utils import timezone
        self.status = self.STATUS_SENT
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at', 'updated_at'])
    
    def mark_as_delivered(self):
        """Mark email as delivered."""
        from django.utils import timezone
        self.status = self.STATUS_DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])
    
    def mark_as_opened(self, ip_address=None, user_agent=None):
        """Mark email as opened."""
        from django.utils import timezone
        self.status = self.STATUS_OPENED
        self.open_count += 1
        self.last_opened_at = timezone.now()
        if not self.opened_at:
            self.opened_at = timezone.now()
        if ip_address:
            self.ip_address = ip_address
        if user_agent:
            self.user_agent = user_agent
        self.save(update_fields=['status', 'open_count', 'opened_at', 
                                  'last_opened_at', 'ip_address', 
                                  'user_agent', 'updated_at'])
    
    def mark_as_clicked(self, ip_address=None, user_agent=None):
        """Mark email as clicked."""
        from django.utils import timezone
        self.status = self.STATUS_CLICKED
        self.click_count += 1
        self.last_clicked_at = timezone.now()
        if not self.clicked_at:
            self.clicked_at = timezone.now()
        if ip_address:
            self.ip_address = ip_address
        if user_agent:
            self.user_agent = user_agent
        self.save(update_fields=['status', 'click_count', 'clicked_at',
                                  'last_clicked_at', 'ip_address',
                                  'user_agent', 'updated_at'])
    
    def mark_as_bounced(self, bounce_type, reason='', diagnostic=''):
        """Mark email as bounced."""
        self.status = self.STATUS_BOUNCED
        self.bounce_type = bounce_type
        self.bounce_reason = reason
        self.bounce_diagnostic = diagnostic
        self.save(update_fields=['status', 'bounce_type', 'bounce_reason',
                                  'bounce_diagnostic', 'updated_at'])
    
    def mark_as_complained(self, reason=''):
        """Mark email as complained (spam complaint)."""
        self.status = self.STATUS_COMPLAINED
        self.bounce_reason = reason
        self.save(update_fields=['status', 'bounce_reason', 'updated_at'])
    
    def mark_as_failed(self, error_message='', error_code=''):
        """Mark email as failed."""
        self.status = self.STATUS_FAILED
        self.error_message = error_message
        self.error_code = error_code
        self.save(update_fields=['status', 'error_message', 'error_code', 'updated_at'])
    
    def increment_retry(self, next_retry=None):
        """Increment retry count and set next retry time."""
        self.retry_count += 1
        if next_retry:
            self.next_retry_at = next_retry
        self.save(update_fields=['retry_count', 'next_retry_at', 'updated_at'])


class EmailEvent(TimestampedModel):
    """
    Individual email events from provider webhooks.
    Tracks all events for detailed analytics and debugging.
    """
    
    # Event Types
    EVENT_PROCESSED = 'processed'
    EVENT_DROPPED = 'dropped'
    EVENT_DELIVERED = 'delivered'
    EVENT_DEFERRED = 'deferred'
    EVENT_BOUNCE = 'bounce'
    EVENT_BLOCK = 'block'
    EVENT_OPEN = 'open'
    EVENT_CLICK = 'click'
    EVENT_SPAM_REPORT = 'spamreport'
    EVENT_UNSUBSCRIBE = 'unsubscribe'
    EVENT_GROUP_UNSUBSCRIBE = 'group_unsubscribe'
    EVENT_GROUP_RESUBSCRIBE = 'group_resubscribe'
    EVENT_RENDERING_FAILURE = 'rendering_failure'
    EVENT_SEND = 'send'
    EVENT_REJECT = 'reject'
    EVENT_COMPLAINT = 'complaint'
    
    EVENT_CHOICES = [
        (EVENT_PROCESSED, _('Processed')),
        (EVENT_DROPPED, _('Dropped')),
        (EVENT_DELIVERED, _('Delivered')),
        (EVENT_DEFERRED, _('Deferred')),
        (EVENT_BOUNCE, _('Bounce')),
        (EVENT_BLOCK, _('Block')),
        (EVENT_OPEN, _('Open')),
        (EVENT_CLICK, _('Click')),
        (EVENT_SPAM_REPORT, _('Spam Report')),
        (EVENT_UNSUBSCRIBE, _('Unsubscribe')),
        (EVENT_GROUP_UNSUBSCRIBE, _('Group Unsubscribe')),
        (EVENT_GROUP_RESUBSCRIBE, _('Group Resubscribe')),
        (EVENT_RENDERING_FAILURE, _('Rendering Failure')),
        (EVENT_SEND, _('Send')),
        (EVENT_REJECT, _('Reject')),
        (EVENT_COMPLAINT, _('Complaint')),
    ]
    
    # Event Sources
    SOURCE_SENDGRID = 'sendgrid'
    SOURCE_AWS_SES = 'aws_ses'
    SOURCE_INTERNAL = 'internal'
    
    SOURCE_CHOICES = [
        (SOURCE_SENDGRID, _('SendGrid')),
        (SOURCE_AWS_SES, _('AWS SES')),
        (SOURCE_INTERNAL, _('Internal')),
    ]
    
    email_log = models.ForeignKey(
        EmailLog,
        on_delete=models.CASCADE,
        related_name='events',
        help_text=_("Associated email log entry")
    )
    event_type = models.CharField(
        max_length=30,
        choices=EVENT_CHOICES,
        db_index=True,
        help_text=_("Type of email event")
    )
    event_source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        db_index=True,
        help_text=_("Source of the event")
    )
    
    # Event Data
    event_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Provider event ID")
    )
    timestamp = models.DateTimeField(
        db_index=True,
        help_text=_("When the event occurred (provider timestamp)")
    )
    
    # Provider-Specific Data
    provider_payload = models.JSONField(
        default=dict,
        help_text=_("Raw event payload from provider")
    )
    
    # Parsed Event Data
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_("IP address associated with event")
    )
    user_agent = models.TextField(
        blank=True,
        help_text=_("User agent string")
    )
    url = models.URLField(
        blank=True,
        help_text=_("URL for click events")
    )
    reason = models.TextField(
        blank=True,
        help_text=_("Reason for event (bounce, drop, etc.)")
    )
    response = models.TextField(
        blank=True,
        help_text=_("SMTP response or error message")
    )
    
    # Bounce/Complaint Details
    bounce_type = models.CharField(
        max_length=20,
        blank=True,
        help_text=_("Bounce type")
    )
    bounce_class = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Bounce classification")
    )
    feedback_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Feedback ID for complaints")
    )
    
    # Geolocation (for opens/clicks)
    country = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Country from IP geolocation")
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("City from IP geolocation")
    )
    
    # Device/Client Info
    device_type = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Device type (desktop, mobile, tablet)")
    )
    client_name = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Email client name")
    )
    client_os = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Operating system")
    )
    
    class Meta:
        verbose_name = _("Email Event")
        verbose_name_plural = _("Email Events")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['email_log', 'event_type', '-timestamp']),
            models.Index(fields=['event_source', 'event_type', '-timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.email_log.message_id}"
