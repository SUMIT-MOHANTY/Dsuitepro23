"""
SCORM Models for Enterprise LMS
Provides SCORM 1.2 runtime with registration, suspend/resume data, completion status, and SCORM Cloud integration.
"""

import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.core.models import BaseModel, TimestampedModel
from apps.courses.models import ContentItem

User = get_user_model()


# SCORM 1.2 Error Codes
class SCORMErrorCodes:
    """SCORM 1.2 RTE Error Codes"""
    NO_ERROR = '0'
    GENERAL_EXCEPTION = '101'
    INVALID_ARGUMENT = '201'
    ELEMENT_CANNOT_HAVE_CHILDREN = '202'
    ELEMENT_NOT_ARRAY = '203'
    NOT_INITIALIZED = '301'
    ALREADY_INITIALIZED = '302'
    API_NOT_IMPLEMENTED = '401'
    INVALID_SET_VALUE_KEYWORD = '402'
    ELEMENT_READ_ONLY = '403'
    ELEMENT_WRITE_ONLY = '404'
    INCORRECT_DATA_TYPE = '405'
    
    ERROR_MESSAGES = {
        NO_ERROR: 'No error',
        GENERAL_EXCEPTION: 'General exception',
        INVALID_ARGUMENT: 'Invalid argument error',
        ELEMENT_CANNOT_HAVE_CHILDREN: 'Element cannot have children',
        ELEMENT_NOT_ARRAY: 'Element not an array - cannot have count',
        NOT_INITIALIZED: 'Not initialized',
        ALREADY_INITIALIZED: 'Already initialized',
        API_NOT_IMPLEMENTED: 'Not implemented error',
        INVALID_SET_VALUE_KEYWORD: 'Invalid set value, element is a keyword',
        ELEMENT_READ_ONLY: 'Element is read only',
        ELEMENT_WRITE_ONLY: 'Element is write only',
        INCORRECT_DATA_TYPE: 'Incorrect data type',
    }


