"""
Notifications Models for Enterprise LMS
Provides Notification model for email and in-app notifications with delivery tracking,
idempotency, dead letter queue, and comprehensive audit logging.
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
    Supports email, in-app, and push notification types with delivery tracking,
    idempotency keys, and retry logic for production reliability.
    """
    
    # Notification Channel Choices
    CHANNEL_EMAIL = 'email'
    CHANNEL_IN_APP = 'in_app'
    CHANNEL_PUSH = 'push'
    
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, _('Email')),
        (CHANNEL_IN_APP, _('In-App')),
        (CHANNEL_PUSH, _('Push')),
    ]
    
    # Notification Type Choices (legacy - use channel)
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
    
    # Status Choices - Extended for delivery tracking
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_FAILED = 'failed'
    STATUS_READ = 'read'
    STATUS_DEFERRED = 'deferred'
    STATUS_BOUNCED = 'bounced'
    STATUS_COMPLAINED = 'complained'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, _('Pending')),
        (STATUS_SENT, _('Sent')),
        (STATUS_DELIVERED, _('Delivered')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_READ, _('Read')),
        (STATUS_DEFERRED, _('Deferred')),
        (STATUS_BOUNCED, _('Bounced')),
        (STATUS_COMPLAINED, _('Complained')),
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
    
    # Channel (new field for hardened service)
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_IN_APP,
        db_index=True,
        help_text=_("Delivery channel for this notification")
    )
    
    # Legacy notification_type field (for backward compatibility)
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default=TYPE_IN_APP,
        db_index=True,
        help_text=_("Type of notification (legacy, use channel)")
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
    
    # Delivery tracking timestamps
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
    
    # Idempotency and retry tracking (new fields for hardened service)
    idempotency_key = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        default='',
        help_text=_("Unique key for deduplication (24-hour window)")
    )
    delivery_attempts = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of delivery attempts made")
    )
    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the last delivery attempt was made")
    )
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("When the notification should be delivered (for scheduled notifications)")
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text=_("Error message if delivery failed")
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of retry attempts for failed notifications (legacy)")
    )
    
    # Email-specific fields
    email_subject = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Email subject line (for email notifications)")
    )
    email_template = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Template used for email rendering")
    )
    
    # Provider tracking
    provider = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Email provider used (sendgrid, aws_ses, smtp)")
    )
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Message ID from email provider")
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
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['idempotency_key', 'created_at']),
            models.Index(fields=['scheduled_at', 'status']),
            models.Index(fields=['provider_message_id']),
            models.Index(fields=['delivery_attempts', 'status']),
        ]
    
    def __str__(self):
        return f"{self.channel} - {self.title}"
    
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
    
    def mark_as_bounced(self, error_message=''):
        """Mark notification as bounced."""
        from django.utils import timezone
        self.status = self.STATUS_BOUNCED
        self.error_message = error_message
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'delivered_at', 'updated_at'])
    
    def mark_as_complained(self):
        """Mark notification as complained (spam complaint)."""
        from django.utils import timezone
        self.status = self.STATUS_COMPLAINED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])
    
    def increment_retry(self):
        """Increment retry count (legacy)."""
        self.retry_count += 1
        self.save(update_fields=['retry_count', 'updated_at'])
    
    def record_attempt(self, error_message=''):
        """Record a delivery attempt."""
        from django.utils import timezone
        self.delivery_attempts += 1
        self.last_attempt_at = timezone.now()
        if error_message:
            self.error_message = error_message
        self.save(update_fields=['delivery_attempts', 'last_attempt_at', 'error_message', 'updated_at'])
    
    def should_retry(self, max_attempts=5):
        """Check if notification should be retried."""
        return self.delivery_attempts < max_attempts and self.status in [
            self.STATUS_FAILED, self.STATUS_DEFERRED, self.STATUS_PENDING
        ]
    
    def get_next_retry_delay(self):
        """Calculate exponential backoff delay (2^attempt * 60s with jitter)."""
        import random
        base_delay = (2 ** self.delivery_attempts) * 60
        jitter = random.uniform(0, 0.1 * base_delay)  # 10% jitter
        return int(base_delay + jitter)


