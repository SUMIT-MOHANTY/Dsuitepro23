"""
Analytics Models for Enterprise LMS
Provides data models for reporting, analytics, audit logging, and compliance.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from enum import Enum

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import BaseModel

User = get_user_model()


class EventType(models.TextChoices):
    """Structured event types for UserActivity logging."""
    LOGIN = 'login', 'Login'
    LOGOUT = 'logout', 'Logout'
    ENROLL = 'enroll', 'Enroll'
    COMPLETE = 'complete', 'Complete'
    ASSESS = 'assess', 'Assess'
    GRADE = 'grade', 'Grade'
    CERTIFY = 'certify', 'Certify'
    ADMIN_ACTION = 'admin_action', 'Admin Action'
    VIEW = 'view', 'View'
    DOWNLOAD = 'download', 'Download'
    CREATE = 'create', 'Create'
    UPDATE = 'update', 'Update'
    DELETE = 'delete', 'Delete'


class AuditAction(models.TextChoices):
    """Administrative action types for AuditLog."""
    CREATE = 'create', 'Create'
    UPDATE = 'update', 'Update'
    DELETE = 'delete', 'Delete'
    IMPERSONATE = 'impersonate', 'Impersonate'
    EXPORT = 'export', 'Export'
    GRANT_ACCESS = 'grant_access', 'Grant Access'
    REVOKE_ACCESS = 'revoke_access', 'Revoke Access'
    MODIFY_PERMISSIONS = 'modify_permissions', 'Modify Permissions'
    BULK_OPERATION = 'bulk_operation', 'Bulk Operation'


class ReportStatus(models.TextChoices):
    """Report generation status."""
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    EXPIRED = 'expired', 'Expired'


class ReportType(models.TextChoices):
    """Types of reports that can be generated."""
    GDPR_EXPORT = 'gdpr_export', 'GDPR Data Export'
    SOC2_AUDIT = 'soc2_audit', 'SOC 2 Audit Log'
    LEARNER_PROGRESS = 'learner_progress', 'Learner Progress Report'
    COURSE_ANALYTICS = 'course_analytics', 'Course Analytics'
    SYSTEM_HEALTH = 'system_health', 'System Health Report'
    USER_ACTIVITY = 'user_activity', 'User Activity Report'
    ENROLLMENT_SUMMARY = 'enrollment_summary', 'Enrollment Summary'
    ASSESSMENT_RESULTS = 'assessment_results', 'Assessment Results'


class UserActivity(BaseModel):
    """
    Immutable log of all user activities with structured event types.
    Supports GDPR compliance with data retention policies.
    """
    
    # Event classification
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        db_index=True,
        help_text="Type of activity event"
    )
    
    # Actor information
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
        help_text="User who performed the activity"
    )
    actor_email = models.EmailField(
        blank=True,
        db_index=True,
        help_text="Email of actor (preserved for deleted users)"
    )
    actor_role = models.CharField(
        max_length=50,
        blank=True,
        help_text="Role of actor at time of event"
    )
    
    # Target information
    target_type = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Type of entity affected (e.g., course, lesson, quiz, user)"
    )
    target_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of the affected entity"
    )
    target_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable name of target"
    )
    
    # Event details
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured event metadata"
    )
    before_state = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON representation of entity before change (for updates)"
    )
    after_state = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON representation of entity after change (for updates)"
    )
    
    # Request context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
        help_text="IP address of the user"
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
    session_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Session identifier"
    )
    
    # Timing
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the event occurred"
    )
    
    # Data retention for GDPR
    pii_anonymized = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether PII has been anonymized"
    )
    anonymized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When PII was anonymized"
    )
    retention_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date when this record can be permanently deleted"
    )
    
    class Meta:
        verbose_name = "User Activity"
        verbose_name_plural = "User Activities"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor', 'event_type', 'timestamp']),
            models.Index(fields=['target_type', 'target_id', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(fields=['pii_anonymized', 'retention_until']),
            models.Index(fields=['timestamp', 'pii_anonymized']),
        ]
    
    def __str__(self):
        actor = self.actor_email or (self.actor.email if self.actor else 'Anonymous')
        return f"{self.event_type} by {actor} at {self.timestamp}"
    
    def anonymize_pii(self):
        """
        Anonymize PII fields for GDPR compliance.
        Hashes email, clears IP, and marks as anonymized.
        """
        if not self.pii_anonymized:
            # Hash the email for anonymization
            if self.actor_email:
                self.actor_email = hashlib.sha256(
                    self.actor_email.encode('utf-8')
                ).hexdigest()[:32]
            
            # Clear IP address
            self.ip_address = None
            
            # Remove PII from metadata
            if self.metadata:
                pii_keys = ['email', 'phone', 'address', 'full_name', 'first_name', 'last_name']
                for key in pii_keys:
                    if key in self.metadata:
                        del self.metadata[key]
            
            self.pii_anonymized = True
            self.anonymized_at = timezone.now()
            self.save(update_fields=[
                'actor_email', 'ip_address', 'metadata',
                'pii_anonymized', 'anonymized_at', 'updated_at'
            ])
    
    @classmethod
    def log_activity(cls, event_type, actor=None, target_type='', target_id=None,
                     target_name='', metadata=None, before_state=None, after_state=None,
                     ip_address=None, user_agent='', request_method='', request_path='',
                     session_id=''):
        """
        Factory method to create a user activity log entry.
        """
        if metadata is None:
            metadata = {}
        
        return cls.objects.create(
            event_type=event_type,
            actor=actor,
            actor_email=actor.email if actor else '',
            actor_role=actor.role if actor and hasattr(actor, 'role') else '',
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            metadata=metadata,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            session_id=session_id,
            timestamp=timezone.now(),
            retention_until=timezone.now() + timedelta(days=7*365)  # 7 years
        )


class AuditLog(BaseModel):
    """
    Administrative audit log for sensitive operations.
    Requires justification for sensitive actions.
    """
    
    # Action details
    action = models.CharField(
        max_length=50,
        choices=AuditAction.choices,
        db_index=True,
        help_text="Type of administrative action performed"
    )
    
    # Actor information
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="Administrator who performed the action"
    )
    actor_email = models.EmailField(
        blank=True,
        help_text="Email of actor (preserved for deleted users)"
    )
    actor_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of administrator"
    )
    
    # Target information
    resource_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of resource affected"
    )
    resource_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="ID of affected resource"
    )
    resource_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable name of resource"
    )
    
    # Change tracking
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON diff of changes made"
    )
    before_state = models.JSONField(
        null=True,
        blank=True,
        help_text="Complete state before change"
    )
    after_state = models.JSONField(
        null=True,
        blank=True,
        help_text="Complete state after change"
    )
    
    # Justification (required for sensitive actions)
    justification = models.TextField(
        blank=True,
        help_text="Reason for performing this action"
    )
    is_sensitive = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this is a sensitive action requiring justification"
    )
    
    # Outcome
    outcome = models.CharField(
        max_length=50,
        default='success',
        db_index=True,
        help_text="Outcome of the action (success/failure/blocked)"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if action failed"
    )
    
    # Request context
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    request_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Request correlation ID"
    )
    
    # Timing
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the action was performed"
    )
    
    # Data retention
    retention_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date when this record can be archived"
    )
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor', 'action', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id', 'timestamp']),
            models.Index(fields=['action', 'outcome', 'timestamp']),
            models.Index(fields=['is_sensitive', 'timestamp']),
            models.Index(fields=['request_id', 'timestamp']),
        ]
    
    def __str__(self):
        actor = self.actor_email or (self.actor.email if self.actor else 'System')
        return f"{self.action} on {self.resource_type} by {actor}"
    
    def clean(self):
        """Validate that sensitive actions have justification."""
        from django.core.exceptions import ValidationError
        if self.is_sensitive and not self.justification:
            raise ValidationError({
                'justification': 'Justification is required for sensitive administrative actions.'
            })
    
    def save(self, *args, **kwargs):
        self.clean()
        if not self.retention_until:
            # Audit logs kept for 10 years
            self.retention_until = timezone.now() + timedelta(days=10*365)
        super().save(*args, **kwargs)
    
    @classmethod
    def log_admin_action(cls, action, actor, resource_type, resource_id,
                         resource_name='', changes=None, before_state=None,
                         after_state=None, justification='', is_sensitive=False,
                         outcome='success', error_message='', actor_ip=None,
                         user_agent='', request_id=''):
        """
        Factory method to create an audit log entry.
        """
        if changes is None:
            changes = {}
        
        return cls.objects.create(
            action=action,
            actor=actor,
            actor_email=actor.email if actor else 'system@lms.local',
            actor_ip=actor_ip,
            resource_type=resource_type,
            resource_id=str(resource_id),
            resource_name=resource_name,
            changes=changes,
            before_state=before_state,
            after_state=after_state,
            justification=justification,
            is_sensitive=is_sensitive,
            outcome=outcome,
            error_message=error_message,
            user_agent=user_agent,
            request_id=request_id,
            timestamp=timezone.now()
        )


class ReportJob(BaseModel):
    """
    Async report generation job with secure delivery.
    """
    
    # Report configuration
    report_type = models.CharField(
        max_length=50,
        choices=ReportType.choices,
        help_text="Type of report to generate"
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this report"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of report contents"
    )
    
    # Requester
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='report_jobs',
        help_text="User who requested this report"
    )
    
    # Report parameters
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Report generation parameters"
    )
    filters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Filters applied to the report"
    )
    date_range_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of date range for report"
    )
    date_range_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of date range for report"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True,
        help_text="Current status of report generation"
    )
    progress_percent = models.IntegerField(
        default=0,
        help_text="Report generation progress (0-100)"
    )
    
    # Output
    file_format = models.CharField(
        max_length=10,
        default='csv',
        help_text="Output file format (csv, pdf, xlsx, json)"
    )
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of generated file in bytes"
    )
    file_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Secure download URL for the report"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the download link expires"
    )
    
    # Error handling
    error_message = models.TextField(
        blank=True,
        help_text="Error message if generation failed"
    )
    retry_count = models.IntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    
    # Timing
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When report generation started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When report generation completed"
    )
    
    # Notification
    notify_on_complete = models.BooleanField(
        default=True,
        help_text="Whether to notify user when complete"
    )
    notification_sent = models.BooleanField(
        default=False,
        help_text="Whether completion notification was sent"
    )
    
    class Meta:
        verbose_name = "Report Job"
        verbose_name_plural = "Report Jobs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['requested_by', 'status', 'created_at']),
            models.Index(fields=['report_type', 'status', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['expires_at', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def mark_started(self):
        """Mark report as started processing."""
        self.status = ReportStatus.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_completed(self, file_url='', file_size=0):
        """Mark report as completed with download URL."""
        self.status = ReportStatus.COMPLETED
        self.progress_percent = 100
        self.completed_at = timezone.now()
        self.file_url = file_url
        self.file_size = file_size
        self.expires_at = timezone.now() + timedelta(days=7)
        self.save(update_fields=[
            'status', 'progress_percent', 'completed_at',
            'file_url', 'file_size', 'expires_at', 'updated_at'
        ])
    
    def mark_failed(self, error_message):
        """Mark report as failed with error message."""
        self.status = ReportStatus.FAILED
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    
    def update_progress(self, percent):
        """Update report generation progress."""
        self.progress_percent = min(max(percent, 0), 100)
        self.save(update_fields=['progress_percent', 'updated_at'])
    
    def is_expired(self):
        """Check if the download link has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def can_download(self):
        """Check if report is available for download."""
        return (
            self.status == ReportStatus.COMPLETED and
            self.file_url and
            not self.is_expired()
        )


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
            timestamp=timezone.now(),
            response_time_ms=response_time_ms
        )


