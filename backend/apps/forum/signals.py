"""
Forum Signals for Enterprise LMS
Provides signal handlers for forum post events, notifications, and moderation triggers.
"""

import logging
from typing import Any

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import DiscussionPost, PostVote, ModerationAction, DiscussionForum
from apps.notifications.tasks import (
    send_forum_reply_notification,
    send_email_task
)

logger = logging.getLogger(__name__)
User = get_user_model()

# Upvote threshold for triggering notifications
UPVOTE_THRESHOLD = 10


@receiver(post_save, sender=DiscussionPost)
def handle_post_save(sender, instance: DiscussionPost, created: bool, **kwargs: Any) -> None:
    """
    Handle post-save events for DiscussionPost.
    - Update forum statistics
    - Update parent post reply counts
    - Send notifications for replies
    """
    if created:
        # Update forum stats
        instance.forum.update_stats()
        
        # Update parent post reply count if this is a reply
        if instance.parent:
            instance.parent.update_reply_count()
            
            # Send notification to parent post author
            if instance.parent.notify_replies:
                try:
                    send_forum_reply_notification.delay(
                        str(instance.parent_id),
                        str(instance.author_id)
                    )
                    logger.info(f"Queued reply notification for post {instance.parent_id}")
                except Exception as exc:
                    logger.error(f"Failed to queue reply notification: {str(exc)}")
        
        logger.info(f"New post created: {instance.id} by {instance.author.email}")


@receiver(post_delete, sender=DiscussionPost)
def handle_post_delete(sender, instance: DiscussionPost, **kwargs: Any) -> None:
    """
    Handle post-delete events for DiscussionPost.
    - Update forum statistics
    - Update parent post reply counts
    """
    # Update forum stats
    try:
        instance.forum.update_stats()
    except Exception:
        pass
    
    # Update parent reply count
    if instance.parent:
        try:
            instance.parent.update_reply_count()
        except Exception:
            pass
    
    logger.info(f"Post deleted: {instance.id}")


@receiver(post_save, sender=PostVote)
def handle_vote_save(sender, instance: PostVote, created: bool, **kwargs: Any) -> None:
    """
    Handle post-save events for PostVote.
    - Check for upvote threshold and notify author
    - Log significant vote events
    """
    if created and instance.vote_type == PostVote.VOTE_UP:
        post = instance.post
        
        # Check if post crossed the upvote threshold
        if post.upvotes == UPVOTE_THRESHOLD:
            # Send notification to post author about milestone
            try:
                from apps.notifications.services import NotificationService
                from apps.notifications.models import Notification
                
                service = NotificationService()
                service.send_notification(
                    user=post.author,
                    title=f"Your post reached {UPVOTE_THRESHOLD} upvotes!",
                    message=f"Your post '{post.title or 'in ' + post.forum.course.title}' has received {UPVOTE_THRESHOLD} upvotes.",
                    category=Notification.CATEGORY_FORUM,
                    data={
                        'post_id': str(post.id),
                        'forum_id': str(post.forum_id),
                        'upvote_count': post.upvotes
                    },
                    action_url=f"/courses/{post.forum.course.slug}/forum/posts/{post.id}"
                )
                logger.info(f"Upvote milestone notification sent for post {post.id}")
            except Exception as exc:
                logger.error(f"Failed to send upvote milestone notification: {str(exc)}")


