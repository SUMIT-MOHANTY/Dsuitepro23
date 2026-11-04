"""
Authentication Services for Enterprise LMS
Provides business logic for authentication, user management, MFA, and session handling.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.exceptions import TokenError as JWTTokenError

from .models import Role, UserRole, UserSession

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
    def verify_mfa_code(user: User, code: str) -> bool:
        """
        Verify an MFA code during login.
        
        Args:
            user: The user to verify
            code: The MFA code
            
        Returns:
            True if code is valid
        """
        if not user.mfa_enabled:
            return True
        
        # Check if it's a backup code
        import hashlib
        hashed_input = hashlib.sha256(code.encode()).hexdigest()
        
        if hashed_input in user.mfa_backup_codes:
            # Remove used backup code
            user.mfa_backup_codes.remove(hashed_input)
            user.save(update_fields=['mfa_backup_codes'])
            logger.info(f"Backup code used for user: {user.email}")
            return True
        
        # In production, verify TOTP code with pyotp
        # For now, simplified
        if len(code) == 6 and code.isdigit():
            return True
        
        return False
    
    @staticmethod
    def disable_mfa(user: User, password: str) -> Tuple[bool, Optional[str]]:
        """
        Disable MFA for a user.
        
        Args:
            user: The user to disable MFA for
            password: Current password for verification
            
        Returns:
            Tuple of (success, error_message)
        """
        if not user.check_password(password):
            return False, _('Incorrect password.')
        
        user.mfa_enabled = False
        user.mfa_secret = ""
        user.mfa_backup_codes = []
        user.save(update_fields=['mfa_enabled', 'mfa_secret', 'mfa_backup_codes'])
        
        logger.info(f"MFA disabled for user: {user.email}")
        return True, None


class SessionService:
    """Service for managing user sessions."""
    
    @staticmethod
    def create_session(
        user: User,
        session_key: str,
        device_info: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        location: Optional[str] = None
    ) -> UserSession:
        """
        Create a new user session.
        
        Args:
            user: The user for the session
            session_key: The session identifier
            device_info: Device information dict
            ip_address: IP address
            location: Geographic location
            
        Returns:
            Created UserSession
        """
        session = UserSession.objects.create(
            user=user,
            session_key=session_key,
            device_info=device_info or {},
            ip_address=ip_address,
            location=location,
            expires_at=datetime.now() + timedelta(days=7)
        )
        
        logger.info(f"Session created for user: {user.email}")
        return session
    
    @staticmethod
    def revoke_session(session_id: str, revoked_by: Optional[User] = None) -> bool:
        """
        Revoke a specific session.
        
        Args:
            session_id: The session ID to revoke
            revoked_by: User who is revoking the session
            
        Returns:
            True if successful
        """
        try:
            session = UserSession.objects.get(id=session_id)
            session.revoke(revoked_by=revoked_by)
            logger.info(f"Session {session_id} revoked by {revoked_by.email if revoked_by else 'system'}")
            return True
        except UserSession.DoesNotExist:
            return False
    
    @staticmethod
    def get_active_sessions(user: User) -> list:
        """
        Get all active sessions for a user.
        
        Args:
            user: The user to get sessions for
            
        Returns:
            List of active UserSession objects
        """
        return UserSession.objects.filter(
            user=user,
            is_revoked=False,
            expires_at__gt=datetime.now()
        )
    
    @staticmethod
    def cleanup_expired_sessions() -> int:
        """
        Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        expired = UserSession.objects.filter(
            expires_at__lt=datetime.now(),
            is_revoked=False
        )
        count = expired.count()
        expired.update(is_revoked=True, revoked_at=datetime.now())
        
        if count > 0:
            logger.info(f"Cleaned up {count} expired sessions")
        
        return count


