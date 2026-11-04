"""
Django Signals for Users App
Handles post-save and pre-delete operations for users, authentication events,
and security audit logging for SOC 2 compliance.
"""

import logging
from datetime import datetime

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.utils import timezone

from apps.analytics.models import SecurityAuditLog
from apps.analytics.services import AuditLoggingService

from .models import User, UserSession, UserRole

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for User model.
    - Send welcome email for new users
    - Log user creation/updates
    - Log access removal when user is deactivated (SOC 2 CC6.3)
    """
    if created:
        logger.info(f"New user created: {instance.email}")
        # Welcome email would be sent here via Celery task
        # from apps.notifications.tasks import send_welcome_email
        # send_welcome_email.delay(instance.id)


@receiver(pre_save, sender=User)
def user_pre_save(sender, instance, **kwargs):
    """
    Handle pre-save operations for User model.
    - Detect deactivation and log access removal (SOC 2 CC6.3)
    - Log role changes
    """
    if instance.pk:
        try:
            old_user = User.objects.get(pk=instance.pk)
            
            # Detect deactivation (SOC 2 CC6.3: Access removal on termination)
            if old_user.is_active and not instance.is_active:
                logger.info(f"User deactivated: {instance.email}")
                
                # Log to SecurityAuditLog
                try:
                    SecurityAuditLog.log_event(
                        event_type=SecurityAuditLog.EVENT_ROLE_REVOKED,
                        event_category=SecurityAuditLog.CATEGORY_AUTHZ,
                        severity=SecurityAuditLog.SEVERITY_WARNING,
                        actor_user=None,  # System action
                        actor_email='system',
                        target_resource='user_account',
                        target_resource_id=str(instance.id),
                        outcome='success',
                        reason='User account deactivated - all access revoked',
                        details={
                            'user_email': instance.email,
                            'previous_active': True,
                            'new_active': False,
                            'action': 'access_removal_on_deactivation',
                            'compliance_control': 'SOC2_CC6.3'
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to log deactivation audit: {e}")
                
                # Revoke all active sessions
                revoked_count = UserSession.objects.filter(
                    user=instance,
                    is_revoked=False
                ).update(
                    is_revoked=True,
                    revoked_at=timezone.now(),
                    revoked_by=None  # System revocation
                )
                
                logger.info(f"Revoked {revoked_count} sessions for deactivated user: {instance.email}")
                
        except User.DoesNotExist:
            pass


@receiver(pre_delete, sender=User)
def user_pre_delete(sender, instance, **kwargs):
    """
    Handle pre-delete operations for User model.
    - Clean up user sessions before deletion
    - Log deletion for audit purposes
    """
    logger.info(f"User being deleted: {instance.email}")
    
    # Revoke all active sessions
    UserSession.objects.filter(
        user=instance,
        is_revoked=False
    ).update(is_revoked=True)


@receiver(post_save, sender=UserSession)
def session_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for UserSession model.
    - Log new session creation
    - Log session revocation
    """
    if created:
        logger.info(f"New session created for user: {instance.user.email}")
        
        # Log session creation to SecurityAuditLog
        try:
            device_info = instance.device_info or {}
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_SESSION_CREATED,
                event_category=SecurityAuditLog.CATEGORY_SESSION,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=instance.user,
                target_resource='user_session',
                target_resource_id=str(instance.id),
                outcome='success',
                ip_address=instance.ip_address,
                user_agent=device_info.get('user_agent', ''),
                details={
                    'session_key_prefix': instance.session_key[:8] if instance.session_key else None,
                    'device_fingerprint': device_info.get('fingerprint'),
                    'browser': device_info.get('browser'),
                    'os': device_info.get('os'),
                    'location': instance.location
                }
            )
        except Exception as e:
            logger.error(f"Failed to log session creation audit: {e}")
    
    # Log session revocation
    if not created and instance.is_revoked and instance.revoked_at:
        try:
            # Check if this is a fresh revocation (within last few seconds)
            time_since_revocation = (timezone.now() - instance.revoked_at).total_seconds()
            if time_since_revocation < 5:  # Fresh revocation
                SecurityAuditLog.log_event(
                    event_type=SecurityAuditLog.EVENT_SESSION_REVOKED,
                    event_category=SecurityAuditLog.CATEGORY_SESSION,
                    severity=SecurityAuditLog.SEVERITY_INFO,
                    actor_user=instance.revoked_by,
                    target_resource='user_session',
                    target_resource_id=str(instance.id),
                    outcome='success',
                    reason='Session revoked',
                    details={
                        'revoked_by': instance.revoked_by.email if instance.revoked_by else 'system',
                        'session_key_prefix': instance.session_key[:8] if instance.session_key else None,
                        'user_email': instance.user.email
                    }
                )
        except Exception as e:
            logger.error(f"Failed to log session revocation audit: {e}")


