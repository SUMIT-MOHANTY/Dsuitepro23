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
    
    # Timing
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the action occurred"
    )
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['is_sensitive', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.action} on {self.resource_type} by {self.actor_email}"
    
    @classmethod
    def log_action(cls, action, actor, resource_type, resource_id, resource_name='',
                   changes=None, before_state=None, after_state=None, justification='',
                   is_sensitive=False, actor_ip=None):
        """
        Factory method to create an audit log entry.
        """
        if changes is None:
            changes = {}
        
        return cls.objects.create(
            action=action,
            actor=actor,
            actor_email=actor.email if actor else '',
            actor_ip=actor_ip,
            resource_type=resource_type,
            resource_id=str(resource_id),
            resource_name=resource_name,
            changes=changes,
            before_state=before_state,
            after_state=after_state,
            justification=justification,
            is_sensitive=is_sensitive,
            timestamp=timezone.now()
        )


class ReportJob(BaseModel):
    """
    Background report generation job tracking.
    """
    
    # Report metadata
    report_type = models.CharField(
        max_length=50,
        choices=ReportType.choices,
        db_index=True,
        help_text="Type of report being generated"
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this report"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the report"
    )
    
    # Requester
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='report_jobs',
        help_text="User who requested this report"
    )
    
    # Parameters
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Report-specific parameters"
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
        help_text="Current status of the report"
    )
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text="Progress percentage (0-100)"
    )
    
    # Results
    result_file = models.FileField(
        upload_to='reports/%Y/%m/',
        null=True,
        blank=True,
        help_text="Generated report file"
    )
    result_url = models.URLField(
        blank=True,
        help_text="URL to access the report"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the report will be deleted"
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if report generation failed"
    )
    retry_count = models.PositiveSmallIntegerField(
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
    
    class Meta:
        verbose_name = "Report Job"
        verbose_name_plural = "Report Jobs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type', 'status']),
            models.Index(fields=['requested_by', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def mark_started(self):
        """Mark the report job as started."""
        self.status = ReportStatus.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_completed(self, result_file=None, result_url=''):
        """Mark the report job as completed."""
        self.status = ReportStatus.COMPLETED
        self.progress_percent = 100
        self.completed_at = timezone.now()
        self.result_file = result_file
        self.result_url = result_url
        self.expires_at = timezone.now() + timedelta(days=30)  # 30 day retention
        self.save(update_fields=[
            'status', 'progress_percent', 'completed_at',
            'result_file', 'result_url', 'expires_at', 'updated_at'
        ])
    
    def mark_failed(self, error_message):
        """Mark the report job as failed."""
        self.status = ReportStatus.FAILED
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    
    def update_progress(self, percent):
        """Update the progress percentage."""
        self.progress_percent = min(100, max(0, percent))
        self.save(update_fields=['progress_percent', 'updated_at'])


class SecurityAuditLog(BaseModel):
    """
    Security-focused audit log for compliance and incident response.
    Tracks authentication events, access control changes, and security-relevant activities.
    """
    
    # Event categorization
    event_category = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Category of security event (e.g., authentication, authorization, data_access)"
    )
    event_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Specific type of security event"
    )
    severity = models.CharField(
        max_length=20,
        choices=[
            ('critical', 'Critical'),
            ('high', 'High'),
            ('medium', 'Medium'),
            ('low', 'Low'),
            ('info', 'Info')
        ],
        default='info',
        db_index=True,
        help_text="Severity level of the event"
    )
    
    # Actor information
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_events',
        help_text="User associated with the event"
    )
    actor_email = models.EmailField(
        blank=True,
        db_index=True,
        help_text="Email of actor at time of event"
    )
    actor_role = models.CharField(
        max_length=50,
        blank=True,
        help_text="Role of actor at time of event"
    )
    
    # Event details
    description = models.TextField(
        help_text="Human-readable description of the event"
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured event details"
    )
    
    # Target information
    target_type = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Type of target affected"
    )
    target_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="ID of target affected"
    )
    
    # Request context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
        help_text="IP address of the request"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    session_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Session identifier"
    )
    
    # Geolocation (if available)
    country_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="ISO country code"
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        help_text="City name"
    )
    
    # Risk assessment
    risk_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Calculated risk score (0-100)"
    )
    is_suspicious = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this event is flagged as suspicious"
    )
    requires_review = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this event requires manual review"
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_security_events',
        help_text="User who reviewed this event"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the event was reviewed"
    )
    review_notes = models.TextField(
        blank=True,
        help_text="Notes from the review"
    )
    
    # Timing
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the event occurred"
    )
    
    # Retention
    retention_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this record can be deleted"
    )
    
    class Meta:
        verbose_name = "Security Audit Log"
        verbose_name_plural = "Security Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_category', 'event_type', 'timestamp']),
            models.Index(fields=['severity', 'timestamp']),
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['is_suspicious', 'requires_review']),
            models.Index(fields=['session_id', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.severity} at {self.timestamp}"
    
    @classmethod
    def log_security_event(cls, event_category, event_type, description, actor=None,
                           severity='info', details=None, target_type='', target_id='',
                           ip_address=None, user_agent='', session_id='',
                           is_suspicious=False, requires_review=False, risk_score=None):
        """
        Factory method to create a security audit log entry.
        """
        if details is None:
            details = {}
        
        return cls.objects.create(
            event_category=event_category,
            event_type=event_type,
            severity=severity,
            description=description,
            actor=actor,
            actor_email=actor.email if actor else '',
            actor_role=getattr(actor, 'role', '') if actor else '',
            details=details,
            target_type=target_type,
            target_id=str(target_id) if target_id else '',
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            is_suspicious=is_suspicious,
            requires_review=requires_review,
            risk_score=risk_score,
            timestamp=timezone.now(),
            retention_until=timezone.now() + timedelta(days=7*365)  # 7 years
        )


# ============================================================================
# GDPR & SOC 2 COMPLIANCE MODELS
# ============================================================================

class ConsentType(models.TextChoices):
    """Types of consent that can be collected."""
    TERMS_OF_SERVICE = 'tos', 'Terms of Service'
    PRIVACY_POLICY = 'privacy', 'Privacy Policy'
    MARKETING_EMAILS = 'marketing', 'Marketing Emails'
    ANALYTICS_COOKIES = 'analytics_cookies', 'Analytics Cookies'
    THIRD_PARTY_SHARING = 'third_party', 'Third-Party Data Sharing'
    DATA_PROCESSING = 'data_processing', 'Data Processing'
    BIOMETRIC_DATA = 'biometric', 'Biometric Data'
    LOCATION_DATA = 'location', 'Location Data'


class ConsentStatus(models.TextChoices):
    """Status of a consent record."""
    GRANTED = 'granted', 'Granted'
    WITHDRAWN = 'withdrawn', 'Withdrawn'
    EXPIRED = 'expired', 'Expired'
    PENDING = 'pending', 'Pending'


class ConsentRecord(BaseModel):
    """
    GDPR-compliant consent management record.
    Tracks granular user consent for different data processing activities.
    """
    
    # User relationship
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='consent_records',
        help_text="User who gave/withdrew consent"
    )
    
    # Consent details
    consent_type = models.CharField(
        max_length=50,
        choices=ConsentType.choices,
        db_index=True,
        help_text="Type of consent"
    )
    status = models.CharField(
        max_length=20,
        choices=ConsentStatus.choices,
        default=ConsentStatus.PENDING,
        db_index=True,
        help_text="Current consent status"
    )
    
    # Version tracking
    version = models.CharField(
        max_length=20,
        help_text="Version of the consent terms accepted"
    )
    consent_text = models.TextField(
        help_text="Full text of the consent that was presented"
    )
    
    # Timing
    granted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When consent was granted"
    )
    withdrawn_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When consent was withdrawn"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When consent expires (if applicable)"
    )
    
    # Context at time of consent
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address when consent was given"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent when consent was given"
    )
    
    # Withdrawal details
    withdrawal_reason = models.TextField(
        blank=True,
        help_text="Reason for withdrawal (if provided)"
    )
    
    class Meta:
        verbose_name = "Consent Record"
        verbose_name_plural = "Consent Records"
        ordering = ['-granted_at']
        indexes = [
            models.Index(fields=['user', 'consent_type', 'status']),
            models.Index(fields=['consent_type', 'status']),
            models.Index(fields=['granted_at']),
            models.Index(fields=['expires_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'consent_type', 'version'],
                name='unique_user_consent_version'
            )
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.consent_type} ({self.status})"
    
    def grant(self, ip_address=None, user_agent=''):
        """Grant consent."""
        self.status = ConsentStatus.GRANTED
        self.granted_at = timezone.now()
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.save(update_fields=[
            'status', 'granted_at', 'ip_address', 'user_agent', 'updated_at'
        ])
    
    def withdraw(self, reason=''):
        """Withdraw consent."""
        self.status = ConsentStatus.WITHDRAWN
        self.withdrawn_at = timezone.now()
        self.withdrawal_reason = reason
        self.save(update_fields=[
            'status', 'withdrawn_at', 'withdrawal_reason', 'updated_at'
        ])
    
    def is_active(self):
        """Check if consent is currently active."""
        if self.status != ConsentStatus.GRANTED:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class DSARType(models.TextChoices):
    """Types of Data Subject Access Requests."""
    ACCESS = 'access', 'Right to Access'
    PORTABILITY = 'portability', 'Right to Data Portability'
    ERASURE = 'erasure', 'Right to Erasure (Right to be Forgotten)'
    RECTIFICATION = 'rectification', 'Right to Rectification'
    RESTRICTION = 'restriction', 'Right to Restriction of Processing'
    OBJECTION = 'objection', 'Right to Object'


class DSARStatus(models.TextChoices):
    """Status of a Data Subject Access Request."""
    PENDING = 'pending', 'Pending'
    IN_REVIEW = 'in_review', 'In Review'
    PROCESSING = 'processing', 'Processing'
    AWAITING_INFO = 'awaiting_info', 'Awaiting Additional Information'
    COMPLETED = 'completed', 'Completed'
    REJECTED = 'rejected', 'Rejected'
    CANCELLED = 'cancelled', 'Cancelled'


class DataSubjectRequest(BaseModel):
    """
    Data Subject Access Request (DSAR) tracking.
    Manages GDPR data subject rights requests.
    """
    
    # Request identification
    request_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique identifier for the request"
    )
    
    # Requester
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='dsar_requests',
        help_text="User who made the request"
    )
    request_type = models.CharField(
        max_length=20,
        choices=DSARType.choices,
        db_index=True,
        help_text="Type of data subject request"
    )
    
    # Request details
    description = models.TextField(
        blank=True,
        help_text="Additional details about the request"
    )
    scope = models.JSONField(
        default=dict,
        blank=True,
        help_text="Scope of data to include (e.g., specific date ranges, systems)"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=DSARStatus.choices,
        default=DSARStatus.PENDING,
        db_index=True,
        help_text="Current status of the request"
    )
    priority = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low'),
            ('normal', 'Normal'),
            ('high', 'High'),
            ('urgent', 'Urgent')
        ],
        default='normal',
        help_text="Priority level"
    )
    
    # SLA tracking
    received_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the request was received"
    )
    sla_deadline = models.DateTimeField(
        help_text="GDPR deadline for response (30 days)"
    )
    extension_requested = models.BooleanField(
        default=False,
        help_text="Whether an extension was requested"
    )
    extension_reason = models.TextField(
        blank=True,
        help_text="Reason for extension (if applicable)"
    )
    extended_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Extended deadline (if approved)"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the request was completed"
    )
    
    # Assignment
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_dsars',
        help_text="DPO or admin assigned to handle this request"
    )
    
    # Identity verification
    identity_verified = models.BooleanField(
        default=False,
        help_text="Whether the requester's identity has been verified"
    )
    identity_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When identity was verified"
    )
    verification_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="Method used for identity verification"
    )
    
    # Result
    result_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Structured result data (for access/portability requests)"
    )
    result_file = models.FileField(
        upload_to='dsar_results/%Y/%m/',
        null=True,
        blank=True,
        help_text="Export file (for portability requests)"
    )
    result_summary = models.TextField(
        blank=True,
        help_text="Summary of actions taken"
    )
    
    # Rejection details
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if applicable)"
    )
    
    class Meta:
        verbose_name = "Data Subject Request"
        verbose_name_plural = "Data Subject Requests"
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['request_type', 'status']),
            models.Index(fields=['status', 'sla_deadline']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['received_at']),
        ]
    
    def __str__(self):
        return f"{self.request_id} - {self.request_type} ({self.status})"
    
    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = f"DSAR-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        if not self.sla_deadline:
            self.sla_deadline = self.received_at + timedelta(days=30)
        super().save(*args, **kwargs)
    
    def days_until_deadline(self):
        """Calculate days remaining until SLA deadline."""
        deadline = self.extended_deadline or self.sla_deadline
        return (deadline - timezone.now()).days
    
    def is_overdue(self):
        """Check if the request is past its deadline."""
        deadline = self.extended_deadline or self.sla_deadline
        return timezone.now() > deadline
    
    def request_extension(self, reason, days=60):
        """Request an extension to the SLA deadline."""
        self.extension_requested = True
        self.extension_reason = reason
        self.extended_deadline = self.sla_deadline + timedelta(days=days)
        self.save(update_fields=[
            'extension_requested', 'extension_reason', 'extended_deadline', 'updated_at'
        ])
    
    def verify_identity(self, method, verified_by):
        """Mark identity as verified."""
        self.identity_verified = True
        self.identity_verified_at = timezone.now()
        self.verification_method = method
        self.save(update_fields=[
            'identity_verified', 'identity_verified_at', 'verification_method', 'updated_at'
        ])
        
        # Log the verification
        SecurityAuditLog.log_security_event(
            event_category='data_subject_rights',
            event_type='identity_verified',
            description=f"Identity verified for DSAR {self.request_id}",
            actor=verified_by,
            severity='info',
            target_type='dsar',
            target_id=str(self.id)
        )
    
    def complete(self, result_summary='', result_data=None, result_file=None):
        """Mark the request as completed."""
        self.status = DSARStatus.COMPLETED
        self.completed_at = timezone.now()
        self.result_summary = result_summary
        if result_data:
            self.result_data = result_data
        if result_file:
            self.result_file = result_file
        self.save(update_fields=[
            'status', 'completed_at', 'result_summary', 'result_data', 'result_file', 'updated_at'
        ])
    
    def reject(self, reason, rejected_by):
        """Reject the request."""
        self.status = DSARStatus.REJECTED
        self.rejection_reason = reason
        self.completed_at = timezone.now()
        self.assigned_to = rejected_by
        self.save(update_fields=[
            'status', 'rejection_reason', 'completed_at', 'assigned_to', 'updated_at'
        ])


