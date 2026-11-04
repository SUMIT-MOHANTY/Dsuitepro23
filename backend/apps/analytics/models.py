"""
Analytics Models for Enterprise LMS
Provides data models for reporting and analytics.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import BaseModel

User = get_user_model()


class UserActivityLog(BaseModel):
    """
    Model for tracking user activities across the platform.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activity_logs',
        help_text="User who performed the activity"
    )
    action = models.CharField(
        max_length=100,
        help_text="Type of activity performed"
    )
    entity_type = models.CharField(
        max_length=50,
        help_text="Type of entity affected (e.g., course, lesson, quiz)"
    )
    entity_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID of the affected entity"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional activity metadata"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )

    class Meta:
        verbose_name = "User Activity Log"
        verbose_name_plural = "User Activity Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.action} at {self.created_at}"


class SecurityAuditLog(BaseModel):
    """
    Tamper-evident security audit log for SOC 2 compliance.
    Tracks all security events with hash chain integrity verification.
    """
    
    # Event Categories
    CATEGORY_AUTHN = 'authentication'
    CATEGORY_AUTHZ = 'authorization'
    CATEGORY_DATA_ACCESS = 'data_access'
    CATEGORY_SYSTEM = 'system'
    CATEGORY_IMPERSONATION = 'impersonation'
    CATEGORY_SESSION = 'session'
    
    CATEGORY_CHOICES = [
        (CATEGORY_AUTHN, 'Authentication'),
        (CATEGORY_AUTHZ, 'Authorization'),
        (CATEGORY_DATA_ACCESS, 'Data Access'),
        (CATEGORY_SYSTEM, 'System'),
        (CATEGORY_IMPERSONATION, 'Impersonation'),
        (CATEGORY_SESSION, 'Session Management'),
    ]
    
    # Severity Levels
    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_CRITICAL = 'critical'
    
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, 'Info'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]
    
    # Event Types
    EVENT_LOGIN_SUCCESS = 'login_success'
    EVENT_LOGIN_FAILURE = 'login_failure'
    EVENT_LOGOUT = 'logout'
    EVENT_TOKEN_REFRESH = 'token_refresh'
    EVENT_MFA_CHALLENGE = 'mfa_challenge'
    EVENT_MFA_SUCCESS = 'mfa_success'
    EVENT_MFA_FAILURE = 'mfa_failure'
    EVENT_ACCESS_DENIED = 'access_denied'
    EVENT_ACCESS_GRANTED = 'access_granted'
    EVENT_BULK_EXPORT = 'bulk_export'
    EVENT_PII_QUERY = 'pii_query'
    EVENT_IMPERSONATION_START = 'impersonation_start'
    EVENT_IMPERSONATION_END = 'impersonation_end'
    EVENT_SESSION_CREATED = 'session_created'
    EVENT_SESSION_REVOKED = 'session_revoked'
    EVENT_SESSION_EXPIRED = 'session_expired'
    EVENT_PASSWORD_CHANGE = 'password_change'
    EVENT_PASSWORD_RESET = 'password_reset'
    EVENT_ROLE_ASSIGNED = 'role_assigned'
    EVENT_ROLE_REVOKED = 'role_revoked'
    
    event_type = models.CharField(
        max_length=50,
        help_text="Type of security event"
    )
    event_category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_SYSTEM,
        help_text="Category of the security event"
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        help_text="Severity level of the event"
    )
    
    # Actor Information
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_audit_logs',
        help_text="User who performed the action"
    )
    actor_email = models.EmailField(
        blank=True,
        help_text="Email of the actor (for deleted users)"
    )
    
    # Target Information
    target_resource = models.CharField(
        max_length=255,
        blank=True,
        help_text="Resource being accessed or modified"
    )
    target_resource_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="ID of the target resource"
    )
    
    # Event Details
    outcome = models.CharField(
        max_length=50,
        help_text="Outcome of the event (success/failure/blocked)"
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason for the outcome (e.g., permission denied)"
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional event details"
    )
    
    # Request Context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    request_method = models.CharField(
        max_length=10,
        blank=True,
        help_text="HTTP method"
    )
    request_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Request path"
    )
    
    # Timing
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the event occurred"
    )
    response_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Response time in milliseconds"
    )
    
    # Tamper-evident Hash Chain
    previous_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Hash of the previous log entry"
    )
    current_hash = models.CharField(
        max_length=64,
        help_text="Hash of this log entry"
    )
    hash_verified = models.BooleanField(
        default=False,
        help_text="Whether the hash chain has been verified"
    )
    
    class Meta:
        verbose_name = "Security Audit Log"
        verbose_name_plural = "Security Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_category', 'severity', 'timestamp']),
            models.Index(fields=['actor_user', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['outcome', 'timestamp']),
        ]
    
    def __str__(self):
        actor = self.actor_email or (self.actor_user.email if self.actor_user else 'Anonymous')
        return f"{self.event_type} by {actor} at {self.timestamp}"
    
    def calculate_hash(self):
        """
        Calculate SHA-256 hash of this log entry.
        Includes all fields except current_hash and hash_verified.
        """
        data = {
            'event_type': self.event_type,
            'event_category': self.event_category,
            'severity': self.severity,
            'actor_user_id': str(self.actor_user_id) if self.actor_user_id else None,
            'actor_email': self.actor_email,
            'target_resource': self.target_resource,
            'target_resource_id': self.target_resource_id,
            'outcome': self.outcome,
            'reason': self.reason,
            'details': self.details,
            'ip_address': str(self.ip_address) if self.ip_address else None,
            'user_agent': self.user_agent,
            'request_method': self.request_method,
            'request_path': self.request_path,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'response_time_ms': self.response_time_ms,
            'previous_hash': self.previous_hash,
        }
        
        # Sort keys for consistent hashing
        json_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_data.encode('utf-8')).hexdigest()
    
    def save(self, *args, **kwargs):
        """
        Override save to compute hash chain.
        """
        # Get previous hash if this is a new entry
        if not self.pk:
            try:
                previous_log = SecurityAuditLog.objects.order_by('-timestamp').first()
                self.previous_hash = previous_log.current_hash if previous_log else '0' * 64
            except Exception:
                self.previous_hash = '0' * 64
        
        # Calculate current hash before saving
        self.current_hash = self.calculate_hash()
        
        super().save(*args, **kwargs)
    
    def verify_integrity(self):
        """
        Verify the integrity of this log entry.
        Returns True if the hash matches the calculated value.
        """
        expected_hash = self.calculate_hash()
        return self.current_hash == expected_hash
    
    @classmethod
    def verify_chain_integrity(cls, start_from=None):
        """
        Verify the integrity of the entire hash chain.
        Returns a tuple (is_valid, broken_at_id) where broken_at_id is the
        ID of the first log entry with a broken chain, or None if valid.
        """
        queryset = cls.objects.all().order_by('timestamp')
        if start_from:
            queryset = queryset.filter(timestamp__gte=start_from)
        
        previous_hash = '0' * 64
        
        for log in queryset:
            # Verify current hash
            if not log.verify_integrity():
                return False, log.id
            
            # Verify chain link
            if log.previous_hash != previous_hash:
                return False, log.id
            
            previous_hash = log.current_hash
        
        return True, None
    
    @classmethod
    def log_event(cls, event_type, event_category, severity, actor_user=None,
                  actor_email='', target_resource='', target_resource_id='',
                  outcome='success', reason='', details=None, ip_address=None,
                  user_agent='', request_method='', request_path='',
                  response_time_ms=None):
        """
        Factory method to create a security audit log entry.
        """
        if details is None:
            details = {}
        
        return cls.objects.create(
            event_type=event_type,
            event_category=event_category,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_email or (actor_user.email if actor_user else ''),
            target_resource=target_resource,
            target_resource_id=target_resource_id,
            outcome=outcome,
            reason=reason,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            response_time_ms=response_time_ms
        )


