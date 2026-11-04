"""
Forum Views for Enterprise LMS
Provides ForumViewSet and PostViewSet for managing discussion forums and posts.
"""

import logging
from typing import Optional

from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from .models import DiscussionForum, DiscussionPost, PostVote, ModerationAction
from .serializers import (
    DiscussionForumSerializer,
    DiscussionForumListSerializer,
    DiscussionPostSerializer,
    DiscussionPostCreateSerializer,
    DiscussionPostUpdateSerializer,
    DiscussionPostBriefSerializer,
    RecursivePostSerializer,
    PostVoteSerializer,
    VoteActionSerializer,
    ModerationActionSerializer,
    ModerationActionListSerializer,
    ForumStatsSerializer,
    PostSearchSerializer,
    PostFilterSerializer
)
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


class ForumPagination(LimitOffsetPagination):
    """Custom pagination for forums."""
    default_limit = 20
    max_limit = 100


class PostPagination(LimitOffsetPagination):
    """Custom pagination for posts."""
    default_limit = 20
    max_limit = 100


class IsForumModerator(permissions.BasePermission):
    """
    Permission to check if user is a forum moderator.
    Allows instructors and admins to moderate forums.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.is_instructor() or request.user.is_admin()


class IsPostAuthorOrModerator(permissions.BasePermission):
    """
    Permission to check if user is post author or moderator.
    """
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        # Author can edit their own posts
        if obj.author == request.user:
            return True
        # Moderators can edit any post
        return request.user.is_instructor() or request.user.is_admin()


class ForumFilter(filters.FilterSet):
    """Filter set for forums."""
    
    class Meta:
        model = DiscussionForum
        fields = {
            'is_active': ['exact'],
            'is_moderated': ['exact'],
            'course': ['exact'],
        }
    
    search = filters.CharFilter(method='filter_search')
    
    def filter_search(self, queryset, name, value):
        """Search in title and description."""
        if value:
            return queryset.filter(
                Q(title__icontains=value) | Q(description__icontains=value)
            )
        return queryset


class PostFilter(filters.FilterSet):
    """Filter set for posts."""
    
    class Meta:
        model = DiscussionPost
        fields = {
            'post_type': ['exact'],
            'moderation_status': ['exact'],
            'is_pinned': ['exact'],
            'is_locked': ['exact'],
            'is_hidden': ['exact'],
            'author': ['exact'],
            'forum': ['exact'],
            'created_at': ['gte', 'lte'],
        }
    
    search = filters.CharFilter(method='filter_search')
    
    def filter_search(self, queryset, name, value):
        """Search in title and content."""
        if value:
            return queryset.filter(
                Q(title__icontains=value) | Q(content__icontains=value)
            )
        return queryset


class ForumViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing discussion forums.
    
    Provides endpoints for:
    - Listing forums
    - Creating forums (instructors/admins)
    - Updating forum settings (moderators)
    - Getting forum statistics
    """
    
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ForumPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ForumFilter
    
    def get_queryset(self):
        """Return active forums."""
        queryset = DiscussionForum.objects.filter(is_active=True)
        
        # Prefetch related data for performance
        queryset = queryset.select_related('course', 'last_post_by')
        
        # Annotate with post counts
        queryset = queryset.annotate(
            actual_post_count=Count('posts', distinct=True),
            actual_topic_count=Count('posts', filter=Q(posts__post_type=DiscussionPost.TYPE_TOPIC), distinct=True)
        )
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return DiscussionForumListSerializer
        return DiscussionForumSerializer
    
    def get_permissions(self):
        """Return appropriate permissions based on action."""
        if self.action in ['create', 'destroy']:
            return [permissions.IsAuthenticated(), IsForumModerator()]
        return [permissions.IsAuthenticated()]
    
    def list(self, request, *args, **kwargs):
        """
        List discussion forums.
        
        Query Parameters:
        - is_active: Filter by active status
        - is_moderated: Filter by moderation status
        - course: Filter by course ID
        - search: Search in title and description
        """
        return super().list(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve a specific forum with full details.
        """
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        """
        Get statistics for a forum.
        
        Returns:
        {
            "total_posts": 100,
            "total_topics": 25,
            "total_replies": 75,
            "active_users_today": 10,
            "posts_today": 5
        }
        """
        forum = self.get_object()
        
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        total_posts = forum.posts.count()
        total_topics = forum.posts.filter(post_type=DiscussionPost.TYPE_TOPIC).count()
        total_replies = total_posts - total_topics
        
        active_users_today = forum.posts.filter(
            created_at__gte=today
        ).values('author').distinct().count()
        
        posts_today = forum.posts.filter(created_at__gte=today).count()
        
        # Get most active topic
        most_active = forum.posts.filter(
            post_type=DiscussionPost.TYPE_TOPIC
        ).annotate(
            reply_count=Count('replies')
        ).order_by('-reply_count').first()
        
        data = {
            'total_posts': total_posts,
            'total_topics': total_topics,
            'total_replies': total_replies,
            'active_users_today': active_users_today,
            'posts_today': posts_today,
            'most_active_topic': DiscussionPostBriefSerializer(most_active).data if most_active else None
        }
        
        serializer = ForumStatsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='posts')
    def posts(self, request, pk=None):
        """
        Get posts for a forum.
        
        Query Parameters:
        - post_type: Filter by type (topic/reply)
        - is_pinned: Filter by pinned status
        - order_by: Sort order (created_at, -created_at, vote_score, -vote_score)
        """
        forum = self.get_object()
        
        # Get posts for this forum
        queryset = DiscussionPost.objects.filter(forum=forum)
        
        # Filter out hidden posts for non-moderators
        if not (request.user.is_instructor() or request.user.is_admin()):
            queryset = queryset.filter(
                Q(is_hidden=False) | Q(author=request.user)
            )
        
        # Apply filters
        post_type = request.query_params.get('post_type')
        if post_type:
            queryset = queryset.filter(post_type=post_type)
        
        is_pinned = request.query_params.get('is_pinned')
        if is_pinned is not None:
            queryset = queryset.filter(is_pinned=is_pinned.lower() == 'true')
        
        # Apply ordering
        order_by = request.query_params.get('order_by', '-created_at')
        if order_by in ['created_at', '-created_at', 'vote_score', '-vote_score']:
            queryset = queryset.order_by(order_by)
        else:
            queryset = queryset.order_by('-is_pinned', '-created_at')
        
        # Prefetch related data
        queryset = queryset.select_related('author').prefetch_related('replies')
        
        # Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DiscussionPostBriefSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = DiscussionPostBriefSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='toggle-moderation')
    def toggle_moderation(self, request, pk=None):
        """
        Toggle moderation status for a forum.
        
        Request Body:
        {
            "is_moderated": true
        }
        
        Returns:
        {
            "is_moderated": true,
            "message": "Forum moderation enabled"
        }
        """
        forum = self.get_object()
        
        is_moderated = request.data.get('is_moderated')
        if is_moderated is None:
            return Response(
                {'error': 'is_moderated is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        forum.is_moderated = is_moderated
        forum.save(update_fields=['is_moderated', 'updated_at'])
        
        return Response({
            'is_moderated': forum.is_moderated,
            'message': f"Forum moderation {'enabled' if is_moderated else 'disabled'}"
        })


class PostViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing discussion posts.
    
    Provides endpoints for:
    - Creating posts and replies
    - Updating/deleting posts (author or moderator)
    - Voting on posts
    - Pinning/locking posts (moderators)
    """
    
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PostPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = PostFilter
    
    def get_queryset(self):
        """Return posts with related data."""
        queryset = DiscussionPost.objects.all()
        
        # Filter out hidden posts for non-moderators
        if not (self.request.user.is_instructor() or self.request.user.is_admin()):
            queryset = queryset.filter(
                Q(is_hidden=False) | Q(author=self.request.user)
            )
        
        # Prefetch related data
        queryset = queryset.select_related('author', 'forum', 'parent', 'edited_by')
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return DiscussionPostCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return DiscussionPostUpdateSerializer
        return DiscussionPostSerializer
    
    def get_permissions(self):
        """Return appropriate permissions based on action."""
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsPostAuthorOrModerator()]
        return [permissions.IsAuthenticated()]
    
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve a specific post with full details including replies.
        Automatically increments view count.
        """
        post = self.get_object()
        
        # Increment view count
        post.increment_view_count()
        
        serializer = self.get_serializer(post)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """
        Create a new post or reply.
        
        Request Body:
        {
            "forum_id": "uuid",
            "parent_id": "uuid",  // Optional, for replies
            "title": "Post Title",
            "content": "Post content...",
            "notify_replies": true
        }
        
        Returns:
        The created post with full details.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set author from request
        post = serializer.save()
        
        # Update forum stats
        post.forum.update_stats()
        
        # Send notification to parent post author if this is a reply
        if post.parent and post.parent.notify_replies and post.parent.author != request.user:
            notification_service = NotificationService()
            notification_service.send_notification(
                user=post.parent.author,
                title=f"New reply to: {post.parent.title}",
                message=f"{request.user.get_full_name()} replied to your post in {post.forum.title}",
                category='forum',
                action_url=f"/forums/{post.forum.id}/posts/{post.id}"
            )
        
        # Return full post details
        response_serializer = DiscussionPostSerializer(post, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """
        Update an existing post.
        Only the author or moderators can update.
        """
        partial = kwargs.pop('partial', False)
        post = self.get_object()
        
        serializer = self.get_serializer(post, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        post = serializer.save()
        
        response_serializer = DiscussionPostSerializer(post, context={'request': request})
        return Response(response_serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        """
        Soft delete a post.
        Only the author or moderators can delete.
        """
        post = self.get_object()
        
        # Soft delete
        post.soft_delete(deleted_by=request.user)
        
        # Update forum stats
        post.forum.update_stats()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], url_path='reply')
    def reply(self, request, pk=None):
        """
        Create a reply to a post.
        
        Request Body:
        {
            "content": "Reply content...",
            "notify_replies": true
        }
        
        Returns:
        The created reply with full details.
        """
        parent_post = self.get_object()
        
        # Check if post is locked
        if parent_post.is_locked:
            return Response(
                {'error': 'This post is locked and cannot receive replies'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create reply data
        reply_data = {
            'forum_id': str(parent_post.forum.id),
            'parent_id': str(parent_post.id),
            'content': request.data.get('content'),
            'notify_replies': request.data.get('notify_replies', True)
        }
        
        # Auto-generate title from parent
        if parent_post.title:
            reply_data['title'] = f"Re: {parent_post.title[:50]}"
        
        serializer = DiscussionPostCreateSerializer(data=reply_data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        reply = serializer.save()
        
        # Update parent reply count
        parent_post.update_reply_count()
        
        # Update forum stats
        reply.forum.update_stats()
        
        # Send notification to parent post author
        if parent_post.notify_replies and parent_post.author != request.user:
            notification_service = NotificationService()
            notification_service.send_notification(
                user=parent_post.author,
                title=f"New reply to: {parent_post.title}",
                message=f"{request.user.get_full_name()} replied to your post",
                category='forum',
                action_url=f"/forums/{reply.forum.id}/posts/{reply.id}"
            )
        
        response_serializer = DiscussionPostSerializer(reply, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path='vote')
    def vote(self, request, pk=None):
        """
        Vote on a post (upvote or downvote).
        
        Request Body:
        {
            "vote_type": 1  // 1 for upvote, -1 for downvote
        }
        
        Returns:
        {
            "vote_type": 1,
            "upvotes": 10,
            "downvotes": 2,
            "vote_score": 8,
            "message": "Vote recorded"
        }
        """
        post = self.get_object()
        
        # Validate vote type
        serializer = VoteActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        vote_type = serializer.validated_data['vote_type']
        
        # Check if user already voted
        existing_vote = PostVote.objects.filter(
            post=post,
            user=request.user
        ).first()
        
        if existing_vote:
            if existing_vote.vote_type == vote_type:
                # Remove vote if same type (toggle off)
                existing_vote.delete()
                message = "Vote removed"
            else:
                # Change vote type
                existing_vote.vote_type = vote_type
                existing_vote.save()
                message = "Vote updated"
        else:
            # Create new vote
            PostVote.objects.create(
                post=post,
                user=request.user,
                vote_type=vote_type
            )
            message = "Vote recorded"
        
        # Refresh post to get updated counts
        post.refresh_from_db()
        
        return Response({
            'vote_type': vote_type if not existing_vote or existing_vote.vote_type == vote_type else None,
            'upvotes': post.upvotes,
            'downvotes': post.downvotes,
            'vote_score': post.vote_score,
            'message': message
        })
    
    @action(detail=True, methods=['post'], url_path='pin')
    def pin(self, request, pk=None):
        """
        Pin a post to the top (moderators only).
        
        Returns:
        {
            "is_pinned": true,
            "message": "Post pinned"
        }
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can pin posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        post.pin()
        
        # Log moderation action
        ModerationAction.objects.create(
            post=post,
            moderator=request.user,
            action=ModerationAction.ACTION_PIN,
            reason='Post pinned by moderator'
        )
        
        return Response({
            'is_pinned': True,
            'message': 'Post pinned'
        })
    
    @action(detail=True, methods=['post'], url_path='unpin')
    def unpin(self, request, pk=None):
        """
        Unpin a post (moderators only).
        
        Returns:
        {
            "is_pinned": false,
            "message": "Post unpinned"
        }
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can unpin posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        post.unpin()
        
        # Log moderation action
        ModerationAction.objects.create(
            post=post,
            moderator=request.user,
            action=ModerationAction.ACTION_UNPIN,
            reason='Post unpinned by moderator'
        )
        
        return Response({
            'is_pinned': False,
            'message': 'Post unpinned'
        })
    
    @action(detail=True, methods=['post'], url_path='lock')
    def lock(self, request, pk=None):
        """
        Lock a post to prevent new replies (moderators only).
        
        Returns:
        {
            "is_locked": true,
            "message": "Post locked"
        }
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can lock posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        post.lock()
        
        # Log moderation action
        ModerationAction.objects.create(
            post=post,
            moderator=request.user,
            action=ModerationAction.ACTION_LOCK,
            reason='Post locked by moderator'
        )
        
        return Response({
            'is_locked': True,
            'message': 'Post locked'
        })
    
    @action(detail=True, methods=['post'], url_path='unlock')
    def unlock(self, request, pk=None):
        """
        Unlock a post to allow new replies (moderators only).
        
        Returns:
        {
            "is_locked": false,
            "message": "Post unlocked"
        }
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can unlock posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        post.unlock()
        
        # Log moderation action
        ModerationAction.objects.create(
            post=post,
            moderator=request.user,
            action=ModerationAction.ACTION_UNLOCK,
            reason='Post unlocked by moderator'
        )
        
        return Response({
            'is_locked': False,
            'message': 'Post unlocked'
        })
    
    @action(detail=True, methods=['post'], url_path='hide')
    def hide(self, request, pk=None):
        """
        Hide a post (moderators only).
        
        Request Body:
        {
            "reason": "Off-topic content"
        }
        
        Returns:
        {
            "is_hidden": true,
            "message": "Post hidden"
        }
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can hide posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        reason = request.data.get('reason', 'Hidden by moderator')
        
        post.is_hidden = True
        post.save(update_fields=['is_hidden', 'updated_at'])
        
        # Log moderation action
        ModerationAction.objects.create(
            post=post,
            moderator=request.user,
            action=ModerationAction.ACTION_HIDE,
            reason=reason
        )
        
        return Response({
            'is_hidden': True,
            'message': 'Post hidden'
        })
    
    @action(detail=True, methods=['post'], url_path='unhide')
    def unhide(self, request, pk=None):
        """
        Unhide a post (moderators only).
        
        Returns:
        {
            "is_hidden": false,
            "message": "Post unhidden"
        }
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can unhide posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        
        post.is_hidden = False
        post.save(update_fields=['is_hidden', 'updated_at'])
        
        # Log moderation action
        ModerationAction.objects.create(
            post=post,
            moderator=request.user,
            action=ModerationAction.ACTION_UNHIDE,
            reason='Post unhidden by moderator'
        )
        
        return Response({
            'is_hidden': False,
            'message': 'Post unhidden'
        })
    
    @action(detail=True, methods=['get'], url_path='replies')
    def get_replies(self, request, pk=None):
        """
        Get replies for a post with nested threading.
        
        Query Parameters:
        - max_depth: Maximum nesting depth (default: 3)
        
        Returns:
        List of replies with nested structure.
        """
        post = self.get_object()
        
        max_depth = int(request.query_params.get('max_depth', 3))
        max_depth = min(max_depth, 5)  # Cap at 5 levels
        
        # Get direct replies
        replies = post.replies.filter(
            moderation_status=DiscussionPost.MODERATION_APPROVED,
            is_hidden=False
        ).order_by('-vote_score', 'created_at')
        
        serializer = RecursivePostSerializer(
            replies,
            many=True,
            context={'request': request, 'depth': 0, 'max_depth': max_depth}
        )
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='moderation-history')
    def moderation_history(self, request, pk=None):
        """
        Get moderation history for a post.
        
        Returns:
        List of moderation actions.
        """
        if not (request.user.is_instructor() or request.user.is_admin()):
            return Response(
                {'error': 'Only moderators can view moderation history'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        post = self.get_object()
        actions = post.moderation_actions.all().order_by('-created_at')
        
        serializer = ModerationActionListSerializer(actions, many=True)
        return Response(serializer.data)


class ModerationActionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing moderation actions.
    Read-only for moderators.
    """
    
    permission_classes = [permissions.IsAuthenticated, IsForumModerator]
    serializer_class = ModerationActionSerializer
    pagination_class = PostPagination
    
    def get_queryset(self):
        """Return moderation actions."""
        queryset = ModerationAction.objects.all()
        
        # Filter by post if specified
        post_id = self.request.query_params.get('post_id')
        if post_id:
            queryset = queryset.filter(post_id=post_id)
        
        # Filter by moderator if specified
        moderator_id = self.request.query_params.get('moderator_id')
        if moderator_id:
            queryset = queryset.filter(moderator_id=moderator_id)
        
        return queryset.select_related('post', 'moderator').order_by('-created_at')
