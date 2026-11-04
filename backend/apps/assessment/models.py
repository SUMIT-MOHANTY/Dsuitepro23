"""
Assessment Models for Enterprise LMS
Provides data models for quizzes, assignments, questions, and grading.
"""

import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.core.models import BaseModel

User = get_user_model()


class Quiz(BaseModel):
    """
    Model representing a quiz assessment.
    """
    # Course relationship
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='quizzes',
        help_text="Course this quiz belongs to"
    )
    
    # Basic Information
    title = models.CharField(
        max_length=255,
        help_text="Title of the quiz"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the quiz"
    )
    
    # Quiz Settings
    time_limit_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time limit in minutes (null for no limit)"
    )
    passing_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=70.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Minimum score required to pass (percentage)"
    )
    max_attempts = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of attempts allowed (0 for unlimited)"
    )
    randomize_questions = models.BooleanField(
        default=False,
        help_text="Whether to randomize question order"
    )
    show_correct_answers = models.BooleanField(
        default=False,
        help_text="Whether to show correct answers after submission"
    )
    
    # Status
    is_published = models.BooleanField(
        default=False,
        help_text="Whether the quiz is published and available"
    )
    
    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'is_published']),
            models.Index(fields=['is_published', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    @property
    def total_points(self):
        """Calculate total points for all questions in the quiz."""
        return sum(q.points for q in self.questions.all())
    
    @property
    def question_count(self):
        """Return the number of questions in the quiz."""
        return self.questions.count()


class Question(BaseModel):
    """
    Model representing a question in a quiz.
    """
    QUESTION_TYPES = [
        ('mcq', 'Multiple Choice'),
        ('multi_select', 'Multiple Select'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
        ('match', 'Matching'),
    ]
    
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='questions',
        help_text="Quiz this question belongs to"
    )
    question_text = models.TextField(
        help_text="The question text"
    )
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES,
        default='mcq',
        help_text="Type of question"
    )
    
    # Options stored as JSON for flexibility
    # For MCQ: {"A": "Option A text", "B": "Option B text", ...}
    # For match: {"left": ["Item 1", "Item 2"], "right": ["Match 1", "Match 2"]}
    options = models.JSONField(
        default=dict,
        blank=True,
        help_text="Question options (for MCQ, multi-select, matching)"
    )
    
    # Correct answer stored as JSON
    # For MCQ: "A"
    # For multi_select: ["A", "C"]
    # For short_answer: ["acceptable", "answer", "variations"]
    # For match: {"Item 1": "Match 1", "Item 2": "Match 2"}
    correct_answer = models.JSONField(
        default=None,
        null=True,
        blank=True,
        help_text="Correct answer(s) for auto-grading"
    )
    
    points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(0)],
        help_text="Points awarded for correct answer"
    )
    order_index = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Order of this question in the quiz"
    )
    
    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ['order_index', 'created_at']
        indexes = [
            models.Index(fields=['quiz', 'order_index']),
        ]
    
    def __str__(self):
        return f"{self.quiz.title} - Question {self.order_index}"
    
    def is_auto_gradable(self):
        """Check if this question type can be auto-graded."""
        return self.question_type in ['mcq', 'multi_select', 'match']


