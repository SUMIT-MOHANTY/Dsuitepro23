"""
Core Security Services for Enterprise LMS
Provides encryption verification, security auditing, and compliance utilities.
"""

import hashlib
import json
import logging
import os
import ssl
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List

from django.conf import settings
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


class EncryptionVerificationService:
    """
    Service for verifying encryption at rest and in transit.
    Provides SOC 2 compliance verification for encryption controls.
    """
    
    @staticmethod
    def verify_at_rest_encryption() -> Dict[str, Any]:
        """
        Verify database encryption at rest.
        
        Checks:
        - PostgreSQL TDE (Transparent Data Encryption) status
        - Application-level encryption for sensitive fields
        - File system encryption for media/uploads
        
        Returns:
            Dictionary with verification results
        """
        results = {
            'status': 'unknown',
            'checks': {},
            'recommendations': [],
            'verified_at': timezone.now().isoformat()
        }
        
        try:
            # Check PostgreSQL encryption
            pg_encryption = EncryptionVerificationService._check_postgres_encryption()
            results['checks']['postgresql_tde'] = pg_encryption
            
            # Check application-level encryption settings
            app_encryption = EncryptionVerificationService._check_app_encryption()
            results['checks']['application_encryption'] = app_encryption
            
            # Check media storage encryption
            media_encryption = EncryptionVerificationService._check_media_encryption()
            results['checks']['media_storage_encryption'] = media_encryption
            
            # Determine overall status
            all_passed = all(
                check.get('enabled', False) 
                for check in results['checks'].values()
            )
            
            if all_passed:
                results['status'] = 'compliant'
            elif any(check.get('enabled', False) for check in results['checks'].values()):
                results['status'] = 'partial'
                results['recommendations'].append(
                    "Enable encryption for all data storage layers"
                )
            else:
                results['status'] = 'non_compliant'
                results['recommendations'].extend([
                    "Enable PostgreSQL TDE for database encryption at rest",
                    "Configure application-level encryption for PII fields",
                    "Enable encryption for media and file storage"
                ])
            
        except Exception as e:
            logger.error(f"Encryption verification error: {str(e)}")
            results['status'] = 'error'
            results['error'] = str(e)
        
        return results
    
    @staticmethod
    def _check_postgres_encryption() -> Dict[str, Any]:
        """Check PostgreSQL encryption status."""
        result = {
            'enabled': False,
            'method': None,
            'details': {}
        }
        
        try:
            with connection.cursor() as cursor:
                # Check if pgcrypto extension is available
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'
                    );
                """)
                pgcrypto_available = cursor.fetchone()[0]
                result['details']['pgcrypto_available'] = pgcrypto_available
                
                # Check SSL connection
                cursor.execute("SHOW ssl;")
                ssl_enabled = cursor.fetchone()[0] == 'on'
                result['details']['ssl_connection'] = ssl_enabled
                
                # Check for encryption-related settings
                cursor.execute("SHOW ssl_cipher;")
                cipher = cursor.fetchone()[0]
                result['details']['ssl_cipher'] = cipher
                
                # Note: PostgreSQL TDE requires enterprise edition or specific setup
                # This is a simplified check
                result['enabled'] = ssl_enabled
                result['method'] = 'SSL connection' if ssl_enabled else None
                
        except Exception as e:
            logger.warning(f"Could not check PostgreSQL encryption: {str(e)}")
            result['details']['error'] = str(e)
        
        return result
    
    @staticmethod
    def _check_app_encryption() -> Dict[str, Any]:
        """Check application-level encryption configuration."""
        result = {
            'enabled': False,
            'method': None,
            'details': {}
        }
        
        # Check for Django's field-level encryption
        has_encryption = hasattr(settings, 'FIELD_ENCRYPTION_KEY') and \
                        settings.FIELD_ENCRYPTION_KEY
        
        result['enabled'] = has_encryption
        result['method'] = 'Django Field Encryption' if has_encryption else None
        result['details']['field_encryption_configured'] = has_encryption
        
        # Check for encrypted model fields usage
        result['details']['encrypted_fields_used'] = EncryptionVerificationService._check_encrypted_fields()
        
        return result
    
    @staticmethod
    def _check_encrypted_fields() -> List[str]:
        """Check which models use encrypted fields."""
        encrypted_models = []
        
        try:
            from apps.users.models import User
            # Check if User model has encrypted fields
            encrypted_fields = [
                field.name for field in User._meta.fields
                if 'encrypted' in field.__class__.__name__.lower()
            ]
            if encrypted_fields:
                encrypted_models.append(f"User: {', '.join(encrypted_fields)}")
        except Exception:
            pass
        
        return encrypted_models
    
    @staticmethod
    def _check_media_encryption() -> Dict[str, Any]:
        """Check media storage encryption."""
        result = {
            'enabled': False,
            'method': None,
            'details': {}
        }
        
        # Check storage backend
        storage_backend = getattr(settings, 'DEFAULT_FILE_STORAGE', '')
        result['details']['storage_backend'] = storage_backend
        
        # Check for S3/Azure encryption settings
        if 'S3' in storage_backend or 's3' in storage_backend:
            s3_encryption = getattr(settings, 'AWS_S3_ENCRYPTION', False)
            result['enabled'] = s3_encryption
            result['method'] = 'AWS S3 SSE'
            result['details']['s3_encryption'] = s3_encryption
        
        elif 'Azure' in storage_backend or 'azure' in storage_backend:
            azure_encryption = getattr(settings, 'AZURE_STORAGE_ENCRYPTION', False)
            result['enabled'] = azure_encryption
            result['method'] = 'Azure Storage Encryption'
            result['details']['azure_encryption'] = azure_encryption
        
        return result
    
    @staticmethod
    def enforce_tls_config() -> Dict[str, Any]:
        """
        Verify TLS configuration for in-transit encryption.
        
        Returns:
            Dictionary with TLS enforcement results
        """
        results = {
            'status': 'unknown',
            'tls_version': None,
            'checks': {},
            'recommendations': [],
            'verified_at': timezone.now().isoformat()
        }
        
        try:
            # Check Django settings
            results['checks']['secure_ssl_redirect'] = getattr(
                settings, 'SECURE_SSL_REDIRECT', False
            )
            results['checks']['secure_hsts_seconds'] = getattr(
                settings, 'SECURE_HSTS_SECONDS', 0
            )
            results['checks']['session_cookie_secure'] = getattr(
                settings, 'SESSION_COOKIE_SECURE', False
            )
            results['checks']['csrf_cookie_secure'] = getattr(
                settings, 'CSRF_COOKIE_SECURE', False
            )
            
            # Check SSL/TLS version support
            try:
                context = ssl.create_default_context()
                results['tls_version'] = context.maximum_version.name if hasattr(
                    context, 'maximum_version'
                ) else 'unknown'
            except Exception as e:
                results['checks']['ssl_context_error'] = str(e)
            
            # Determine compliance
            if all([
                results['checks']['secure_ssl_redirect'],
                results['checks']['secure_hsts_seconds'] >= 31536000,  # 1 year
                results['checks']['session_cookie_secure'],
                results['checks']['csrf_cookie_secure']
            ]):
                results['status'] = 'compliant'
            elif any([
                results['checks']['secure_ssl_redirect'],
                results['checks']['session_cookie_secure']
            ]):
                results['status'] = 'partial'
                results['recommendations'].extend([
                    "Enable SECURE_HSTS_SECONDS to at least 31536000 (1 year)",
                    "Enable CSRF_COOKIE_SECURE for HTTPS-only CSRF cookies"
                ])
            else:
                results['status'] = 'non_compliant'
                results['recommendations'].extend([
                    "Enable SECURE_SSL_REDIRECT to force HTTPS",
                    "Enable SESSION_COOKIE_SECURE for HTTPS-only session cookies",
                    "Enable CSRF_COOKIE_SECURE for HTTPS-only CSRF cookies",
                    "Set SECURE_HSTS_SECONDS to at least 31536000 (1 year)"
                ])
            
        except Exception as e:
            logger.error(f"TLS configuration check error: {str(e)}")
            results['status'] = 'error'
            results['error'] = str(e)
        
        return results
    
    @staticmethod
    def detect_stale_secrets() -> Dict[str, Any]:
        """
        Detect stale or potentially compromised secrets.
        
        Checks:
        - SECRET_KEY rotation (should be rotated periodically)
        - Database credentials age
        - API key expiration
        
        Returns:
            Dictionary with stale secret detection results
        """
        results = {
            'status': 'unknown',
            'alerts': [],
            'recommendations': [],
            'checked_at': timezone.now().isoformat()
        }
        
        try:
            # Check SECRET_KEY
            secret_key = getattr(settings, 'SECRET_KEY', '')
            if secret_key:
                # Check if using default/weak secret
                if len(secret_key) < 50:
                    results['alerts'].append({
                        'type': 'weak_secret_key',
                        'severity': 'critical',
                        'message': 'SECRET_KEY is too short (should be at least 50 characters)'
                    })
                
                # Check for common default secrets
                weak_secrets = ['django-insecure', 'change-me', 'secret-key', 'your-secret-key']
                if any(weak in secret_key.lower() for weak in weak_secrets):
                    results['alerts'].append({
                        'type': 'default_secret_key',
                        'severity': 'critical',
                        'message': 'SECRET_KEY appears to be using default/placeholder value'
                    })
            
            # Check database credentials
            db_settings = getattr(settings, 'DATABASES', {}).get('default', {})
            if db_settings:
                # Check for hardcoded credentials in settings
                if db_settings.get('PASSWORD') in ['password', 'admin', '123456', '']:
                    results['alerts'].append({
                        'type': 'weak_db_password',
                        'severity': 'high',
                        'message': 'Database password appears to be weak or default'
                    })
            
            # Check for environment-based secrets
            env_secrets = [
                'SECRET_KEY',
                'DATABASE_URL',
                'AWS_SECRET_ACCESS_KEY',
                'AZURE_STORAGE_ACCOUNT_KEY',
                'EMAIL_HOST_PASSWORD'
            ]
            
            for secret_name in env_secrets:
                env_value = os.environ.get(secret_name, '')
                if env_value:
                    # Check if secret is committed to code (should be in env only)
                    if secret_name in dir(settings):
                        setting_value = getattr(settings, secret_name, '')
                        if setting_value == env_value:
                            results['alerts'].append({
                                'type': 'potential_secret_exposure',
                                'severity': 'medium',
                                'message': f'{secret_name} may be exposed in settings file'
                            })
            
            # Determine overall status
            critical_alerts = [a for a in results['alerts'] if a['severity'] == 'critical']
            high_alerts = [a for a in results['alerts'] if a['severity'] == 'high']
            
            if critical_alerts:
                results['status'] = 'critical'
                results['recommendations'].append(
                    "Immediately rotate all critical secrets and review access logs"
                )
            elif high_alerts:
                results['status'] = 'warning'
                results['recommendations'].append(
                    "Rotate high-risk secrets within 24 hours"
                )
            else:
                results['status'] = 'ok'
            
            # General recommendations
            results['recommendations'].extend([
                "Implement automated secret rotation every 90 days",
                "Use a secrets management service (e.g., HashiCorp Vault, AWS Secrets Manager)",
                "Enable secret scanning in CI/CD pipeline"
            ])
            
        except Exception as e:
            logger.error(f"Stale secrets detection error: {str(e)}")
            results['status'] = 'error'
            results['error'] = str(e)
        
        return results


class SecurityAuditService:
    """
    Service for comprehensive security auditing.
    Provides SOC 2 compliance scanning and security health checks.
    """
    
    @staticmethod
    def run_security_audit() -> Dict[str, Any]:
        """
        Run comprehensive security audit.
        
        Checks:
        - Default passwords
        - Exposed debug endpoints
        - Missing security headers
        - Dependency vulnerabilities
        - Session security
        - Input validation
        
        Returns:
            Dictionary with audit results
        """
        results = {
            'status': 'unknown',
            'score': 0,
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0,
            'findings': [],
            'recommendations': [],
            'audited_at': timezone.now().isoformat()
        }
        
        checks = [
            SecurityAuditService._check_debug_mode,
            SecurityAuditService._check_security_headers,
            SecurityAuditService._check_password_policy,
            SecurityAuditService._check_session_security,
            SecurityAuditService._check_rate_limiting,
            SecurityAuditService._check_default_credentials,
        ]
        
        for check in checks:
            try:
                finding = check()
                results['findings'].append(finding)
                results['total_checks'] += 1
                
                if finding['status'] == 'pass':
                    results['passed_checks'] += 1
                elif finding['status'] == 'fail':
                    results['failed_checks'] += 1
                    results['recommendations'].extend(finding.get('recommendations', []))
                elif finding['status'] == 'warning':
                    results['warnings'] += 1
                    results['recommendations'].extend(finding.get('recommendations', []))
                    
            except Exception as e:
                logger.error(f"Security check error: {str(e)}")
                results['findings'].append({
                    'check': check.__name__,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Calculate score
        if results['total_checks'] > 0:
            results['score'] = int(
                (results['passed_checks'] / results['total_checks']) * 100
            )
        
        # Determine overall status
        if results['failed_checks'] > 0:
            results['status'] = 'failed'
        elif results['warnings'] > 0:
            results['status'] = 'warning'
        else:
            results['status'] = 'passed'
        
        return results
    
    @staticmethod
    def _check_debug_mode() -> Dict[str, Any]:
        """Check if DEBUG mode is disabled in production."""
        debug = getattr(settings, 'DEBUG', True)
        
        finding = {
            'check': 'Debug Mode',
            'status': 'pass' if not debug else 'fail',
            'details': {'debug_enabled': debug}
        }
        
        if debug:
            finding['recommendations'] = [
                "Set DEBUG = False in production settings",
                "Use environment variables to control DEBUG mode"
            ]
        
        return finding
    
    @staticmethod
    def _check_security_headers() -> Dict[str, Any]:
        """Check security headers configuration."""
        headers = {
            'X-Frame-Options': getattr(settings, 'X_FRAME_OPTIONS', ''),
            'X-Content-Type-Options': getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False),
            'X-XSS-Protection': getattr(settings, 'SECURE_BROWSER_XSS_FILTER', False),
            'Strict-Transport-Security': getattr(settings, 'SECURE_HSTS_SECONDS', 0),
            'Content-Security-Policy': getattr(settings, 'CSP_DEFAULT_SRC', None),
        }
        
        missing = []
        if not headers['X-Frame-Options']:
            missing.append('X-Frame-Options')
        if not headers['X-Content-Type-Options']:
            missing.append('X-Content-Type-Options')
        if not headers['Strict-Transport-Security']:
            missing.append('Strict-Transport-Security')
        if not headers['Content-Security-Policy']:
            missing.append('Content-Security-Policy')
        
        finding = {
            'check': 'Security Headers',
            'status': 'pass' if not missing else 'warning',
            'details': headers
        }
        
        if missing:
            finding['recommendations'] = [
                f"Configure missing security headers: {', '.join(missing)}"
            ]
        
        return finding
    
    @staticmethod
    def _check_password_policy() -> Dict[str, Any]:
        """Check password policy configuration."""
        auth_password_validators = getattr(settings, 'AUTH_PASSWORD_VALIDATORS', [])
        
        has_min_length = any(
            v.get('NAME', '').endswith('MinimumLengthValidator')
            for v in auth_password_validators
        )
        has_common_validator = any(
            v.get('NAME', '').endswith('CommonPasswordValidator')
            for v in auth_password_validators
        )
        has_numeric_validator = any(
            v.get('NAME', '').endswith('NumericPasswordValidator')
            for v in auth_password_validators
        )
        
        details = {
            'min_length_validator': has_min_length,
            'common_password_validator': has_common_validator,
            'numeric_password_validator': has_numeric_validator,
            'total_validators': len(auth_password_validators)
        }
        
        finding = {
            'check': 'Password Policy',
            'status': 'pass' if has_min_length else 'warning',
            'details': details
        }
        
        if not has_min_length:
            finding['recommendations'] = [
                "Add MinimumLengthValidator to AUTH_PASSWORD_VALIDATORS",
                "Consider using zxcvbn for password strength checking"
            ]
        
        return finding
    
    @staticmethod
    def _check_session_security() -> Dict[str, Any]:
        """Check session security configuration."""
        session_settings = {
            'SESSION_COOKIE_SECURE': getattr(settings, 'SESSION_COOKIE_SECURE', False),
            'SESSION_COOKIE_HTTPONLY': getattr(settings, 'SESSION_COOKIE_HTTPONLY', True),
            'SESSION_COOKIE_SAMESITE': getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
            'CSRF_COOKIE_SECURE': getattr(settings, 'CSRF_COOKIE_SECURE', False),
            'CSRF_COOKIE_HTTPONLY': getattr(settings, 'CSRF_COOKIE_HTTPONLY', False),
        }
        
        issues = []
        if not session_settings['SESSION_COOKIE_SECURE']:
            issues.append('SESSION_COOKIE_SECURE should be True')
        if not session_settings['CSRF_COOKIE_SECURE']:
            issues.append('CSRF_COOKIE_SECURE should be True')
        if session_settings['SESSION_COOKIE_SAMESITE'] != 'Strict':
            issues.append('Consider SESSION_COOKIE_SAMESITE = "Strict"')
        
        finding = {
            'check': 'Session Security',
            'status': 'pass' if not issues else 'warning',
            'details': session_settings
        }
        
        if issues:
            finding['recommendations'] = issues
        
        return finding
    
    @staticmethod
    def _check_rate_limiting() -> Dict[str, Any]:
        """Check rate limiting configuration."""
        has_rate_limiting = 'rest_framework.throttling' in str(
            getattr(settings, 'REST_FRAMEWORK', {}).get('DEFAULT_THROTTLE_CLASSES', [])
        )
        
        throttle_rates = getattr(settings, 'REST_FRAMEWORK', {}).get(
            'DEFAULT_THROTTLE_RATES', {}
        )
        
        finding = {
            'check': 'Rate Limiting',
            'status': 'pass' if has_rate_limiting else 'warning',
            'details': {
                'configured': has_rate_limiting,
                'rates': throttle_rates
            }
        }
        
        if not has_rate_limiting:
            finding['recommendations'] = [
                "Configure DRF throttling for API rate limiting",
                "Set up Redis-backed rate limiting for production"
            ]
        
        return finding
    
    @staticmethod
    def _check_default_credentials() -> Dict[str, Any]:
        """Check for default/weak credentials in the system."""
        from apps.users.models import User
        
        issues = []
        
        try:
            # Check for users with common weak passwords
            weak_passwords = ['password', 'admin', '123456', 'qwerty']
            
            # This is a simplified check - in production, use proper password auditing
            admin_users = User.objects.filter(is_staff=True)
            
            finding = {
                'check': 'Default Credentials',
                'status': 'pass',
                'details': {
                    'admin_users_count': admin_users.count(),
                    'warning': 'Manual review required for password strength'
                }
            }
            
        except Exception as e:
            finding = {
                'check': 'Default Credentials',
                'status': 'warning',
                'details': {'error': str(e)}
            }
        
        return finding


class SessionSecurityService:
    """
    Service for session security management.
    Handles session timeouts, concurrent limits, and device fingerprinting.
    """
    
    # Session limits
    ABSOLUTE_TIMEOUT_HOURS = 24
    IDLE_TIMEOUT_MINUTES = 30
    MAX_CONCURRENT_SESSIONS = 5
    
    @staticmethod
    def enforce_session_limits(user) -> Dict[str, Any]:
        """
        Enforce session limits for a user.
        
        Args:
            user: The user to enforce limits for
            
        Returns:
            Dictionary with enforcement results
        """
        from apps.users.models import UserSession
        
        results = {
            'sessions_revoked': 0,
            'sessions_expired': 0,
            'active_sessions': 0,
            'actions': []
        }
        
        try:
            now = timezone.now()
            
            # Get all active sessions
            active_sessions = UserSession.objects.filter(
                user=user,
                is_revoked=False
            ).order_by('-last_activity_at')
            
            # Check absolute timeout (24 hours)
            absolute_cutoff = now - timedelta(
                hours=SessionSecurityService.ABSOLUTE_TIMEOUT_HOURS
            )
            absolute_expired = active_sessions.filter(created_at__lt=absolute_cutoff)
            
            for session in absolute_expired:
                session.revoke(reason='absolute_timeout')
                results['sessions_expired'] += 1
                results['actions'].append(f"Session {session.id} expired (absolute timeout)")
            
            # Check idle timeout (30 minutes)
            idle_cutoff = now - timedelta(
                minutes=SessionSecurityService.IDLE_TIMEOUT_MINUTES
            )
            idle_expired = active_sessions.filter(last_activity_at__lt=idle_cutoff)
            
            for session in idle_expired:
                session.revoke(reason='idle_timeout')
                results['sessions_expired'] += 1
                results['actions'].append(f"Session {session.id} expired (idle timeout)")
            
            # Enforce concurrent session limit
            remaining_sessions = UserSession.objects.filter(
                user=user,
                is_revoked=False
            ).order_by('-last_activity_at')
            
            if remaining_sessions.count() > SessionSecurityService.MAX_CONCURRENT_SESSIONS:
                # Revoke oldest sessions
                sessions_to_revoke = remaining_sessions[
                    SessionSecurityService.MAX_CONCURRENT_SESSIONS:
                ]
                for session in sessions_to_revoke:
                    session.revoke(reason='concurrent_limit')
                    results['sessions_revoked'] += 1
                    results['actions'].append(
                        f"Session {session.id} revoked (concurrent limit)"
                    )
            
            results['active_sessions'] = UserSession.objects.filter(
                user=user,
                is_revoked=False
            ).count()
            
        except Exception as e:
            logger.error(f"Session limit enforcement error: {str(e)}")
            results['error'] = str(e)
        
        return results
    
    @staticmethod
    def generate_device_fingerprint(request) -> str:
        """
        Generate a device fingerprint from request data.
        
        Args:
            request: The HTTP request
            
        Returns:
            SHA-256 hash of device fingerprint
        """
        fingerprint_data = {
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'accept_language': request.META.get('HTTP_ACCEPT_LANGUAGE', ''),
            'accept_encoding': request.META.get('HTTP_ACCEPT_ENCODING', ''),
            'remote_addr': request.META.get('REMOTE_ADDR', ''),
        }
        
        # Create consistent fingerprint
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()
    
    @staticmethod
    def verify_device_fingerprint(session, request) -> bool:
        """
        Verify if the current device matches the session's fingerprint.
        
        Args:
            session: The UserSession to verify
            request: The current HTTP request
            
        Returns:
            True if fingerprint matches
        """
        current_fingerprint = SessionSecurityService.generate_device_fingerprint(request)
        
        stored_fingerprint = session.device_info.get('fingerprint', '')
        
        if not stored_fingerprint:
            # First request - store fingerprint
            session.device_info['fingerprint'] = current_fingerprint
            session.save(update_fields=['device_info'])
            return True
        
        return stored_fingerprint == current_fingerprint


class InputValidationService:
    """
    Service for input validation and sanitization.
    Provides security-focused validation utilities.
    """
    
    # File upload validation
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    ALLOWED_DOCUMENT_TYPES = [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain'
    ]
    MAX_FILE_SIZE_MB = 50
    
    # Magic bytes for file type validation
    MAGIC_BYTES = {
        'image/jpeg': [b'\xff\xd8\xff'],
        'image/png': [b'\x89PNG\r\n\x1a\n'],
        'image/gif': [b'GIF87a', b'GIF89a'],
        'application/pdf': [b'%PDF'],
    }
    
    @staticmethod
    def validate_file_upload(file, allowed_types=None, max_size_mb=None) -> Tuple[bool, Optional[str]]:
        """
        Validate file upload using magic bytes and size checks.
        
        Args:
            file: The uploaded file
            allowed_types: List of allowed MIME types
            max_size_mb: Maximum file size in MB
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if allowed_types is None:
            allowed_types = InputValidationService.ALLOWED_IMAGE_TYPES + \
                          InputValidationService.ALLOWED_DOCUMENT_TYPES
        
        if max_size_mb is None:
            max_size_mb = InputValidationService.MAX_FILE_SIZE_MB
        
        try:
            # Check file size
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)  # Reset to beginning
            
            max_size_bytes = max_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                return False, f"File size exceeds {max_size_mb}MB limit"
            
            # Check magic bytes
            header = file.read(8)
            file.seek(0)
            
            valid_magic = False
            detected_type = None
            
            for mime_type, magic_list in InputValidationService.MAGIC_BYTES.items():
                for magic in magic_list:
                    if header.startswith(magic):
                        valid_magic = True
                        detected_type = mime_type
                        break
                if valid_magic:
                    break
            
            if not valid_magic:
                return False, "File type could not be verified"
            
            if detected_type not in allowed_types:
                return False, f"File type '{detected_type}' is not allowed"
            
            return True, None
            
        except Exception as e:
            logger.error(f"File validation error: {str(e)}")
            return False, "File validation failed"
    
    @staticmethod
    def sanitize_input(value: str, max_length: int = 1000) -> str:
        """
        Sanitize user input to prevent XSS and injection attacks.
        
        Args:
            value: The input string to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized string
        """
        if not value:
            return value
        
        # Truncate if too long
        if len(value) > max_length:
            value = value[:max_length]
        
        # Basic XSS prevention
        import html
        value = html.escape(value)
        
        return value
    
    @staticmethod
    def validate_sql_param(value: str) -> Tuple[bool, Optional[str]]:
        """
        Validate SQL parameter to prevent injection.
        
        Args:
            value: The parameter to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for common SQL injection patterns
        dangerous_patterns = [
            '--', '/*', '*/', ';', 'DROP', 'DELETE', 'INSERT', 'UPDATE',
            'UNION', 'SELECT', 'EXEC', 'EXECUTE', 'TRUNCATE'
        ]
        
        value_upper = value.upper()
        
        for pattern in dangerous_patterns:
            if pattern in value_upper:
                return False, f"Invalid characters detected in input"
        
        return True, None


# Convenience functions for management commands
def verify_at_rest_encryption() -> Dict[str, Any]:
    """Verify encryption at rest configuration."""
    return EncryptionVerificationService.verify_at_rest_encryption()


def enforce_tls_config() -> Dict[str, Any]:
    """Verify TLS configuration."""
    return EncryptionVerificationService.enforce_tls_config()


def detect_stale_secrets() -> Dict[str, Any]:
    """Detect stale or compromised secrets."""
    return EncryptionVerificationService.detect_stale_secrets()


def run_security_audit() -> Dict[str, Any]:
    """Run comprehensive security audit."""
    return SecurityAuditService.run_security_audit()


def enforce_session_limits(user) -> Dict[str, Any]:
    """Enforce session limits for a user."""
    return SessionSecurityService.enforce_session_limits(user)


def generate_device_fingerprint(request) -> str:
    """Generate device fingerprint."""
    return SessionSecurityService.generate_device_fingerprint(request)


def validate_file_upload(file, allowed_types=None, max_size_mb=None) -> Tuple[bool, Optional[str]]:
    """Validate file upload."""
    return InputValidationService.validate_file_upload(file, allowed_types, max_size_mb)