# ============================================================================
# Authentication Event Signals
# ============================================================================

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Log successful login events to SecurityAuditLog.
    Captures login success for SOC 2 compliance.
    """
    try:
        # Get request metadata
        ip_address = AuditLoggingService._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Log to SecurityAuditLog
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=user,
            target_resource='user_account',
            target_resource_id=str(user.id),
            outcome='success',
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request.method,
            request_path=request.path,
            details={
                'login_method': 'password',
                'mfa_used': user.mfa_enabled,
                'email_verified': user.email_verified
            }
        )
        
        logger.info(f"Login success logged for user: {user.email}")
        
    except Exception as e:
        logger.error(f"Failed to log login success: {e}")


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """
    Log logout events to SecurityAuditLog.
    Captures logout for audit trail completeness.
    """
    if user:  # User may be None for session expiry
        try:
            ip_address = AuditLoggingService._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGOUT,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=user,
                target_resource='user_account',
                target_resource_id=str(user.id),
                outcome='success',
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request.method,
                request_path=request.path,
                details={
                    'logout_type': 'manual',
                    'session_terminated': True
                }
            )
            
            logger.info(f"Logout logged for user: {user.email}")
            
        except Exception as e:
            logger.error(f"Failed to log logout: {e}")


@receiver(user_login_failed)
def log_login_failure(sender, credentials, request, **kwargs):
    """
    Log failed login attempts to SecurityAuditLog.
    Critical for SOC 2 CC7.2: Security incident detection.
    """
    try:
        email = credentials.get('email', credentials.get('username', 'unknown'))
        ip_address = AuditLoggingService._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Try to find the user for the failed attempt
        actor_user = None
        try:
            actor_user = User.objects.filter(email=email).first()
        except Exception:
            pass
        
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=actor_user,
            actor_email=email,
            target_resource='user_account',
            target_resource_id=str(actor_user.id) if actor_user else None,
            outcome='failure',
            reason='Invalid credentials',
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request.method,
            request_path=request.path,
            details={
                'attempted_email': email,
                'failure_reason': 'authentication_failed',
                'ip_address': str(ip_address)
            }
        )
        
        logger.warning(f"Login failure logged for: {email} from IP: {ip_address}")
        
        # Check for brute force patterns (anomaly detection)
        _check_brute_force_pattern(ip_address, email)
        
    except Exception as e:
        logger.error(f"Failed to log login failure: {e}")


def _check_brute_force_pattern(ip_address, email):
    """
    Check for brute force attack patterns.
    SOC 2 CC7.2: Security incident detection.
    """
    try:
        from datetime import timedelta
        
        # Count failed attempts in last 15 minutes
        cutoff_time = timezone.now() - timedelta(minutes=15)
        
        failed_attempts = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            ip_address=ip_address,
            timestamp__gte=cutoff_time
        ).count()
        
        # Alert if threshold exceeded (5 attempts in 15 minutes)
        if failed_attempts >= 5:
            SecurityAuditLog.log_event(
                event_type='brute_force_detected',
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_CRITICAL,
                actor_email='system',
                target_resource='security_monitoring',
                outcome='alert',
                reason=f'Potential brute force attack: {failed_attempts} failed attempts from {ip_address}',
                ip_address=ip_address,
                details={
                    'failed_attempts': failed_attempts,
                    'target_email': email,
                    'time_window_minutes': 15,
                    'recommendation': 'Consider IP blocking or CAPTCHA'
                }
            )
            
            logger.critical(f"Brute force pattern detected from IP: {ip_address}")
            
    except Exception as e:
        logger.error(f"Failed to check brute force pattern: {e}")


# ============================================================================
# UserRole Signals
# ============================================================================

@receiver(post_save, sender=UserRole)
def userrole_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for UserRole model.
    - Log role assignments
    - Trigger RBAC conflict detection
    """
    if created:
        try:
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_ROLE_ASSIGNED,
                event_category=SecurityAuditLog.CATEGORY_AUTHZ,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=instance.assigned_by,
                target_resource='user_role',
                target_resource_id=str(instance.id),
                outcome='success',
                details={
                    'user_email': instance.user.email,
                    'role_name': instance.role.role_name,
                    'role_display': instance.role.display_name,
                    'is_primary': instance.is_primary,
                    'expires_at': instance.expires_at.isoformat() if instance.expires_at else None
                }
            )
            
            logger.info(f"Role {instance.role.role_name} assigned to {instance.user.email}")
            
            # Trigger RBAC conflict detection
            from apps.users.services import RBACEdgeCaseService
            RBACEdgeCaseService.detect_role_conflicts(instance.user)
            
        except Exception as e:
            logger.error(f"Failed to log role assignment: {e}")


@receiver(pre_delete, sender=UserRole)
def userrole_pre_delete(sender, instance, **kwargs):
    """
    Handle pre-delete operations for UserRole model.
    - Log role revocations
    """
    try:
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ROLE_REVOKED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=None,  # System action
            target_resource='user_role',
            target_resource_id=str(instance.id),
            outcome='success',
            details={
                'user_email': instance.user.email,
                'role_name': instance.role.role_name,
                'role_display': instance.role.display_name,
                'action': 'role_revoked'
            }
        )
        
        logger.info(f"Role {instance.role.role_name} revoked from {instance.user.email}")
        
    except Exception as e:
        logger.error(f"Failed to log role revocation: {e}")