# SCORM 1.2 Lesson Status Values
class SCORMLessonStatus:
    """SCORM 1.2 cmi.core.lesson_status values"""
    PASSED = 'passed'
    COMPLETED = 'completed'
    FAILED = 'failed'
    INCOMPLETE = 'incomplete'
    NOT_ATTEMPTED = 'not attempted'
    BROWSED = 'browsed'
    
    CHOICES = [
        (PASSED, 'Passed'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
        (INCOMPLETE, 'Incomplete'),
        (NOT_ATTEMPTED, 'Not Attempted'),
        (BROWSED, 'Browsed'),
    ]


# SCORM 1.2 Entry Values
class SCORMEntry:
    """SCORM 1.2 cmi.core.entry values"""
    AB_INITIO = 'ab-initio'
    RESUME = 'resume'
    EMPTY = ''
    
    CHOICES = [
        (AB_INITIO, 'Ab-initio'),
        (RESUME, 'Resume'),
        (EMPTY, 'Empty'),
    ]


# SCORM 1.2 Exit Values
class SCORMExit:
    """SCORM 1.2 cmi.core.exit values"""
    SUSPEND = 'suspend'
    LOGOUT = 'logout'
    TIMEOUT = 'timeout'
    NORMAL = ''
    
    CHOICES = [
        (SUSPEND, 'Suspend'),
        (LOGOUT, 'Logout'),
        (TIMEOUT, 'Timeout'),
        (NORMAL, 'Normal'),
    ]


# SCORM 1.2 Credit Values
class SCORMCredit:
    """SCORM 1.2 cmi.core.credit values"""
    CREDIT = 'credit'
    NO_CREDIT = 'no-credit'
    
    CHOICES = [
        (CREDIT, 'Credit'),
        (NO_CREDIT, 'No Credit'),
    ]


# SCORM 1.2 Lesson Mode Values
class SCORMLessonMode:
    """SCORM 1.2 cmi.core.lesson_mode values"""
    BROWSE = 'browse'
    NORMAL = 'normal'
    REVIEW = 'review'
    
    CHOICES = [
        (BROWSE, 'Browse'),
        (NORMAL, 'Normal'),
        (REVIEW, 'Review'),
    ]


# SCORM Registration Status
class SCORMRegistrationStatus:
    """Internal SCORM registration status"""
    NOT_ATTEMPTED = 'not_attempted'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    PASSED = 'passed'
    FAILED = 'failed'
    SUSPENDED = 'suspended'
    
    CHOICES = [
        (NOT_ATTEMPTED, 'Not Attempted'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed'),
        (PASSED, 'Passed'),
        (FAILED, 'Failed'),
        (SUSPENDED, 'Suspended'),
    ]


class SCORMRegistration(BaseModel):
    """
    Model representing a user's registration for SCORM content.
    Tracks learner progress through SCORM packages with SCORM Cloud integration support.
    """
    
    # Status choices for SCORM registration
    STATUS_NOT_ATTEMPTED = 'not_attempted'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_PASSED = 'passed'
    STATUS_FAILED = 'failed'
    STATUS_SUSPENDED = 'suspended'
    
    STATUS_CHOICES = [
        (STATUS_NOT_ATTEMPTED, 'Not Attempted'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_PASSED, 'Passed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SUSPENDED, 'Suspended'),
    ]
    
    # Completion status choices (SCORM 1.2 cmi.core.lesson_status)
    COMPLETION_STATUS_NOT_ATTEMPTED = 'not attempted'
    COMPLETION_STATUS_INCOMPLETE = 'incomplete'
    COMPLETION_STATUS_COMPLETED = 'completed'
    COMPLETION_STATUS_PASSED = 'passed'
    COMPLETION_STATUS_FAILED = 'failed'
    
    COMPLETION_STATUS_CHOICES = [
        (COMPLETION_STATUS_NOT_ATTEMPTED, 'Not Attempted'),
        (COMPLETION_STATUS_INCOMPLETE, 'Incomplete'),
        (COMPLETION_STATUS_COMPLETED, 'Completed'),
        (COMPLETION_STATUS_PASSED, 'Passed'),
        (COMPLETION_STATUS_FAILED, 'Failed'),
    ]
    
    # Exit status choices
    EXIT_STATUS_TIMEOUT = 'timeout'
    EXIT_STATUS_SUSPEND = 'suspend'
    EXIT_STATUS_LOGOUT = 'logout'
    EXIT_STATUS_NORMAL = ''
    
    EXIT_STATUS_CHOICES = [
        (EXIT_STATUS_TIMEOUT, 'Timeout'),
        (EXIT_STATUS_SUSPEND, 'Suspend'),
        (EXIT_STATUS_LOGOUT, 'Logout'),
        (EXIT_STATUS_NORMAL, 'Normal'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scorm_registrations',
        help_text="User registered for SCORM content"
    )
    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name='scorm_registrations',
        help_text="Content item (SCORM package) being accessed"
    )
    
    # SCORM Cloud Integration
    scorm_cloud_registration_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="SCORM Cloud registration ID for external content"
    )
    scorm_cloud_course_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="SCORM Cloud course ID"
    )
    
    # Registration metadata
    registration_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique registration identifier (internal)"
    )
    launch_url = models.URLField(
        blank=True,
        help_text="URL to launch the SCORM content"
    )
    
    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOT_ATTEMPTED,
        db_index=True,
        help_text="Current registration status"
    )
    completion_status = models.CharField(
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default=COMPLETION_STATUS_NOT_ATTEMPTED,
        db_index=True,
        help_text="SCORM completion status (cmi.core.lesson_status)"
    )
    exit_status = models.CharField(
        max_length=20,
        choices=EXIT_STATUS_CHOICES,
        default=EXIT_STATUS_NORMAL,
        blank=True,
        help_text="Exit status from last session"
    )
    
    # Score tracking
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Raw score achieved (cmi.core.score.raw)"
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Maximum possible score (cmi.core.score.max)"
    )
    score_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Minimum possible score (cmi.core.score.min)"
    )
    
    # Time tracking
    total_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Total time spent in the content (cmi.core.total_time) - HHHH:MM:SS format"
    )
    session_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Time spent in current session (cmi.core.session_time)"
    )
    
    # Suspend/Resume data
    lesson_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Current bookmark/location in the content (cmi.core.lesson_location)"
    )
    suspend_data = models.TextField(
        blank=True,
        help_text="SCORM suspend_data for resume functionality (cmi.suspend_data)"
    )
    
    # SCORM 1.2 specific fields
    credit = models.CharField(
        max_length=20,
        default='credit',
        help_text="Credit mode (cmi.core.credit)"
    )
    lesson_mode = models.CharField(
        max_length=20,
        default='normal',
        help_text="Lesson mode (cmi.core.lesson_mode)"
    )
    entry = models.CharField(
        max_length=20,
        default='ab-initio',
        help_text="Entry status (cmi.core.entry)"
    )
    
    # Launch tracking
    launch_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this registration has been launched"
    )
    last_launched_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the registration was last launched"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the registration was completed"
    )
    
    # SCORM Cloud sync
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When progress was last synced with SCORM Cloud"
    )
    sync_status = models.CharField(
        max_length=20,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('synced', 'Synced'),
            ('failed', 'Failed'),
            ('disabled', 'Disabled'),
        ],
        help_text="SCORM Cloud sync status"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional SCORM metadata"
    )
    
    class Meta:
        verbose_name = "SCORM Registration"
        verbose_name_plural = "SCORM Registrations"
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'content_item', 'status']),
            models.Index(fields=['scorm_cloud_registration_id']),
            models.Index(fields=['status', 'completion_status']),
            models.Index(fields=['user', 'completed_at']),
        ]
        unique_together = ['user', 'content_item']
    
    def __str__(self):
        return f"{self.user.email} - {self.content_item.title}"
    
    @property
    def student_id(self):
        """Return student ID for SCORM cmi.core.student_id"""
        return str(self.user.id)
    
    @property
    def student_name(self):
        """Return student name for SCORM cmi.core.student_name"""
        return self.user.get_full_name() or self.user.email
    
    @property
    def is_completed(self):
        """Check if the SCORM content is completed."""
        return self.completion_status in [self.COMPLETION_STATUS_COMPLETED, self.COMPLETION_STATUS_PASSED]
    
    @property
    def is_passed(self):
        """Check if the SCORM content is passed."""
        return self.completion_status == self.COMPLETION_STATUS_PASSED
    
    @property
    def is_failed(self):
        """Check if the SCORM content is failed."""
        return self.completion_status == self.COMPLETION_STATUS_FAILED
    
    @property
    def score_percentage(self):
        """Calculate score percentage if raw and max scores are available."""
        if self.score_raw is not None and self.score_max and self.score_max > 0:
            return (self.score_raw / self.score_max) * 100
        return None
    
    def increment_launch_count(self):
        """Increment the launch count and update last launched timestamp."""
        from django.utils import timezone
        self.launch_count += 1
        self.last_launched_at = timezone.now()
        self.save(update_fields=['launch_count', 'last_launched_at', 'updated_at'])
    
    def mark_completed(self):
        """Mark this registration as completed."""
        from django.utils import timezone
        self.status = self.STATUS_COMPLETED
        self.completion_status = self.COMPLETION_STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completion_status', 'completed_at', 'updated_at'])
    
    def mark_passed(self, score=None):
        """Mark this registration as passed with optional score."""
        from django.utils import timezone
        self.status = self.STATUS_PASSED
        self.completion_status = self.COMPLETION_STATUS_PASSED
        if score is not None:
            self.score_raw = score
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completion_status', 'score_raw', 'completed_at', 'updated_at'])
    
    def mark_failed(self, score=None):
        """Mark this registration as failed with optional score."""
        from django.utils import timezone
        self.status = self.STATUS_FAILED
        self.completion_status = self.COMPLETION_STATUS_FAILED
        if score is not None:
            self.score_raw = score
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completion_status', 'score_raw', 'completed_at', 'updated_at'])
    
    def mark_suspended(self):
        """Mark this registration as suspended."""
        self.status = self.STATUS_SUSPENDED
        self.exit_status = self.EXIT_STATUS_SUSPEND
        self.save(update_fields=['status', 'exit_status', 'updated_at'])
    
    def calculate_entry_mode(self):
        """Calculate entry mode based on previous session data."""
        if self.total_time and self.total_time != '0000:00:00':
            return self.ENTRY_STATUS_RESUME
        return self.ENTRY_STATUS_AB_INITIO


