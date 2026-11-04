"""
Courses Models for Enterprise LMS
Provides Course, Module, Lesson, and ContentItem models with hierarchical relationships.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

from apps.core.models import BaseModel, MetadataModel

User = get_user_model()


class Course(BaseModel, MetadataModel):
    """
    Model representing a course in the LMS.
    Supports hierarchical structure: Course -> Modules -> Lessons -> ContentItems
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
    
    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    
    CATEGORY_CHOICES = [
        ('technology', 'Technology'),
        ('business', 'Business'),
        ('design', 'Design'),
        ('marketing', 'Marketing'),
        ('health', 'Health & Wellness'),
        ('languages', 'Languages'),
        ('personal_development', 'Personal Development'),
        ('other', 'Other'),
    ]
    
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('CAD', 'Canadian Dollar'),
        ('AUD', 'Australian Dollar'),
    ]
    
    # Basic Information
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
    
    # Categorization
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='other',
        help_text="Course category"
    )
    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default='beginner',
        help_text="Difficulty level of the course"
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of tags for the course"
    )
    
    # Instructor Relationship
    instructor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='courses_created',
        help_text="Instructor who created the course"
    )
    
    # Media
    thumbnail = models.ImageField(
        upload_to='courses/thumbnails/%Y/%m/',
        blank=True,
        null=True,
        help_text="Course thumbnail image"
    )
    thumbnail_url = models.URLField(
        blank=True,
        help_text="URL to course thumbnail image"
    )
    
    # Status and Visibility
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True,
        help_text="Current status of the course"
    )
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='public',
        help_text="Visibility level of the course"
    )
    
    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
        help_text="Course price (0.00 for free courses)"
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD',
        help_text="Currency for the course price"
    )
    
    # Course Metrics
    duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Total duration of the course in minutes"
    )
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the course is featured"
    )
    max_enrollments = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of enrollments (null for unlimited)"
    )
    
    # Enrollment Statistics (denormalized for performance)
    enrollment_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of enrolled students"
    )
    rating_average = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        help_text="Average rating (0.00 to 5.00)"
    )
    rating_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of ratings received"
    )
    
    # Dates
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
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
        indexes = [
            models.Index(fields=['status', 'visibility']),
            models.Index(fields=['category', 'level']),
            models.Index(fields=['price', 'currency']),
            models.Index(fields=['is_featured', '-published_at']),
            models.Index(fields=['instructor', 'status']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def is_published(self):
        """Check if the course is published."""
        return self.status == 'published'
    
    @property
    def is_free(self):
        """Check if the course is free."""
        return self.price == 0
    
    @property
    def duration_display(self):
        """Return human-readable duration."""
        hours = self.duration_minutes // 60
        minutes = self.duration_minutes % 60
        if hours > 0:
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
        return f"{minutes}m"


class Module(BaseModel):
    """
    Model representing a module within a course.
    Modules are ordered containers for lessons.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
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
    order_index = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Order of this module within the course"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text="Current status of the module"
    )
    duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Total duration of the module in minutes"
    )
    
    class Meta:
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        ordering = ['course', 'order_index']
        unique_together = ['course', 'order_index']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    @property
    def is_published(self):
        """Check if the module is published."""
        return self.status == 'published'
    
    def save(self, *args, **kwargs):
        """Auto-assign order_index if not set."""
        if self.order_index == 0 and not self.pk:
            last_module = Module.objects.filter(course=self.course).order_by('-order_index').first()
            self.order_index = (last_module.order_index + 1) if last_module else 1
        super().save(*args, **kwargs)


class Lesson(BaseModel):
    """
    Model representing a lesson within a module.
    Lessons contain content items and track learning progress.
    """
    CONTENT_TYPE_CHOICES = [
        ('video', 'Video'),
        ('pdf', 'PDF Document'),
        ('scorm', 'SCORM Package'),
        ('text', 'Text Content'),
        ('quiz', 'Quiz'),
        ('assignment', 'Assignment'),
        ('interactive', 'Interactive Content'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='lessons',
        help_text="Module this lesson belongs to"
    )
    title = models.CharField(
        max_length=255,
        help_text="Title of the lesson"
    )
    description = models.TextField(
        blank=True,
        help_text="Lesson description"
    )
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        default='text',
        help_text="Type of content in this lesson"
    )
    duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Duration of the lesson in minutes"
    )
    order_index = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Order of this lesson within the module"
    )
    is_preview = models.BooleanField(
        default=False,
        help_text="Whether this lesson is available as a preview"
    )
    is_required = models.BooleanField(
        default=True,
        help_text="Whether this lesson must be completed"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text="Current status of the lesson"
    )
    
    class Meta:
        verbose_name = "Lesson"
        verbose_name_plural = "Lessons"
        ordering = ['module', 'order_index']
        unique_together = ['module', 'order_index']
    
    def __str__(self):
        return f"{self.module.title} - {self.title}"
    
    @property
    def is_published(self):
        """Check if the lesson is published."""
        return self.status == 'published'
    
    @property
    def course(self):
        """Get the course this lesson belongs to."""
        return self.module.course
    
    def save(self, *args, **kwargs):
        """Auto-assign order_index if not set."""
        if self.order_index == 0 and not self.pk:
            last_lesson = Lesson.objects.filter(module=self.module).order_by('-order_index').first()
            self.order_index = (last_lesson.order_index + 1) if last_lesson else 1
        super().save(*args, **kwargs)


class ContentItem(BaseModel, MetadataModel):
    """
    Model representing a content item within a lesson.
    Content items store the actual learning material (video, PDF, SCORM, etc.)
    """
    CONTENT_TYPE_CHOICES = [
        ('video', 'Video'),
        ('video_hls', 'Video (HLS)'),
        ('pdf', 'PDF Document'),
        ('scorm', 'SCORM Package'),
        ('text', 'Text Content'),
        ('html', 'HTML Content'),
        ('embed', 'Embedded Content'),
        ('download', 'Downloadable File'),
        ('link', 'External Link'),
    ]
    
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='content_items',
        help_text="Lesson this content item belongs to"
    )
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        help_text="Type of content"
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional title for this content item"
    )
    storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="Storage key/path for the content file"
    )
    file_url = models.URLField(
        blank=True,
        help_text="Direct URL to the content file"
    )
    file_size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Size of the file in bytes"
    )
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration in seconds (for video/audio)"
    )
    order_index = models.PositiveIntegerField(
        default=0,
        help_text="Order of this content item within the lesson"
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Whether this is the primary content for the lesson"
    )
    
    class Meta:
        verbose_name = "Content Item"
        verbose_name_plural = "Content Items"
        ordering = ['lesson', 'order_index']
    
    def __str__(self):
        return f"{self.lesson.title} - {self.get_content_type_display()}"
    
    @property
    def module(self):
        """Get the module this content item belongs to."""
        return self.lesson.module
    
    @property
    def course(self):
        """Get the course this content item belongs to."""
        return self.lesson.module.course
    
    def get_metadata_value(self, key, default=None):
        """Get a metadata value with dot-notation support."""
        if not self.metadata:
            return default
        keys = key.split('.')
        value = self.metadata
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
    
    def set_metadata_value(self, key, value):
        """Set a metadata value with dot-notation support."""
        if self.metadata is None:
            self.metadata = {}
        keys = key.split('.')
        target = self.metadata
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save(update_fields=['metadata'])
