"""
Analytics Models for Enterprise LMS
Provides data models for reporting and analytics.
"""

from django.db import models
from django.contrib.auth import get_user_model

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