class DataRetentionPolicy(BaseModel):
    """
    Data retention policy configuration.
    Defines retention periods for different data types.
    """
    
    # Policy identification
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Policy name"
    )
    description = models.TextField(
        blank=True,
        help_text="Policy description"
    )
    
    # Data classification
    data_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Type of data (e.g., user_activity, audit_logs, user_profiles)"
    )
    data_category = models.CharField(
        max_length=50,
        choices=[
            ('personal', 'Personal Data'),
            ('sensitive', 'Sensitive Personal Data'),
            ('financial', 'Financial Data'),
            ('technical', 'Technical Data'),
            ('administrative', 'Administrative Data')
        ],
        help_text="Category of data under GDPR"
    )
    
    # Retention rules
    retention_days = models.PositiveIntegerField(
        help_text="Number of days to retain data"
    )
    active_retention_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Days to retain active data (before archival)"
    )
    archive_before_delete = models.BooleanField(
        default=True,
        help_text="Whether to archive before deletion"
    )
    
    # Legal basis
    legal_basis = models.TextField(
        help_text="Legal basis for retention (e.g., 'legitimate_interest', 'legal_obligation')"
    )
    legal_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reference to applicable law or regulation"
    )
    
    # Policy status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this policy is currently active"
    )
    effective_date = models.DateField(
        help_text="When this policy takes effect"
    )
    review_date = models.DateField(
        null=True,
        blank=True,
        help_text="When this policy should be reviewed"
    )
    
    # Automation
    auto_delete = models.BooleanField(
        default=False,
        help_text="Whether to automatically delete expired data"
    )
    notify_before_deletion = models.BooleanField(
        default=True,
        help_text="Whether to notify before deletion"
    )
    notification_days_before = models.PositiveIntegerField(
        default=30,
        help_text="Days before deletion to send notification"
    )
    
    class Meta:
        verbose_name = "Data Retention Policy"
        verbose_name_plural = "Data Retention Policies"
        ordering = ['data_type']
        indexes = [
            models.Index(fields=['data_type', 'is_active']),
            models.Index(fields=['data_category', 'is_active']),
            models.Index(fields=['effective_date']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.data_type} - {self.retention_days} days)"
    
    def calculate_retention_date(self, start_date=None):
        """Calculate the retention expiration date from a start date."""
        if start_date is None:
            start_date = timezone.now()
        return start_date + timedelta(days=self.retention_days)


