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
    
    # Session data (transient until commit)
    session_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Transient SCORM data for this session"
    )
    
    # Client information
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string from client"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the client"
    )
    
    class Meta:
        verbose_name = "SCORM Session"
        verbose_name_plural = "SCORM Sessions"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['registration', 'status']),
            models.Index(fields=['session_id']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        return f"Session {self.session_id} for {self.registration}"
    
    @property
    def duration_seconds(self):
        """Calculate session duration in seconds."""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
    
    def end_session(self, status=SESSION_STATUS_COMPLETED):
        """End this session with the specified status."""
        from django.utils import timezone
        self.status = status
        self.ended_at = timezone.now()
        self.save(update_fields=['status', 'ended_at', 'updated_at'])


class SCORMRuntimeData(TimestampedModel):
    """
    Model storing SCORM runtime data (cmi.* values) with full history.
    Maintains a history of all SCORM data commits for audit and recovery.
    """
    
    DATA_TYPE_COMMIT = 'commit'
    DATA_TYPE_FINISH = 'finish'
    DATA_TYPE_SUSPEND = 'suspend'
    
    DATA_TYPE_CHOICES = [
        (DATA_TYPE_COMMIT, 'Commit'),
        (DATA_TYPE_FINISH, 'Finish'),
        (DATA_TYPE_SUSPEND, 'Suspend'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='runtime_data_history',
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
        default=DATA_TYPE_COMMIT,
        help_text="Type of data storage event"
    )
    
    # Core SCORM data elements
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
    Model logging SCORM Cloud synchronization attempts and results.
    Used for debugging and monitoring external LMS integrations.
    """
    
    SYNC_STATUS_PENDING = 'pending'
    SYNC_STATUS_SUCCESS = 'success'
    SYNC_STATUS_FAILED = 'failed'
    SYNC_STATUS_RETRY = 'retry'
    
    SYNC_STATUS_CHOICES = [
        (SYNC_STATUS_PENDING, 'Pending'),
        (SYNC_STATUS_SUCCESS, 'Success'),
        (SYNC_STATUS_FAILED, 'Failed'),
        (SYNC_STATUS_RETRY, 'Retry'),
    ]
    
    registration = models.ForeignKey(
        SCORMRegistration,
        on_delete=models.CASCADE,
        related_name='sync_logs',
        help_text="Associated SCORM registration"
    )
    
    # Sync details
    sync_type = models.CharField(
        max_length=50,
        help_text="Type of sync operation (e.g., 'progress', 'completion', 'registration')"
    )
    status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_STATUS_PENDING,
        help_text="Sync status"
    )
    
    # Request/Response data
    request_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Data sent to SCORM Cloud"
    )
    response_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Response from SCORM Cloud"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if sync failed"
    )
    
    # Timing
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the sync started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the sync completed"
    )
    
    # Retry tracking
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    
    class Meta:
        verbose_name = "SCORM Cloud Sync Log"
        verbose_name_plural = "SCORM Cloud Sync Logs"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['registration', 'status']),
            models.Index(fields=['sync_type', 'status']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        return f"{self.sync_type} sync for {self.registration} - {self.status}"
    
    def mark_success(self, response_data=None):
        """Mark this sync as successful."""
        from django.utils import timezone
        self.status = self.SYNC_STATUS_SUCCESS
        self.completed_at = timezone.now()
        if response_data:
            self.response_data = response_data
        self.save(update_fields=['status', 'completed_at', 'response_data', 'updated_at'])
    
    def mark_failed(self, error_message, response_data=None):
        """Mark this sync as failed."""
        from django.utils import timezone
        self.status = self.SYNC_STATUS_FAILED
        self.completed_at = timezone.now()
        self.error_message = error_message
        if response_data:
            self.response_data = response_data
        self.save(update_fields=['status', 'completed_at', 'error_message', 'response_data', 'updated_at'])


class xAPIStatement(TimestampedModel):
    """
    Model storing xAPI (Experience API) statements.
    Converts SCORM data to xAPI format for LRS integration.
    """
    
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_RETRY = 'retry'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_RETRY, 'Retry'),
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
        help_text="Unique xAPI statement ID"
    )
    actor = models.JSONField(
        help_text="xAPI actor (learner) data"
    )
    verb = models.JSONField(
        help_text="xAPI verb data"
    )
    object = models.JSONField(
        help_text="xAPI object (activity) data"
    )
    result = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI result data"
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI context data"
    )
    timestamp = models.DateTimeField(
        help_text="xAPI statement timestamp"
    )
    
    # Full statement JSON
    statement_json = models.JSONField(
        help_text="Complete xAPI statement as JSON"
    )
    
    # Sending status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
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
            models.Index(fields=['registration', 'status']),
            models.Index(fields=['statement_id']),
            models.Index(fields=['status', 'retry_count']),
        ]
    
    def __str__(self):
        return f"xAPI Statement {self.statement_id} for {self.registration}"
