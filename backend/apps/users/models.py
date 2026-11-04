"""
Users Models for Enterprise LMS
Provides User model with role-based access control, UserRole linking, and UserSession tracking.
"""

import uuid
from datetime import datetime

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel


class Role(TimestampedModel):
    """
    Role model for defining user roles in the system.
    Supports learner, instructor, admin, and custom roles.
    """
    ROLE_LEARNER = 'learner'
    ROLE_INSTRUCTOR = 'instructor'
    ROLE_ADMIN = 'admin'
    ROLE_CONTENT_MANAGER = 'content_manager'
    ROLE_SUPPORT = 'support'
    
    ROLE_CHOICES = [
        (ROLE_LEARNER, _('Learner')),
        (ROLE_INSTRUCTOR, _('Instructor')),
        (ROLE_ADMIN, _('Administrator')),
        (ROLE_CONTENT_MANAGER, _('Content Manager')),
        (ROLE_SUPPORT, _('Support Staff')),
    ]
    
    role_name = models.CharField(
        _('role name'),
        max_length=50,
        unique=True,
        choices=ROLE_CHOICES,
        help_text="System name for the role"
    )
    display_name = models.CharField(
        _('display name'),
        max_length=100,
        help_text="Human-readable name for the role"
    )
    description = models.TextField(
        _('description'),
        blank=True,
        help_text="Description of the role and its permissions"
    )
    permissions = models.JSONField(
        _('permissions'),
        default=list,
        blank=True,
        help_text="List of permission codenames for this role"
    )
    is_system_role = models.BooleanField(
        _('system role'),
        default=False,
        help_text="Whether this is a built-in system role that cannot be deleted"
    )
    
    class Meta:
        verbose_name = _('role')
        verbose_name_plural = _('roles')
        ordering = ['role_name']
    
    def __str__(self):
        return self.display_name


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    """
    Custom User model with UUID primary key and email-based authentication.
    Supports roles, MFA, and profile management.
    """
    email = models.EmailField(
        _('email address'),
        unique=True,
        help_text="User's email address (used for login)"
    )
    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        blank=True,
        help_text="User's display name"
    )
    first_name = models.CharField(
        _('first name'),
        max_length=150,
        blank=True,
        help_text="User's first name"
    )
    last_name = models.CharField(
        _('last name'),
        max_length=150,
        blank=True,
        help_text="User's last name"
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text="Whether the user account is active"
    )
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text="Whether the user can access the admin site"
    )
    email_verified = models.BooleanField(
        default=False,
        help_text="Whether the email address has been verified"
    )
    avatar_url = models.URLField(
        blank=True,
        help_text="URL to user's avatar image"
    )
    bio = models.TextField(
        blank=True,
        help_text="User's biography"
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        help_text="User's phone number"
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="User's preferred timezone"
    )
    locale = models.CharField(
        max_length=10,
        default='en-US',
        help_text="User's preferred locale"
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="User's date of birth"
    )
    
    # MFA fields
    mfa_enabled = models.BooleanField(
        _('MFA enabled'),
        default=False,
        help_text="Whether multi-factor authentication is enabled"
    )
    mfa_secret = models.CharField(
        _('MFA secret'),
        max_length=255,
        blank=True,
        help_text="Encrypted MFA secret key"
    )
    mfa_backup_codes = models.JSONField(
        _('MFA backup codes'),
        default=list,
        blank=True,
        help_text="Hashed MFA backup codes"
    )
    
    # Role relationship - using related_name to avoid conflicts
    # through_fields specifies which FK in UserRole to use for the M2M
    assigned_roles = models.ManyToManyField(
        Role,
        through='UserRole',
        through_fields=('user', 'role'),
        related_name='assigned_users',
        blank=True,
        help_text="Roles assigned to this user"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional user metadata"
    )
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Return the user's full name."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_short_name(self):
        """Return the user's short name."""
        return self.first_name or self.username or self.email
    
    def has_role(self, role_name):
        """Check if user has a specific role."""
        return self.assigned_roles.filter(role_name=role_name).exists()
    
    def get_primary_role(self):
        """Get the user's primary role (first assigned)."""
        role = self.assigned_roles.first()
        return role.role_name if role else None
    
    def is_admin(self):
        """Check if user is an administrator."""
        return self.has_role(Role.ROLE_ADMIN) or self.is_superuser
    
    def is_instructor(self):
        """Check if user is an instructor."""
        return self.has_role(Role.ROLE_INSTRUCTOR)


class UserRole(TimestampedModel):
    """
    Through model for User-Role relationship with timestamp tracking.
    Tracks when and by whom a role was assigned.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='user_role_links',
        help_text="User who has the role"
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='role_user_links',
        help_text="Role assigned to the user"
    )
    assigned_at = models.DateTimeField(
        _('assigned at'),
        auto_now_add=True,
        help_text="When the role was assigned"
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='roles_assigned',
        help_text="User who assigned this role"
    )
    expires_at = models.DateTimeField(
        _('expires at'),
        null=True,
        blank=True,
        help_text="Optional expiration date for temporary roles"
    )
    is_primary = models.BooleanField(
        _('primary role'),
        default=False,
        help_text="Whether this is the user's primary role"
    )
    
    class Meta:
        verbose_name = _('user role')
        verbose_name_plural = _('user roles')
        unique_together = ['user', 'role']
        ordering = ['-is_primary', '-assigned_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.role.display_name}"
    
    def is_expired(self):
        """Check if this role assignment has expired."""
        if self.expires_at:
            return datetime.now() > self.expires_at
        return False


class UserSession(TimestampedModel):
    """
    User session model for tracking active sessions and device information.
    Supports session revocation and device tracking.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions',
        help_text="User who owns this session"
    )
    session_key = models.CharField(
        _('session key'),
        max_length=255,
        unique=True,
        help_text="Django session key or JWT token identifier"
    )
    device_info = models.JSONField(
        _('device info'),
        default=dict,
        blank=True,
        help_text="Device information (user agent, OS, browser)"
    )
    ip_address = models.GenericIPAddressField(
        _('IP address'),
        null=True,
        blank=True,
        help_text="IP address of the session"
    )
    location = models.CharField(
        _('location'),
        max_length=255,
        blank=True,
        help_text="Geographic location of the session"
    )
    is_revoked = models.BooleanField(
        _('revoked'),
        default=False,
        help_text="Whether this session has been revoked"
    )
    revoked_at = models.DateTimeField(
        _('revoked at'),
        null=True,
        blank=True,
        help_text="When the session was revoked"
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revoked_sessions',
        help_text="User who revoked this session"
    )
    expires_at = models.DateTimeField(
        _('expires at'),
        null=True,
        blank=True,
        help_text="When this session expires"
    )
    last_activity_at = models.DateTimeField(
        _('last activity'),
        auto_now=True,
        help_text="Last activity timestamp"
    )
    
    class Meta:
        verbose_name = _('user session')
        verbose_name_plural = _('user sessions')
        ordering = ['-last_activity_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.session_key[:8]}..."
    
    def revoke(self, revoked_by=None):
        """Revoke this session."""
        self.is_revoked = True
        self.revoked_at = datetime.now()
        self.revoked_by = revoked_by
        self.save(update_fields=['is_revoked', 'revoked_at', 'revoked_by'])
    
    def is_expired(self):
        """Check if this session has expired."""
        if self.expires_at:
            return datetime.now() > self.expires_at
        return False
    
    def is_active(self):
        """Check if this session is active (not revoked and not expired)."""
        return not self.is_revoked and not self.is_expired()