class SCORMSession(TimestampedModel):
    """
    Model tracking individual SCORM learning sessions.
    A session starts when the user launches content and ends when they finish or suspend.
    """
    
    SESSION_STATUS_ACTIVE = 'active'
    SESSION_STATUS_SUSPENDED = 'suspended'
    SESSION_STATUS_COMPLETED = 'completed'
    SESSION_STATUS_TERMINATED = 'terminated'
    SESSION_STATUS_TIMEOUT = 'timeout'
    
    SESSION_STATUS_CHOICES = [
        (SESSION_STATUS_ACTIVE, 'Active'),
        (SESSION_STATUS_SUSPENDED, 'Suspended'),
        (SESSION_STATUS_COMPLETED, 'Completed'),
        (SESSION_STATUS_TERMINATED, 'Terminated'),
        (SESSION_STATUS_TIMEOUT, 'Timeout'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='sessions',
        help_text="Associated SCORM registration"
    )
    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique session identifier"
    )
    
    # Session status
    status = models.CharField(
        max_length=20,
        choices=SESSION_STATUS_CHOICES,
        default=SESSION_STATUS_ACTIVE,
        db_index=True,
        help_text="Current session status"
    )
    
    # Timing
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the session started"
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session ended"
    )
    last_activity_at = models.DateTimeField(
        auto_now=True,
        help_text="Last activity timestamp"
    )
    
    # Session tracking
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this session is currently active"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string from the browser"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the learner"
    )
    
    # SCORM 1.2 RTE State Tracking
    api_initialized = models.BooleanField(
        default=False,
        help_text="Whether LMSInitialize has been called"
    )
    last_error_code = models.CharField(
        max_length=10,
        default='0',
        help_text="Last SCORM error code (cmi.core.last_error)"
    )
    error_diagnostic = models.TextField(
        blank=True,
        help_text="Diagnostic information for the last error"
    )
    launch_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the SCORM content was launched"
    )
    commit_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last LMSCommit was called"
    )
    
    # Accumulated session time (in seconds)
    accumulated_time = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated session time in seconds"
    )
    
    # Current CMI data snapshot (for quick access)
    cmi_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Current CMI data snapshot"
    )
    
    class Meta:
        verbose_name = "SCORM Session"
        verbose_name_plural = "SCORM Sessions"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['registration', 'is_active']),
            models.Index(fields=['session_id']),
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['started_at']),
            models.Index(fields=['last_activity_at']),
        ]
    
    def __str__(self):
        return f"Session {self.session_id} for {self.registration}"
    
    def end_session(self, status=None):
        """End this session with the given status."""
        from django.utils import timezone
        self.is_active = False
        self.ended_at = timezone.now()
        if status:
            self.status = status
        self.save(update_fields=['is_active', 'ended_at', 'status', 'updated_at'])
    
    def mark_suspended(self):
        """Mark this session as suspended."""
        self.end_session(self.SESSION_STATUS_SUSPENDED)
    
    def mark_completed(self):
        """Mark this session as completed."""
        self.end_session(self.SESSION_STATUS_COMPLETED)
    
    def mark_timeout(self):
        """Mark this session as timed out."""
        self.end_session(self.SESSION_STATUS_TIMEOUT)
    
    def update_activity(self):
        """Update the last activity timestamp."""
        from django.utils import timezone
        self.last_activity_at = timezone.now()
        self.save(update_fields=['last_activity_at'])
    
    def set_error(self, code, diagnostic=''):
        """Set the last error code and diagnostic."""
        self.last_error_code = code
        self.error_diagnostic = diagnostic
        self.save(update_fields=['last_error_code', 'error_diagnostic', 'updated_at'])
    
    def clear_error(self):
        """Clear the error state."""
        self.last_error_code = '0'
        self.error_diagnostic = ''
        self.save(update_fields=['last_error_code', 'error_diagnostic', 'updated_at'])
    
    def record_commit(self):
        """Record a commit operation."""
        from django.utils import timezone
        self.commit_time = timezone.now()
        self.save(update_fields=['commit_time', 'updated_at'])
    
    def record_launch(self):
        """Record the launch time."""
        from django.utils import timezone
        self.launch_time = timezone.now()
        self.save(update_fields=['launch_time', 'updated_at'])


