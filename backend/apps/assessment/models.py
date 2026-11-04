"""
Assessment Models for Enterprise LMS
Provides data models for quizzes, assignments, questions, and grading.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


class Quiz(BaseModel):
    """
    Model representing a quiz assessment.
    """
    title = models.CharField(
        max_length=255,
        help_text="Title of the quiz"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the quiz"
    )
    time_limit_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time limit in minutes (null for no limit)"
    )
    passing_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=70.00,
        help_text="Minimum score required to pass (percentage)"
    )
    max_attempts = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of attempts allowed"
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Whether the quiz is published and available"
    )
    
    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class Question(BaseModel):
    """
    Model representing a question in a quiz.
    """
    QUESTION_TYPES = [
        ('mcq', 'Multiple Choice'),
        ('multi_select', 'Multiple Select'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
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
    points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.00,
        help_text="Points awarded for correct answer"
    )
    sequence_order = models.PositiveIntegerField(
        default=0,
        help_text="Order of this question in the quiz"
    )
    
    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ['sequence_order', 'created_at']
    
    def __str__(self):
        return f"{self.quiz.title} - Question {self.sequence_order}"
