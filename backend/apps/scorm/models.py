"""
SCORM Models for Enterprise LMS
Provides SCORM registration and runtime data tracking.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class SCORMRegistration(BaseModel):
    """
    Model representing a user's registration for SCORM content.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scorm_registrations',
        help_text="User registered for SCORM content"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='scorm_registrations',
        help_text="Course containing SCORM content"
    )
    scorm_package_url = models.URLField(
        help_text="URL to the SCORM package"
    )
    registration_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique registration identifier"
    )
    
    class Meta:
        verbose_name = "SCORM Registration"
        verbose_name_plural = "SCORM Registrations"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title}"


class SCORMRuntimeData(BaseModel):
    """
    Model storing SCORM runtime data (cmi.* values).
    """
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='runtime_data',
        help_text="Associated SCORM registration"
    )
    lesson_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Current bookmark/location in the content"
    )
    suspend_data = models.TextField(
        blank=True,
        help_text="SCORM suspend_data for resume functionality"
    )
    lesson_status = models.CharField(
        max_length=50,
        blank=True,
        help_text="Current lesson status (passed/failed/incomplete/completed)"
    )
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Raw score achieved"
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum possible score"
    )
    score_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum possible score"
    )
    total_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Total time spent in the content"
    )
    session_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Time spent in current session"
    )
    
    class Meta:
        verbose_name = "SCORM Runtime Data"
        verbose_name_plural = "SCORM Runtime Data"
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Runtime data for {self.registration}"
