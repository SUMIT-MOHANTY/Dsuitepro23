"""
Forum Serializers for Enterprise LMS
Provides serializers for DiscussionForum, DiscussionPost, PostVote, and ModerationAction models.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import DiscussionForum, DiscussionPost, PostVote, ModerationAction
from apps.courses.models import Course

User = get_user_model()


class AuthorSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for post/forum authors.
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'full_name', 'avatar_url']


class CourseBriefSerializer(serializers.ModelSerializer):
    """
    Brief serializer for course info in forum context.
    """
    class Meta:
        model = Course
        fields = ['id', 'title', 'slug', 'thumbnail_url']


class DiscussionForumSerializer(serializers.ModelSerializer):
    """
    Serializer for DiscussionForum model.
    Used for listing and retrieving forums.
    """
    course = CourseBriefSerializer(read_only=True)
    course_id = serializers.UUIDField(write_only=True)
    last_post_by = AuthorSerializer(read_only=True)
    
    class Meta:
        model = DiscussionForum
        fields = [
            'id', 'course', 'course_id', 'title', 'description',
            'is_moderated', 'is_active', 'allow_anonymous_posts',
            'require_approval_for_new_users', 'post_count', 'topic_count',
            'last_post_at', 'last_post_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'post_count', 'topic_count', 'last_post_at', 'last_post_by', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        course_id = validated_data.pop('course_id')
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise serializers.ValidationError(
                {'course_id': _('Course not found.')}
            )
        
        # Check if forum already exists for this course
        if DiscussionForum.objects.filter(course=course).exists():
            raise serializers.ValidationError(
                {'course_id': _('A forum already exists for this course.')}
            )
        
        return DiscussionForum.objects.create(course=course, **validated_data)
    
    def update(self, instance, validated_data):
        validated_data.pop('course_id', None)  # Prevent course change on update
        return super().update(instance, validated_data)


class DiscussionForumListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for forum lists.
    """
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = DiscussionForum
        fields = [
            'id', 'course_title', 'title', 'is_moderated',
            'is_active', 'post_count', 'topic_count', 'last_post_at'
        ]