class NotificationDLQ(TimestampedModel):
    """
    Dead Letter Queue for failed notifications.
    Stores notifications that exceeded max retry attempts for manual review.
    """
    
    # DLQ Status Choices
    STATUS_PENDING_REVIEW = 'pending_review'
    STATUS_REQUEUED = 'requeued'
    STATUS_DISCARDED = 'discarded'
    STATUS_RESOLVED = 'resolved'
    
    STATUS_CHOICES = [
        (STATUS_PENDING_REVIEW, _('Pending Review')),
        (STATUS_REQUEUED, _('Requeued')),
        (STATUS_DISCARDED, _('Discarded')),
        (STATUS_RESOLVED, _('Resolved')),
    ]
    
    # Original notification reference
    original_notification = models.OneToOneField(
        Notification,
        on_delete=models.CASCADE,
        related_name='dlq_entry',
        help_text=_("Original notification that failed")
    )
    
    # DLQ tracking
    failed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text=_("When the notification entered DLQ")
    )
    error_message = models.TextField(
        help_text=_("Final error message that caused DLQ entry")
    )
    attempt_count = models.PositiveIntegerField(
        help_text=_("Number of delivery attempts before DLQ")
    )
    
    # Payload preservation
    payload = models.JSONField(
        default=dict,
        help_text=_("Complete notification payload for reprocessing")
    )
    
    # DLQ management
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING_REVIEW,
        db_index=True,
        help_text=_("Current DLQ status")
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the DLQ entry was reviewed")
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dlq_reviews',
        help_text=_("User who reviewed this DLQ entry")
    )
    resolution_notes = models.TextField(
        blank=True,
        help_text=_("Notes about resolution")
    )
    
    class Meta:
        verbose_name = _("Notification DLQ Entry")
        verbose_name_plural = _("Notification DLQ Entries")
        ordering = ['-failed_at']
        indexes = [
            models.Index(fields=['status', 'failed_at']),
            models.Index(fields=['original_notification']),
        ]
    
    def __str__(self):
        return f"DLQ: {self.original_notification.title}"
    
    def mark_as_requeued(self, reviewed_by=None):
        """Mark DLQ entry as requeued."""
        from django.utils import timezone
        self.status = self.STATUS_REQUEUED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])
    
    def mark_as_discarded(self, reviewed_by=None, notes=''):
        """Mark DLQ entry as discarded."""
        from django.utils import timezone
        self.status = self.STATUS_DISCARDED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.resolution_notes = notes
        self.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'resolution_notes', 'updated_at'])
    
    def mark_as_resolved(self, reviewed_by=None, notes=''):
        """Mark DLQ entry as resolved."""
        from django.utils import timezone
        self.status = self.STATUS_RESOLVED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.resolution_notes = notes
        self.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'resolution_notes', 'updated_at'])


class NotificationDeliveryLog(TimestampedModel):
    """
    Detailed delivery log for each notification attempt.
    Provides audit trail for SOC 2 compliance.
    """
    
    # Attempt Status Choices
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_RETRY = 'retry'
    STATUS_SKIPPED = 'skipped'
    
    STATUS_CHOICES = [
        (STATUS_SUCCESS, _('Success')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_RETRY, _('Retry')),
        (STATUS_SKIPPED, _('Skipped')),
    ]
    
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='delivery_logs',
        help_text=_("Notification being delivered")
    )
    attempt_number = models.PositiveIntegerField(
        help_text=_("Attempt number (1-indexed)")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        help_text=_("Result of this delivery attempt")
    )
    error_details = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Detailed error information")
    )
    webhook_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Response from webhook callbacks")
    )
    provider_response = models.TextField(
        blank=True,
        help_text=_("Raw response from email provider")
    )
    duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Request duration in milliseconds")
    )
    
    class Meta:
        verbose_name = _("Notification Delivery Log")
        verbose_name_plural = _("Notification Delivery Logs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['notification', 'attempt_number']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Attempt {self.attempt_number} for {self.notification.id}"


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
        
        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Crosses midnight
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end
    
    def should_send_channel(self, channel):
        """Check if a channel is enabled for this user."""
        if channel == Notification.CHANNEL_EMAIL:
            return self.email_enabled
        elif channel == Notification.CHANNEL_IN_APP:
            return self.in_app_enabled
        elif channel == Notification.CHANNEL_PUSH:
            return self.push_enabled
        return True
    
    def should_send_category(self, category):
        """Check if a category is enabled for this user."""
        category_map = {
            Notification.CATEGORY_COURSE: self.notify_on_course_updates,
            Notification.CATEGORY_ASSIGNMENT: self.notify_on_assignments,
            Notification.CATEGORY_FORUM: self.notify_on_forum_replies,
            Notification.CERTIFICATE: self.notify_on_certificates,
            Notification.CATEGORY_ENROLLMENT: self.notify_on_enrollments,
        }
        return category_map.get(category, True)


class PushSubscription(TimestampedModel):
    """
    Push notification subscription for a user device.
    """
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='push_subscriptions',
        help_text=_("User who owns this subscription")
    )
    endpoint = models.URLField(
        help_text=_("Push service endpoint URL")
    )
    p256dh = models.CharField(
        max_length=255,
        help_text=_("P256DH key for encryption")
    )
    auth = models.CharField(
        max_length=255,
        help_text=_("Auth secret for encryption")
    )
    device_info = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Device information (browser, OS, etc.)")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this subscription is active")
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When this subscription was last used")
    )
    
    class Meta:
        verbose_name = _("Push Subscription")
        verbose_name_plural = _("Push Subscriptions")
        unique_together = ['user', 'endpoint']
    
    def __str__(self):
        return f"Push subscription for {self.user.email}"


