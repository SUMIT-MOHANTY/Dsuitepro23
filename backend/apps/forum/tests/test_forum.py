"""
Forum Tests for Enterprise LMS
Provides comprehensive test coverage for forum models, views, and API endpoints.
"""

import uuid
from datetime import datetime, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.forum.models import DiscussionForum, DiscussionPost, PostVote, ModerationAction
from apps.courses.models import Course

User = get_user_model()


class DiscussionForumModelTests(TestCase):
    """Tests for DiscussionForum model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.user
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum',
            description='Test forum description',
            is_moderated=True
        )
    
    def test_forum_creation(self):
        """Test forum creation."""
        self.assertEqual(self.forum.title, 'Test Forum')
        self.assertEqual(self.forum.course, self.course)
        self.assertTrue(self.forum.is_moderated)
        self.assertTrue(self.forum.is_active)
    
    def test_forum_str(self):
        """Test forum string representation."""
        expected = f"{self.course.title} - {self.forum.title}"
        self.assertEqual(str(self.forum), expected)
    
    def test_forum_update_stats(self):
        """Test forum stats update."""
        # Create posts
        DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Topic 1',
            content='Content 1'
        )
        
        self.forum.update_stats()
        self.assertEqual(self.forum.topic_count, 1)
        self.assertEqual(self.forum.post_count, 1)


class DiscussionPostModelTests(TestCase):
    """Tests for DiscussionPost model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.user
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum',
            is_moderated=True
        )
        self.topic = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Test Topic',
            content='Test content'
        )
    
    def test_topic_creation(self):
        """Test topic post creation."""
        self.assertEqual(self.topic.post_type, DiscussionPost.TYPE_TOPIC)
        self.assertEqual(self.topic.depth, 0)
        self.assertIsNone(self.topic.parent)
        self.assertIsNone(self.topic.root_post)
    
    def test_reply_creation(self):
        """Test reply post creation."""
        reply = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply content'
        )
        
        self.assertEqual(reply.post_type, DiscussionPost.TYPE_REPLY)
        self.assertEqual(reply.depth, 1)
        self.assertEqual(reply.parent, self.topic)
        self.assertEqual(reply.root_post, self.topic)
    
    def test_nested_reply(self):
        """Test nested reply creation."""
        reply1 = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply 1'
        )
        reply2 = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=reply1,
            content='Reply 2'
        )
        
        self.assertEqual(reply2.depth, 2)
        self.assertEqual(reply2.root_post, self.topic)
    
    def test_post_str(self):
        """Test post string representation."""
        expected = f"{self.topic.title} by {self.user.email}"
        self.assertEqual(str(self.topic), expected)
    
    def test_is_topic(self):
        """Test is_topic method."""
        self.assertTrue(self.topic.is_topic())
        
        reply = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply'
        )
        self.assertFalse(reply.is_topic())
    
    def test_is_reply(self):
        """Test is_reply method."""
        self.assertFalse(self.topic.is_reply())
        
        reply = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply'
        )
        self.assertTrue(reply.is_reply())
    
    def test_get_thread_root(self):
        """Test get_thread_root method."""
        self.assertEqual(self.topic.get_thread_root(), self.topic)
        
        reply = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply'
        )
        self.assertEqual(reply.get_thread_root(), self.topic)
    
    def test_pin_unpin(self):
        """Test pin and unpin methods."""
        self.assertFalse(self.topic.is_pinned)
        
        self.topic.pin()
        self.assertTrue(self.topic.is_pinned)
        
        self.topic.unpin()
        self.assertFalse(self.topic.is_pinned)
    
    def test_lock_unlock(self):
        """Test lock and unlock methods."""
        self.assertFalse(self.topic.is_locked)
        
        self.topic.lock()
        self.assertTrue(self.topic.is_locked)
        
        self.topic.unlock()
        self.assertFalse(self.topic.is_locked)
    
    def test_approve_reject(self):
        """Test approve and reject methods."""
        self.assertEqual(self.topic.moderation_status, DiscussionPost.MODERATION_APPROVED)
        
        self.topic.reject()
        self.assertEqual(self.topic.moderation_status, DiscussionPost.MODERATION_REJECTED)
        
        self.topic.approve()
        self.assertEqual(self.topic.moderation_status, DiscussionPost.MODERATION_APPROVED)
    
    def test_mark_as_spam(self):
        """Test mark_as_spam method."""
        self.topic.mark_as_spam()
        self.assertEqual(self.topic.moderation_status, DiscussionPost.MODERATION_SPAM)
        self.assertTrue(self.topic.is_hidden)
    
    def test_mark_as_edited(self):
        """Test mark_as_edited method."""
        self.topic.mark_as_edited(edited_by=self.user, reason='Typo fix')
        self.assertTrue(self.topic.is_edited)
        self.assertIsNotNone(self.topic.edited_at)
        self.assertEqual(self.topic.edited_by, self.user)
        self.assertEqual(self.topic.edit_reason, 'Typo fix')
    
    def test_increment_view_count(self):
        """Test increment_view_count method."""
        initial_count = self.topic.view_count
        self.topic.increment_view_count()
        self.assertEqual(self.topic.view_count, initial_count + 1)
    
    def test_update_reply_count(self):
        """Test update_reply_count method."""
        # Create replies
        DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply 1'
        )
        DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            parent=self.topic,
            content='Reply 2'
        )
        
        self.topic.update_reply_count()
        self.assertEqual(self.topic.reply_count, 2)


