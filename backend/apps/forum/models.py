"""
Forum Models for Enterprise LMS
Provides DiscussionThread and Post models.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class DiscussionThread(BaseModel):
    """
    Model representing a discussion thread in a course forum.
    """
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='discussion_threads',
        help_text="Course this thread belongs to"
    )
    title = models.CharField(
        max_length=255,
        help_text="Title of the discussion thread"
    )
    content = models.TextField(
        help_text="Initial post content"
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='threads_created',
        help_text="User who created the thread"
    )
    is_pinned = models.BooleanField(
        default=False,
        help_text="Whether the thread is pinned to the top"
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Whether the thread is locked (no new replies)"
    )
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times the thread has been viewed"
    )
    
    class Meta:
        verbose_name = "Discussion Thread"
        verbose_name_plural = "Discussion Threads"
        ordering = ['-is_pinned', '-created_at']
    
    def __str__(self):
        return self.title


class Post(BaseModel):
    """
    Model representing a post/reply in a discussion thread.
    """
    thread = models.ForeignKey(
        DiscussionThread,
        on_delete=models.CASCADE,
        related_name='posts',
        help_text="Thread this post belongs to"
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text="Parent post (for threaded replies)"
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_posts',
        help_text="User who wrote the post"
    )
    content = models.TextField(
        help_text="Post content"
    )
    is_edited = models.BooleanField(
        default=False,
        help_text="Whether the post has been edited"
    )
    edited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the post was last edited"
    )
    
    class Meta:
        verbose_name = "Post"
        verbose_name_plural = "Posts"
        ordering = ['created_at']
    
    def __str__(self):
        return f"Post by {self.author.email} in {self.thread.title}"
