"""
Enrollment Models for Enterprise LMS
Provides Enrollment and Progress tracking models.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class Enrollment(BaseModel):
    """
    Model representing a user's enrollment in a course.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='enrollments',
        help_text="User who is enrolled"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
        help_text="Course the user is enrolled in"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Current enrollment status"
    )
    progress_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Completion percentage (0.00 - 100.00)"
    )
    enrolled_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the user enrolled"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user completed the course"
    )
    
    class Meta:
        verbose_name = "Enrollment"
        verbose_name_plural = "Enrollments"
        ordering = ['-enrolled_at']
        unique_together = ['user', 'course']
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title}"
