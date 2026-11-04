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
    
    # Session context
    session_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Session identifier"
    )
    
    # Timestamp
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the action was performed"
    )
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id', 'timestamp']),
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['is_sensitive', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.action} on {self.resource_type} by {self.actor_email}"
    
    def clean(self):
        """Validate that sensitive actions have justification."""
        from django.core.exceptions import ValidationError
        if self.is_sensitive and not self.justification:
            raise ValidationError("Sensitive actions require a justification.")
    
    @classmethod
    def log_action(cls, action, actor, resource_type, resource_id, resource_name='',
                   changes=None, before_state=None, after_state=None,
                   justification='', is_sensitive=False, session_id='', actor_ip=None):
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
            resource_id=resource_id,
            resource_name=resource_name,
            changes=changes,
            before_state=before_state,
            after_state=after_state,
            justification=justification,
            is_sensitive=is_sensitive,
            session_id=session_id,
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
        help_text="Human-readable report name"
    )
    description = models.TextField(
        blank=True,
        help_text="Report description"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True,
        help_text="Current generation status"
    )
    
    # Request parameters
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Report generation parameters"
    )
    
    # Result tracking
    file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to generated report file"
    )
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of generated file in bytes"
    )
    download_url = models.URLField(
        blank=True,
        help_text="Temporary download URL"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the report expires"
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if generation failed"
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    
    # Requester
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='report_jobs',
        help_text="User who requested the report"
    )
    
    # Timing
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When generation started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When generation completed"
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
        """Mark the report as started."""
        self.status = ReportStatus.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_completed(self, file_path='', file_size=None, download_url=''):
        """Mark the report as completed."""
        self.status = ReportStatus.COMPLETED
        self.completed_at = timezone.now()
        self.file_path = file_path
        self.file_size = file_size
        self.download_url = download_url
        self.save(update_fields=[
            'status', 'completed_at', 'file_path', 'file_size',
            'download_url', 'updated_at'
        ])
    
    def mark_failed(self, error_message):
        """Mark the report as failed."""
        self.status = ReportStatus.FAILED
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])