class SCORMRuntimeData(TimestampedModel):
    """
    Model storing SCORM runtime data (cmi.* values).
    Tracks the current state of SCORM data elements during a session.
    """
    
    DATA_TYPE_CURRENT = 'current'
    DATA_TYPE_SNAPSHOT = 'snapshot'
    DATA_TYPE_COMMIT = 'commit'
    
    DATA_TYPE_CHOICES = [
        (DATA_TYPE_CURRENT, 'Current'),
        (DATA_TYPE_SNAPSHOT, 'Snapshot'),
        (DATA_TYPE_COMMIT, 'Commit'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='runtime_data',
        help_text="Associated SCORM registration"
    )
    session = models.ForeignKey(
        SCORMSession,
        on_delete=models.CASCADE,
        related_name='runtime_data',
        null=True,
        blank=True,
        help_text="Associated SCORM session"
    )
    
    # Data type
    data_type = models.CharField(
        max_length=20,
        choices=DATA_TYPE_CHOICES,
        default=DATA_TYPE_CURRENT,
        help_text="Type of runtime data"
    )
    
    # Core CMI data
    lesson_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Current bookmark/location in the content (cmi.core.lesson_location)"
    )
    suspend_data = models.TextField(
        blank=True,
        help_text="SCORM suspend_data for resume functionality (cmi.suspend_data)"
    )
    lesson_status = models.CharField(
        max_length=50,
        blank=True,
        help_text="Current lesson status (cmi.core.lesson_status)"
    )
    
    # Score data
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Raw score achieved (cmi.core.score.raw)"
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum possible score (cmi.core.score.max)"
    )
    score_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum possible score (cmi.core.score.min)"
    )
    
    # Time data
    total_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Total time spent in the content (cmi.core.total_time)"
    )
    session_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Time spent in current session (cmi.core.session_time)"
    )
    
    # Additional SCORM data (flexible storage)
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional SCORM data elements"
    )
    
    class Meta:
        verbose_name = "SCORM Runtime Data"
        verbose_name_plural = "SCORM Runtime Data"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['registration', '-created_at']),
            models.Index(fields=['session', 'data_type']),
        ]
    
    def __str__(self):
        return f"Runtime data for {self.registration} at {self.created_at}"


