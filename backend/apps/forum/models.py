"""
Forum Models for Enterprise LMS
Provides DiscussionForum and DiscussionPost models with threaded discussions, voting, and moderation.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class DiscussionForum(BaseModel):
    """
    Model representing a discussion forum for a course.
    Each course can have one forum with multiple discussion threads.
    """
    course = models.OneToOneField(
        Course,
        on_delete=models.CASCADE,
        related_name='forum',
        help_text=_("Course this forum belongs to")
    )
    title = models.CharField(
        max_length=255,
        default=_("Discussion Forum"),
        help_text=_("Title of the forum")
    )
    description = models.TextField(
        blank=True,
        help_text=_("Description of the forum")
    )
    is_moderated = models.BooleanField(
        default=True,
        help_text=_("Whether posts require moderation before being visible")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether the forum is active")
    )
    allow_anonymous_posts = models.BooleanField(
        default=False,
        help_text=_("Whether anonymous posts are allowed")
    )
    require_approval_for_new_users = models.BooleanField(
        default=True,
        help_text=_("Whether new users' posts require approval")
    )
    post_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Cached count of posts in this forum")
    )
    topic_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Cached count of topics (top-level posts) in this forum")
    )
    last_post_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("When the last post was made")
    )
    last_post_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_forum_posts',
        help_text=_("User who made the last post")
    )
    
    class Meta:
        verbose_name = _("Discussion Forum")
        verbose_name_plural = _("Discussion Forums")
        ordering = ['-last_post_at', '-created_at']
        indexes = [
            models.Index(fields=['is_active', '-last_post_at']),
            models.Index(fields=['is_moderated', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def update_stats(self):
        """Update cached statistics for this forum."""
        from django.db.models import Max
        
        self.topic_count = self.posts.filter(parent__isnull=True).count()
        self.post_count = self.posts.count()
        
        last_post = self.posts.order_by('-created_at').first()
        if last_post:
            self.last_post_at = last_post.created_at
            self.last_post_by = last_post.author
        
        self.save(update_fields=['topic_count', 'post_count', 'last_post_at', 'last_post_by'])


class DiscussionPost(BaseModel):
    """
    Model representing a post in a discussion forum.
    Supports threaded replies with self-referential parent relationship.
    Includes voting, pinning, and locking functionality.
    """
    # Post Type Choices
    TYPE_TOPIC = 'topic'
    TYPE_REPLY = 'reply'
    
    TYPE_CHOICES = [
        (TYPE_TOPIC, _('Topic')),
        (TYPE_REPLY, _('Reply')),
    ]
    
    # Moderation Status Choices
    MODERATION_PENDING = 'pending'
    MODERATION_APPROVED = 'approved'
    MODERATION_REJECTED = 'rejected'
    MODERATION_SPAM = 'spam'
    
    MODERATION_CHOICES = [
        (MODERATION_PENDING, _('Pending')),
        (MODERATION_APPROVED, _('Approved')),
        (MODERATION_REJECTED, _('Rejected')),
        (MODERATION_SPAM, _('Spam')),
    ]
    
    forum = models.ForeignKey(
        DiscussionForum,
        on_delete=models.CASCADE,
        related_name='posts',
        help_text=_("Forum this post belongs to")
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='forum_posts',
        help_text=_("User who created the post")
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text=_("Parent post for threaded replies")
    )
    post_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_TOPIC,
        db_index=True,
        help_text=_("Type of post")
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Title of the post (for topics)")
    )
    content = models.TextField(
        help_text=_("Post content")
    )
    content_html = models.TextField(
        blank=True,
        help_text=_("Rendered HTML content")
    )
    
    # Moderation and Status
    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_CHOICES,
        default=MODERATION_APPROVED,
        db_index=True,
        help_text=_("Moderation status of the post")
    )
    is_pinned = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether the post is pinned to the top")
    )
    is_locked = models.BooleanField(
        default=False,
        help_text=_("Whether the post is locked (no new replies)")
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text=_("Whether the post is hidden from normal view")
    )
    
    # Voting
    upvotes = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of upvotes")
    )
    downvotes = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of downvotes")
    )
    vote_score = models.IntegerField(
        default=0,
        db_index=True,
        help_text=_("Calculated vote score (upvotes - downvotes)")
    )
    
    # Engagement Metrics
    view_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of times the post has been viewed")
    )
    reply_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Cached count of replies")
    )
    
    # Thread Tracking (for replies)
    root_post = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='thread_posts',
        help_text=_("Root post of this thread (for replies)")
    )
    depth = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Nesting depth in the thread")
    )
    
    # Edit Tracking
    is_edited = models.BooleanField(
        default=False,
        help_text=_("Whether the post has been edited")
    )
    edited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the post was last edited")
    )
    edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edited_posts',
        help_text=_("User who last edited the post")
    )
    edit_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Reason for the edit")
    )
    
    # Notifications
    notify_replies = models.BooleanField(
        default=True,
        help_text=_("Whether to notify author of replies")
    )
    
    class Meta:
        verbose_name = _("Discussion Post")
        verbose_name_plural = _("Discussion Posts")
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['forum', 'post_type', '-created_at']),
            models.Index(fields=['forum', 'moderation_status', '-created_at']),
            models.Index(fields=['parent', 'created_at']),
            models.Index(fields=['root_post', 'depth', 'created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['vote_score', '-created_at']),
            models.Index(fields=['is_pinned', '-created_at']),
        ]
    
    def __str__(self):
        if self.title:
            return f"{self.title} by {self.author.email}"
        return f"Reply by {self.author.email}"
    
    def save(self, *args, **kwargs):
        """Override save to set post_type and root_post based on parent."""
        if self.parent:
            self.post_type = self.TYPE_REPLY
            self.root_post = self.parent.root_post or self.parent
            self.depth = self.parent.depth + 1
            if not self.title:
                self.title = f"Re: {self.parent.title[:50]}"
        else:
            self.post_type = self.TYPE_TOPIC
            self.root_post = None
            self.depth = 0
        
        # Calculate vote score
        self.vote_score = self.upvotes - self.downvotes
        
        super().save(*args, **kwargs)
    
    def is_topic(self):
        """Check if this is a top-level topic post."""
        return self.post_type == self.TYPE_TOPIC
    
    def is_reply(self):
        """Check if this is a reply post."""
        return self.post_type == self.TYPE_REPLY
    
    def get_thread_root(self):
        """Get the root post of this thread."""
        return self.root_post or self
    
    def get_replies(self, include_nested=True):
        """Get replies to this post."""
        if include_nested:
            return self.replies.all()
        return self.replies.filter(depth=self.depth + 1)
    
    def increment_view_count(self):
        """Increment the view count."""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def update_reply_count(self):
        """Update the cached reply count."""
        self.reply_count = self.replies.count()
        self.save(update_fields=['reply_count'])
    
    def mark_as_edited(self, edited_by=None, reason=''):
        """Mark the post as edited."""
        from django.utils import timezone
        self.is_edited = True
        self.edited_at = timezone.now()
        self.edited_by = edited_by
        self.edit_reason = reason
        self.save(update_fields=['is_edited', 'edited_at', 'edited_by', 'edit_reason'])
    
    def pin(self):
        """Pin this post to the top."""
        self.is_pinned = True
        self.save(update_fields=['is_pinned'])
    
    def unpin(self):
        """Unpin this post."""
        self.is_pinned = False
        self.save(update_fields=['is_pinned'])
    
    def lock(self):
        """Lock this post to prevent new replies."""
        self.is_locked = True
        self.save(update_fields=['is_locked'])
    
    def unlock(self):
        """Unlock this post to allow new replies."""
        self.is_locked = False
        self.save(update_fields=['is_locked'])
    
    def approve(self):
        """Approve this post (for moderated forums)."""
        self.moderation_status = self.MODERATION_APPROVED
        self.save(update_fields=['moderation_status'])
    
    def reject(self):
        """Reject this post (for moderated forums)."""
        self.moderation_status = self.MODERATION_REJECTED
        self.save(update_fields=['moderation_status'])
    
    def mark_as_spam(self):
        """Mark this post as spam."""
        self.moderation_status = self.MODERATION_SPAM
        self.is_hidden = True
        self.save(update_fields=['moderation_status', 'is_hidden'])


class PostVote(BaseModel):
    """
    Model representing a vote on a post.
    Tracks upvotes and downvotes with user association.
    """
    VOTE_UP = 1
    VOTE_DOWN = -1
    
    VOTE_CHOICES = [
        (VOTE_UP, _('Upvote')),
        (VOTE_DOWN, _('Downvote')),
    ]
    
    post = models.ForeignKey(
        DiscussionPost,
        on_delete=models.CASCADE,
        related_name='votes',
        help_text=_("Post being voted on")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='post_votes',
        help_text=_("User who cast the vote")
    )
    vote_type = models.SmallIntegerField(
        choices=VOTE_CHOICES,
        help_text=_("Type of vote")
    )
    
    class Meta:
        verbose_name = _("Post Vote")
        verbose_name_plural = _("Post Votes")
        unique_together = ['post', 'user']
        ordering = ['-created_at']
    
    def __str__(self):
        vote_str = "upvote" if self.vote_type == self.VOTE_UP else "downvote"
        return f"{vote_str} by {self.user.email} on {self.post.id}"
    
    def save(self, *args, **kwargs):
        """Override save to update post vote counts."""
        is_new = self.pk is None
        old_vote = None
        
        if not is_new:
            old_vote = PostVote.objects.get(pk=self.pk).vote_type
        
        super().save(*args, **kwargs)
        
        # Update post vote counts
        post = self.post
        if is_new:
            if self.vote_type == self.VOTE_UP:
                post.upvotes += 1
            else:
                post.downvotes += 1
        elif old_vote != self.vote_type:
            # Vote changed
            if old_vote == self.VOTE_UP:
                post.upvotes -= 1
                post.downvotes += 1
            else:
                post.downvotes -= 1
                post.upvotes += 1
        
        post.vote_score = post.upvotes - post.downvotes
        post.save(update_fields=['upvotes', 'downvotes', 'vote_score'])
    
    def delete(self, *args, **kwargs):
        """Override delete to update post vote counts."""
        post = self.post
        if self.vote_type == self.VOTE_UP:
            post.upvotes = max(0, post.upvotes - 1)
        else:
            post.downvotes = max(0, post.downvotes - 1)
        post.vote_score = post.upvotes - post.downvotes
        post.save(update_fields=['upvotes', 'downvotes', 'vote_score'])
        super().delete(*args, **kwargs)


class ModerationAction(BaseModel):
    """
    Model representing a moderation action on a forum post.
    Tracks who moderated what and why.
    """
    ACTION_HIDE = 'hide'
    ACTION_UNHIDE = 'unhide'
    ACTION_LOCK = 'lock'
    ACTION_UNLOCK = 'unlock'
    ACTION_PIN = 'pin'
    ACTION_UNPIN = 'unpin'
    ACTION_APPROVE = 'approve'
    ACTION_REJECT = 'reject'
    ACTION_MARK_SPAM = 'mark_spam'
    ACTION_EDIT = 'edit'
    ACTION_DELETE = 'delete'
    ACTION_RESTORE = 'restore'
    ACTION_WARNING = 'warning'
    ACTION_BAN_USER = 'ban_user'
    
    ACTION_CHOICES = [
        (ACTION_HIDE, _('Hide Post')),
        (ACTION_UNHIDE, _('Unhide Post')),
        (ACTION_LOCK, _('Lock Post')),
        (ACTION_UNLOCK, _('Unlock Post')),
        (ACTION_PIN, _('Pin Post')),
        (ACTION_UNPIN, _('Unpin Post')),
        (ACTION_APPROVE, _('Approve Post')),
        (ACTION_REJECT, _('Reject Post')),
        (ACTION_MARK_SPAM, _('Mark as Spam')),
        (ACTION_EDIT, _('Edit Post')),
        (ACTION_DELETE, _('Delete Post')),
        (ACTION_RESTORE, _('Restore Post')),
        (ACTION_WARNING, _('Issue Warning')),
        (ACTION_BAN_USER, _('Ban User')),
    ]
    
    post = models.ForeignKey(
        DiscussionPost,
        on_delete=models.CASCADE,
        related_name='moderation_actions',
        help_text=_("Post that was moderated")
    )
    moderator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='moderation_actions_taken',
        help_text=_("User who performed the moderation")
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text=_("Type of moderation action")
    )
    reason = models.TextField(
        help_text=_("Reason for the moderation action")
    )
    previous_value = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Previous values before the action")
    )
    new_value = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("New values after the action")
    )
    
    class Meta:
        verbose_name = _("Moderation Action")
        verbose_name_plural = _("Moderation Actions")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['moderator', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} on {self.post.id} by {self.moderator.email}"