@receiver(post_save, sender=ModerationAction)
def handle_moderation_action_save(sender, instance: ModerationAction, created: bool, **kwargs: Any) -> None:
    """
    Handle post-save events for ModerationAction.
    - Log moderation actions
    - Send notifications for significant moderation events
    """
    if created:
        post = instance.post
        moderator = instance.moderator
        action = instance.action
        
        logger.info(f"Moderation action '{action}' on post {post.id} by {moderator.email}")
        
        # Notify post author for certain actions
        notify_actions = [
            ModerationAction.ACTION_HIDE,
            ModerationAction.ACTION_DELETE,
            ModerationAction.ACTION_REJECT,
            ModerationAction.ACTION_MARK_SPAM,
            ModerationAction.ACTION_WARNING,
            ModerationAction.ACTION_BAN_USER,
        ]
        
        if action in notify_actions and post.author != moderator:
            try:
                from apps.notifications.services import NotificationService
                from apps.notifications.models import Notification
                
                service = NotificationService()
                
                action_messages = {
                    ModerationAction.ACTION_HIDE: "Your post has been hidden by a moderator.",
                    ModerationAction.ACTION_DELETE: "Your post has been deleted by a moderator.",
                    ModerationAction.ACTION_REJECT: "Your post has been rejected by a moderator.",
                    ModerationAction.ACTION_MARK_SPAM: "Your post has been marked as spam.",
                    ModerationAction.ACTION_WARNING: "You have received a warning from a moderator.",
                    ModerationAction.ACTION_BAN_USER: "You have been banned from the forum.",
                }
                
                service.send_notification(
                    user=post.author,
                    title=f"Forum Moderation: {action.replace('_', ' ').title()}",
                    message=action_messages.get(action, f"A moderation action was taken on your post. Reason: {instance.reason}"),
                    category=Notification.CATEGORY_FORUM,
                    priority='high' if action in [ModerationAction.ACTION_BAN_USER, ModerationAction.ACTION_WARNING] else 'normal',
                    data={
                        'post_id': str(post.id),
                        'action': action,
                        'moderator_id': str(moderator.id),
                        'reason': instance.reason
                    }
                )
                logger.info(f"Moderation notification sent to {post.author.email}")
            except Exception as exc:
                logger.error(f"Failed to send moderation notification: {str(exc)}")


@receiver(pre_save, sender=DiscussionPost)
def handle_post_pre_save(sender, instance: DiscussionPost, **kwargs: Any) -> None:
    """
    Handle pre-save events for DiscussionPost.
    - Track edit history
    - Validate content changes
    """
    if instance.pk:
        # Post is being updated
        try:
            old_instance = DiscussionPost.objects.get(pk=instance.pk)
            
            # Check if content changed
            if old_instance.content != instance.content:
                # Content changed - is_edited will be set by mark_as_edited
                # but we need to ensure edited_at is set
                if not instance.is_edited:
                    from django.utils import timezone
                    instance.is_edited = True
                    instance.edited_at = timezone.now()
                    
        except DiscussionPost.DoesNotExist:
            pass


def notify_mentions_in_post(post: DiscussionPost) -> None:
    """
    Notify users mentioned in a post.
    Extracts @username mentions and sends notifications.
    
    Args:
        post: The post to scan for mentions
    """
    import re
    
    # Extract @username mentions
    mentions = re.findall(r'@(\w+)', post.content)
    
    if not mentions:
        return
    
    from apps.notifications.services import NotificationService
    from apps.notifications.models import Notification
    
    service = NotificationService()
    notified_count = 0
    
    for username in mentions:
        try:
            mentioned_user = User.objects.get(username=username)
            
            # Don't notify self-mentions
            if mentioned_user.id == post.author_id:
                continue
            
            service.send_notification(
                user=mentioned_user,
                title=f"You were mentioned in {post.forum.course.title}",
                message=f"{post.author.get_full_name()} mentioned you in a post: '{post.title or 'Reply'}'",
                category=Notification.CATEGORY_FORUM,
                data={
                    'post_id': str(post.id),
                    'forum_id': str(post.forum_id),
                    'mentioned_by': str(post.author_id)
                },
                action_url=f"/courses/{post.forum.course.slug}/forum/posts/{post.id}"
            )
            notified_count += 1
            
        except User.DoesNotExist:
            continue
        except Exception as exc:
            logger.error(f"Failed to send mention notification to @{username}: {str(exc)}")
    
    if notified_count > 0:
        logger.info(f"Sent {notified_count} mention notifications for post {post.id}")


# Connect mention notification to post_save signal
@receiver(post_save, sender=DiscussionPost)
def handle_mentions(sender, instance: DiscussionPost, created: bool, **kwargs: Any) -> None:
    """
    Handle @mentions in posts.
    """
    if created:
        notify_mentions_in_post(instance)