class SCORMInteraction(BaseModel):
    """
    Model storing SCORM interaction data (cmi.interactions.*).
    Tracks learner interactions with the content (questions, objectives, etc.).
    """
    
    RESULT_CHOICES = [
        ('correct', 'Correct'),
        ('wrong', 'Wrong'),
        ('unanticipated', 'Unanticipated'),
        ('neutral', 'Neutral'),
        ('', 'Not Set'),
    ]
    
    TYPE_CHOICES = [
        ('true-false', 'True/False'),
        ('choice', 'Multiple Choice'),
        ('fill-in', 'Fill In'),
        ('matching', 'Matching'),
        ('performance', 'Performance'),
        ('sequencing', 'Sequencing'),
        ('likert', 'Likert'),
        ('numeric', 'Numeric'),
        ('other', 'Other'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='interactions',
        help_text="Associated SCORM registration"
    )
    
    # Interaction identification
    interaction_id = models.CharField(
        max_length=255,
        help_text="Unique identifier for this interaction (cmi.interactions.n.id)"
    )
    interaction_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        help_text="Type of interaction (cmi.interactions.n.type)"
    )
    
    # Interaction data
    objectives = models.JSONField(
        default=list,
        blank=True,
        help_text="Objectives associated with this interaction"
    )
    timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the interaction occurred"
    )
    correct_responses = models.JSONField(
        default=list,
        blank=True,
        help_text="Correct response patterns"
    )
    weighting = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Weight of this interaction"
    )
    student_response = models.TextField(
        blank=True,
        help_text="Learner's response"
    )
    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES,
        default='',
        blank=True,
        help_text="Result of the interaction"
    )
    latency = models.CharField(
        max_length=20,
        blank=True,
        help_text="Time taken to respond (HHHH:MM:SS format)"
    )
    
    # Ordering
    interaction_index = models.PositiveIntegerField(
        default=0,
        help_text="Index of this interaction"
    )
    
    class Meta:
        verbose_name = "SCORM Interaction"
        verbose_name_plural = "SCORM Interactions"
        ordering = ['registration', 'interaction_index']
        unique_together = ['registration', 'interaction_id']
        indexes = [
            models.Index(fields=['registration', 'interaction_index']),
            models.Index(fields=['interaction_id']),
        ]
    
    def __str__(self):
        return f"Interaction {self.interaction_id} for {self.registration}"


