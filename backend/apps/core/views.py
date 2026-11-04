"""
Core Views for Enterprise LMS
Provides healthcheck, system status, and security health endpoints.
"""

import hashlib
import logging
from datetime import datetime, timedelta

from django.db import connection
from django.db.utils import OperationalError
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.core.services import (
    EncryptionVerificationService,
    SecurityAuditService,
    SessionSecurityService,
)

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """
    Health check endpoint for monitoring and load balancer health checks.
    
    Returns system status including database connectivity.
    Used by monitoring tools and deployment health checks.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        summary="Health Check",
        description="Returns the current health status of the API and database connectivity.",
        responses={
            200: OpenApiResponse(
                description="Service is healthy",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "ok"},
                        "database": {"type": "string", "example": "connected"},
                    },
                },
            ),
            503: OpenApiResponse(
                description="Service is unhealthy",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "error"},
                        "database": {"type": "string", "example": "disconnected"},
                    },
                },
            ),
        },
        tags=["system"],
    )
    def get(self, request):
        """
        GET /api/health/
        
        Returns health status with database connectivity check.
        """
        health_status = {
            "status": "ok",
            "database": "connected",
        }
        status_code = status.HTTP_200_OK

        # Check database connectivity
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError:
            health_status["status"] = "error"
            health_status["database"] = "disconnected"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(health_status, status=status_code)


class SystemInfoView(APIView):
    """
    System information endpoint.
    
    Returns basic information about the API version and environment.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        summary="System Information",
        description="Returns API version and environment information.",
        responses={
            200: OpenApiResponse(
                description="System information",
                response={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "environment": {"type": "string"},
                    },
                },
            ),
        },
        tags=["system"],
    )
    def get(self, request):
        """
        GET /api/info/
        
        Returns system information.
        """
        info = {
            "name": "Enterprise LMS API",
            "version": "1.0.0",
            "environment": "development" if settings.DEBUG else "production",
        }
        
        return Response(info)


