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
    """
    
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
    
    # Push preferences
    push_enabled = models.BooleanField(
        default=False,
        help_text=_("Whether push notifications are enabled")
    )
    push_device_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of push notification device tokens")
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


class NotificationDigest(TimestampedModel):
    """
    Tracks notification digests sent to users.
    """
    
    DIGEST_TYPE_HOURLY = 'hourly'
    DIGEST_TYPE_DAILY = 'daily'
    DIGEST_TYPE_WEEKLY = 'weekly'
    
    DIGEST_TYPE_CHOICES = [
        (DIGEST_TYPE_HOURLY, _('Hourly')),
        (DIGEST_TYPE_DAILY, _('Daily')),
        (DIGEST_TYPE_WEEKLY, _('Weekly')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_digests',
        help_text=_("User who received the digest")
    )
    digest_type = models.CharField(
        max_length=20,
        choices=DIGEST_TYPE_CHOICES,
        help_text=_("Type of digest")
    )
    notification_count = models.PositiveIntegerField(
        help_text=_("Number of notifications included in digest")
    )
    notification_ids = models.JSONField(
        default=list,
        help_text=_("IDs of notifications included in digest")
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the digest was sent")
    )
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the digest was opened")
    )
    
    class Meta:
        verbose_name = _("Notification Digest")
        verbose_name_plural = _("Notification Digests")
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.digest_type} digest for {self.user.email}"