class NotificationDigest(TimestampedModel):
    """
    Notification digest for batching notifications.
    """
    
    # Digest Type Choices
    TYPE_HOURLY = 'hourly'
    TYPE_DAILY = 'daily'
    TYPE_WEEKLY = 'weekly'
    
    TYPE_CHOICES = [
        (TYPE_HOURLY, _('Hourly')),
        (TYPE_DAILY, _('Daily')),
        (TYPE_WEEKLY, _('Weekly')),
    ]
    
    # Status Choices
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, _('Pending')),
        (STATUS_SENT, _('Sent')),
        (STATUS_FAILED, _('Failed')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_digests',
        help_text=_("User who receives this digest")
    )
    digest_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        help_text=_("Type of digest")
    )
    notifications = models.ManyToManyField(
        Notification,
        related_name='digests',
        help_text=_("Notifications included in this digest")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text=_("Status of this digest")
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When this digest was sent")
    )
    
    class Meta:
        verbose_name = _("Notification Digest")
        verbose_name_plural = _("Notification Digests")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.digest_type} digest for {self.user.email}"


class EmailProvider(TimestampedModel):
    """
    Email provider configuration.
    """
    
    # Provider Choices
    PROVIDER_SENDGRID = 'sendgrid'
    PROVIDER_AWS_SES = 'aws_ses'
    PROVIDER_SMTP = 'smtp'
    
    PROVIDER_CHOICES = [
        (PROVIDER_SENDGRID, _('SendGrid')),
        (PROVIDER_AWS_SES, _('AWS SES')),
        (PROVIDER_SMTP, _('SMTP')),
    ]
    
    name = models.CharField(
        max_length=100,
        help_text=_("Provider name")
    )
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        help_text=_("Email provider type")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this provider is active")
    )
    is_default = models.BooleanField(
        default=False,
        help_text=_("Whether this is the default provider")
    )
    priority = models.PositiveIntegerField(
        default=0,
        help_text=_("Priority for provider selection (higher = preferred)")
    )
    config = models.JSONField(
        default=dict,
        help_text=_("Provider-specific configuration")
    )
    rate_limit = models.PositiveIntegerField(
        default=100,
        help_text=_("Rate limit per minute")
    )
    daily_limit = models.PositiveIntegerField(
        default=10000,
        help_text=_("Daily sending limit")
    )
    sent_today = models.PositiveIntegerField(
        default=0,
        help_text=_("Emails sent today")
    )
    last_reset_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the daily counter was last reset")
    )
    
    class Meta:
        verbose_name = _("Email Provider")
        verbose_name_plural = _("Email Providers")
        ordering = ['-priority', 'name']
    
    def __str__(self):
        return self.name


class EmailTemplate(TimestampedModel):
    """
    Email template for notifications.
    """
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Template name")
    )
    subject = models.CharField(
        max_length=255,
        help_text=_("Email subject template")
    )
    html_content = models.TextField(
        help_text=_("HTML email content template")
    )
    text_content = models.TextField(
        help_text=_("Plain text email content template")
    )
    description = models.TextField(
        blank=True,
        help_text=_("Template description")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this template is active")
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Template category")
    )
    
    class Meta:
        verbose_name = _("Email Template")
        verbose_name_plural = _("Email Templates")
        ordering = ['name']
    
    def __str__(self):
        return self.name


