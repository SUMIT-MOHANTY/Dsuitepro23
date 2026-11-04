"""
Analytics Services for Enterprise LMS
Provides audit logging services for security events and compliance.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.analytics.models import SecurityAuditLog, AuditLogExport

User = get_user_model()


class AuditLoggingService:
    """
    Service for logging security events to the tamper-evident SecurityAuditLog.
    Provides structured logging for authentication, authorization, data access,
    and system events.
    """
    
    @staticmethod
    def log_auth_event(
        event_type: str,
        actor_user: Optional[User] = None,
        actor_email: str = '',
        outcome: str = 'success',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_path: str = '',
        response_time_ms: Optional[int] = None
    ) -> SecurityAuditLog:
        """
        Log an authentication event.
        
        Events:
        - login_success: User successfully logged in
        - login_failure: Failed login attempt
        - logout: User logged out
        - token_refresh: Access token refreshed
        - mfa_challenge: MFA challenge issued
        - mfa_success: MFA verification successful
        - mfa_failure: MFA verification failed
        - password_change: Password changed
        - password_reset: Password reset requested/completed
        
        Args:
            event_type: Type of authentication event
            actor_user: User who performed the action (if authenticated)
            actor_email: Email of the actor (for failed logins)
            outcome: 'success', 'failure', or 'blocked'
            reason: Reason for failure if applicable
            details: Additional event details
            ip_address: IP address of the request
            user_agent: User agent string
            request_path: Request path
            response_time_ms: Response time in milliseconds
            
        Returns:
            Created SecurityAuditLog instance
        """
        severity = SecurityAuditLog.SEVERITY_INFO
        if event_type in ['login_failure', 'mfa_failure']:
            severity = SecurityAuditLog.SEVERITY_WARNING
        elif outcome == 'failure':
            severity = SecurityAuditLog.SEVERITY_WARNING
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_email or (actor_user.email if actor_user else ''),
            target_resource='authentication',
            target_resource_id='',
            outcome=outcome,
            reason=reason,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='POST',
            request_path=request_path,
            response_time_ms=response_time_ms
        )
    
    @staticmethod
    def log_authorization_decision(
        event_type: str,
        actor_user: Optional[User],
        target_resource: str,
        target_resource_id: str = '',
        outcome: str = 'granted',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_method: str = '',
        request_path: str = '',
        response_time_ms: Optional[int] = None
    ) -> SecurityAuditLog:
        """
        Log an authorization decision (access granted or denied).
        
        Events:
        - access_granted: Access was permitted
        - access_denied: Access was denied
        - role_assigned: Role assigned to user
        - role_revoked: Role revoked from user
        
        Args:
            event_type: Type of authorization event
            actor_user: User attempting the action
            target_resource: Resource being accessed
            target_resource_id: ID of the target resource
            outcome: 'granted' or 'denied'
            reason: Reason for denial if applicable
            details: Additional event details (e.g., required_permission)
            ip_address: IP address of the request
            user_agent: User agent string
            request_method: HTTP method
            request_path: Request path
            response_time_ms: Response time in milliseconds
            
        Returns:
            Created SecurityAuditLog instance
        """
        severity = SecurityAuditLog.SEVERITY_INFO
        if outcome == 'denied':
            severity = SecurityAuditLog.SEVERITY_WARNING
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_user.email if actor_user else '',
            target_resource=target_resource,
            target_resource_id=target_resource_id,
            outcome=outcome,
            reason=reason,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            response_time_ms=response_time_ms
        )
    
    @staticmethod
    def log_sensitive_data_access(
        event_type: str,
        actor_user: User,
        target_resource: str,
        target_resource_id: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_path: str = '',
        response_time_ms: Optional[int] = None
    ) -> SecurityAuditLog:
        """
        Log access to sensitive data (PII, bulk exports, etc.).
        
        Events:
        - bulk_export: Bulk data export performed
        - pii_query: Query accessing PII data
        - audit_log_export: Security audit logs exported
        - user_data_export: User data exported (GDPR)
        
        Args:
            event_type: Type of data access event
            actor_user: User accessing the data
            target_resource: Type of data accessed
            target_resource_id: ID of specific resource if applicable
            details: Additional details (e.g., record_count, filters_used)
            ip_address: IP address of the request
            user_agent: User agent string
            request_path: Request path
            response_time_ms: Response time in milliseconds
            
        Returns:
            Created SecurityAuditLog instance
        """
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_DATA_ACCESS,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=actor_user,
            actor_email=actor_user.email,
            target_resource=target_resource,
            target_resource_id=target_resource_id,
            outcome='success',
            reason='',
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='GET',
            request_path=request_path,
            response_time_ms=response_time_ms
        )
    
    @staticmethod
    def log_session_event(
        event_type: str,
        actor_user: User,
        session_key: str = '',
        outcome: str = 'success',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = ''
    ) -> SecurityAuditLog:
        """
        Log session management events.
        
        Events:
        - session_created: New session created
        - session_revoked: Session revoked by user/admin
        - session_expired: Session expired due to timeout
        
        Args:
            event_type: Type of session event
            actor_user: User whose session is affected
            session_key: Session identifier
            outcome: 'success' or 'failure'
            reason: Reason for revocation/expiration
            details: Additional event details
            ip_address: IP address
            user_agent: User agent string
            
        Returns:
            Created SecurityAuditLog instance
        """
        details = details or {}
        details['session_key_prefix'] = session_key[:8] if session_key else None
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_SESSION,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=actor_user,
            actor_email=actor_user.email,
            target_resource='session',
            target_resource_id=session_key[:16] if session_key else '',
            outcome=outcome,
            reason=reason,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='POST',
            request_path='/api/v1/auth/session/',
            response_time_ms=None
        )
    
    @staticmethod
    def log_impersonation_event(
        event_type: str,
        admin_user: User,
        impersonated_user: User,
        outcome: str = 'success',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_path: str = ''
    ) -> SecurityAuditLog:
        """
        Log admin impersonation events.
        
        Events:
        - impersonation_start: Admin started impersonating user
        - impersonation_end: Admin stopped impersonating user
        
        Args:
            event_type: Type of impersonation event
            admin_user: Admin performing the impersonation
            impersonated_user: User being impersonated
            outcome: 'success' or 'failure'
            reason: Reason for failure if applicable
            details: Additional event details
            ip_address: IP address
            user_agent: User agent string
            request_path: Request path
            
        Returns:
            Created SecurityAuditLog instance
        """
        details = details or {}
        details['impersonated_user_id'] = str(impersonated_user.id)
        details['impersonated_user_email'] = impersonated_user.email
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_IMPERSONATION,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=admin_user,
            actor_email=admin_user.email,
            target_resource='user',
            target_resource_id=str(impersonated_user.id),
            outcome=outcome,
            reason=reason,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='POST',
            request_path=request_path,
            response_time_ms=None
        )
    
    @staticmethod
    def log_system_event(
        event_type: str,
        severity: str,
        details: Optional[Dict[str, Any]] = None,
        reason: str = '',
        actor_user: Optional[User] = None
    ) -> SecurityAuditLog:
        """
        Log system-level security events.
        
        Events:
        - encryption_verification_failed: Encryption check failed
        - secret_rotation_needed: Secret key rotation required
        - security_scan_completed: Security audit scan completed
        - rbac_conflict_detected: Role conflict detected
        
        Args:
            event_type: Type of system event
            severity: Severity level (info/warning/critical)
            details: Additional event details
            reason: Reason or explanation
            actor_user: User associated with the event (if any)
            
        Returns:
            Created SecurityAuditLog instance
        """
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_SYSTEM,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_user.email if actor_user else 'system',
            target_resource='system',
            target_resource_id='',
            outcome='success',
            reason=reason,
            details=details or {},
            ip_address=None,
            user_agent='',
            request_method='',
            request_path='',
            response_time_ms=None
        )


class AuditLogExportService:
    """
    Service for exporting audit logs in various formats.
    Tracks exports for compliance purposes.
    """
    
    @staticmethod
    def create_export_request(
        requested_by: User,
        start_date: datetime,
        end_date: datetime,
        event_categories: Optional[List[str]] = None,
        severity_levels: Optional[List[str]] = None,
        export_format: str = AuditLogExport.FORMAT_CSV
    ) -> AuditLogExport:
        """
        Create a new audit log export request.
        
        Args:
            requested_by: User requesting the export
            start_date: Start of date range
            end_date: End of date range
            event_categories: Filter by event categories
            severity_levels: Filter by severity levels
            export_format: Export format (csv/json/pdf)
            
        Returns:
            Created AuditLogExport instance
        """
        return AuditLogExport.objects.create(
            requested_by=requested_by,
            start_date=start_date,
            end_date=end_date,
            event_categories=event_categories or [],
            severity_levels=severity_levels or [],
            export_format=export_format,
            status=AuditLogExport.STATUS_PENDING
        )
    
    @staticmethod
    def process_export(export_id: str) -> bool:
        """
        Process an audit log export request.
        Generates the export file and updates status.
        
        Args:
            export_id: ID of the export request
            
        Returns:
            True if export was successful, False otherwise
        """
        try:
            export = AuditLogExport.objects.get(id=export_id)
        except AuditLogExport.DoesNotExist:
            return False
        
        export.status = AuditLogExport.STATUS_PROCESSING
        export.started_at = timezone.now()
        export.save(update_fields=['status', 'started_at'])
        
        try:
            # Build query
            queryset = SecurityAuditLog.objects.filter(
                timestamp__gte=export.start_date,
                timestamp__lte=export.end_date
            )
            
            if export.event_categories:
                queryset = queryset.filter(event_category__in=export.event_categories)
            
            if export.severity_levels:
                queryset = queryset.filter(severity__in=export.severity_levels)
            
            export.record_count = queryset.count()
            
            # Generate file based on format
            if export.export_format == AuditLogExport.FORMAT_CSV:
                file_path = AuditLogExportService._export_to_csv(queryset, export_id)
            elif export.export_format == AuditLogExport.FORMAT_JSON:
                file_path = AuditLogExportService._export_to_json(queryset, export_id)
            else:
                # PDF not implemented in base version
                raise NotImplementedError("PDF export not implemented")
            
            export.file_path = file_path
            export.status = AuditLogExport.STATUS_COMPLETED
            export.completed_at = timezone.now()
            export.save(update_fields=['file_path', 'status', 'completed_at', 'record_count'])
            
            return True
            
        except Exception as e:
            export.status = AuditLogExport.STATUS_FAILED
            export.error_message = str(e)
            export.completed_at = timezone.now()
            export.save(update_fields=['status', 'error_message', 'completed_at'])
            return False
    
    @staticmethod
    def _export_to_csv(queryset, export_id: str) -> str:
        """
        Export audit logs to CSV format.
        
        Args:
            queryset: QuerySet of SecurityAuditLog entries
            export_id: Export request ID
            
        Returns:
            Path to the generated CSV file
        """
        import csv
        import os
        from django.conf import settings
        
        export_dir = os.path.join(settings.MEDIA_ROOT, 'audit_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        file_path = os.path.join(export_dir, f'audit_export_{export_id}.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow([
                'timestamp', 'event_type', 'event_category', 'severity',
                'actor_email', 'target_resource', 'target_resource_id',
                'outcome', 'reason', 'ip_address', 'request_method',
                'request_path', 'response_time_ms', 'details'
            ])
            
            # Write data
            for log in queryset.iterator():
                writer.writerow([
                    log.timestamp.isoformat(),
                    log.event_type,
                    log.event_category,
                    log.severity,
                    log.actor_email,
                    log.target_resource,
                    log.target_resource_id,
                    log.outcome,
                    log.reason,
                    log.ip_address,
                    log.request_method,
                    log.request_path,
                    log.response_time_ms,
                    json.dumps(log.details)
                ])
        
        return file_path
    
    @staticmethod
    def _export_to_json(queryset, export_id: str) -> str:
        """
        Export audit logs to JSON format.
        
        Args:
            queryset: QuerySet of SecurityAuditLog entries
            export_id: Export request ID
            
        Returns:
            Path to the generated JSON file
        """
        import os
        from django.conf import settings
        
        export_dir = os.path.join(settings.MEDIA_ROOT, 'audit_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        file_path = os.path.join(export_dir, f'audit_export_{export_id}.json')
        
        data = []
        for log in queryset.iterator():
            data.append({
                'timestamp': log.timestamp.isoformat(),
                'event_type': log.event_type,
                'event_category': log.event_category,
                'severity': log.severity,
                'actor_email': log.actor_email,
                'target_resource': log.target_resource,
                'target_resource_id': log.target_resource_id,
                'outcome': log.outcome,
                'reason': log.reason,
                'ip_address': str(log.ip_address) if log.ip_address else None,
                'user_agent': log.user_agent,
                'request_method': log.request_method,
                'request_path': log.request_path,
                'response_time_ms': log.response_time_ms,
                'details': log.details,
                'current_hash': log.current_hash,
                'previous_hash': log.previous_hash,
            })
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        return file_path


class AuditLogQueryService:
    """
    Service for querying and analyzing audit logs.
    """
    
    @staticmethod
    def get_failed_login_attempts(
        ip_address: Optional[str] = None,
        email: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SecurityAuditLog]:
        """
        Get failed login attempts for security monitoring.
        
        Args:
            ip_address: Filter by IP address
            email: Filter by email
            since: Filter by time range
            limit: Maximum number of results
            
        Returns:
            List of SecurityAuditLog entries
        """
        queryset = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            outcome='failure'
        )
        
        if ip_address:
            queryset = queryset.filter(ip_address=ip_address)
        
        if email:
            queryset = queryset.filter(actor_email=email)
        
        if since:
            queryset = queryset.filter(timestamp__gte=since)
        
        return list(queryset.order_by('-timestamp')[:limit])
    
    @staticmethod
    def get_access_denials(
        user: Optional[User] = None,
        resource: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SecurityAuditLog]:
        """
        Get access denial events for security review.
        
        Args:
            user: Filter by user
            resource: Filter by resource type
            since: Filter by time range
            limit: Maximum number of results
            
        Returns:
            List of SecurityAuditLog entries
        """
        queryset = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            outcome='denied'
        )
        
        if user:
            queryset = queryset.filter(actor_user=user)
        
        if resource:
            queryset = queryset.filter(target_resource=resource)
        
        if since:
            queryset = queryset.filter(timestamp__gte=since)
        
        return list(queryset.order_by('-timestamp')[:limit])
    
    @staticmethod
    def get_user_activity(
        user: User,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_categories: Optional[List[str]] = None
    ) -> List[SecurityAuditLog]:
        """
        Get all activity for a specific user.
        
        Args:
            user: User to query
            start_date: Start of date range
            end_date: End of date range
            event_categories: Filter by categories
            
        Returns:
            List of SecurityAuditLog entries
        """
        queryset = SecurityAuditLog.objects.filter(actor_user=user)
        
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        if event_categories:
            queryset = queryset.filter(event_category__in=event_categories)
        
        return list(queryset.order_by('-timestamp'))
    
    @staticmethod
    def get_suspicious_activity(
        threshold: int = 5,
        time_window_minutes: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Detect suspicious activity patterns.
        
        Args:
            threshold: Number of failed attempts to flag
            time_window_minutes: Time window for counting attempts
            
        Returns:
            List of suspicious activity summaries
        """
        from django.db.models import Count
        from django.utils import timezone
        from datetime import timedelta
        
        since = timezone.now() - timedelta(minutes=time_window_minutes)
        
        # Group by IP and count failed logins
        suspicious_ips = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            timestamp__gte=since
        ).values('ip_address').annotate(
            failure_count=Count('id')
        ).filter(failure_count__gte=threshold)
        
        results = []
        for item in suspicious_ips:
            results.append({
                'type': 'brute_force_attempt',
                'ip_address': item['ip_address'],
                'failure_count': item['failure_count'],
                'time_window_minutes': time_window_minutes,
                'recommendation': 'Consider blocking IP or requiring CAPTCHA'
            })
        
        return results