class SecurityHealthView(APIView):
    """
    Security health check endpoint for SOC 2 compliance monitoring.
    
    Returns encryption status, TLS configuration, secret rotation status,
    and security configuration verification.
    
    Requires admin authentication.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        summary="Security Health Check",
        description="Returns comprehensive security health status including encryption, TLS, and secrets.",
        responses={
            200: OpenApiResponse(
                description="Security health status",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "healthy"},
                        "encryption": {"type": "object"},
                        "tls": {"type": "object"},
                        "secrets": {"type": "object"},
                        "alerts": {"type": "array"},
                    },
                },
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Admin access required"),
        },
        tags=["security"],
    )
    def get(self, request):
        """
        GET /api/v1/core/security-health/
        
        Returns comprehensive security health status:
        - Encryption at-rest status
        - TLS configuration
        - Secret rotation status
        - Security alerts
        """
        try:
            # Gather security health data
            encryption_status = EncryptionVerificationService.verify_at_rest_encryption()
            tls_status = EncryptionVerificationService.enforce_tls_config()
            secret_status = EncryptionVerificationService.detect_stale_secrets()
            
            # Determine overall status
            overall_status = "healthy"
            alerts = []
            
            if not encryption_status.get('encrypted', False):
                overall_status = "warning"
                alerts.append({
                    "severity": "warning",
                    "code": "ENCRYPTION_NOT_VERIFIED",
                    "message": "Database encryption status could not be verified",
                    "recommendation": "Verify PostgreSQL TDE or application-level encryption"
                })
            
            if not tls_status.get('tls_enforced', False):
                overall_status = "critical"
                alerts.append({
                    "severity": "critical",
                    "code": "TLS_NOT_ENFORCED",
                    "message": "TLS 1.3 is not enforced",
                    "recommendation": "Enable TLS 1.3-only mode in production settings"
                })
            
            if secret_status.get('stale_secrets_detected', False):
                overall_status = "warning"
                for secret in secret_status.get('stale_secrets', []):
                    alerts.append({
                        "severity": "warning",
                        "code": "STALE_SECRET",
                        "message": f"Secret '{secret['name']}' may be stale",
                        "details": secret,
                        "recommendation": "Rotate secret immediately"
                    })
            
            # Check certificate expiry
            cert_expiry = tls_status.get('certificate_expiry')
            if cert_expiry:
                days_until_expiry = (cert_expiry - datetime.now()).days
                if days_until_expiry < 30:
                    overall_status = "warning"
                    alerts.append({
                        "severity": "warning",
                        "code": "CERTIFICATE_EXPIRING",
                        "message": f"TLS certificate expires in {days_until_expiry} days",
                        "recommendation": "Renew certificate before expiry"
                    })
            
            response_data = {
                "status": overall_status,
                "timestamp": datetime.now().isoformat(),
                "encryption": {
                    "at_rest": encryption_status,
                    "verified": encryption_status.get('encrypted', False)
                },
                "tls": {
                    "enforced": tls_status.get('tls_enforced', False),
                    "min_version": tls_status.get('min_version', 'unknown'),
                    "certificate_expiry": cert_expiry.isoformat() if cert_expiry else None,
                    "hsts_enabled": tls_status.get('hsts_enabled', False)
                },
                "secrets": {
                    "rotation_required": secret_status.get('stale_secrets_detected', False),
                    "stale_count": len(secret_status.get('stale_secrets', [])),
                    "details": secret_status.get('stale_secrets', [])
                },
                "alerts": alerts,
                "recommendations": self._generate_recommendations(alerts)
            }
            
            # Log security health check
            logger.info(f"Security health check performed by {request.user.email}")
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Security health check error: {str(e)}")
            return Response({
                "status": "error",
                "error": "Failed to perform security health check",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_recommendations(self, alerts):
        """Generate security recommendations based on alerts."""
        recommendations = []
        
        critical_count = sum(1 for a in alerts if a['severity'] == 'critical')
        warning_count = sum(1 for a in alerts if a['severity'] == 'warning')
        
        if critical_count > 0:
            recommendations.append(
                f"Address {critical_count} critical security issue(s) immediately"
            )
        
        if warning_count > 0:
            recommendations.append(
                f"Review and resolve {warning_count} warning(s) within 7 days"
            )
        
        if not any(a['code'] == 'TLS_NOT_ENFORCED' for a in alerts):
            recommendations.append("TLS configuration is compliant")
        
        if not recommendations:
            recommendations.append("Security posture is healthy - maintain regular audits")
        
        return recommendations


class SecurityAuditReportView(APIView):
    """
    Security audit report endpoint.
    
    Returns comprehensive security audit results including:
    - Default password detection
    - Exposed debug endpoints
    - Missing security headers
    - Dependency vulnerabilities
    
    Requires admin authentication.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        summary="Security Audit Report",
        description="Returns comprehensive security audit results.",
        responses={
            200: OpenApiResponse(
                description="Security audit report",
                response={
                    "type": "object",
                    "properties": {
                        "scan_id": {"type": "string"},
                        "timestamp": {"type": "string"},
                        "findings": {"type": "array"},
                        "summary": {"type": "object"},
                    },
                },
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Admin access required"),
        },
        tags=["security"],
    )
    def get(self, request):
        """
        GET /api/v1/core/security-audit/
        
        Returns comprehensive security audit report.
        """
        try:
            # Run security audit
            audit_results = SecurityAuditService.run_security_audit()
            
            # Generate scan ID
            scan_id = hashlib.sha256(
                f"{request.user.id}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]
            
            response_data = {
                "scan_id": scan_id,
                "timestamp": datetime.now().isoformat(),
                "performed_by": request.user.email,
                "findings": audit_results.get('findings', []),
                "summary": {
                    "total_checks": audit_results.get('total_checks', 0),
                    "passed": audit_results.get('passed', 0),
                    "warnings": audit_results.get('warnings', 0),
                    "critical": audit_results.get('critical', 0),
                    "compliance_score": self._calculate_compliance_score(audit_results)
                },
                "recommendations": audit_results.get('recommendations', [])
            }
            
            # Log audit report generation
            logger.info(f"Security audit report generated by {request.user.email}")
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Security audit error: {str(e)}")
            return Response({
                "error": "Failed to generate security audit report",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _calculate_compliance_score(self, audit_results):
        """Calculate SOC 2 compliance score from audit results."""
        total = audit_results.get('total_checks', 0)
        if total == 0:
            return 100
        
        passed = audit_results.get('passed', 0)
        warnings = audit_results.get('warnings', 0)
        critical = audit_results.get('critical', 0)
        
        # Weight: passed=1, warning=0.5, critical=0
        score = ((passed * 1) + (warnings * 0.5) + (critical * 0)) / total * 100
        return round(score, 1)


class SessionSecurityView(APIView):
    """
    Session security management endpoint.
    
    Provides session security status and enforcement capabilities.
    Requires admin authentication.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        summary="Session Security Status",
        description="Returns current session security configuration and active sessions.",
        responses={
            200: OpenApiResponse(
                description="Session security status",
                response={
                    "type": "object",
                    "properties": {
                        "configuration": {"type": "object"},
                        "active_sessions": {"type": "integer"},
                        "violations": {"type": "array"},
                    },
                },
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Admin access required"),
        },
        tags=["security"],
    )
    def get(self, request):
        """
        GET /api/v1/core/session-security/
        
        Returns session security configuration and status.
        """
        try:
            # Get session configuration from settings
            config = {
                "absolute_timeout_hours": getattr(settings, 'SESSION_ABSOLUTE_TIMEOUT', 24),
                "idle_timeout_minutes": getattr(settings, 'SESSION_IDLE_TIMEOUT', 30),
                "concurrent_limit": getattr(settings, 'SESSION_CONCURRENT_LIMIT', 5),
                "device_fingerprinting": getattr(settings, 'SESSION_DEVICE_FINGERPRINT', True),
                "secure_cookies": getattr(settings, 'SESSION_COOKIE_SECURE', not settings.DEBUG),
                "http_only": getattr(settings, 'SESSION_COOKIE_HTTPONLY', True),
                "same_site": getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
            }
            
            # Count active sessions
            from apps.users.models import UserSession
            active_sessions = UserSession.objects.filter(
                is_revoked=False
            ).count()
            
            # Check for session violations
            violations = SessionSecurityService.enforce_session_limits()
            
            response_data = {
                "configuration": config,
                "active_sessions": active_sessions,
                "violations": violations,
                "compliant": len(violations) == 0,
                "timestamp": datetime.now().isoformat()
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Session security check error: {str(e)}")
            return Response({
                "error": "Failed to retrieve session security status",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="Enforce Session Limits",
        description="Manually enforce session limits and revoke excess sessions.",
        responses={
            200: OpenApiResponse(
                description="Session enforcement results",
                response={
                    "type": "object",
                    "properties": {
                        "enforced": {"type": "boolean"},
                        "revoked_sessions": {"type": "integer"},
                    },
                },
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Admin access required"),
        },
        tags=["security"],
    )
    def post(self, request):
        """
        POST /api/v1/core/session-security/
        
        Manually enforce session limits and revoke excess sessions.
        """
        try:
            violations = SessionSecurityService.enforce_session_limits()
            
            # Revoke sessions for users exceeding limits
            revoked_count = 0
            for violation in violations:
                if violation.get('action') == 'revoke_excess':
                    revoked_count += violation.get('revoked_count', 0)
            
            # Log enforcement action
            logger.info(
                f"Session limits enforced by {request.user.email}: "
                f"{revoked_count} sessions revoked"
            )
            
            return Response({
                "enforced": True,
                "violations_found": len(violations),
                "revoked_sessions": revoked_count,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Session enforcement error: {str(e)}")
            return Response({
                "error": "Failed to enforce session limits",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
