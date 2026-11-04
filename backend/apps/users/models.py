"""
Users Models for Enterprise LMS
Provides User model with role-based access control.
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _

from apps.core.models import UUIDModel, TimestampedModel


class User(AbstractBaseUser, PermissionsMixin, UUIDModel, TimestampedModel):
    """
    Custom User model with UUID primary key and email-based authentication.
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