# Convenience functions for common logging operations

def log_login_success(user: User, ip_address: str, user_agent: str, request_path: str = '/api/v1/auth/login/'):
    """Log successful login."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
        actor_user=user,
        outcome='success',
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path
    )


def log_login_failure(email: str, ip_address: str, user_agent: str, reason: str = '', request_path: str = '/api/v1/auth/login/'):
    """Log failed login attempt."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
        actor_email=email,
        outcome='failure',
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path
    )


def log_logout(user: User, ip_address: str, user_agent: str):
    """Log user logout."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_LOGOUT,
        actor_user=user,
        outcome='success',
        ip_address=ip_address,
        user_agent=user_agent,
        request_path='/api/v1/auth/logout/'
    )


def log_token_refresh(user: User, ip_address: str, user_agent: str):
    """Log token refresh."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_TOKEN_REFRESH,
        actor_user=user,
        outcome='success',
        ip_address=ip_address,
        user_agent=user_agent,
        request_path='/api/v1/auth/refresh/'
    )


def log_access_denied(user: User, resource: str, resource_id: str, reason: str, ip_address: str, request_path: str):
    """Log access denial."""
    return AuditLoggingService.log_authorization_decision(
        event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
        actor_user=user,
        target_resource=resource,
        target_resource_id=resource_id,
        outcome='denied',
        reason=reason,
        ip_address=ip_address,
        request_path=request_path
    )


def log_bulk_export(user: User, record_count: int, filters: Dict[str, Any], ip_address: str):
    """Log bulk data export."""
    return AuditLoggingService.log_sensitive_data_access(
        event_type=SecurityAuditLog.EVENT_BULK_EXPORT,
        actor_user=user,
        target_resource='data_export',
        details={'record_count': record_count, 'filters': filters},
        ip_address=ip_address,
        request_path='/api/v1/analytics/audit-logs/export/'
    )