class PIARiskLevel(models.TextChoices):
    """Risk levels for Privacy Impact Assessments."""
    LOW = 'low', 'Low Risk'
    MEDIUM = 'medium', 'Medium Risk'
    HIGH = 'high', 'High Risk'
    CRITICAL = 'critical', 'Critical Risk'


class PIAStatus(models.TextChoices):
    """Status of a Privacy Impact Assessment."""
    DRAFT = 'draft', 'Draft'
    IN_REVIEW = 'in_review', 'In Review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    IMPLEMENTATION = 'implementation', 'In Implementation'
    COMPLETED = 'completed', 'Completed'
    ARCHIVED = 'archived', 'Archived'


class PrivacyImpactAssessment(BaseModel):
    """
    Privacy Impact Assessment (PIA) record.
    Documents privacy risk assessments for data processing activities.
    """
    
    # Assessment identification
    pia_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique PIA identifier"
    )
    title = models.CharField(
        max_length=255,
        help_text="Title of the assessment"
    )
    description = models.TextField(
        help_text="Description of the processing activity"
    )
    
    # Scope
    data_types = models.JSONField(
        default=list,
        help_text="Types of personal data involved"
    )
    data_subjects = models.JSONField(
        default=list,
        help_text="Categories of data subjects (e.g., employees, customers)"
    )
    processing_purposes = models.JSONField(
        default=list,
        help_text="Purposes of processing"
    )
    legal_basis = models.JSONField(
        default=list,
        help_text="Legal basis for processing"
    )
    
    # Risk assessment
    risk_level = models.CharField(
        max_length=20,
        choices=PIARiskLevel.choices,
        default=PIARiskLevel.LOW,
        help_text="Assessed risk level"
    )
    risks_identified = models.JSONField(
        default=list,
        help_text="List of identified risks"
    )
    mitigation_measures = models.JSONField(
        default=list,
        help_text="Measures to mitigate risks"
    )
    residual_risk = models.TextField(
        blank=True,
        help_text="Remaining risk after mitigation"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=PIAStatus.choices,
        default=PIAStatus.DRAFT,
        db_index=True,
        help_text="Current status of the PIA"
    )
    
    # Stakeholders
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_pias',
        help_text="Business owner of the processing activity"
    )
    dpo = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_pias',
        help_text="Data Protection Officer who reviewed the PIA"
    )
    approver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_pias',
        help_text="Person who approved the PIA"
    )
    
    # Timeline
    created_date = models.DateField(
        default=timezone.now,
        help_text="When the PIA was created"
    )
    review_date = models.DateField(
        null=True,
        blank=True,
        help_text="When the PIA should be reviewed"
    )
    approved_date = models.DateField(
        null=True,
        blank=True,
        help_text="When the PIA was approved"
    )
    
    # Related systems/processes
    related_systems = models.JSONField(
        default=list,
        blank=True,
        help_text="Systems involved in processing"
    )
    data_flow_diagram = models.FileField(
        upload_to='pia_diagrams/',
        null=True,
        blank=True,
        help_text="Data flow diagram"
    )
    
    # DPO consultation
    dpo_consulted = models.BooleanField(
        default=False,
        help_text="Whether DPO was consulted"
    )
    dpo_opinion = models.TextField(
        blank=True,
        help_text="DPO's opinion on the assessment"
    )
    
    class Meta:
        verbose_name = "Privacy Impact Assessment"
        verbose_name_plural = "Privacy Impact Assessments"
        ordering = ['-created_date']
        indexes = [
            models.Index(fields=['status', 'risk_level']),
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['review_date']),
        ]
    
    def __str__(self):
        return f"{self.pia_id} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.pia_id:
            self.pia_id = f"PIA-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)
    
    def approve(self, approver_user):
        """Approve the PIA."""
        self.status = PIAStatus.APPROVED
        self.approved_date = timezone.now()
        self.approver = approver_user
        self.save(update_fields=['status', 'approved_date', 'approver', 'updated_at'])
    
    def requires_dpo_consultation(self):
        """Determine if DPO consultation is required based on risk level."""
        return self.risk_level in [PIARiskLevel.HIGH, PIARiskLevel.CRITICAL]