class EmailLog(TimestampedModel):
    """
    Log of sent emails for tracking and debugging.
    """
    
    # Status Choices
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_OPENED = 'opened'
    STATUS_CLICKED = 'clicked'
    STATUS_BOUNCED = 'bounced'
    STATUS_COMPLAINED = 'complained'
    STATUS_FAILED = 'failed'
    
    STATUS_CHOICES = [
        (STATUS_SENT, _('Sent')),
        (STATUS_DELIVERED, _('Delivered')),
        (STATUS_OPENED, _('Opened')),
        (STATUS_CLICKED, _('Clicked')),
        (STATUS_BOUNCED, _('Bounced')),
        (STATUS_COMPLAINED, _('Complained')),
        (STATUS_FAILED, _('Failed')),
    ]
    
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='email_logs',
        null=True,
        blank=True,
        help_text=_("Related notification")
    )
    recipient = models.EmailField(
        help_text=_("Email recipient")
    )
    subject = models.CharField(
        max_length=255,
        help_text=_("Email subject")
    )
    template = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Template used")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SENT,
        db_index=True,
        help_text=_("Email status")
    )
    provider = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Email provider used")
    )
    message_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Provider message ID")
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the email was sent")
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the email was delivered")
    )
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the email was opened")
    )
    clicked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When a link was clicked")
    )
    error_message = models.TextField(
        blank=True,
        help_text=_("Error message if failed")
    )
    
    class Meta:
        verbose_name = _("Email Log")
        verbose_name_plural = _("Email Logs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['message_id']),
        ]
    
    def __str__(self):
        return f"Email to {self.recipient}"


class EmailEvent(TimestampedModel):
    """
    Email event from webhook callbacks (SendGrid, SES).
    """
    
    # Event Type Choices
    EVENT_DELIVERED = 'delivered'
    EVENT_BOUNCE = 'bounce'
    EVENT_COMPLAINT = 'complaint'
    EVENT_OPEN = 'open'
    EVENT_CLICK = 'click'
    EVENT_DEFERRED = 'deferred'
    EVENT_DROPPED = 'dropped'
    EVENT_PROCESSED = 'processed'
    EVENT_SEND = 'send'
    
    EVENT_CHOICES = [
        (EVENT_DELIVERED, _('Delivered')),
        (EVENT_BOUNCE, _('Bounce')),
        (EVENT_COMPLAINT, _('Complaint')),
        (EVENT_OPEN, _('Open')),
        (EVENT_CLICK, _('Click')),
        (EVENT_DEFERRED, _('Deferred')),
        (EVENT_DROPPED, _('Dropped')),
        (EVENT_PROCESSED, _('Processed')),
        (EVENT_SEND, _('Send')),
    ]
    
    email_log = models.ForeignKey(
        EmailLog,
        on_delete=models.CASCADE,
        related_name='events',
        null=True,
        blank=True,
        help_text=_("Related email log")
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_CHOICES,
        db_index=True,
        help_text=_("Type of email event")
    )
    provider = models.CharField(
        max_length=50,
        help_text=_("Provider that sent this event")
    )
    message_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text=_("Provider message ID")
    )
    recipient = models.EmailField(
        help_text=_("Email recipient")
    )
    timestamp = models.DateTimeField(
        help_text=_("When the event occurred (from provider)")
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_("IP address associated with event")
    )
    user_agent = models.TextField(
        blank=True,
        help_text=_("User agent string (for open/click events)")
    )
    url = models.URLField(
        blank=True,
        help_text=_("URL clicked (for click events)")
    )
    reason = models.TextField(
        blank=True,
        help_text=_("Reason for bounce/complaint")
    )
    raw_data = models.JSONField(
        default=dict,
        help_text=_("Raw event data from provider")
    )
    
    class Meta:
        verbose_name = _("Email Event")
        verbose_name_plural = _("Email Events")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['message_id', 'event_type']),
            models.Index(fields=['recipient', 'event_type']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.event_type} event for {self.recipient}"
