"""
Notifications Models for Enterprise LMS
Provides Notification model for email and in-app notifications.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


class Notification(BaseModel):
    """
    Model representing a notification for a user.
    """
    NOTIFICATION_TYPES = [
        ('email', 'Email'),
        ('in_app', 'In-App'),
        ('push', 'Push'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="User who receives the notification"
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default='in_app',
        help_text="Type of notification"
    )
    title = models.CharField(
        max_length=255,
        help_text="Notification title"
    )
    message = models.TextField(
        help_text="Notification message"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Current delivery status"
    )
    action_url = models.URLField(
        blank=True,
        help_text="URL to navigate to when notification is clicked"
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was sent"
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was read"
    )
    
    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type} - {self.title}"