class DiscussionPostBriefSerializer(serializers.ModelSerializer):
    """
    Brief serializer for posts in lists.
    """
    author = AuthorSerializer(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = DiscussionPost
        fields = [
            'id', 'title', 'author', 'post_type',
            'is_pinned', 'is_locked', 'vote_score',
            'view_count', 'reply_count', 'created_at'
        ]


class RecursivePostSerializer(serializers.ModelSerializer):
    """
    Recursive serializer for nested replies.
    """
    author = AuthorSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    is_edited = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = DiscussionPost
        fields = [
            'id', 'author', 'title', 'content', 'content_html',
            'post_type', 'depth', 'is_pinned', 'is_locked',
            'is_hidden', 'moderation_status', 'vote_score',
            'upvotes', 'downvotes', 'view_count', 'reply_count',
            'is_edited', 'edited_at', 'edit_reason',
            'notify_replies', 'created_at', 'updated_at', 'replies'
        ]
    
    def get_replies(self, obj):
        """Get nested replies up to a certain depth."""
        # Limit recursion depth to prevent excessive nesting
        current_depth = self.context.get('depth', 0)
        max_depth = self.context.get('max_depth', 3)
        
        if current_depth >= max_depth:
            return []
        
        replies = obj.replies.filter(
            moderation_status=DiscussionPost.MODERATION_APPROVED,
            is_hidden=False
        ).order_by('-vote_score', 'created_at')[:10]
        
        serializer = RecursivePostSerializer(
            replies,
            many=True,
            context={'depth': current_depth + 1, 'max_depth': max_depth}
        )
        return serializer.data


class DiscussionPostSerializer(serializers.ModelSerializer):
    """
    Serializer for DiscussionPost model.
    Used for creating, updating, and retrieving posts.
    """
    author = AuthorSerializer(read_only=True)
    forum_id = serializers.UUIDField(write_only=True)
    parent_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    parent = DiscussionPostBriefSerializer(read_only=True)
    replies = RecursivePostSerializer(many=True, read_only=True)
    user_vote = serializers.SerializerMethodField()
    
    class Meta:
        model = DiscussionPost
        fields = [
            'id', 'forum', 'forum_id', 'author', 'parent', 'parent_id',
            'post_type', 'title', 'content', 'content_html',
            'moderation_status', 'is_pinned', 'is_locked', 'is_hidden',
            'upvotes', 'downvotes', 'vote_score', 'view_count', 'reply_count',
            'depth', 'root_post', 'is_edited', 'edited_at', 'edited_by',
            'edit_reason', 'notify_replies', 'replies', 'user_vote',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'author', 'post_type', 'content_html', 'moderation_status',
            'vote_score', 'view_count', 'reply_count', 'depth', 'root_post',
            'is_edited', 'edited_at', 'edited_by', 'edit_reason',
            'created_at', 'updated_at'
        ]
    
    def get_user_vote(self, obj):
        """Get the current user's vote on this post."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                vote = PostVote.objects.get(post=obj, user=request.user)
                return vote.vote_type
            except PostVote.DoesNotExist:
                return None
        return None
    
    def validate(self, data):
        """Validate post data."""
        # Validate forum exists
        forum_id = data.get('forum_id')
        if forum_id:
            try:
                forum = DiscussionForum.objects.get(id=forum_id)
                if not forum.is_active:
                    raise serializers.ValidationError(
                        {'forum_id': _('This forum is not active.')}
                    )
            except DiscussionForum.DoesNotExist:
                raise serializers.ValidationError(
                    {'forum_id': _('Forum not found.')}
                )
        
        # Validate parent post
        parent_id = data.get('parent_id')
        if parent_id:
            try:
                parent = DiscussionPost.objects.get(id=parent_id)
                if parent.is_locked:
                    raise serializers.ValidationError(
                        {'parent_id': _('This post is locked and cannot receive replies.')}
                    )
                if parent.forum_id != forum_id:
                    raise serializers.ValidationError(
                        {'parent_id': _('Parent post must be in the same forum.')}
                    )
            except DiscussionPost.DoesNotExist:
                raise serializers.ValidationError(
                    {'parent_id': _('Parent post not found.')}
                )
        
        # Validate title for topics
        if not parent_id and not data.get('title'):
            raise serializers.ValidationError(
                {'title': _('Title is required for new topics.')}
            )
        
        return data
    
    def create(self, validated_data):
        forum_id = validated_data.pop('forum_id')
        parent_id = validated_data.pop('parent_id', None)
        
        forum = DiscussionForum.objects.get(id=forum_id)
        
        parent = None
        if parent_id:
            parent = DiscussionPost.objects.get(id=parent_id)
        
        # Set author from request
        request = self.context.get('request')
        if request:
            validated_data['author'] = request.user
        
        post = DiscussionPost.objects.create(
            forum=forum,
            parent=parent,
            **validated_data
        )
        
        return post


class DiscussionPostCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new posts.
    """
    forum_id = serializers.UUIDField(required=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    
    class Meta:
        model = DiscussionPost
        fields = ['forum_id', 'parent_id', 'title', 'content', 'notify_replies']
    
    def validate_forum_id(self, value):
        try:
            forum = DiscussionForum.objects.get(id=value)
            if not forum.is_active:
                raise serializers.ValidationError(_('This forum is not active.'))
            return value
        except DiscussionForum.DoesNotExist:
            raise serializers.ValidationError(_('Forum not found.'))
    
    def validate_parent_id(self, value):
        if value is None:
            return value
        try:
            parent = DiscussionPost.objects.get(id=value)
            if parent.is_locked:
                raise serializers.ValidationError(_('This post is locked and cannot receive replies.'))
            return value
        except DiscussionPost.DoesNotExist:
            raise serializers.ValidationError(_('Parent post not found.'))
    
    def validate(self, data):
        # Title required for top-level posts
        if not data.get('parent_id') and not data.get('title'):
            raise serializers.ValidationError(
                {'title': _('Title is required for new topics.')}
            )
        return data


class DiscussionPostUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating existing posts.
    """
    class Meta:
        model = DiscussionPost
        fields = ['title', 'content', 'notify_replies']
    
    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request:
            instance.mark_as_edited(
                edited_by=request.user,
                reason='User edit'
            )
        return super().update(instance, validated_data)


class PostVoteSerializer(serializers.ModelSerializer):
    """
    Serializer for PostVote model.
    """
    user = AuthorSerializer(read_only=True)
    post_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = PostVote
        fields = ['id', 'post', 'post_id', 'user', 'vote_type', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
    
    def validate_post_id(self, value):
        try:
            post = DiscussionPost.objects.get(id=value)
            if post.is_hidden:
                raise serializers.ValidationError(_('Cannot vote on hidden posts.'))
            return value
        except DiscussionPost.DoesNotExist:
            raise serializers.ValidationError(_('Post not found.'))
    
    def create(self, validated_data):
        post_id = validated_data.pop('post_id')
        post = DiscussionPost.objects.get(id=post_id)
        
        request = self.context.get('request')
        user = request.user if request else None
        
        # Update or create vote
        vote, created = PostVote.objects.update_or_create(
            post=post,
            user=user,
            defaults={'vote_type': validated_data['vote_type']}
        )
        
        return vote


class VoteActionSerializer(serializers.Serializer):
    """
    Serializer for vote actions.
    """
    VOTE_CHOICES = [
        (1, _('Upvote')),
        (-1, _('Downvote')),
    ]
    
    vote_type = serializers.ChoiceField(choices=VOTE_CHOICES, required=True)


class ModerationActionSerializer(serializers.ModelSerializer):
    """
    Serializer for ModerationAction model.
    """
    moderator = AuthorSerializer(read_only=True)
    post_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = ModerationAction
        fields = [
            'id', 'post', 'post_id', 'moderator', 'action',
            'reason', 'previous_value', 'new_value', 'created_at'
        ]
        read_only_fields = ['id', 'moderator', 'previous_value', 'new_value', 'created_at']
    
    def validate_post_id(self, value):
        try:
            DiscussionPost.objects.get(id=value)
            return value
        except DiscussionPost.DoesNotExist:
            raise serializers.ValidationError(_('Post not found.'))
    
    def create(self, validated_data):
        post_id = validated_data.pop('post_id')
        post = DiscussionPost.objects.get(id=post_id)
        
        request = self.context.get('request')
        moderator = request.user if request else None
        
        action = validated_data['action']
        
        # Store previous values before applying action
        previous_value = {}
        new_value = {}
        
        if action == ModerationAction.ACTION_HIDE:
            previous_value['is_hidden'] = post.is_hidden
            post.is_hidden = True
            new_value['is_hidden'] = True
        elif action == ModerationAction.ACTION_UNHIDE:
            previous_value['is_hidden'] = post.is_hidden
            post.is_hidden = False
            new_value['is_hidden'] = False
        elif action == ModerationAction.ACTION_LOCK:
            previous_value['is_locked'] = post.is_locked
            post.lock()
            new_value['is_locked'] = True
        elif action == ModerationAction.ACTION_UNLOCK:
            previous_value['is_locked'] = post.is_locked
            post.unlock()
            new_value['is_locked'] = False
        elif action == ModerationAction.ACTION_PIN:
            previous_value['is_pinned'] = post.is_pinned
            post.pin()
            new_value['is_pinned'] = True
        elif action == ModerationAction.ACTION_UNPIN:
            previous_value['is_pinned'] = post.is_pinned
            post.unpin()
            new_value['is_pinned'] = False
        elif action == ModerationAction.ACTION_APPROVE:
            previous_value['moderation_status'] = post.moderation_status
            post.approve()
            new_value['moderation_status'] = DiscussionPost.MODERATION_APPROVED
        elif action == ModerationAction.ACTION_REJECT:
            previous_value['moderation_status'] = post.moderation_status
            post.reject()
            new_value['moderation_status'] = DiscussionPost.MODERATION_REJECTED
        elif action == ModerationAction.ACTION_MARK_SPAM:
            previous_value['moderation_status'] = post.moderation_status
            previous_value['is_hidden'] = post.is_hidden
            post.mark_as_spam()
            new_value['moderation_status'] = DiscussionPost.MODERATION_SPAM
            new_value['is_hidden'] = True
        
        post.save()
        
        return ModerationAction.objects.create(
            post=post,
            moderator=moderator,
            previous_value=previous_value,
            new_value=new_value,
            **validated_data
        )


class ModerationActionListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for moderation action lists.
    """
    moderator_name = serializers.CharField(source='moderator.get_full_name', read_only=True)
    
    class Meta:
        model = ModerationAction
        fields = ['id', 'action', 'moderator_name', 'reason', 'created_at']


class ForumStatsSerializer(serializers.Serializer):
    """
    Serializer for forum statistics.
    """
    total_posts = serializers.IntegerField()
    total_topics = serializers.IntegerField()
    total_replies = serializers.IntegerField()
    active_users_today = serializers.IntegerField()
    posts_today = serializers.IntegerField()
    most_active_topic = DiscussionPostBriefSerializer(required=False)


class PostSearchSerializer(serializers.Serializer):
    """
    Serializer for post search queries.
    """
    query = serializers.CharField(required=True, min_length=2, max_length=200)
    forum_id = serializers.UUIDField(required=False)
    author_id = serializers.UUIDField(required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)


class PostFilterSerializer(serializers.Serializer):
    """
    Serializer for filtering posts.
    """
    post_type = serializers.ChoiceField(
        choices=DiscussionPost.TYPE_CHOICES,
        required=False
    )
    moderation_status = serializers.ChoiceField(
        choices=DiscussionPost.MODERATION_CHOICES,
        required=False
    )
    is_pinned = serializers.BooleanField(required=False)
    is_locked = serializers.BooleanField(required=False)
    author_id = serializers.UUIDField(required=False)
    order_by = serializers.ChoiceField(
        choices=['created_at', '-created_at', 'vote_score', '-vote_score'],
        default='-created_at'
    )
