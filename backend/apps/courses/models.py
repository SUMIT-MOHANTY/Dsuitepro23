"""
Courses Models for Enterprise LMS
Provides Course, Module, Lesson, and ContentItem models.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


class Course(BaseModel):
    """
    Model representing a course in the LMS.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Review'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('private', 'Private'),
        ('enrolled', 'Enrolled Only'),
    ]
    
    title = models.CharField(
        max_length=255,
        help_text="Title of the course"
    )
    slug = models.SlugField(
        unique=True,
        help_text="URL-friendly identifier for the course"
    )
    description = models.TextField(
        blank=True,
        help_text="Course description"
    )
    syllabus = models.TextField(
        blank=True,
        help_text="Course syllabus"
    )
    instructor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='courses_created',
        help_text="Instructor who created the course"
    )
    thumbnail_url = models.URLField(
        blank=True,
        help_text="URL to course thumbnail image"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text="Current status of the course"
    )
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='public',
        help_text="Visibility level of the course"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Course price (0.00 for free courses)"
    )
    is_featured = models.BooleanField(
        default=False,
        help_text="Whether the course is featured"
    )
    max_enrollments = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of enrollments (null for unlimited)"
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the course was published"
    )
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Course start date"
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Course end date"
    )
    
    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class Module(BaseModel):
    """
    Model representing a module within a course.
    """
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='modules',
        help_text="Course this module belongs to"
    )
    title = models.CharField(
        max_length=255,
        help_text="Title of the module"
    )
    description = models.TextField(
        blank=True,
        help_text="Module description"
    )
    sequence_order = models.PositiveIntegerField(
        default=0,
        help_text="Order of this module within the course"
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Whether the module is published"
    )
    
    class Meta:
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        ordering = ['course', 'sequence_order']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