class PostVoteModelTests(TestCase):
    """Tests for PostVote model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            email='other@example.com',
            username='otheruser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.user
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum'
        )
        self.post = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Test Post',
            content='Test content'
        )
    
    def test_upvote_creation(self):
        """Test upvote creation."""
        vote = PostVote.objects.create(
            post=self.post,
            user=self.other_user,
            vote_type=PostVote.VOTE_UP
        )
        
        self.assertEqual(vote.vote_type, PostVote.VOTE_UP)
        
        # Refresh post
        self.post.refresh_from_db()
        self.assertEqual(self.post.upvotes, 1)
        self.assertEqual(self.post.vote_score, 1)
    
    def test_downvote_creation(self):
        """Test downvote creation."""
        vote = PostVote.objects.create(
            post=self.post,
            user=self.other_user,
            vote_type=PostVote.VOTE_DOWN
        )
        
        self.assertEqual(vote.vote_type, PostVote.VOTE_DOWN)
        
        # Refresh post
        self.post.refresh_from_db()
        self.assertEqual(self.post.downvotes, 1)
        self.assertEqual(self.post.vote_score, -1)
    
    def test_vote_change(self):
        """Test changing vote from upvote to downvote."""
        vote = PostVote.objects.create(
            post=self.post,
            user=self.other_user,
            vote_type=PostVote.VOTE_UP
        )
        
        self.post.refresh_from_db()
        self.assertEqual(self.post.upvotes, 1)
        self.assertEqual(self.post.downvotes, 0)
        
        # Change vote
        vote.vote_type = PostVote.VOTE_DOWN
        vote.save()
        
        self.post.refresh_from_db()
        self.assertEqual(self.post.upvotes, 0)
        self.assertEqual(self.post.downvotes, 1)
    
    def test_vote_deletion(self):
        """Test vote deletion updates counts."""
        vote = PostVote.objects.create(
            post=self.post,
            user=self.other_user,
            vote_type=PostVote.VOTE_UP
        )
        
        self.post.refresh_from_db()
        self.assertEqual(self.post.upvotes, 1)
        
        vote.delete()
        
        self.post.refresh_from_db()
        self.assertEqual(self.post.upvotes, 0)
    
    def test_unique_vote_per_user(self):
        """Test that a user can only vote once per post."""
        PostVote.objects.create(
            post=self.post,
            user=self.other_user,
            vote_type=PostVote.VOTE_UP
        )
        
        # Should raise IntegrityError
        with self.assertRaises(Exception):
            PostVote.objects.create(
                post=self.post,
                user=self.other_user,
                vote_type=PostVote.VOTE_DOWN
            )


class ModerationActionModelTests(TestCase):
    """Tests for ModerationAction model."""
    
    def setUp(self):
        self.moderator = User.objects.create_user(
            email='moderator@example.com',
            username='moderator',
            password='testpass123'
        )
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.moderator
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum',
            is_moderated=True
        )
        self.post = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Test Post',
            content='Test content'
        )
    
    def test_moderation_action_creation(self):
        """Test moderation action creation."""
        action = ModerationAction.objects.create(
            post=self.post,
            moderator=self.moderator,
            action=ModerationAction.ACTION_HIDE,
            reason='Inappropriate content'
        )
        
        self.assertEqual(action.action, ModerationAction.ACTION_HIDE)
        self.assertEqual(action.moderator, self.moderator)
        self.assertEqual(action.reason, 'Inappropriate content')
    
    def test_moderation_action_str(self):
        """Test moderation action string representation."""
        action = ModerationAction.objects.create(
            post=self.post,
            moderator=self.moderator,
            action=ModerationAction.ACTION_HIDE,
            reason='Inappropriate content'
        )
        
        expected = f"{action.action} on {self.post.id} by {self.moderator.email}"
        self.assertEqual(str(action), expected)


class ForumAPITests(APITestCase):
    """Tests for Forum API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum',
            is_moderated=True
        )
    
    def authenticate(self, user):
        """Authenticate as a specific user."""
        self.client.force_authenticate(user=user)
    
    def test_list_forums(self):
        """Test listing forums."""
        self.authenticate(self.user)
        url = reverse('forum-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_retrieve_forum(self):
        """Test retrieving a specific forum."""
        self.authenticate(self.user)
        url = reverse('forum-detail', kwargs={'pk': self.forum.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Forum')
    
    def test_create_forum(self):
        """Test creating a new forum."""
        self.authenticate(self.instructor)
        
        # Create another course
        course2 = Course.objects.create(
            title='Test Course 2',
            slug='test-course-2',
            description='Test course description',
            instructor=self.instructor
        )
        
        url = reverse('forum-list')
        data = {
            'course_id': str(course2.id),
            'title': 'New Forum',
            'description': 'New forum description',
            'is_moderated': True
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Forum')
    
    def test_create_forum_duplicate(self):
        """Test creating a forum for a course that already has one."""
        self.authenticate(self.instructor)
        url = reverse('forum-list')
        data = {
            'course_id': str(self.course.id),
            'title': 'Another Forum',
            'description': 'Another forum'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PostAPITests(APITestCase):
    """Tests for Post API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            email='other@example.com',
            username='otheruser',
            password='testpass123'
        )
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum',
            is_moderated=True
        )
        self.topic = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Test Topic',
            content='Test content'
        )
    
    def authenticate(self, user):
        """Authenticate as a specific user."""
        self.client.force_authenticate(user=user)
    
    def test_list_posts(self):
        """Test listing posts."""
        self.authenticate(self.user)
        url = reverse('post-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_create_topic(self):
        """Test creating a new topic."""
        self.authenticate(self.user)
        url = reverse('post-list')
        data = {
            'forum_id': str(self.forum.id),
            'title': 'New Topic',
            'content': 'New topic content'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Topic')
    
    def test_create_reply(self):
        """Test creating a reply to a topic."""
        self.authenticate(self.user)
        url = reverse('post-list')
        data = {
            'forum_id': str(self.forum.id),
            'parent_id': str(self.topic.id),
            'content': 'This is a reply'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['post_type'], DiscussionPost.TYPE_REPLY)
    
    def test_create_reply_to_locked_post(self):
        """Test creating a reply to a locked post."""
        self.authenticate(self.user)
        self.topic.lock()
        
        url = reverse('post-list')
        data = {
            'forum_id': str(self.forum.id),
            'parent_id': str(self.topic.id),
            'content': 'This should fail'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_post(self):
        """Test updating a post."""
        self.authenticate(self.user)
        url = reverse('post-detail', kwargs={'pk': self.topic.id})
        data = {
            'title': 'Updated Title',
            'content': 'Updated content'
        }
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Title')
    
    def test_update_post_not_author(self):
        """Test updating a post by non-author."""
        self.authenticate(self.other_user)
        url = reverse('post-detail', kwargs={'pk': self.topic.id})
        data = {
            'title': 'Updated Title'
        }
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_post(self):
        """Test deleting a post."""
        self.authenticate(self.user)
        url = reverse('post-detail', kwargs={'pk': self.topic.id})
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_vote_post(self):
        """Test voting on a post."""
        self.authenticate(self.other_user)
        url = reverse('post-vote', kwargs={'pk': self.topic.id})
        data = {
            'vote_type': PostVote.VOTE_UP
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh post
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.upvotes, 1)
    
    def test_pin_post(self):
        """Test pinning a post."""
        self.authenticate(self.instructor)
        url = reverse('post-pin', kwargs={'pk': self.topic.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.topic.refresh_from_db()
        self.assertTrue(self.topic.is_pinned)
    
    def test_lock_post(self):
        """Test locking a post."""
        self.authenticate(self.instructor)
        url = reverse('post-lock', kwargs={'pk': self.topic.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.topic.refresh_from_db()
        self.assertTrue(self.topic.is_locked)
    
    def test_get_replies(self):
        """Test getting replies for a post."""
        self.authenticate(self.user)
        
        # Create a reply
        reply = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.other_user,
            parent=self.topic,
            content='Test reply'
        )
        
        url = reverse('post-replies', kwargs={'pk': self.topic.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ForumPermissionTests(APITestCase):
    """Tests for forum permissions."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum'
        )
        self.topic = DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Test Topic',
            content='Test content'
        )
    
    def test_unauthenticated_access(self):
        """Test that unauthenticated users cannot access forum endpoints."""
        url = reverse('forum-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_non_moderator_cannot_pin(self):
        """Test that non-moderators cannot pin posts."""
        self.client.force_authenticate(user=self.user)
        url = reverse('post-pin', kwargs={'pk': self.topic.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_non_moderator_cannot_lock(self):
        """Test that non-moderators cannot lock posts."""
        self.client.force_authenticate(user=self.user)
        url = reverse('post-lock', kwargs={'pk': self.topic.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ForumSearchTests(APITestCase):
    """Tests for forum search functionality."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.user
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum'
        )
        
        # Create posts
        DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Python Programming',
            content='Learn Python basics'
        )
        DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Django Framework',
            content='Web development with Django'
        )
    
    def test_search_posts(self):
        """Test searching posts."""
        self.client.force_authenticate(user=self.user)
        url = reverse('post-list')
        response = self.client.get(url, {'search': 'Python'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_filter_by_author(self):
        """Test filtering posts by author."""
        self.client.force_authenticate(user=self.user)
        url = reverse('post-list')
        response = self.client.get(url, {'author_id': str(self.user.id)})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ForumStatsTests(APITestCase):
    """Tests for forum statistics."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.user
        )
        self.forum = DiscussionForum.objects.create(
            course=self.course,
            title='Test Forum'
        )
    
    def test_forum_stats(self):
        """Test getting forum statistics."""
        self.client.force_authenticate(user=self.user)
        
        # Create posts
        DiscussionPost.objects.create(
            forum=self.forum,
            author=self.user,
            title='Topic 1',
            content='Content 1'
        )
        
        url = reverse('forum-stats', kwargs={'pk': self.forum.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
