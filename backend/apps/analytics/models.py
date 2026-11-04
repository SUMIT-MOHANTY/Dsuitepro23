"""
Analytics Models for Enterprise LMS
Provides data models for reporting and analytics.
"""

import hashlib
import json
from datetime import datetime

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