class SecurityAuditLog(BaseModel):
    """
    Security-focused audit log for compliance (SOC 2, ISO 27001).
    Tracks authentication, authorization, and security events.
    """
    
    # Event classification
    SEVERITY_LOW = 'low'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_HIGH = 'high'
    SEVERITY_CRITICAL = 'critical'
    
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, 'Low'),
        (SEVERITY_MEDIUM, 'Medium'),
        (SEVERITY_HIGH, 'High'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]
    
    EVENT_LOGIN_SUCCESS = 'login_success'
    EVENT_LOGIN_FAILURE = 'login_failure'
    EVENT_LOGOUT = 'logout'
    EVENT_TOKEN_REFRESH = 'token_refresh'
    EVENT_ACCESS_DENIED = 'access_denied'
    EVENT_PERMISSION_CHANGE = 'permission_change'
    EVENT_DATA_EXPORT = 'data_export'
    EVENT_BULK_OPERATION = 'bulk_operation'
    EVENT_SUSPICIOUS_ACTIVITY = 'suspicious_activity'
    EVENT_MFA_ENABLED = 'mfa_enabled'
    EVENT_MFA_DISABLED = 'mfa_disabled'
    EVENT_PASSWORD_CHANGE = 'password_change'
    EVENT_PASSWORD_RESET = 'password_reset'
    EVENT_SESSION_REVOKED = 'session_revoked'
    EVENT_API_KEY_CREATED = 'api_key_created'
    EVENT_API_KEY_REVOKED = 'api_key_revoked'
    
    EVENT_CHOICES = [
        (EVENT_LOGIN_SUCCESS, 'Login Success'),
        (EVENT_LOGIN_FAILURE, 'Login Failure'),
        (EVENT_LOGOUT, 'Logout'),
        (EVENT_TOKEN_REFRESH, 'Token Refresh'),
        (EVENT_ACCESS_DENIED, 'Access Denied'),
        (EVENT_PERMISSION_CHANGE, 'Permission Change'),
        (EVENT_DATA_EXPORT, 'Data Export'),
        (EVENT_BULK_OPERATION, 'Bulk Operation'),
        (EVENT_SUSPICIOUS_ACTIVITY, 'Suspicious Activity'),
        (EVENT_MFA_ENABLED, 'MFA Enabled'),
        (EVENT_MFA_DISABLED, 'MFA Disabled'),
        (EVENT_PASSWORD_CHANGE, 'Password Change'),
        (EVENT_PASSWORD_RESET, 'Password Reset'),
        (EVENT_SESSION_REVOKED, 'Session Revoked'),
        (EVENT_API_KEY_CREATED, 'API Key Created'),
        (EVENT_API_KEY_REVOKED, 'API Key Revoked'),
    ]
    
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        db_index=True,
        help_text="Type of security event"
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_LOW,
        db_index=True,
        help_text="Event severity level"
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
        help_text="Email of actor (preserved for deleted users)"
    )
    actor_role = models.CharField(
        max_length=50,
        blank=True,
        help_text="Role of actor at time of event"
    )
    
    # Event details
    description = models.TextField(
        help_text="Human-readable event description"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional event metadata"
    )
    
    # Request context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
        help_text="IP address"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
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
    
    # Geographic info (for anomaly detection)
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
    
    # Risk scoring
    risk_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Calculated risk score (0-100)"
    )
    is_anomaly = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this event was flagged as anomalous"
    )
    
    # Alert status
    alert_sent = models.BooleanField(
        default=False,
        help_text="Whether an alert was sent for this event"
    )
    alert_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When alert was sent"
    )
    
    # Timestamp
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the event occurred"
    )
    
    class Meta:
        verbose_name = "Security Audit Log"
        verbose_name_plural = "Security Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_type', 'severity', 'timestamp']),
            models.Index(fields=['actor', 'event_type', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['is_anomaly', 'timestamp']),
            models.Index(fields=['severity', 'is_anomaly', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.event_type} ({self.severity}) at {self.timestamp}"
    
    @classmethod
    def log_security_event(cls, event_type, severity=SEVERITY_LOW, actor=None,
                          description='', metadata=None, ip_address=None,
                          user_agent='', request_path='', session_id='',
                          risk_score=None, is_anomaly=False):
        """
        Factory method to create a security audit log entry.
        """
        if metadata is None:
            metadata = {}
        
        return cls.objects.create(
            event_type=event_type,
            severity=severity,
            actor=actor,
            actor_email=actor.email if actor else '',
            actor_role=actor.role if actor and hasattr(actor, 'role') else '',
            description=description,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            session_id=session_id,
            risk_score=risk_score,
            is_anomaly=is_anomaly,
            timestamp=timezone.now()
        )


# =============================================================================
# LRS (Learning Record Store) Integration Models
# =============================================================================

class LRSType(models.TextChoices):
    """Types of Learning Record Store endpoints."""
    SCORM_CLOUD = 'scorm_cloud', 'SCORM Cloud'
    CUSTOM_LRS = 'custom_lrs', 'Custom LRS'
    WATERSHED = 'watershed', 'Watershed LRS'
    LEARNING_LOCKER = 'learning_locker', 'Learning Locker'
    VERACITY = 'veracity', 'Veracity LRS'
    OTHER = 'other', 'Other'


class LRSSyncMode(models.TextChoices):
    """Synchronization modes for LRS."""
    PUSH = 'push', 'Push (Send to LRS)'
    PULL = 'pull', 'Pull (Receive from LRS)'
    BIDIRECTIONAL = 'bidirectional', 'Bidirectional'


class LRSCredentialType(models.TextChoices):
    """Authentication credential types for LRS."""
    BASIC_AUTH = 'basic_auth', 'Basic Authentication'
    OAUTH2 = 'oauth2', 'OAuth 2.0'
    API_KEY = 'api_key', 'API Key'
    SAML = 'saml', 'SAML Assertion'


class LRSConfiguration(BaseModel):
    """
    Configuration for external Learning Record Store (LRS) endpoints.
    Supports SCORM Cloud, Watershed, Learning Locker, and custom LRS implementations.
    """
    
    # Basic Information
    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this LRS configuration"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this LRS configuration"
    )
    
    # LRS Type
    lrs_type = models.CharField(
        max_length=50,
        choices=LRSType.choices,
        default=LRSType.CUSTOM_LRS,
        db_index=True,
        help_text="Type of LRS endpoint"
    )
    
    # Endpoint Configuration
    endpoint_url = models.URLField(
        help_text="LRS endpoint URL (e.g., https://lrs.example.com/xAPI/)"
    )
    statement_endpoint = models.URLField(
        blank=True,
        help_text="Optional: Specific statements endpoint if different from base"
    )
    
    # Authentication Credentials (encrypted at rest)
    credential_type = models.CharField(
        max_length=50,
        choices=LRSCredentialType.choices,
        default=LRSCredentialType.BASIC_AUTH,
        help_text="Authentication method"
    )
    
    # For Basic Auth / API Key
    api_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="API Key or Basic Auth username (encrypted)"
    )
    api_secret = models.CharField(
        max_length=500,
        blank=True,
        help_text="API Secret or Basic Auth password (encrypted)"
    )
    
    # For OAuth 2.0
    oauth_client_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="OAuth 2.0 Client ID"
    )
    oauth_client_secret = models.CharField(
        max_length=500,
        blank=True,
        help_text="OAuth 2.0 Client Secret (encrypted)"
    )
    oauth_token_url = models.URLField(
        blank=True,
        help_text="OAuth 2.0 Token Endpoint"
    )
    oauth_access_token = models.TextField(
        blank=True,
        help_text="Cached OAuth Access Token (encrypted)"
    )
    oauth_token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="OAuth Token Expiration Time"
    )
    oauth_scope = models.CharField(
        max_length=255,
        blank=True,
        default='statements/write statements/read',
        help_text="OAuth Scope"
    )
    
    # Sync Configuration
    sync_mode = models.CharField(
        max_length=20,
        choices=LRSSyncMode.choices,
        default=LRSSyncMode.PUSH,
        help_text="Synchronization mode"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this LRS is active"
    )
    is_primary = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Primary LRS for statement forwarding"
    )
    
    # Batch Processing
    batch_size = models.PositiveIntegerField(
        default=100,
        help_text="Number of statements to batch per request"
    )
    batch_interval_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Minutes between batch sync attempts"
    )
    
    # Retry Configuration
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum retry attempts for failed statements"
    )
    retry_delay_seconds = models.PositiveIntegerField(
        default=60,
        help_text="Delay between retry attempts in seconds"
    )
    
    # Statement Filtering
    statement_filter = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON filter for which statements to forward (e.g., {'verb': ['completed', 'passed']})"
    )
    include_attachments = models.BooleanField(
        default=False,
        help_text="Whether to include attachments in forwarded statements"
    )
    
    # SCORM Cloud Specific
    scorm_cloud_app_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="SCORM Cloud Application ID"
    )
    scorm_cloud_region = models.CharField(
        max_length=50,
        blank=True,
        default='US',
        help_text="SCORM Cloud Region (US, EU, AU, CA)"
    )
    
    # Health Check
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful sync timestamp"
    )
    last_sync_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="Status of last sync attempt"
    )
    last_error_message = models.TextField(
        blank=True,
        help_text="Last error message if sync failed"
    )
    consecutive_failures = models.PositiveIntegerField(
        default=0,
        help_text="Count of consecutive sync failures"
    )
    
    # Version Info
    xapi_version = models.CharField(
        max_length=10,
        default='1.0.3',
        help_text="xAPI version supported"
    )
    
    # Ownership
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lrs_configurations',
        help_text="User who created this configuration"
    )
    
    class Meta:
        verbose_name = "LRS Configuration"
        verbose_name_plural = "LRS Configurations"
        ordering = ['-is_primary', 'name']
        indexes = [
            models.Index(fields=['lrs_type', 'is_active']),
            models.Index(fields=['is_primary', 'is_active']),
            models.Index(fields=['sync_mode', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.lrs_type})"
    
    def mark_sync_success(self):
        """Mark the last sync as successful."""
        self.last_synced_at = timezone.now()
        self.last_sync_status = 'success'
        self.consecutive_failures = 0
        self.save(update_fields=['last_synced_at', 'last_sync_status', 'consecutive_failures', 'updated_at'])
    
    def mark_sync_failure(self, error_message):
        """Mark the last sync as failed."""
        self.last_sync_status = 'failed'
        self.last_error_message = error_message[:1000]  # Limit length
        self.consecutive_failures += 1
        self.save(update_fields=['last_sync_status', 'last_error_message', 'consecutive_failures', 'updated_at'])
    
    def is_healthy(self):
        """Check if LRS is healthy (not too many consecutive failures)."""
        return self.consecutive_failures < self.max_retries
    
    def should_sync(self):
        """Check if LRS should be synced based on interval."""
        if not self.last_synced_at:
            return True
        next_sync = self.last_synced_at + timedelta(minutes=self.batch_interval_minutes)
        return timezone.now() >= next_sync


class xAPIStatementStatus(models.TextChoices):
    """Delivery status for xAPI statements."""
    PENDING = 'pending', 'Pending'
    QUEUED = 'queued', 'Queued'
    SENDING = 'sending', 'Sending'
    DELIVERED = 'delivered', 'Delivered'
    FAILED = 'failed', 'Failed'
    RETRYING = 'retrying', 'Retrying'
    EXPIRED = 'expired', 'Expired'


class xAPIStatement(BaseModel):
    """
    xAPI statement for forwarding to external LRS.
    Tracks delivery status and retry attempts.
    """
    
    # Statement Identification
    statement_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Unique xAPI statement ID"
    )
    
    # Target LRS
    target_lrs = models.ForeignKey(
        LRSConfiguration,
        on_delete=models.CASCADE,
        related_name='statements',
        help_text="Target LRS for this statement"
    )
    
    # Statement Content
    statement = models.JSONField(
        help_text="Complete xAPI statement JSON"
    )
    verb = models.CharField(
        max_length=255,
        db_index=True,
        help_text="xAPI verb ID"
    )
    actor_email = models.EmailField(
        blank=True,
        db_index=True,
        help_text="Actor email for filtering"
    )
    activity_id = models.CharField(
        max_length=500,
        blank=True,
        db_index=True,
        help_text="Activity ID"
    )
    timestamp = models.DateTimeField(
        db_index=True,
        help_text="Statement timestamp"
    )
    
    # Delivery Status
    status = models.CharField(
        max_length=20,
        choices=xAPIStatementStatus.choices,
        default=xAPIStatementStatus.PENDING,
        db_index=True,
        help_text="Delivery status"
    )
    
    # Retry Tracking
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of delivery attempts"
    )
    last_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last retry timestamp"
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Next scheduled retry"
    )
    
    # Response Tracking
    lrs_response_code = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="HTTP response code from LRS"
    )
    lrs_response_body = models.TextField(
        blank=True,
        help_text="Response body from LRS"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if delivery failed"
    )
    
    # Delivery Confirmation
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When statement was successfully delivered"
    )
    confirmed_by_lrs = models.BooleanField(
        default=False,
        help_text="Whether LRS confirmed receipt"
    )
    
    # Source Information
    source = models.CharField(
        max_length=50,
        default='internal',
        help_text="Source of statement (internal, scorm, import, etc.)"
    )
    source_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="ID of source record (e.g., SCORM registration ID)"
    )
    
    # Expiration
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this statement expires and can be deleted"
    )
    
    class Meta:
        verbose_name = "xAPI Statement"
        verbose_name_plural = "xAPI Statements"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['target_lrs', 'status', 'timestamp']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['verb', 'status']),
            models.Index(fields=['actor_email', 'timestamp']),
            models.Index(fields=['activity_id', 'timestamp']),
            models.Index(fields=['source', 'source_id']),
        ]
    
    def __str__(self):
        return f"Statement {self.statement_id} ({self.status})"
    
    def mark_delivered(self, response_code=None, response_body=''):
        """Mark statement as successfully delivered."""
        self.status = xAPIStatementStatus.DELIVERED
        self.delivered_at = timezone.now()
        self.lrs_response_code = response_code
        self.lrs_response_body = response_body[:1000]  # Limit length
        self.confirmed_by_lrs = True
        self.save(update_fields=[
            'status', 'delivered_at', 'lrs_response_code',
            'lrs_response_body', 'confirmed_by_lrs', 'updated_at'
        ])
    
    def mark_failed(self, error_message, response_code=None):
        """Mark statement as failed."""
        self.status = xAPIStatementStatus.FAILED
        self.error_message = error_message[:1000]
        self.lrs_response_code = response_code
        self.save(update_fields=['status', 'error_message', 'lrs_response_code', 'updated_at'])
    
    def schedule_retry(self, delay_minutes=5):
        """Schedule a retry attempt."""
        self.retry_count += 1
        self.last_retry_at = timezone.now()
        self.next_retry_at = timezone.now() + timedelta(minutes=delay_minutes)
        self.status = xAPIStatementStatus.RETRYING
        self.save(update_fields=['retry_count', 'last_retry_at', 'next_retry_at', 'status', 'updated_at'])
    
    def should_retry(self, max_retries=3):
        """Check if statement should be retried."""
        if self.retry_count >= max_retries:
            return False
        if self.next_retry_at and timezone.now() < self.next_retry_at:
            return False
        return self.status in [xAPIStatementStatus.PENDING, xAPIStatementStatus.FAILED, xAPIStatementStatus.RETRYING]