class AuditLogExport(BaseModel):
    """
    Model for tracking audit log exports.
    Required for compliance - tracks who exported audit data and when.
    """
    
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    FORMAT_CSV = 'csv'
    FORMAT_JSON = 'json'
    FORMAT_PDF = 'pdf'
    
    FORMAT_CHOICES = [
        (FORMAT_CSV, 'CSV'),
        (FORMAT_JSON, 'JSON'),
        (FORMAT_PDF, 'PDF'),
    ]
    
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='audit_exports',
        help_text="User who requested the export"
    )
    
    # Export Parameters
    start_date = models.DateTimeField(
        help_text="Start of export date range"
    )
    end_date = models.DateTimeField(
        help_text="End of export date range"
    )
    event_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Filter by event categories"
    )
    severity_levels = models.JSONField(
        default=list,
        blank=True,
        help_text="Filter by severity levels"
    )
    
    # Export Configuration
    export_format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        default=FORMAT_CSV,
        help_text="Export file format"
    )
    
    # Export Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Export status"
    )
    
    # Results
    file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to exported file"
    )
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of exported file in bytes"
    )
    record_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of records exported"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if export failed"
    )
    
    # Timestamps
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When export processing started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When export completed"
    )
    
    class Meta:
        verbose_name = "Audit Log Export"
        verbose_name_plural = "Audit Log Exports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Export by {self.requested_by.email} ({self.start_date} to {self.end_date})"


