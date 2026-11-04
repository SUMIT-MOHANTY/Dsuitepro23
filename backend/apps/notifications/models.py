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


# =============================================================================
# Email Service Integration Models (SendGrid/AWS SES)
# =============================================================================

class EmailProvider(TimestampedModel):
    """
    Email provider configuration for SendGrid and AWS SES.
    Supports multiple providers with failover priority.
    """
    
    # Provider Types
    PROVIDER_SENDGRID = 'sendgrid'
    PROVIDER_AWS_SES = 'aws_ses'
    
    PROVIDER_CHOICES = [
        (PROVIDER_SENDGRID, _('SendGrid')),
        (PROVIDER_AWS_SES, _('AWS SES')),
    ]
    
    # Provider Status
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_DEGRADED = 'degraded'
    STATUS_MAINTENANCE = 'maintenance'
    
    STATUS_CHOICES = [
        (STATUS_ACTIVE, _('Active')),
        (STATUS_INACTIVE, _('Inactive')),
        (STATUS_DEGRADED, _('Degraded')),
        (STATUS_MAINTENANCE, _('Maintenance')),
    ]
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Unique name for this provider configuration")
    )
    provider_type = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        help_text=_("Email service provider type")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text=_("Current provider status")
    )
    
    # Failover Configuration
    priority = models.PositiveIntegerField(
        default=1,
        db_index=True,
        help_text=_("Failover priority (lower = higher priority)")
    )
    is_primary = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether this is the primary provider")
    )
    
    # SendGrid Configuration
    sendgrid_api_key = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("SendGrid API key (encrypted at rest)")
    )
    sendgrid_from_email = models.EmailField(
        blank=True,
        help_text=_("Default from email for SendGrid")
    )
    sendgrid_from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Default from name for SendGrid")
    )
    
    # AWS SES Configuration
    aws_access_key_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("AWS Access Key ID (encrypted at rest)")
    )
    aws_secret_access_key = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("AWS Secret Access Key (encrypted at rest)")
    )
    aws_region = models.CharField(
        max_length=50,
        default='us-east-1',
        help_text=_("AWS region for SES")
    )
    aws_from_email = models.EmailField(
        blank=True,
        help_text=_("Verified SES from email address")
    )
    aws_configuration_set = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("AWS SES configuration set for event tracking")
    )
    
    # Rate Limiting & Throttling
    rate_limit_per_second = models.PositiveIntegerField(
        default=10,
        help_text=_("Maximum emails per second")
    )
    rate_limit_per_day = models.PositiveIntegerField(
        default=50000,
        help_text=_("Maximum emails per day")
    )
    daily_sent_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Emails sent today (resets at midnight)")
    )
    daily_sent_reset_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When daily counter was last reset")
    )
    
    # IP Warm-up Settings
    ip_warmup_enabled = models.BooleanField(
        default=False,
        help_text=_("Whether IP warm-up is enabled")
    )
    ip_warmup_day = models.PositiveIntegerField(
        default=0,
        help_text=_("Current day of IP warm-up (0-30)")
    )
    ip_warmup_daily_limit = models.PositiveIntegerField(
        default=50,
        help_text=_("Daily sending limit during warm-up")
    )
    
    # Health Monitoring
    last_health_check = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Last health check timestamp")
    )
    health_check_failures = models.PositiveIntegerField(
        default=0,
        help_text=_("Consecutive health check failures")
    )
    reputation_score = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=100.00,
        help_text=_("Provider reputation score (0-100)")
    )
    
    # Webhook Configuration
    webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Secret for webhook signature verification")
    )
    webhook_url_path = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("URL path for provider webhooks")
    )
    
    class Meta:
        verbose_name = _("Email Provider")
        verbose_name_plural = _("Email Providers")
        ordering = ['priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.provider_type})"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary provider
        if self.is_primary:
            EmailProvider.objects.filter(is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class EmailTemplate(TimestampedModel):
    """
    MJML-based email template with versioning support.
    """
    
    # Template Types
    TYPE_TRANSACTIONAL = 'transactional'
    TYPE_MARKETING = 'marketing'
    TYPE_DIGEST = 'digest'
    TYPE_SYSTEM = 'system'
    
    TYPE_CHOICES = [
        (TYPE_TRANSACTIONAL, _('Transactional')),
        (TYPE_MARKETING, _('Marketing')),
        (TYPE_DIGEST, _('Digest')),
        (TYPE_SYSTEM, _('System')),
    ]
    
    # Template Status
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, _('Draft')),
        (STATUS_ACTIVE, _('Active')),
        (STATUS_ARCHIVED, _('Archived')),
    ]
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Unique template name")
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text=_("URL-friendly identifier")
    )
    template_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_TRANSACTIONAL,
        db_index=True,
        help_text=_("Type of email template")
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        help_text=_("Template status")
    )
    
    # Template Content
    subject = models.CharField(
        max_length=255,
        help_text=_("Email subject line (supports Jinja2 variables)")
    )
    mjml_content = models.TextField(
        help_text=_("MJML template source code")
    )
    html_content = models.TextField(
        blank=True,
        help_text=_("Compiled HTML content (auto-generated from MJML)")
    )
    text_content = models.TextField(
        blank=True,
        help_text=_("Plain text fallback content")
    )
    
    # Template Variables
    variables_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("JSON schema for template variables validation")
    )
    sample_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Sample data for template preview")
    )
    
    # Versioning
    version = models.PositiveIntegerField(
        default=1,
        help_text=_("Template version number")
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether this is the default version")
    )
    parent_template = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='versions',
        help_text=_("Parent template for versioning")
    )
    
    # A/B Testing
    ab_test_enabled = models.BooleanField(
        default=False,
        help_text=_("Whether A/B testing is enabled for this template")
    )
    ab_test_variant_id = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Variant ID if this is an A/B test variant")
    )
    
    # Usage Statistics
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
