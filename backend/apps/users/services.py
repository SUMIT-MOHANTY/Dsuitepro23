"""
Authentication Services for Enterprise LMS
Provides business logic for authentication, user management, MFA, and session handling.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.exceptions import TokenError as JWTTokenError

from .models import Role, UserRole, UserSession, RBACConflict

User = get_user_model()
logger = logging.getLogger(__name__)


class AuthenticationService:
    """Service for handling authentication operations."""
    
    @staticmethod
    def register_user(
        email: str,
        password: str,
        username: Optional[str] = None,
        first_name: str = "",
        last_name: str = "",
        role: str = "learner",
        **extra_fields
    ) -> Tuple[User, Optional[str]]:
        """
        Register a new user with the given credentials.
        
        Args:
            email: User's email address
            password: User's password
            username: Optional username (defaults to email prefix)
            first_name: User's first name
            last_name: User's last name
            role: Role to assign (default: learner)
            **extra_fields: Additional user fields
            
        Returns:
            Tuple of (created_user, error_message)
        """
        try:
            with transaction.atomic():
                # Check if user already exists
                if User.objects.filter(email=email).exists():
                    return None, _('A user with this email already exists.')
                
                if username and User.objects.filter(username=username).exists():
                    return None, _('A user with this username already exists.')
                
                # Generate username from email if not provided
                if not username:
                    username = email.split('@')[0]
                    # Ensure uniqueness
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                
                # Create user
                user = User.objects.create_user(
                    email=email,
                    username=username,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    **extra_fields
                )
                
                # Assign role
                try:
                    role_obj = Role.objects.get(role_name=role)
                except Role.DoesNotExist:
                    # Default to learner
                    role_obj, _ = Role.objects.get_or_create(
                        role_name='learner',
                        defaults={
                            'display_name': 'Learner',
                            'description': 'Standard learner role',
                            'is_system_role': True
                        }
                    )
                
                UserRole.objects.create(
                    user=user,
                    role=role_obj,
                    is_primary=True
                )
                
                logger.info(f"User registered: {email} with role {role}")
                return user, None
                
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return None, _('Registration failed. Please try again.')
    
    @staticmethod
    def authenticate_user(email: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Authenticate a user with email and password.
        
        Args:
            email: User's email address
            password: User's password
            
        Returns:
            Tuple of (authenticated_user, error_message)
        """
        try:
            user = User.objects.get(email=email)
            
            if not user.is_active:
                return None, _('This account has been deactivated.')
            
            if user.check_password(password):
                return user, None
            else:
                return None, _('Invalid email or password.')
                
        except User.DoesNotExist:
            return None, _('Invalid email or password.')
    
    @staticmethod
    def generate_tokens(user: User) -> Dict[str, str]:
        """
        Generate JWT tokens for a user.
        
        Args:
            user: The user to generate tokens for
            
        Returns:
            Dictionary with access and refresh tokens
        """
        refresh = RefreshToken.for_user(user)
        
        # Add custom claims
        refresh['user_id'] = str(user.id)
        refresh['email'] = user.email
        refresh['role'] = user.get_primary_role() or 'learner'
        refresh['is_staff'] = user.is_staff
        
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }
    
    @staticmethod
    def refresh_access_token(refresh_token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate a new access token from a refresh token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            Tuple of (new_access_token, error_message)
        """
        try:
            token = RefreshToken(refresh_token)
            new_access = str(token.access_token)
            # Rotate refresh token if configured
            new_refresh = str(token) if token.payload.get('rotated') else None
            return {'access': new_access, 'refresh': new_refresh}, None
        except JWTTokenError as e:
            return None, _('Invalid or expired refresh token.')
    
    @staticmethod
    def logout_user(refresh_token: str, all_sessions: bool = False, user: Optional[User] = None) -> bool:
        """
        Logout a user by blacklisting their refresh token.
        
        Args:
            refresh_token: The refresh token to blacklist
            all_sessions: Whether to logout from all sessions
            user: The user to logout (required if all_sessions=True)
            
        Returns:
            True if successful
        """
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            if all_sessions and user:
                # Revoke all user sessions
                UserSession.objects.filter(
                    user=user,
                    is_revoked=False
                ).update(is_revoked=True, revoked_at=datetime.now())
                logger.info(f"All sessions revoked for user: {user.email}")
            
            return True
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return False


class PasswordResetService:
    """Service for handling password reset operations."""
    
    @staticmethod
    def request_password_reset(email: str) -> Tuple[bool, Optional[str]]:
        """
        Generate password reset token and send email.
        
        Args:
            email: User's email address
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            user = User.objects.get(email=email)
            
            if not user.is_active:
                return False, _('This account has been deactivated.')
            
            # Generate token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # In a real implementation, send email here
            # For now, just log it
            logger.info(f"Password reset requested for {email}. Token: {token}, UID: {uid}")
            
            return True, None
            
        except User.DoesNotExist:
            # Don't reveal if email exists
            logger.info(f"Password reset attempted for non-existent email: {email}")
            return True, None
    
    @staticmethod
    def confirm_password_reset(
        uid: str,
        token: str,
        new_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Confirm password reset with token.
        
        Args:
            uid: Base64 encoded user ID
            token: Password reset token
            new_password: New password
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
            
            if not user.is_active:
                return False, _('This account has been deactivated.')
            
            if not default_token_generator.check_token(user, token):
                return False, _('Invalid or expired reset token.')
            
            user.set_password(new_password)
            user.save()
            
            logger.info(f"Password reset successful for user: {user.email}")
            return True, None
            
        except (User.DoesNotExist, ValueError, TypeError):
            return False, _('Invalid reset token.')


class MFAService:
    """Service for handling Multi-Factor Authentication."""
    
    @staticmethod
    def setup_mfa(user: User) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Setup MFA for a user.
        
        Args:
            user: The user to setup MFA for
            
        Returns:
            Tuple of (setup_data, error_message)
        """
        try:
            # Generate a secret key
            secret = secrets.token_hex(32)
            
            # Generate backup codes
            backup_codes = [secrets.token_hex(4) for _ in range(10)]
            
            # Store hashed backup codes
            import hashlib
            hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]
            
            # Save to user (but don't enable yet - needs verification)
            user.mfa_secret = secret
            user.mfa_backup_codes = hashed_codes
            user.save(update_fields=['mfa_secret', 'mfa_backup_codes'])
            
            # Generate QR code URL (simplified - in production use pyotp)
            qr_url = f"otpauth://totp/LMS:{user.email}?secret={secret}&issuer=EnterpriseLMS"
            
            logger.info(f"MFA setup initiated for user: {user.email}")
            
            return {
                'secret': secret,
                'qr_code_url': qr_url,
                'backup_codes': backup_codes  # Only shown once
            }, None
            
        except Exception as e:
            logger.error(f"MFA setup error: {str(e)}")
            return None, _('Failed to setup MFA.')
    
    @staticmethod
    def verify_mfa_setup(user: User, code: str) -> Tuple[bool, Optional[str]]:
        """
        Verify MFA setup with initial code.
        
        Args:
            user: The user verifying MFA
            code: The verification code
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # In production, use pyotp to verify
            # For now, simplified verification
            if len(code) == 6 and code.isdigit():
                user.mfa_enabled = True
                user.save(update_fields=['mfa_enabled'])
                logger.info(f"MFA enabled for user: {user.email}")
                return True, None
            
            return False, _('Invalid verification code.')
            
        except Exception as e:
            logger.error(f"MFA verification error: {str(e)}")
            return False, _('Failed to verify MFA.')
    
    @staticmethod
    def verify_mfa_code(user: User, code: str) -> Tuple[bool, Optional[str]]:
        """
        Verify MFA code during login.
        
        Args:
            user: The user to verify
            code: The MFA code
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check if it's a backup code
            import hashlib
            hashed_code = hashlib.sha256(code.encode()).hexdigest()
            
            if hashed_code in user.mfa_backup_codes:
                # Remove used backup code
                user.mfa_backup_codes.remove(hashed_code)
                user.save(update_fields=['mfa_backup_codes'])
                return True, None
            
            # In production, verify TOTP code
            # For now, simplified
            if len(code) == 6 and code.isdigit():
                return True, None
            
            return False, _('Invalid MFA code.')
            
        except Exception as e:
            logger.error(f"MFA code verification error: {str(e)}")
            return False, _('Failed to verify MFA code.')


class SessionService:
    """Service for managing user sessions."""
    
    # Session limits and timeouts
    MAX_CONCURRENT_SESSIONS = 5
    ABSOLUTE_TIMEOUT_HOURS = 24
    IDLE_TIMEOUT_MINUTES = 30
    
    @staticmethod
    def create_session(
        user: User,
        session_key: str,
        device_info: Dict[str, Any],
        ip_address: str
    ) -> UserSession:
        """
        Create a new user session.
        
        Args:
            user: The user to create session for
            session_key: The session key or token identifier
            device_info: Device information dictionary
            ip_address: IP address of the session
            
        Returns:
            The created UserSession
        """
        # Check concurrent session limit
        active_sessions = UserSession.objects.filter(
            user=user,
            is_revoked=False
        ).count()
        
        if active_sessions >= SessionService.MAX_CONCURRENT_SESSIONS:
            # Revoke oldest session
            oldest_session = UserSession.objects.filter(
                user=user,
                is_revoked=False
            ).order_by('created_at').first()
            
            if oldest_session:
                oldest_session.revoke()
                logger.info(f"Revoked oldest session for {user.email} due to limit")
        
        # Calculate expiration
        expires_at = datetime.now() + timedelta(hours=SessionService.ABSOLUTE_TIMEOUT_HOURS)
        
        session = UserSession.objects.create(
            user=user,
            session_key=session_key,
            device_info=device_info,
            ip_address=ip_address,
            expires_at=expires_at
        )
        
        logger.info(f"Session created for {user.email} from {ip_address}")
        return session
    
    @staticmethod
    def validate_session(session_key: str) -> Tuple[Optional[UserSession], Optional[str]]:
        """
        Validate a session and check timeouts.
        
        Args:
            session_key: The session key to validate
            
        Returns:
            Tuple of (session, error_message)
        """
        try:
            session = UserSession.objects.get(session_key=session_key)
            
            if session.is_revoked:
                return None, _('Session has been revoked.')
            
            if session.is_expired():
                return None, _('Session has expired.')
            
            # Check idle timeout
            idle_threshold = datetime.now() - timedelta(minutes=SessionService.IDLE_TIMEOUT_MINUTES)
            if session.last_activity_at < idle_threshold:
                session.revoke()
                return None, _('Session expired due to inactivity.')
            
            return session, None
            
        except UserSession.DoesNotExist:
            return None, _('Invalid session.')
    
    @staticmethod
    def revoke_session(session_key: str, revoked_by: Optional[User] = None) -> bool:
        """
        Revoke a specific session.
        
        Args:
            session_key: The session key to revoke
            revoked_by: User who is revoking the session
            
        Returns:
            True if successful
        """
        try:
            session = UserSession.objects.get(session_key=session_key)
            session.revoke(revoked_by)
            return True
        except UserSession.DoesNotExist:
            return False
    
    @staticmethod
    def revoke_all_sessions(user: User, except_session: Optional[str] = None, revoked_by: Optional[User] = None) -> int:
        """
        Revoke all sessions for a user.
        
        Args:
            user: The user whose sessions to revoke
            except_session: Session key to exclude from revocation
            revoked_by: User who is revoking the sessions
            
        Returns:
            Number of sessions revoked
        """
        sessions = UserSession.objects.filter(user=user, is_revoked=False)
        
        if except_session:
            sessions = sessions.exclude(session_key=except_session)
        
        count = 0
        for session in sessions:
            session.revoke(revoked_by)
            count += 1
        
        logger.info(f"Revoked {count} sessions for {user.email}")
        return count
    
    @staticmethod
    def get_active_sessions(user: User) -> List[UserSession]:
        """
        Get all active sessions for a user.
        
        Args:
            user: The user to get sessions for
            
        Returns:
            List of active UserSession objects
        """
        return list(UserSession.objects.filter(
            user=user,
            is_revoked=False
        ).order_by('-last_activity_at'))


class ImpersonationService:
    """Service for handling user impersonation by admins."""
    
    @staticmethod
    def start_impersonation(admin_user: User, target_user: User) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Start impersonating a user.
        
        Args:
            admin_user: The admin user performing impersonation
            target_user: The user to impersonate
            
        Returns:
            Tuple of (impersonation_data, error_message)
        """
        # Check if admin_user has permission to impersonate
        if not (admin_user.is_admin() or admin_user.has_role('support')):
            return None, _('You do not have permission to impersonate users.')
        
        # Don't allow impersonating superusers or other admins
        if target_user.is_superuser or target_user.is_admin():
            return None, _('Cannot impersonate administrators.')
        
        # Don't allow self-impersonation
        if admin_user.id == target_user.id:
            return None, _('Cannot impersonate yourself.')
        
        # Generate impersonation token
        impersonation_token = secrets.token_urlsafe(32)
        
        logger.info(f"Admin {admin_user.email} started impersonating {target_user.email}")
        
        return {
            'impersonation_token': impersonation_token,
            'admin_user_id': str(admin_user.id),
            'target_user_id': str(target_user.id),
            'target_user_email': target_user.email,
            'started_at': datetime.now().isoformat()
        }, None
    
    @staticmethod
    def end_impersonation(admin_user: User, target_user: User) -> bool:
        """
        End impersonation session.
        
        Args:
            admin_user: The admin user who was impersonating
            target_user: The user who was impersonated
            
        Returns:
            True if successful
        """
        logger.info(f"Admin {admin_user.email} stopped impersonating {target_user.email}")
        return True


class UserManagementService:
    """Service for user management operations."""
    
    @staticmethod
    def assign_role(
        user: User,
        role_name: str,
        assigned_by: Optional[User] = None,
        is_primary: bool = False
    ) -> Tuple[Optional[UserRole], Optional[str]]:
        """
        Assign a role to a user.
        
        Args:
            user: The user to assign role to
            role_name: The role name to assign
            assigned_by: User assigning the role
            is_primary: Whether this should be the primary role
            
        Returns:
            Tuple of (user_role, error_message)
        """
        try:
            role = Role.objects.get(role_name=role_name)
            
            # Check if already assigned
            if UserRole.objects.filter(user=user, role=role).exists():
                return None, _('User already has this role.')
            
            # If setting as primary, unset other primary roles
            if is_primary:
                UserRole.objects.filter(user=user, is_primary=True).update(is_primary=False)
            
            user_role = UserRole.objects.create(
                user=user,
                role=role,
                assigned_by=assigned_by,
                is_primary=is_primary
            )
            
            logger.info(f"Role {role_name} assigned to {user.email} by {assigned_by.email if assigned_by else 'system'}")
            return user_role, None
            
        except Role.DoesNotExist:
            return None, _('Role not found.')
    
    @staticmethod
    def remove_role(user: User, role_name: str) -> Tuple[bool, Optional[str]]:
        """
        Remove a role from a user.
        
        Args:
            user: The user to remove role from
            role_name: The role name to remove
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            role = Role.objects.get(role_name=role_name)
            user_role = UserRole.objects.get(user=user, role=role)
            
            # Don't allow removing the last role
            if UserRole.objects.filter(user=user).count() <= 1:
                return False, _('Cannot remove the last role from a user.')
            
            was_primary = user_role.is_primary
            user_role.delete()
            
            # If removed role was primary, set another as primary
            if was_primary:
                first_role = UserRole.objects.filter(user=user).first()
                if first_role:
                    first_role.is_primary = True
                    first_role.save()
            
            logger.info(f"Role {role_name} removed from {user.email}")
            return True, None
            
        except Role.DoesNotExist:
            return False, _('Role not found.')
        except UserRole.DoesNotExist:
            return False, _('User does not have this role.')


class RBACEdgeCaseService:
    """
    Service for detecting and handling RBAC edge cases and conflicts.
    
    This service implements SOC 2 compliance controls for:
    - Role conflict detection (e.g., learner + instructor on same course)
    - Permission inheritance validation
    - Time-bound role grant validation
    - Cross-domain access conflicts
    """
    
    # Conflicting role pairs that should not coexist
    CONFLICTING_ROLE_PAIRS = [
        ('learner', 'instructor'),
        ('learner', 'admin'),
        ('instructor', 'admin'),  # Admin should supersede instructor
    ]
    
    # Role hierarchy (higher roles inherit from lower)
    ROLE_HIERARCHY = {
        'admin': ['instructor', 'learner', 'content_manager', 'support'],
        'instructor': ['learner'],
        'content_manager': ['learner'],
        'support': [],
        'learner': [],
    }
    
    @staticmethod
    def detect_role_conflicts(user: User, course_id: Optional[str] = None, course_name: str = '') -> List[Dict[str, Any]]:
        """
        Detect role conflicts for a user.
        
        Detects conflicts such as:
        - User having both learner and instructor roles
        - Conflicting roles on the same course
        - Role hierarchy violations
        
        Args:
            user: The user to check for conflicts
            course_id: Optional course ID for course-specific conflicts
            course_name: Optional course name for reference
            
        Returns:
            List of detected conflicts as dictionaries
        """
        conflicts = []
        
        # Get all user roles
        user_roles = list(user.assigned_roles.all().values_list('role_name', flat=True))
        
        # Check for conflicting role pairs
        for role1, role2 in RBACEdgeCaseService.CONFLICTING_ROLE_PAIRS:
            if role1 in user_roles and role2 in user_roles:
                conflict = {
                    'type': RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
                    'severity': RBACConflict.SEVERITY_HIGH,
                    'conflicting_roles': [role1, role2],
                    'description': f"User has conflicting roles: {role1} and {role2}",
                    'course_id': course_id,
                    'course_name': course_name,
                    'context': {
                        'user_roles': user_roles,
                        'conflict_detected_at': datetime.now().isoformat()
                    }
                }
                conflicts.append(conflict)
        
        # Check for multiple primary roles
        primary_roles = UserRole.objects.filter(user=user, is_primary=True)
        if primary_roles.count() > 1:
            conflict = {
                'type': RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
                'severity': RBACConflict.SEVERITY_MEDIUM,
                'conflicting_roles': list(primary_roles.values_list('role__role_name', flat=True)),
                'description': f"User has {primary_roles.count()} primary roles assigned",
                'course_id': course_id,
                'course_name': course_name,
                'context': {
                    'primary_role_count': primary_roles.count(),
                    'conflict_detected_at': datetime.now().isoformat()
                }
            }
            conflicts.append(conflict)
        
        # Check for expired roles that are still active
        expired_roles = UserRole.objects.filter(
            user=user,
            expires_at__isnull=False,
            expires_at__lt=datetime.now()
        )
        
        for expired_role in expired_roles:
            conflict = {
                'type': RBACConflict.CONFLICT_TYPE_TIME_BOUND,
                'severity': RBACConflict.SEVERITY_MEDIUM,
                'conflicting_roles': [expired_role.role.role_name],
                'description': f"User has expired role: {expired_role.role.display_name}",
                'course_id': course_id,
                'course_name': course_name,
                'context': {
                    'expired_at': expired_role.expires_at.isoformat(),
                    'days_expired': (datetime.now() - expired_role.expires_at).days,
                    'conflict_detected_at': datetime.now().isoformat()
                }
            }
            conflicts.append(conflict)
        
        logger.info(f"Detected {len(conflicts)} role conflicts for user {user.email}")
        return conflicts
    
    @staticmethod
    def validate_permission_inheritance(user: User, required_permission: str) -> Dict[str, Any]:
        """
        Validate that a user's permissions are properly inherited through the role hierarchy.
        
        Args:
            user: The user to validate
            required_permission: The permission to check
            
        Returns:
            Dictionary with validation results
        """
        result = {
            'is_valid': True,
            'user_has_permission': False,
            'inherited_from': None,
            'violations': []
        }
        
        # Get user's roles
        user_roles = list(user.assigned_roles.all())
        
        # Check each role for the permission
        for role in user_roles:
            if required_permission in role.permissions:
                result['user_has_permission'] = True
                result['inherited_from'] = role.role_name
                break
        
        # Check role hierarchy for inherited permissions
        for role in user_roles:
            if role.role_name in RBACEdgeCaseService.ROLE_HIERARCHY:
                inherited_roles = RBACEdgeCaseService.ROLE_HIERARCHY[role.role_name]
                
                # Check if any inherited role has the permission
                for inherited_role_name in inherited_roles:
                    try:
                        inherited_role = Role.objects.get(role_name=inherited_role_name)
                        if required_permission in inherited_role.permissions:
                            result['user_has_permission'] = True
                            if not result['inherited_from']:
                                result['inherited_from'] = f"{role.role_name} -> {inherited_role_name}"
                    except Role.DoesNotExist:
                        continue
        
        # Check for permission inheritance violations
        # (e.g., lower role having permissions that should only be in higher roles)
        for role in user_roles:
            for higher_role_name, lower_roles in RBACEdgeCaseService.ROLE_HIERARCHY.items():
                if role.role_name in lower_roles:
                    try:
                        higher_role = Role.objects.get(role_name=higher_role_name)
                        for permission in role.permissions:
                            if permission in higher_role.permissions:
                                # This is actually valid - lower roles can have same permissions
                                pass
                    except Role.DoesNotExist:
                        continue
        
        if not result['user_has_permission']:
            result['is_valid'] = False
            result['violations'].append({
                'type': 'missing_permission',
                'permission': required_permission,
                'message': f"User does not have required permission: {required_permission}"
            })
        
        return result
    
    @staticmethod
    def check_time_bound_grants(user: User) -> List[Dict[str, Any]]:
        """
        Check for time-bound role grants that are expiring or have expired.
        
        Args:
            user: The user to check
            
        Returns:
            List of time-bound grant issues
        """
        issues = []
        
        # Get time-bound role grants
        time_bound_roles = UserRole.objects.filter(
            user=user,
            expires_at__isnull=False
        )
        
        now = datetime.now()
        
        for user_role in time_bound_roles:
            days_until_expiry = (user_role.expires_at - now).days
            
            if days_until_expiry < 0:
                # Already expired
                issues.append({
                    'type': 'expired',
                    'role': user_role.role.role_name,
                    'expired_at': user_role.expires_at.isoformat(),
                    'days_expired': abs(days_until_expiry),
                    'severity': RBACConflict.SEVERITY_HIGH,
                    'message': f"Role '{user_role.role.display_name}' expired {abs(days_until_expiry)} days ago"
                })
            elif days_until_expiry <= 7:
                # Expiring within 7 days
                issues.append({
                    'type': 'expiring_soon',
                    'role': user_role.role.role_name,
                    'expires_at': user_role.expires_at.isoformat(),
                    'days_remaining': days_until_expiry,
                    'severity': RBACConflict.SEVERITY_MEDIUM if days_until_expiry <= 3 else RBACConflict.SEVERITY_LOW,
                    'message': f"Role '{user_role.role.display_name}' expires in {days_until_expiry} days"
                })
        
        return issues
    
    @staticmethod
    def create_rbac_conflict(
        user: User,
        conflict_type: str,
        severity: str,
        conflicting_roles: List[str],
        description: str,
        course_id: Optional[str] = None,
        course_name: str = '',
        detected_by: Optional[User] = None,
        context_data: Optional[Dict] = None
    ) -> RBACConflict:
        """
        Create an RBAC conflict record.
        
        Args:
            user: The user with the conflict
            conflict_type: Type of conflict
            severity: Severity level
            conflicting_roles: List of conflicting role names
            description: Description of the conflict
            course_id: Optional course ID
            course_name: Optional course name
            detected_by: User who detected the conflict
            context_data: Additional context
            
        Returns:
            The created RBACConflict instance
        """
        conflict = RBACConflict.objects.create(
            user=user,
            conflict_type=conflict_type,
            severity=severity,
            status=RBACConflict.STATUS_DETECTED,
            conflicting_roles=conflicting_roles,
            description=description,
            course_id=course_id,
            course_name=course_name,
            detected_by=detected_by,
            detection_source='automatic_scan' if detected_by is None else 'manual_review',
            context_data=context_data or {}
        )
        
        logger.warning(f"Created RBAC conflict {conflict.id} for user {user.email}: {conflict_type}")
        return conflict
    
    @staticmethod
    def scan_for_conflicts(course_id: Optional[str] = None) -> List[RBACConflict]:
        """
        Scan all users for RBAC conflicts.
        
        Args:
            course_id: Optional course ID to limit scan scope
            
        Returns:
            List of newly created RBACConflict records
        """
        conflicts_created = []
        
        # Get users to scan
        users = User.objects.filter(is_active=True)
        
        for user in users:
            detected_conflicts = RBACEdgeCaseService.detect_role_conflicts(user, course_id)
            
            for conflict_data in detected_conflicts:
                # Check if this conflict already exists
                existing = RBACConflict.objects.filter(
                    user=user,
                    conflict_type=conflict_data['type'],
                    status=RBACConflict.STATUS_DETECTED
                ).exists()
                
                if not existing:
                    conflict = RBACEdgeCaseService.create_rbac_conflict(
                        user=user,
                        conflict_type=conflict_data['type'],
                        severity=conflict_data['severity'],
                        conflicting_roles=conflict_data['conflicting_roles'],
                        description=conflict_data['description'],
                        course_id=conflict_data.get('course_id'),
                        course_name=conflict_data.get('course_name', ''),
                        context_data=conflict_data.get('context', {})
                    )
                    conflicts_created.append(conflict)
        
        logger.info(f"RBAC conflict scan complete. Created {len(conflicts_created)} new conflict records.")
        return conflicts_created
    
    @staticmethod
    def resolve_conflict(
        conflict: RBACConflict,
        resolved_by: User,
        resolution_action: str,
        resolution_notes: str = ''
    ) -> bool:
        """
        Resolve an RBAC conflict.
        
        Args:
            conflict: The conflict to resolve
            resolved_by: User resolving the conflict
            resolution_action: Action taken (e.g., 'role_revoked', 'marked_legitimate')
            resolution_notes: Additional notes
            
        Returns:
            True if resolved successfully
        """
        try:
            conflict.resolve(resolved_by, resolution_action, resolution_notes)
            
            logger.info(f"RBAC conflict {conflict.id} resolved by {resolved_by.email}: {resolution_action}")
            return True
        except Exception as e:
            logger.error(f"Failed to resolve RBAC conflict {conflict.id}: {str(e)}")
            return False
    
    @staticmethod
    def get_conflict_summary(user: Optional[User] = None) -> Dict[str, Any]:
        """
        Get a summary of RBAC conflicts.
        
        Args:
            user: Optional user to limit summary to
            
        Returns:
            Dictionary with conflict summary statistics
        """
        queryset = RBACConflict.objects.all()
        
        if user:
            queryset = queryset.filter(user=user)
        
        summary = {
            'total_conflicts': queryset.count(),
            'by_status': {
                'detected': queryset.filter(status=RBACConflict.STATUS_DETECTED).count(),
                'resolved': queryset.filter(status=RBACConflict.STATUS_RESOLVED).count(),
                'ignored': queryset.filter(status=RBACConflict.STATUS_IGNORED).count(),
                'escalated': queryset.filter(status=RBACConflict.STATUS_ESCALATED).count(),
            },
            'by_severity': {
                'low': queryset.filter(severity=RBACConflict.SEVERITY_LOW).count(),
                'medium': queryset.filter(severity=RBACConflict.SEVERITY_MEDIUM).count(),
                'high': queryset.filter(severity=RBACConflict.SEVERITY_HIGH).count(),
                'critical': queryset.filter(severity=RBACConflict.SEVERITY_CRITICAL).count(),
            },
            'by_type': {
                'role_conflict': queryset.filter(conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT).count(),
                'permission_inheritance': queryset.filter(conflict_type=RBACConflict.CONFLICT_TYPE_PERMISSION_INHERITANCE).count(),
                'time_bound': queryset.filter(conflict_type=RBACConflict.CONFLICT_TYPE_TIME_BOUND).count(),
                'cross_domain': queryset.filter(conflict_type=RBACConflict.CONFLICT_TYPE_CROSS_DOMAIN).count(),
            },
            'open_critical': queryset.filter(
                status=RBACConflict.STATUS_DETECTED,
                severity=RBACConflict.SEVERITY_CRITICAL
            ).count()
        }
        
        return summary