class LearningRecordAggregation(BaseModel):
    """
    Aggregated learning records from multiple LRS sources.
    Provides unified view for cross-platform analytics.
    """
    
    # Record Identification
    record_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique aggregation record ID"
    )
    
    # Source Information
    source_lrs = models.ForeignKey(
        LRSConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aggregated_records',
        help_text="Source LRS (null for internal records)"
    )
    source_statement_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original statement ID from source LRS"
    )
    
    # Actor Information
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='learning_records',
        help_text="User associated with this record"
    )
    actor_identifier = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Actor identifier (email or account)"
    )
    actor_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Actor display name"
    )
    
    # Activity Information
    activity_id = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Activity ID (URI)"
    )
    activity_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Activity display name"
    )
    activity_type = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Activity type URI"
    )
    
    # Verb Information
    verb_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Verb ID (URI)"
    )
    verb_display = models.CharField(
        max_length=100,
        blank=True,
        help_text="Verb display name"
    )
    
    # Result Information
    result_success = models.BooleanField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Whether the activity was successful"
    )
    result_completion = models.BooleanField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Whether the activity was completed"
    )
    result_score_raw = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Raw score"
    )
    result_score_scaled = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Scaled score (0-1)"
    )
    result_duration = models.DurationField(
        null=True,
        blank=True,
        help_text="Activity duration"
    )
    result_response = models.TextField(
        blank=True,
        help_text="Learner response"
    )
    
    # Context Information
    context_registration = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Registration UUID from context"
    )
    context_platform = models.CharField(
        max_length=100,
        blank=True,
        help_text="Platform from context"
    )
    
    # Timestamps
    statement_timestamp = models.DateTimeField(
        db_index=True,
        help_text="Original statement timestamp"
    )
    stored_timestamp = models.DateTimeField(
        db_index=True,
        help_text="When statement was stored in source LRS"
    )
    
    # Full Statement
    full_statement = models.JSONField(
        help_text="Complete xAPI statement"
    )
    
    # Conflict Resolution
    is_conflict_resolved = models.BooleanField(
        default=True,
        help_text="Whether any conflicts have been resolved"
    )
    conflict_resolution_notes = models.TextField(
        blank=True,
        help_text="Notes on conflict resolution"
    )
    
    class Meta:
        verbose_name = "Learning Record Aggregation"
        verbose_name_plural = "Learning Record Aggregations"
        ordering = ['-statement_timestamp']
        indexes = [
            models.Index(fields=['user', 'statement_timestamp']),
            models.Index(fields=['actor_identifier', 'statement_timestamp']),
            models.Index(fields=['activity_id', 'statement_timestamp']),
            models.Index(fields=['verb_id', 'statement_timestamp']),
            models.Index(fields=['result_success', 'statement_timestamp']),
            models.Index(fields=['result_completion', 'statement_timestamp']),
            models.Index(fields=['context_registration', 'statement_timestamp']),
            models.Index(fields=['source_lrs', 'statement_timestamp']),
        ]
        unique_together = [
            ('source_lrs', 'source_statement_id'),
        ]
    
    def __str__(self):
        return f"{self.actor_identifier} {self.verb_display} {self.activity_name}"


