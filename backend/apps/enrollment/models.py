"""
Enrollment Models for Enterprise LMS
Provides Enrollment, LearningPath, LearningPathItem, and LessonProgress models.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.core.models import BaseModel
from apps.courses.models import Course, Lesson

User = get_user_model()


class Enrollment(BaseModel):
    """
    Model representing a user's enrollment in a course.
    Tracks enrollment status, progress, and completion.
    """
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_DROPPED = 'dropped'
    STATUS_SUSPENDED = 'suspended'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_DROPPED, 'Dropped'),
        (STATUS_SUSPENDED, 'Suspended'),
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
        default=STATUS_PENDING,
        db_index=True,
        help_text="Current enrollment status"
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Completion percentage (0.00 - 100.00)"
    )
    enrolled_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the user enrolled"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the user completed the course"
    )
    last_accessed_lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_accessed_by',
        help_text="Last lesson the user accessed"
    )
    last_accessed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user last accessed the course"
    )
    total_time_spent_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Total time spent in the course (minutes)"
    )
    certificate_issued = models.BooleanField(
        default=False,
        help_text="Whether a certificate has been issued"
    )
    certificate_issued_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the certificate was issued"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this enrollment"
    )
    
    class Meta:
        verbose_name = "Enrollment"
        verbose_name_plural = "Enrollments"
        ordering = ['-enrolled_at']
        unique_together = ['user', 'course']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['course', 'status']),
            models.Index(fields=['status', 'enrolled_at']),
            models.Index(fields=['progress_percentage', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title}"
    
    @property
    def is_active(self):
        """Check if enrollment is active."""
        return self.status == self.STATUS_ACTIVE
    
    @property
    def is_completed(self):
        """Check if enrollment is completed."""
        return self.status == self.STATUS_COMPLETED
    
    @property
    def is_pending(self):
        """Check if enrollment is pending."""
        return self.status == self.STATUS_PENDING
    
    def mark_completed(self):
        """Mark enrollment as completed."""
        from django.utils import timezone
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.progress_percentage = 100.00
        self.save(update_fields=['status', 'completed_at', 'progress_percentage', 'updated_at'])
    
    def activate(self):
        """Activate a pending enrollment."""
        if self.status == self.STATUS_PENDING:
            self.status = self.STATUS_ACTIVE
            self.save(update_fields=['status', 'updated_at'])
    
    def update_progress(self, percentage):
        """Update progress percentage."""
        self.progress_percentage = min(100.00, max(0.00, percentage))
        if self.progress_percentage >= 100.00:
            self.mark_completed()
        else:
            self.save(update_fields=['progress_percentage', 'updated_at'])


class LearningPath(BaseModel):
    """
    Model representing a curated learning path consisting of multiple courses.
    Learning paths guide users through a structured sequence of courses.
    """
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ARCHIVED, 'Archived'),
    ]
    
    CATEGORY_TECHNOLOGY = 'technology'
    CATEGORY_BUSINESS = 'business'
    CATEGORY_DESIGN = 'design'
    CATEGORY_MARKETING = 'marketing'
    CATEGORY_LEADERSHIP = 'leadership'
    CATEGORY_OTHER = 'other'
    
    CATEGORY_CHOICES = [
        (CATEGORY_TECHNOLOGY, 'Technology'),
        (CATEGORY_BUSINESS, 'Business'),
        (CATEGORY_DESIGN, 'Design'),
        (CATEGORY_MARKETING, 'Marketing'),
        (CATEGORY_LEADERSHIP, 'Leadership'),
        (CATEGORY_OTHER, 'Other'),
    ]
    
    title = models.CharField(
        max_length=255,
        help_text="Title of the learning path"
    )
    slug = models.SlugField(
        unique=True,
        help_text="URL-friendly identifier for the learning path"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the learning path"
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
        help_text="Category of the learning path"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='learning_paths_created',
        help_text="User who created this learning path"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        help_text="Current status of the learning path"
    )
    thumbnail = models.ImageField(
        upload_to='learning_paths/thumbnails/%Y/%m/',
        blank=True,
        null=True,
        help_text="Learning path thumbnail image"
    )
    estimated_duration_hours = models.PositiveIntegerField(
        default=0,
        help_text="Estimated total duration in hours"
    )
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this learning path is featured"
    )
    prerequisites = models.JSONField(
        default=list,
        blank=True,
        help_text="List of prerequisite course IDs or requirements"
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the learning path was published"
    )
    
    class Meta:
        verbose_name = "Learning Path"
        verbose_name_plural = "Learning Paths"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'category']),
            models.Index(fields=['is_featured', '-published_at']),
            models.Index(fields=['created_by', 'status']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def is_published(self):
        """Check if learning path is published."""
        return self.status == self.STATUS_PUBLISHED
    
    @property
    def course_count(self):
        """Get the number of courses in this path."""
        return self.items.count()
    
    @property
    def required_course_count(self):
        """Get the number of required courses."""
        return self.items.filter(is_required=True).count()


class LearningPathItem(BaseModel):
    """
    Model representing a course item within a learning path.
    Defines the order and requirements for courses in a path.
    """
    path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="Learning path this item belongs to"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='learning_path_items',
        help_text="Course in this learning path"
    )
    order_index = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Order of this course within the path (1-based)"
    )
    is_required = models.BooleanField(
        default=True,
        help_text="Whether this course is required to complete the path"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description for this item"
    )
    
    class Meta:
        verbose_name = "Learning Path Item"
        verbose_name_plural = "Learning Path Items"
        ordering = ['path', 'order_index']
        unique_together = ['path', 'course']
        indexes = [
            models.Index(fields=['path', 'order_index']),
            models.Index(fields=['course', 'is_required']),
        ]
    
    def __str__(self):
        return f"{self.path.title} - {self.course.title}"
    
    def save(self, *args, **kwargs):
        """Auto-assign order_index if not set."""
        if self.order_index == 0 and not self.pk:
            last_item = LearningPathItem.objects.filter(path=self.path).order_by('-order_index').first()
            self.order_index = (last_item.order_index + 1) if last_item else 1
        super().save(*args, **kwargs)


class LearningPathEnrollment(BaseModel):
    """
    Model representing a user's enrollment in a learning path.
    Tracks overall progress through the path.
    """
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_DROPPED = 'dropped'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_DROPPED, 'Dropped'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='learning_path_enrollments',
        help_text="User enrolled in the learning path"
    )
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name='enrollments',
        help_text="Learning path the user is enrolled in"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Current enrollment status"
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Completion percentage of the learning path"
    )
    enrolled_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the user enrolled"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user completed the learning path"
    )
    
    class Meta:
        verbose_name = "Learning Path Enrollment"
        verbose_name_plural = "Learning Path Enrollments"
        ordering = ['-enrolled_at']
        unique_together = ['user', 'learning_path']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['learning_path', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.learning_path.title}"
    
    def calculate_progress(self):
        """Calculate progress based on completed course enrollments."""
        path_items = self.learning_path.items.all()
        if not path_items.exists():
            return 0.00
        
        required_items = path_items.filter(is_required=True)
        if not required_items.exists():
            required_items = path_items
        
        total_required = required_items.count()
        completed_count = 0
        
        for item in required_items:
            enrollment = Enrollment.objects.filter(
                user=self.user,
                course=item.course,
                status=Enrollment.STATUS_COMPLETED
            ).first()
            if enrollment:
                completed_count += 1
        
        progress = (completed_count / total_required) * 100 if total_required > 0 else 0
        self.progress_percentage = round(progress, 2)
        
        if self.progress_percentage >= 100:
            self.status = self.STATUS_COMPLETED
            from django.utils import timezone
            self.completed_at = timezone.now()
        
        self.save(update_fields=['progress_percentage', 'status', 'completed_at', 'updated_at'])
        return self.progress_percentage


class LessonProgress(BaseModel):
    """
    Model tracking a user's progress on individual lessons.
    Used to calculate overall course completion.
    """
    STATUS_NOT_STARTED = 'not_started'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_SKIPPED = 'skipped'
    
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, 'Not Started'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]
    
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='lesson_progress',
        help_text="Enrollment this progress belongs to"
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='progress_records',
        help_text="Lesson being tracked"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOT_STARTED,
        db_index=True,
        help_text="Current progress status"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user started this lesson"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user completed this lesson"
    )
    time_spent_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Time spent on this lesson (minutes)"
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Completion percentage for this lesson"
    )
    
    class Meta:
        verbose_name = "Lesson Progress"
        verbose_name_plural = "Lesson Progress Records"
        ordering = ['enrollment', 'lesson__module__order_index', 'lesson__order_index']
        unique_together = ['enrollment', 'lesson']
        indexes = [
            models.Index(fields=['enrollment', 'status']),
            models.Index(fields=['lesson', 'status']),
        ]
    
    def __str__(self):
        return f"{self.enrollment.user.email} - {self.lesson.title}"
    
    def mark_started(self):
        """Mark lesson as started."""
        from django.utils import timezone
        if self.status == self.STATUS_NOT_STARTED:
            self.status = self.STATUS_IN_PROGRESS
            self.started_at = timezone.now()
            self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_completed(self):
        """Mark lesson as completed."""
        from django.utils import timezone
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.progress_percentage = 100.00
        self.save(update_fields=['status', 'completed_at', 'progress_percentage', 'updated_at'])
        
        # Update enrollment's last accessed lesson
        self.enrollment.last_accessed_lesson = self.lesson
        self.enrollment.last_accessed_at = timezone.now()
        self.enrollment.save(update_fields=['last_accessed_lesson', 'last_accessed_at', 'updated_at'])


class PrerequisiteCourse(BaseModel):
    """
    Model defining prerequisite relationships between courses.
    Used to enforce course completion requirements before enrollment.
    """
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='prerequisites',
        help_text="Course that has prerequisites"
    )
    prerequisite_course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='required_for',
        help_text="Course that must be completed first"
    )
    is_strict = models.BooleanField(
        default=True,
        help_text="If True, prerequisite must be completed; if False, only enrolled"
    )
    
    class Meta:
        verbose_name = "Prerequisite Course"
        verbose_name_plural = "Prerequisite Courses"
        unique_together = ['course', 'prerequisite_course']
        ordering = ['course', 'prerequisite_course']
    
    def __str__(self):
        return f"{self.course.title} requires {self.prerequisite_course.title}"


class EnrollmentNote(BaseModel):
    """
    Model for storing notes/audit trail on enrollments.
    Used for tracking administrative actions and communications.
    """
    NOTE_TYPE_GENERAL = 'general'
    NOTE_TYPE_ADMIN = 'admin'
    NOTE_TYPE_PAYMENT = 'payment'
    NOTE_TYPE_ISSUE = 'issue'
    
    NOTE_TYPE_CHOICES = [
        (NOTE_TYPE_GENERAL, 'General'),
        (NOTE_TYPE_ADMIN, 'Administrative'),
        (NOTE_TYPE_PAYMENT, 'Payment'),
        (NOTE_TYPE_ISSUE, 'Issue'),
    ]
    
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='notes',
        help_text="Enrollment this note belongs to"
    )
    note_type = models.CharField(
        max_length=20,
        choices=NOTE_TYPE_CHOICES,
        default=NOTE_TYPE_GENERAL,
        help_text="Type of note"
    )
    content = models.TextField(
        help_text="Note content"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enrollment_notes_created',
        help_text="User who created this note"
    )
    is_internal = models.BooleanField(
        default=True,
        help_text="If True, note is internal only; if False, visible to user"
    )
    
    class Meta:
        verbose_name = "Enrollment Note"
        verbose_name_plural = "Enrollment Notes"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note on {self.enrollment} - {self.note_type}"