class AuditLogExport(BaseModel):
    """
    Export job for audit logs with compliance controls.
    """
    
    EXPORT_FORMAT_CHOICES = [
        ('json', 'JSON'),
        ('csv', 'CSV'),
        ('pdf', 'PDF'),
    ]
    
    EXPORT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    # Export configuration
    start_date = models.DateTimeField(
        help_text="Start date for export range"
    )
    end_date = models.DateTimeField(
        help_text="End date for export range"
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
    
    # Requester
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='audit_exports',
        help_text="User who requested this export"
    )
    
    # Export settings
    format = models.CharField(
        max_length=10,
        choices=EXPORT_FORMAT_CHOICES,
        default='json',
        help_text="Export file format"
    )
    include_verification = models.BooleanField(
        default=True,
        help_text="Include hash chain verification in export"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=EXPORT_STATUS_CHOICES,
        default='pending',
        help_text="Current export status"
    )
    
    # Output
    file = models.FileField(
        upload_to='audit_exports/%Y/%m/',
        null=True,
        blank=True,
        help_text="Exported audit log file"
    )
    record_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of records exported"
    )
    
    # Compliance
    justification = models.TextField(
        help_text="Business justification for this export"
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_audit_exports',
        help_text="Administrator who approved this export"
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the export was approved"
    )
    
    class Meta:
        verbose_name = "Audit Log Export"
        verbose_name_plural = "Audit Log Exports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Export {self.start_date} to {self.end_date} ({self.status})"