class SCORMObjective(BaseModel):
    """
    Model storing SCORM objective data (cmi.objectives.*).
    Tracks learning objectives and their completion status.
    """
    
    STATUS_CHOICES = [
        ('passed', 'Passed'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('incomplete', 'Incomplete'),
        ('not attempted', 'Not Attempted'),
        ('browsed', 'Browsed'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='objectives',
        help_text="Associated SCORM registration"
    )
    
    # Objective identification
    objective_id = models.CharField(
        max_length=255,
        help_text="Unique identifier for this objective (cmi.objectives.n.id)"
    )
    
    # Objective status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not attempted',
        help_text="Status of this objective"
    )
    
    # Score data
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Raw score for this objective"
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum score for this objective"
    )
    score_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum score for this objective"
    )
    
    # Ordering
    objective_index = models.PositiveIntegerField(
        default=0,
        help_text="Index of this objective"
    )
    
    class Meta:
        verbose_name = "SCORM Objective"
        verbose_name_plural = "SCORM Objectives"
        ordering = ['registration', 'objective_index']
        unique_together = ['registration', 'objective_id']
        indexes = [
            models.Index(fields=['registration', 'objective_index']),
            models.Index(fields=['objective_id']),
        ]
    
    def __str__(self):
        return f"Objective {self.objective_id} for {self.registration}"


class SCORMCloudSyncLog(TimestampedModel):
    """
    Model logging SCORM Cloud synchronization attempts.
    Tracks sync status for debugging and audit purposes.
    """
    
    SYNC_TYPE_CHOICES = [
        ('push', 'Push to Cloud'),
        ('pull', 'Pull from Cloud'),
        ('webhook', 'Webhook'),
        ('manual', 'Manual Sync'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='sync_logs',
        help_text="Associated SCORM registration"
    )
    
    sync_type = models.CharField(
        max_length=20,
        choices=SYNC_TYPE_CHOICES,
        help_text="Type of synchronization"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Sync status"
    )
    
    # Sync details
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the sync started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the sync completed"
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if sync failed"
    )
    
    # Raw responses
    scorm_cloud_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw response from SCORM Cloud"
    )
    
    class Meta:
        verbose_name = "SCORM Cloud Sync Log"
        verbose_name_plural = "SCORM Cloud Sync Logs"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['registration', '-started_at']),
            models.Index(fields=['status', 'sync_type']),
        ]
    
    def __str__(self):
        return f"{self.sync_type} sync for {self.registration} - {self.status}"


class xAPIStatement(TimestampedModel):
    """
    Model storing xAPI (Experience API) statements.
    Converts SCORM data to xAPI format for LRS integration.
    """
    
    VERB_CHOICES = [
        ('initialized', 'Initialized'),
        ('launched', 'Launched'),
        ('attempted', 'Attempted'),
        ('experienced', 'Experienced'),
        ('completed', 'Completed'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('suspended', 'Suspended'),
        ('resumed', 'Resumed'),
        ('terminated', 'Terminated'),
        ('interacted', 'Interacted'),
        ('answered', 'Answered'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='xapi_statements',
        help_text="Associated SCORM registration"
    )
    
    # xAPI statement data
    statement_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique xAPI statement ID"
    )
    verb = models.CharField(
        max_length=50,
        choices=VERB_CHOICES,
        help_text="xAPI verb"
    )
    
    # Statement content
    actor = models.JSONField(
        help_text="xAPI actor (learner)"
    )
    object_data = models.JSONField(
        help_text="xAPI object (activity)"
    )
    result = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI result data"
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI context"
    )
    
    # Full statement
    full_statement = models.JSONField(
        help_text="Complete xAPI statement"
    )
    
    # Sending status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Statement sending status"
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the statement was sent to LRS"
    )
    lrs_response = models.TextField(
        blank=True,
        help_text="Response from LRS"
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    
    class Meta:
        verbose_name = "xAPI Statement"
        verbose_name_plural = "xAPI Statements"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['registration', '-created_at']),
            models.Index(fields=['status', 'verb']),
            models.Index(fields=['statement_id']),
        ]
    
    def __str__(self):
        return f"{self.verb} statement for {self.registration}"
