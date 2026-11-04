"""
Calendar Models for Enterprise LMS
Provides CalendarEvent model for scheduling.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class CalendarEvent(BaseModel):
    """
    Model representing a calendar event.
    """
    EVENT_TYPES = [
        ('course_start', 'Course Start'),
        ('course_end', 'Course End'),
        ('assignment_due', 'Assignment Due'),
        ('quiz_start', 'Quiz Start'),
        ('quiz_end', 'Quiz End'),
        ('live_session', 'Live Session'),
        ('meeting', 'Meeting'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(
        max_length=255,
        help_text="Event title"
    )
    description = models.TextField(
        blank=True,
        help_text="Event description"
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        default='other',
        help_text="Type of event"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='calendar_events',
        help_text="Associated course (optional)"
    )
    start_time = models.DateTimeField(
        help_text="Event start time"
    )
    end_time = models.DateTimeField(
        help_text="Event end time"
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="Timezone for the event"
    )
    is_all_day = models.BooleanField(
        default=False,
        help_text="Whether this is an all-day event"
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Event location or URL"
    )
    attendees = models.ManyToManyField(
        User,
        blank=True,
        related_name='calendar_events',
        help_text="Users attending this event"
    )
    
    class Meta:
        verbose_name = "Calendar Event"
        verbose_name_plural = "Calendar Events"
        ordering = ['start_time']
    
    def __str__(self):
        return self.title