class ABTestCampaign(BaseModel):
    """
    A/B test campaign for analytics experiments.
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    name = models.CharField(
        max_length=255,
        help_text="Campaign name"
    )
    description = models.TextField(
        blank=True,
        help_text="Campaign description"
    )
    hypothesis = models.TextField(
        blank=True,
        help_text="Test hypothesis"
    )
    
    # Targeting
    target_segment = models.JSONField(
        default=dict,
        blank=True,
        help_text="User segment criteria"
    )
    traffic_allocation = models.IntegerField(
        default=100,
        help_text="Percentage of traffic to include"
    )
    
    # Timing
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the campaign starts"
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the campaign ends"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text="Current campaign status"
    )
    
    # Metrics
    primary_metric = models.CharField(
        max_length=100,
        help_text="Primary success metric"
    )
    minimum_sample_size = models.IntegerField(
        default=100,
        help_text="Minimum participants per variant"
    )
    
    class Meta:
        verbose_name = "A/B Test Campaign"
        verbose_name_plural = "A/B Test Campaigns"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class ABTestVariant(BaseModel):
    """
    Variant for A/B testing.
    """
    
    campaign = models.ForeignKey(
        ABTestCampaign,
        on_delete=models.CASCADE,
        related_name='variants',
        help_text="Parent campaign"
    )
    name = models.CharField(
        max_length=100,
        help_text="Variant name"
    )
    description = models.TextField(
        blank=True,
        help_text="Variant description"
    )
    traffic_percentage = models.IntegerField(
        default=50,
        help_text="Percentage of traffic for this variant"
    )
    
    # Configuration
    configuration = models.JSONField(
        default=dict,
        help_text="Variant-specific configuration"
    )
    is_control = models.BooleanField(
        default=False,
        help_text="Whether this is the control variant"
    )
    
    # Metrics
    participants = models.IntegerField(
        default=0,
        help_text="Number of participants"
    )
    conversions = models.IntegerField(
        default=0,
        help_text="Number of conversions"
    )
    
    class Meta:
        verbose_name = "A/B Test Variant"
        verbose_name_plural = "A/B Test Variants"
        unique_together = ['campaign', 'name']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.name}"
    
    @property
    def conversion_rate(self):
        """Calculate conversion rate."""
        if self.participants == 0:
            return 0.0
        return (self.conversions / self.participants) * 100


class ABTestRecipientAssignment(BaseModel):
    """
    Tracks which variant a user was assigned to.
    """
    
    campaign = models.ForeignKey(
        ABTestCampaign,
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="Parent campaign"
    )
    variant = models.ForeignKey(
        ABTestVariant,
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="Assigned variant"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ab_test_assignments',
        help_text="Assigned user"
    )
    
    # Assignment
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the assignment was made"
    )
    converted = models.BooleanField(
        default=False,
        help_text="Whether the user converted"
    )
    converted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the conversion occurred"
    )
    
    class Meta:
        verbose_name = "A/B Test Assignment"
        verbose_name_plural = "A/B Test Assignments"
        unique_together = ['campaign', 'user']
    
    def __str__(self):
        return f"{self.user.email} -> {self.variant.name}"


class UserActivityLog(BaseModel):
    """
    Legacy model for tracking user activities across the platform.
    Kept for backward compatibility - new code should use UserActivity.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='legacy_activity_logs',
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
        verbose_name = "User Activity Log (Legacy)"
        verbose_name_plural = "User Activity Logs (Legacy)"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.action} at {self.created_at}"