class SOC2ControlCategory(models.TextChoices):
    """SOC 2 Trust Services Criteria categories."""
    SECURITY = 'CC', 'Common Criteria (Security)'
    AVAILABILITY = 'A', 'Availability'
    PROCESSING_INTEGRITY = 'PI', 'Processing Integrity'
    CONFIDENTIALITY = 'C', 'Confidentiality'
    PRIVACY = 'P', 'Privacy'


class SOC2ControlStatus(models.TextChoices):
    """Status of SOC 2 control implementation."""
    NOT_IMPLEMENTED = 'not_implemented', 'Not Implemented'
    PARTIALLY_IMPLEMENTED = 'partially_implemented', 'Partially Implemented'
    IMPLEMENTED = 'implemented', 'Implemented'
    TESTED = 'tested', 'Tested'
    EXCEPTION = 'exception', 'Exception Granted'


class SOC2Control(BaseModel):
    """
    SOC 2 Control definition.
    Maps to specific Trust Services Criteria requirements.
    """
    
    # Control identification
    control_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique control identifier (e.g., CC6.1, A1.2)"
    )
    title = models.CharField(
        max_length=255,
        help_text="Control title"
    )
    description = models.TextField(
        help_text="Detailed control description"
    )
    
    # Categorization
    category = models.CharField(
        max_length=2,
        choices=SOC2ControlCategory.choices,
        db_index=True,
        help_text="SOC 2 Trust Services Criteria category"
    )
    sub_category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Sub-category or sub-criteria"
    )
    
    # Control details
    control_type = models.CharField(
        max_length=50,
        choices=[
            ('preventive', 'Preventive'),
            ('detective', 'Detective'),
            ('corrective', 'Corrective'),
            ('compensating', 'Compensating')
        ],
        help_text="Type of control"
    )
    frequency = models.CharField(
        max_length=50,
        choices=[
            ('continuous', 'Continuous'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('annually', 'Annually'),
            ('adhoc', 'Ad-hoc')
        ],
        help_text="Control execution frequency"
    )
    
    # Implementation
    status = models.CharField(
        max_length=30,
        choices=SOC2ControlStatus.choices,
        default=SOC2ControlStatus.NOT_IMPLEMENTED,
        db_index=True,
        help_text="Implementation status"
    )
    implementation_date = models.DateField(
        null=True,
        blank=True,
        help_text="When the control was implemented"
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_controls',
        help_text="Control owner"
    )
    
    # Documentation
    policies = models.JSONField(
        default=list,
        blank=True,
        help_text="Related policy documents"
    )
    procedures = models.JSONField(
        default=list,
        blank=True,
        help_text="Related procedures"
    )
    
    class Meta:
        verbose_name = "SOC 2 Control"
        verbose_name_plural = "SOC 2 Controls"
        ordering = ['control_id']
        indexes = [
            models.Index(fields=['category', 'status']),
            models.Index(fields=['owner', 'status']),
        ]
    
    def __str__(self):
        return f"{self.control_id} - {self.title}"


class SOC2ControlEvidence(BaseModel):
    """
    Evidence collected for SOC 2 control testing.
    Supports continuous monitoring and audit readiness.
    """
    
    # Evidence identification
    evidence_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique evidence identifier"
    )
    
    # Related control
    control = models.ForeignKey(
        SOC2Control,
        on_delete=models.CASCADE,
        related_name='evidence',
        help_text="SOC 2 control this evidence supports"
    )
    
    # Evidence details
    title = models.CharField(
        max_length=255,
        help_text="Evidence title"
    )
    description = models.TextField(
        blank=True,
        help_text="Evidence description"
    )
    evidence_type = models.CharField(
        max_length=50,
        choices=[
            ('screenshot', 'Screenshot'),
            ('log_export', 'Log Export'),
            ('policy_document', 'Policy Document'),
            ('configuration', 'Configuration'),
            ('test_result', 'Test Result'),
            ('certificate', 'Certificate'),
            ('report', 'Report'),
            ('interview', 'Interview Notes'),
            ('other', 'Other')
        ],
        help_text="Type of evidence"
    )
    
    # Evidence content
    file = models.FileField(
        upload_to='soc2_evidence/%Y/%m/',
        null=True,
        blank=True,
        help_text="Evidence file"
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash of the file for integrity"
    )
    external_url = models.URLField(
        blank=True,
        help_text="External URL reference (e.g., to ticket system)"
    )
    content = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured evidence content"
    )
    
    # Collection metadata
    collected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collected_evidence',
        help_text="User who collected the evidence"
    )
    collected_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the evidence was collected"
    )
    collection_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="Method used to collect evidence"
    )
    
    # Period covered
    period_start = models.DateField(
        help_text="Start of period covered by evidence"
    )
    period_end = models.DateField(
        help_text="End of period covered by evidence"
    )
    
    # Review status
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_evidence',
        help_text="User who reviewed the evidence"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the evidence was reviewed"
    )
    review_notes = models.TextField(
        blank=True,
        help_text="Review notes"
    )
    is_valid = models.BooleanField(
        default=True,
        help_text="Whether the evidence is valid"
    )
    
    # Automation
    is_automated = models.BooleanField(
        default=False,
        help_text="Whether evidence was collected automatically"
    )
    automation_source = models.CharField(
        max_length=100,
        blank=True,
        help_text="Source system for automated evidence"
    )
    
    class Meta:
        verbose_name = "SOC 2 Control Evidence"
        verbose_name_plural = "SOC 2 Control Evidence"
        ordering = ['-collected_at']
        indexes = [
            models.Index(fields=['control', 'collected_at']),
            models.Index(fields=['evidence_type', 'collected_at']),
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['is_valid', 'reviewed_at']),
        ]
    
    def __str__(self):
        return f"{self.evidence_id} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.evidence_id:
            self.evidence_id = f"EV-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)
    
    def mark_reviewed(self, reviewer, notes=''):
        """Mark evidence as reviewed."""
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=['reviewed_by', 'reviewed_at', 'review_notes', 'updated_at'])