class LRSFederationRule(BaseModel):
    """
    Rules for federating statements between LRS instances.
    Supports complex routing and filtering scenarios.
    """
    
    # Rule Information
    name = models.CharField(
        max_length=255,
        help_text="Rule name"
    )
    description = models.TextField(
        blank=True,
        help_text="Rule description"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this rule is active"
    )
    priority = models.PositiveIntegerField(
        default=100,
        help_text="Rule priority (lower = higher priority)"
    )
    
    # Source LRS (null = internal system)
    source_lrs = models.ForeignKey(
        LRSConfiguration,
        on_delete=models.CASCADE,
        related_name='federation_source_rules',
        null=True,
        blank=True,
        help_text="Source LRS (null for internal statements)"
    )
    
    # Target LRS
    target_lrs = models.ForeignKey(
        LRSConfiguration,
        on_delete=models.CASCADE,
        related_name='federation_target_rules',
        help_text="Target LRS for forwarded statements"
    )
    
    # Filter Conditions (JSON Logic)
    filter_conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON filter conditions (e.g., {'verb': ['completed'], 'actor.email': ['*@example.com']})"
    )
    
    # Transformation Rules
    transform_rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON transformation rules for statement modification"
    )
    
    # Rate Limiting
    rate_limit_per_minute = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum statements per minute (null = unlimited)"
    )
    
    # Statistics
    statements_forwarded = models.PositiveBigIntegerField(
        default=0,
        help_text="Count of statements forwarded by this rule"
    )
    statements_filtered = models.PositiveBigIntegerField(
        default=0,
        help_text="Count of statements filtered by this rule"
    )
    last_triggered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this rule was triggered"
    )
    
    class Meta:
        verbose_name = "LRS Federation Rule"
        verbose_name_plural = "LRS Federation Rules"
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['is_active', 'priority']),
            models.Index(fields=['source_lrs', 'target_lrs']),
        ]
    
    def __str__(self):
        source = self.source_lrs.name if self.source_lrs else 'Internal'
        return f"{source} → {self.target_lrs.name} ({self.name})"
    
    def increment_forwarded(self):
        """Increment forwarded count."""
        self.statements_forwarded += 1
        self.last_triggered_at = timezone.now()
        self.save(update_fields=['statements_forwarded', 'last_triggered_at', 'updated_at'])
    
    def increment_filtered(self):
        """Increment filtered count."""
        self.statements_filtered += 1
        self.last_triggered_at = timezone.now()
        self.save(update_fields=['statements_filtered', 'last_triggered_at', 'updated_at'])