class QuizAttempt(BaseModel):
    """
    Model representing a user's attempt at a quiz.
    """
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('expired', 'Expired'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
        help_text="User who attempted the quiz"
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts',
        help_text="Quiz that was attempted"
    )
    
    # Timing
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the attempt was started"
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the attempt was submitted"
    )
    
    # Scoring
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Score achieved (points)"
    )
    score_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Score as percentage"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        db_index=True,
        help_text="Current status of the attempt"
    )
    
    # Answers stored as JSON
    # Format: {"question_id": "answer", ...}
    # MCQ: "A"
    # Multi-select: ["A", "C"]
    # Short answer/essay: "User's text response"
    answers = models.JSONField(
        default=dict,
        blank=True,
        help_text="User's answers to questions"
    )
    
    # IP tracking for anti-cheating
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user during attempt"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string for the attempt"
    )
    
    class Meta:
        verbose_name = "Quiz Attempt"
        verbose_name_plural = "Quiz Attempts"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'quiz', 'status']),
            models.Index(fields=['quiz', 'status']),
            models.Index(fields=['user', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.quiz.title} (Attempt)"
    
    @property
    def is_passed(self):
        """Check if the attempt passed based on quiz passing score."""
        if self.score_percentage is None:
            return False
        return self.score_percentage >= self.quiz.passing_score
    
    @property
    def attempt_number(self):
        """Get the attempt number for this user on this quiz."""
        return QuizAttempt.objects.filter(
            user=self.user,
            quiz=self.quiz,
            started_at__lte=self.started_at
        ).count()


class Assignment(BaseModel):
    """
    Model representing an assignment in a course.
    """
    LATE_SUBMISSION_POLICY_CHOICES = [
        ('no_late', 'No Late Submissions'),
        ('penalty', 'Penalty Applied'),
        ('accept', 'Accept Without Penalty'),
        ('grace_period', 'Grace Period'),
    ]
    
    # Course relationship
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="Course this assignment belongs to"
    )
    module = models.ForeignKey(
        'courses.Module',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments',
        help_text="Module this assignment belongs to (optional)"
    )
    
    # Basic Information
    title = models.CharField(
        max_length=255,
        help_text="Title of the assignment"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the assignment"
    )
    instructions = models.TextField(
        blank=True,
        help_text="Detailed instructions for the assignment"
    )
    
    # Due date and scheduling
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Due date for the assignment"
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the assignment becomes available"
    )
    available_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the assignment is no longer available"
    )
    
    # Scoring
    max_points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0)],
        help_text="Maximum points for the assignment"
    )
    
    # Late submission policy
    late_submission_policy = models.CharField(
        max_length=20,
        choices=LATE_SUBMISSION_POLICY_CHOICES,
        default='penalty',
        help_text="Policy for late submissions"
    )
    late_penalty_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Penalty percentage for late submissions"
    )
    grace_period_hours = models.PositiveIntegerField(
        default=0,
        help_text="Grace period in hours (for grace_period policy)"
    )
    
    # File upload settings
    allow_file_upload = models.BooleanField(
        default=True,
        help_text="Whether file uploads are allowed"
    )
    max_file_size_mb = models.PositiveIntegerField(
        default=10,
        help_text="Maximum file size in MB"
    )
    allowed_file_types = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed file extensions (e.g., ['.pdf', '.doc'])"
    )
    
    # Status
    is_published = models.BooleanField(
        default=False,
        help_text="Whether the assignment is published"
    )
    
    class Meta:
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'is_published']),
            models.Index(fields=['due_date', 'is_published']),
            models.Index(fields=['course', 'module', 'is_published']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Submission(BaseModel):
    """
    Model representing a user's submission for an assignment.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned for Revision'),
        ('late', 'Late Submission'),
    ]
    
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        help_text="Assignment this submission is for"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
        help_text="User who made the submission"
    )
    
    # Content
    submitted_text = models.TextField(
        blank=True,
        help_text="Text content of the submission"
    )
    file_urls = models.JSONField(
        default=list,
        blank=True,
        help_text="List of uploaded file URLs"
    )
    
    # Timing
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the submission was made"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True,
        help_text="Current status of the submission"
    )
    
    # Version tracking
    version = models.PositiveIntegerField(
        default=1,
        help_text="Submission version number"
    )
    previous_submission = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_versions',
        help_text="Previous submission version (if resubmitted)"
    )
    
    # IP tracking
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user during submission"
    )
    
    class Meta:
        verbose_name = "Submission"
        verbose_name_plural = "Submissions"
        ordering = ['-submitted_at', '-version']
        indexes = [
            models.Index(fields=['assignment', 'user', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['assignment', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.assignment.title} (v{self.version})"


class Grade(BaseModel):
    """
    Model representing a grade for a gradable item (quiz or assignment).
    """
    GRADABLE_TYPE_CHOICES = [
        ('quiz', 'Quiz'),
        ('assignment', 'Assignment'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='grades',
        help_text="User who received the grade"
    )
    
    # Polymorphic reference to gradable item
    gradable_type = models.CharField(
        max_length=20,
        choices=GRADABLE_TYPE_CHOICES,
        help_text="Type of gradable item"
    )
    gradable_id = models.UUIDField(
        help_text="ID of the quiz or assignment"
    )
    
    # Scoring
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Score achieved"
    )
    max_points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Maximum possible points"
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Score as percentage"
    )
    
    # Feedback
    feedback = models.TextField(
        blank=True,
        help_text="Instructor feedback"
    )
    
    # Grading metadata
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grades_given',
        help_text="User who assigned the grade"
    )
    graded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the grade was assigned"
    )
    
    # Auto-grading flag
    is_auto_graded = models.BooleanField(
        default=False,
        help_text="Whether this grade was assigned automatically"
    )
    
    # Related attempt/submission
    attempt_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID of the quiz attempt or submission that was graded"
    )
    
    class Meta:
        verbose_name = "Grade"
        verbose_name_plural = "Grades"
        ordering = ['-graded_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'gradable_type', 'gradable_id']),
            models.Index(fields=['gradable_type', 'gradable_id']),
            models.Index(fields=['user', 'graded_at']),
        ]
        unique_together = [
            ['user', 'gradable_type', 'gradable_id', 'attempt_id'],
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.gradable_type} ({self.percentage}%)"
    
    @property
    def is_passed(self):
        """Check if the grade is a passing grade (>= 60%)."""
        return self.percentage >= 60.00
    
    def save(self, *args, **kwargs):
        """Calculate percentage before saving."""
        if self.score is not None and self.max_points and self.max_points > 0:
            self.percentage = (self.score / self.max_points) * 100
        super().save(*args, **kwargs)