class DataBreachStatus(models.TextChoices):
    """Status of a data breach incident."""
    DETECTED = 'detected', 'Detected'
    UNDER_INVESTIGATION = 'under_investigation', 'Under Investigation'
    CONFIRMED = 'confirmed', 'Confirmed'
    CONTAINED = 'contained', 'Contained'
    NOTIFIED = 'notified', 'Notified'
    RESOLVED = 'resolved', 'Resolved'
    CLOSED = 'closed', 'Closed'


class DataBreachSeverity(models.TextChoices):
    """Severity levels for data breaches."""
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class DataBreachIncident(BaseModel):
    """
    Data breach incident record.
    Tracks breach detection, response, and notification.
    """
    
    # Incident identification
    incident_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique incident identifier"
    )
    title = models.CharField(
        max_length=255,
        help_text="Incident title"
    )
    description = models.TextField(
        help_text="Detailed description of the incident"
    )
    
    # Detection
    detected_at = models.DateTimeField(
        help_text="When the breach was detected"
    )
    detected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='detected_breaches',
        help_text="User who detected the breach"
    )
    detection_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="How the breach was detected"
    )
    
    # Assessment
    severity = models.CharField(
        max_length=20,
        choices=DataBreachSeverity.choices,
        default=DataBreachSeverity.LOW,
        help_text="Severity assessment"
    )
    status = models.CharField(
        max_length=30,
        choices=DataBreachStatus.choices,
        default=DataBreachStatus.DETECTED,
        db_index=True,
        help_text="Current status"
    )
    
    # Impact assessment
    data_types_affected = models.JSONField(
        default=list,
        help_text="Types of data affected"
    )
    data_subjects_affected = models.JSONField(
        default=list,
        help_text="Categories of data subjects affected"
    )
    estimated_records = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated number of records affected"
    )
    
    # Timeline
    occurred_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the breach occurred (if known)"
    )
    contained_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the breach was contained"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the breach was resolved"
    )
    
    # Notification tracking
    supervisory_authority_notified = models.BooleanField(
        default=False,
        help_text="Whether supervisory authority was notified"
    )
    authority_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When authority was notified"
    )
    authority_notification_ref = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reference number from authority"
    )
    
    data_subjects_notified = models.BooleanField(
        default=False,
        help_text="Whether affected data subjects were notified"
    )
    subjects_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When data subjects were notified"
    )
    notification_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="Method used to notify data subjects"
    )
    
    # Response team
    incident_lead = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_breaches',
        help_text="Incident response lead"
    )
    dpo_notified = models.BooleanField(
        default=False,
        help_text="Whether DPO was notified"
    )
    dpo_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When DPO was notified"
    )
    
    # Root cause and remediation
    root_cause = models.TextField(
        blank=True,
        help_text="Root cause analysis"
    )
    remediation_actions = models.JSONField(
        default=list,
        blank=True,
        help_text="Actions taken to remediate"
    )
    lessons_learned = models.TextField(
        blank=True,
        help_text="Lessons learned from the incident"
    )
    
    class Meta:
        verbose_name = "Data Breach Incident"
        verbose_name_plural = "Data Breach Incidents"
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['status', 'severity']),
            models.Index(fields=['detected_at']),
            models.Index(fields=['incident_lead', 'status']),
        ]
    
    def __str__(self):
        return f"{self.incident_id} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.incident_id:
            self.incident_id = f"BREACH-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)
    
    def hours_to_notify(self):
        """Calculate hours remaining to notify supervisory authority (72 hours per GDPR)."""
        if self.supervisory_authority_notified:
            return 0
        if self.detected_at:
            elapsed = (timezone.now() - self.detected_at).total_seconds() / 3600
            return max(0, 72 - elapsed)
        return None
    
    def is_notification_overdue(self):
        """Check if notification to authority is overdue."""
        if self.supervisory_authority_notified:
            return False
        if self.detected_at:
            return (timezone.now() - self.detected_at).total_seconds() > (72 * 3600)
        return False