class SCORMCloudSyncLog(BaseModel):
    """
    Synchronization log for SCORM Cloud integration.
    Tracks content hosting, registration sync, and progress updates.
    """
    
    SYNC_TYPE_CONTENT_UPLOAD = 'content_upload'
    SYNC_TYPE_REGISTRATION_CREATE = 'registration_create'
    SYNC_TYPE_PROGRESS_SYNC = 'progress_sync'
    SYNC_TYPE_STATEMENT_FORWARD = 'statement_forward'
    SYNC_TYPE_COURSE_IMPORT = 'course_import'
    
    SYNC_TYPE_CHOICES = [
        (SYNC_TYPE_CONTENT_UPLOAD, 'Content Upload'),
        (SYNC_TYPE_REGISTRATION_CREATE, 'Registration Create'),
        (SYNC_TYPE_PROGRESS_SYNC, 'Progress Sync'),
        (SYNC_TYPE_STATEMENT_FORWARD, 'Statement Forward'),
        (SYNC_TYPE_COURSE_IMPORT, 'Course Import'),
    ]
    
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PARTIAL, 'Partial'),
    ]
    
    # Sync Information
    sync_type = models.CharField(
        max_length=50,
        choices=SYNC_TYPE_CHOICES,
        db_index=True,
        help_text="Type of synchronization"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Sync status"
    )
    
    # SCORM Cloud Reference
    scorm_cloud_course_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="SCORM Cloud course ID"
    )
    scorm_cloud_registration_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="SCORM Cloud registration ID"
    )
    
    # Local Reference
    local_course_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Local course/content ID"
    )
    local_registration_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Local registration ID"
    )
    
    # Sync Details
    request_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Request payload sent to SCORM Cloud"
    )
    response_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Response from SCORM Cloud"
    )
    
    # Progress Tracking
    items_total = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total items to sync"
    )
    items_processed = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Items successfully processed"
    )
    items_failed = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Items that failed"
    )
    
    # Error Tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if sync failed"
    )
    error_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed error information"
    )
    
    # Timing
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When sync started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When sync completed"
    )
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Sync duration in seconds"
    )
    
    # Retry Information
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum retry attempts"
    )
    
    # User
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scorm_cloud_syncs',
        help_text="User who triggered this sync"
    )
    
    class Meta:
        verbose_name = "SCORM Cloud Sync Log"
        verbose_name_plural = "SCORM Cloud Sync Logs"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['sync_type', 'status']),
            models.Index(fields=['scorm_cloud_course_id', 'status']),
            models.Index(fields=['local_course_id', 'status']),
            models.Index(fields=['started_at', 'status']),
        ]
    
    def __str__(self):
        return f"{self.sync_type} ({self.status}) at {self.started_at}"
    
    def mark_started(self):
        """Mark sync as started."""
        self.status = self.STATUS_IN_PROGRESS
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_completed(self, items_processed=0, items_failed=0):
        """Mark sync as completed."""
        self.status = self.STATUS_SUCCESS if items_failed == 0 else self.STATUS_PARTIAL
        self.completed_at = timezone.now()
        self.items_processed = items_processed
        self.items_failed = items_failed
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.save(update_fields=['status', 'completed_at', 'items_processed', 'items_failed', 'duration_seconds', 'updated_at'])
    
    def mark_failed(self, error_message, error_details=None):
        """Mark sync as failed."""
        self.status = self.STATUS_FAILED
        self.error_message = error_message[:1000]
        if error_details:
            self.error_details = error_details
        self.completed_at = timezone.now()
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.save(update_fields=['status', 'error_message', 'error_details', 'completed_at', 'duration_seconds', 'updated_at'])