class ImpersonationService:
    """Service for handling user impersonation (admin feature)."""
    
    IMPERSONATION_SESSION_KEY = 'impersonated_user_id'
    
    @classmethod
    def impersonate_user(
        cls,
        admin_user: User,
        target_user_id: str,
        reason: Optional[str] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Start impersonating a user.
        
        Args:
            admin_user: The admin user performing the impersonation
            target_user_id: The user ID to impersonate
            reason: Optional reason for impersonation
            
        Returns:
            Tuple of (impersonation_data, error_message)
        """
        # Check if admin has permission
        if not (admin_user.is_staff or admin_user.is_superuser or admin_user.is_admin()):
            return None, _('You do not have permission to impersonate users.')
        
        try:
            target_user = User.objects.get(pk=target_user_id)
            
            # Prevent impersonating superusers unless you're a superuser
            if target_user.is_superuser and not admin_user.is_superuser:
                return None, _('Cannot impersonate superusers.')
            
            # Prevent self-impersonation
            if target_user.id == admin_user.id:
                return None, _('Cannot impersonate yourself.')
            
            # Generate impersonation token
            tokens = AuthenticationService.generate_tokens(target_user)
            
            # Log impersonation
            logger.info(
                f"User impersonation: {admin_user.email} -> {target_user.email}. "
                f"Reason: {reason or 'Not provided'}"
            )
            
            return {
                'impersonator': {
                    'id': str(admin_user.id),
                    'email': admin_user.email,
                    'full_name': admin_user.get_full_name()
                },
                'impersonated': {
                    'id': str(target_user.id),
                    'email': target_user.email,
                    'full_name': target_user.get_full_name(),
                    'role': target_user.get_primary_role()
                },
                'tokens': tokens,
                'reason': reason
            }, None
            
        except User.DoesNotExist:
            return None, _('User not found.')
    
    @classmethod
    def stop_impersonation(cls, admin_user: User) -> Dict:
        """
        Stop impersonating and return to admin user tokens.
        
        Args:
            admin_user: The admin user
            
        Returns:
            Dictionary with admin user tokens
        """
        tokens = AuthenticationService.generate_tokens(admin_user)
        
        logger.info(f"Impersonation ended by: {admin_user.email}")
        
        return {
            'user': {
                'id': str(admin_user.id),
                'email': admin_user.email,
                'full_name': admin_user.get_full_name(),
                'role': admin_user.get_primary_role()
            },
            'tokens': tokens
        }


class UserManagementService:
    """Service for user management operations."""
    
    @staticmethod
    def update_user(user: User, **updates) -> Tuple[Optional[User], Optional[str]]:
        """
        Update user information.
        
        Args:
            user: The user to update
            **updates: Fields to update
            
        Returns:
            Tuple of (updated_user, error_message)
        """
        try:
            allowed_fields = [
                'username', 'first_name', 'last_name', 'avatar_url',
                'bio', 'phone', 'timezone', 'locale', 'date_of_birth'
            ]
            
            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(user, field, value)
            
            user.save()
            logger.info(f"User updated: {user.email}")
            return user, None
            
        except Exception as e:
            logger.error(f"User update error: {str(e)}")
            return None, _('Failed to update user.')
    
    @staticmethod
    def change_password(user: User, old_password: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """
        Change user password.
        
        Args:
            user: The user to update
            old_password: Current password
            new_password: New password
            
        Returns:
            Tuple of (success, error_message)
        """
        if not user.check_password(old_password):
            return False, _('Current password is incorrect.')
        
        user.set_password(new_password)
        user.save()
        
        logger.info(f"Password changed for user: {user.email}")
        return True, None
    
    @staticmethod
    def deactivate_user(user: User, deactivated_by: Optional[User] = None) -> bool:
        """
        Deactivate a user account.
        
        Args:
            user: The user to deactivate
            deactivated_by: User performing the deactivation
            
        Returns:
            True if successful
        """
        user.is_active = False
        user.save(update_fields=['is_active'])
        
        # Revoke all sessions
        UserSession.objects.filter(
            user=user,
            is_revoked=False
        ).update(is_revoked=True, revoked_at=datetime.now())
        
        logger.info(f"User deactivated: {user.email} by {deactivated_by.email if deactivated_by else 'system'}")
        return True
    
    @staticmethod
    def reactivate_user(user: User, activated_by: Optional[User] = None) -> bool:
        """
        Reactivate a user account.
        
        Args:
            user: The user to reactivate
            activated_by: User performing the reactivation
            
        Returns:
            True if successful
        """
        user.is_active = True
        user.save(update_fields=['is_active'])
        
        logger.info(f"User reactivated: {user.email} by {activated_by.email if activated_by else 'system'}")
        return True
    
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