class ComplianceDashboardMetric(BaseModel):
    """
    Pre-computed compliance metrics for DPO dashboard.
    """
    
    metric_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Name of the metric"
    )
    metric_category = models.CharField(
        max_length=50,
        choices=[
            ('gdpr', 'GDPR'),
            ('soc2', 'SOC 2'),
            ('dsar', 'Data Subject Requests'),
            ('consent', 'Consent Management'),
            ('retention', 'Data Retention'),
            ('breach', 'Data Breach'),
            ('pia', 'Privacy Impact Assessment')
        ],
        help_text="Category of the metric"
    )
    
    # Metric values
    current_value = models.JSONField(
        help_text="Current metric value"
    )
    previous_value = models.JSONField(
        null=True,
        blank=True,
        help_text="Previous metric value for comparison"
    )
    trend = models.CharField(
        max_length=20,
        choices=[
            ('up', 'Up'),
            ('down', 'Down'),
            ('stable', 'Stable'),
            ('new', 'New')
        ],
        default='stable',
        help_text="Trend direction"
    )
    
    # Thresholds
    warning_threshold = models.JSONField(
        null=True,
        blank=True,
        help_text="Warning threshold value"
    )
    critical_threshold = models.JSONField(
        null=True,
        blank=True,
        help_text="Critical threshold value"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('normal', 'Normal'),
            ('warning', 'Warning'),
            ('critical', 'Critical')
        ],
        default='normal',
        help_text="Current status based on thresholds"
    )
    
    # Metadata
    computed_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the metric was computed"
    )
    period_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of period"
    )
    period_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of period"
    )
    
    class Meta:
        verbose_name = "Compliance Dashboard Metric"
        verbose_name_plural = "Compliance Dashboard Metrics"
        ordering = ['-computed_at']
        indexes = [
            models.Index(fields=['metric_category', 'computed_at']),
            models.Index(fields=['status', 'metric_category']),
        ]
    
    def __str__(self):
        return f"{self.metric_name} ({self.metric_category})"