# =============================================================================
# Email A/B Testing Models
# =============================================================================

class ABTestCampaign(BaseModel):
    """
    Model for managing email A/B test campaigns.
    Tracks campaign configuration, status, and overall performance metrics.
    """
    
    # Campaign Status
    STATUS_DRAFT = 'draft'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_RUNNING = 'running'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    # Test Type
    TEST_TYPE_SUBJECT = 'subject'
    TEST_TYPE_CONTENT = 'content'
    TEST_TYPE_SENDER = 'sender'
    TEST_TYPE_TIMING = 'timing'
    TEST_TYPE_TEMPLATE = 'template'
    
    TEST_TYPE_CHOICES = [
        (TEST_TYPE_SUBJECT, 'Subject Line'),
        (TEST_TYPE_CONTENT, 'Email Content'),
        (TEST_TYPE_SENDER, 'Sender Name/Email'),
        (TEST_TYPE_TIMING, 'Send Timing'),
        (TEST_TYPE_TEMPLATE, 'Template Design'),
    ]
    
    # Winner Selection Criteria
    WINNER_CRITERIA_OPENS = 'opens'
    WINNER_CRITERIA_CLICKS = 'clicks'
    WINNER_CRITERIA_CONVERSIONS = 'conversions'
    WINNER_CRITERIA_REVENUE = 'revenue'
    
    WINNER_CRITERIA_CHOICES = [
        (WINNER_CRITERIA_OPENS, 'Open Rate'),
        (WINNER_CRITERIA_CLICKS, 'Click Rate'),
        (WINNER_CRITERIA_CONVERSIONS, 'Conversions'),
        (WINNER_CRITERIA_REVENUE, 'Revenue'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Campaign Info
    name = models.CharField(
        max_length=255,
        help_text="Name of the A/B test campaign"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the campaign and test hypothesis"
    )
    
    # Test Configuration
    test_type = models.CharField(
        max_length=50,
        choices=TEST_TYPE_CHOICES,
        default=TEST_TYPE_SUBJECT,
        help_text="What aspect of the email is being tested"
    )
    
    # Winner Selection
    winner_criteria = models.CharField(
        max_length=50,
        choices=WINNER_CRITERIA_CHOICES,
        default=WINNER_CRITERIA_OPENS,
        help_text="Metric used to determine the winning variant"
    )
    winner_selection_delay_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours to wait before selecting winner (minimum test duration)"
    )
    winner_confidence_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.95,
        help_text="Statistical confidence threshold for winner selection (0.0-1.0)"
    )
    
    # Sample Size
    test_percentage = models.PositiveIntegerField(
        default=20,
        help_text="Percentage of recipients to include in the test phase"
    )
    
    # Status
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        help_text="Current status of the campaign"
    )
    
    # Scheduling
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the campaign should start"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the campaign actually started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the campaign completed"
    )
    winner_declared_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the winning variant was determined"
    )
    
    # Winner Reference
    winning_variant = models.ForeignKey(
        'ABTestVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='won_campaigns',
        help_text="The winning variant of this test"
    )
    
    # Target Audience
    target_segment = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON criteria for target audience segmentation"
    )
    recipient_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of recipients in the campaign"
    )
    
    # Created by
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ab_test_campaigns',
        help_text="User who created this campaign"
    )
    
    class Meta:
        verbose_name = "A/B Test Campaign"
        verbose_name_plural = "A/B Test Campaigns"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['test_type', 'status']),
            models.Index(fields=['created_by', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_test_type_display()})"
    
    def can_start(self):
        """Check if the campaign is ready to start."""
        if self.status != self.STATUS_SCHEDULED:
            return False
        if not self.scheduled_at:
            return False
        return timezone.now() >= self.scheduled_at
    
    def get_test_duration(self):
        """Get the duration of the test in hours."""
        if not self.started_at:
            return 0
        end_time = self.winner_declared_at or self.completed_at or timezone.now()
        duration = end_time - self.started_at
        return duration.total_seconds() / 3600
    
    def is_winner_selection_ready(self):
        """Check if enough time has passed to select a winner."""
        if not self.started_at:
            return False
        min_end_time = self.started_at + timedelta(hours=self.winner_selection_delay_hours)
        return timezone.now() >= min_end_time


class ABTestVariant(BaseModel):
    """
    Model for individual A/B test variants.
    Tracks performance metrics for each variant in a campaign.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Relationship to Campaign
    campaign = models.ForeignKey(
        ABTestCampaign,
        on_delete=models.CASCADE,
        related_name='variants',
        help_text="The A/B test campaign this variant belongs to"
    )
    
    # Variant Info
    name = models.CharField(
        max_length=100,
        help_text="Name of the variant (e.g., 'Variant A', 'Control')"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what makes this variant different"
    )
    
    # Variant Content (varies by test type)
    subject_line = models.CharField(
        max_length=255,
        blank=True,
        help_text="Subject line for this variant (for subject line tests)"
    )
    sender_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Sender name for this variant"
    )
    sender_email = models.EmailField(
        blank=True,
        help_text="Sender email for this variant"
    )
    content_html = models.TextField(
        blank=True,
        help_text="HTML content for this variant (for content tests)"
    )
    content_text = models.TextField(
        blank=True,
        help_text="Plain text content for this variant"
    )
    template_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Template ID for this variant (for template tests)"
    )
    send_time_offset_hours = models.IntegerField(
        default=0,
        help_text="Hours to offset send time (for timing tests)"
    )
    
    # Traffic Allocation
    traffic_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        help_text="Percentage of test traffic allocated to this variant"
    )
    
    # Performance Metrics
    recipients_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of recipients for this variant"
    )
    delivered_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of successfully delivered emails"
    )
    bounced_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of bounced emails"
    )
    opened_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of unique opens"
    )
    clicked_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of unique clicks"
    )
    unsubscribed_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of unsubscribes"
    )
    complained_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of spam complaints"
    )
    converted_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of conversions attributed to this variant"
    )
    revenue_generated = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        help_text="Revenue generated from this variant"
    )
    
    # Calculated Rates (stored for performance)
    open_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Open rate as decimal (e.g., 0.25 for 25%)"
    )
    click_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Click rate as decimal"
    )
    click_to_open_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Click-to-open rate (clicks/opens)"
    )
    bounce_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Bounce rate as decimal"
    )
    unsubscribe_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Unsubscribe rate as decimal"
    )
    complaint_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Complaint rate as decimal"
    )
    conversion_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Conversion rate as decimal"
    )
    
    # Statistical Analysis
    is_winner = models.BooleanField(
        default=False,
        help_text="Whether this variant was selected as the winner"
    )
    confidence_level = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Statistical confidence that this variant is better than control"
    )
    lift_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Percentage improvement over control variant"
    )
    
    # Ordering
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for displaying variants"
    )
    
    class Meta:
        verbose_name = "A/B Test Variant"
        verbose_name_plural = "A/B Test Variants"
        ordering = ['campaign', 'sort_order', 'created_at']
        indexes = [
            models.Index(fields=['campaign', 'is_winner']),
            models.Index(fields=['campaign', 'sort_order']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'name'],
                name='unique_variant_name_per_campaign'
            ),
        ]
    
    def __str__(self):
        return f"{self.campaign.name} - {self.name}"
    
    def calculate_rates(self):
        """Calculate and update all performance rates."""
        if self.recipients_count > 0:
            self.open_rate = self.opened_count / self.recipients_count
            self.click_rate = self.clicked_count / self.recipients_count
            self.bounce_rate = self.bounced_count / self.recipients_count
            self.unsubscribe_rate = self.unsubscribed_count / self.recipients_count
            self.complaint_rate = self.complained_count / self.recipients_count
            self.conversion_rate = self.converted_count / self.recipients_count
        
        if self.opened_count > 0:
            self.click_to_open_rate = self.clicked_count / self.opened_count
        
        self.save(update_fields=[
            'open_rate', 'click_rate', 'click_to_open_rate',
            'bounce_rate', 'unsubscribe_rate', 'complaint_rate', 'conversion_rate'
        ])
    
    def get_rate(self, metric):
        """Get a specific rate by metric name."""
        rate_map = {
            'opens': self.open_rate,
            'clicks': self.click_rate,
            'conversions': self.conversion_rate,
            'revenue': self.revenue_generated,
        }
        return rate_map.get(metric, self.open_rate)


class ABTestRecipientAssignment(BaseModel):
    """
    Model for tracking which variant each recipient was assigned to.
    Ensures consistent variant assignment and tracks individual recipient metrics.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Relationships
    campaign = models.ForeignKey(
        ABTestCampaign,
        on_delete=models.CASCADE,
        related_name='recipient_assignments',
        help_text="The A/B test campaign"
    )
    variant = models.ForeignKey(
        ABTestVariant,
        on_delete=models.CASCADE,
        related_name='recipient_assignments',
        help_text="The variant assigned to this recipient"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ab_test_assignments',
        help_text="The recipient user"
    )
    
    # Assignment Info
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this assignment was made"
    )
    is_control_group = models.BooleanField(
        default=False,
        help_text="Whether this recipient is in the control group"
    )
    
    # Engagement Tracking
    email_sent = models.BooleanField(
        default=False,
        help_text="Whether the email was sent"
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email was sent"
    )
    delivered = models.BooleanField(
        default=False,
        help_text="Whether the email was delivered"
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email was delivered"
    )
    opened = models.BooleanField(
        default=False,
        help_text="Whether the email was opened"
    )
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email was first opened"
    )
    open_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of opens"
    )
    clicked = models.BooleanField(
        default=False,
        help_text="Whether any link was clicked"
    )
    clicked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the first click occurred"
    )
    click_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of clicks"
    )
    converted = models.BooleanField(
        default=False,
        help_text="Whether the recipient converted"
    )
    converted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the conversion occurred"
    )
    conversion_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        help_text="Value of the conversion"
    )
    
    # Device/Client Info
    opened_on_device = models.CharField(
        max_length=50,
        blank=True,
        help_text="Device type used to open (desktop, mobile, tablet)"
    )
    opened_email_client = models.CharField(
        max_length=100,
        blank=True,
        help_text="Email client used to open"
    )
    
    class Meta:
        verbose_name = "A/B Test Recipient Assignment"
        verbose_name_plural = "A/B Test Recipient Assignments"
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['campaign', 'variant']),
            models.Index(fields=['user', 'campaign']),
            models.Index(fields=['campaign', 'opened']),
            models.Index(fields=['campaign', 'clicked']),
            models.Index(fields=['campaign', 'converted']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'user'],
                name='unique_user_assignment_per_campaign'
            ),
        ]
    
    def __str__(self):
        return f"{self.user.email} -> {self.variant.name}"
    
    def record_open(self, device_type='', email_client=''):
        """Record an email open event."""
        from django.utils import timezone
        
        if not self.opened:
            self.opened = True
            self.opened_at = timezone.now()
            self.opened_on_device = device_type
            self.opened_email_client = email_client
        
        self.open_count += 1
        self.save(update_fields=[
            'opened', 'opened_at', 'open_count',
            'opened_on_device', 'opened_email_client'
        ])
        
        # Update variant metrics
        self.variant.opened_count = ABTestRecipientAssignment.objects.filter(
            variant=self.variant,
            opened=True
        ).count()
        self.variant.calculate_rates()
    
    def record_click(self):
        """Record a link click event."""
        from django.utils import timezone
        
        if not self.clicked:
            self.clicked = True
            self.clicked_at = timezone.now()
        
        self.click_count += 1
        self.save(update_fields=['clicked', 'clicked_at', 'click_count'])
        
        # Update variant metrics
        self.variant.clicked_count = ABTestRecipientAssignment.objects.filter(
            variant=self.variant,
            clicked=True
        ).count()
        self.variant.calculate_rates()
    
    def record_conversion(self, value=0.00):
        """Record a conversion event."""
        from django.utils import timezone
        
        if not self.converted:
            self.converted = True
            self.converted_at = timezone.now()
            self.conversion_value = value
            self.save(update_fields=['converted', 'converted_at', 'conversion_value'])
            
            # Update variant metrics
            self.variant.converted_count = ABTestRecipientAssignment.objects.filter(
                variant=self.variant,
                converted=True
            ).count()
            self.variant.revenue_generated = ABTestRecipientAssignment.objects.filter(
                variant=self.variant,
                converted=True
            ).aggregate(
                total=models.Sum('conversion_value')
            )['total'] or 0
            self.variant.calculate_rates()
