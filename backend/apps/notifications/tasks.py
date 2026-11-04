"""
Notification Tasks for Enterprise LMS
Provides Celery tasks for async notification processing, email sending, digest generation,
retry scheduling with exponential backoff, and dead letter queue handling.
"""

import logging
import random
import uuid
from typing import List, Optional
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import (
    Notification, NotificationPreference, NotificationDigest,
    NotificationDLQ, NotificationDeliveryLog
)
from .services import NotificationService

logger = logging.getLogger(__name__)
User = get_user_model()

# Maximum retry attempts before moving to DLQ
MAX_RETRY_ATTEMPTS = 5
# Base delay in seconds for exponential backoff
BASE_RETRY_DELAY = 60


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, notification_id: str) -> bool:
    """
    Celery task to send an email notification.
    
    Args:
        notification_id: UUID of the notification to send
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        service = NotificationService()
        result = service._send_email_notification(notification)
        
        if result:
            logger.info(f"Email task succeeded for notification {notification_id}")
        else:
            logger.warning(f"Email task failed for notification {notification_id}")
        
        return result
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return False
    except Exception as exc:
        logger.error(f"Email task error for {notification_id}: {str(exc)}")
        # Retry the task
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_bulk_email_task(self, notification_ids: List[str]) -> dict:
    """
    Celery task to send multiple email notifications.
    
    Args:
        notification_ids: List of notification UUIDs to send
        
    Returns:
        Dict with success and failure counts
    """
    success_count = 0
    failure_count = 0
    
    service = NotificationService()
    
    for notification_id in notification_ids:
        try:
            notification = Notification.objects.get(id=notification_id)
            if service._send_email_notification(notification):
                success_count += 1
            else:
                failure_count += 1
        except Notification.DoesNotExist:
            logger.error(f"Notification {notification_id} not found")
            failure_count += 1
        except Exception as exc:
            logger.error(f"Error sending notification {notification_id}: {str(exc)}")
            failure_count += 1
    
    logger.info(f"Bulk email task completed: {success_count} succeeded, {failure_count} failed")
    
    return {
        'success_count': success_count,
        'failure_count': failure_count,
        'total': len(notification_ids)
    }


@shared_task
def send_digest_task(digest_type: str = 'daily') -> dict:
    """
    Celery task to send notification digests to users.
    
    Args:
        digest_type: Type of digest (hourly, daily, weekly)
        
    Returns:
        Dict with processing statistics
    """
    service = NotificationService()
    sent_count = 0
    skipped_count = 0
    error_count = 0
    
    # Get users who want this digest frequency
    preferences = NotificationPreference.objects.filter(
        email_enabled=True,
        email_digest_frequency=digest_type
    ).select_related('user')
    
    for preference in preferences:
        try:
            # Check if user has unread notifications
            unread_count = Notification.objects.filter(
                user=preference.user,
                is_read=False,
                notification_type=Notification.TYPE_IN_APP
            ).count()
            
            if unread_count == 0:
                skipped_count += 1
                continue
            
            # Send digest
            digest = service.send_digest(preference.user, digest_type)
            
            if digest:
                sent_count += 1
                logger.info(f"Sent {digest_type} digest to {preference.user.email}")
            else:
                skipped_count += 1
                
        except Exception as exc:
            error_count += 1
            logger.error(f"Error sending digest to {preference.user.email}: {str(exc)}")
    
    logger.info(f"Digest task completed: {sent_count} sent, {skipped_count} skipped, {error_count} errors")
    
    return {
        'digest_type': digest_type,
        'sent_count': sent_count,
        'skipped_count': skipped_count,
        'error_count': error_count
    }


@shared_task
def send_hourly_digest_task() -> dict:
    """Task to send hourly notification digests."""
    return send_digest_task.delay('hourly').get()


@shared_task
def send_daily_digest_task() -> dict:
    """Task to send daily notification digests."""
    return send_digest_task.delay('daily').get()


@shared_task
def send_weekly_digest_task() -> dict:
    """Task to send weekly notification digests."""
    return send_digest_task.delay('weekly').get()


def calculate_retry_delay(attempt_count: int) -> int:
    """
    Calculate retry delay with exponential backoff and jitter.
    
    Uses exponential backoff: delay = base_delay * (2 ^ attempt_count)
    Adds jitter: random.uniform(0.5, 1.5) to prevent thundering herd
    
    Args:
        attempt_count: Current number of retry attempts
        
    Returns:
        Delay in seconds
    """
    # Exponential backoff: 60s, 120s, 240s, 480s, 960s
    exponential_delay = BASE_RETRY_DELAY * (2 ** attempt_count)
    
    # Add jitter: multiply by random factor between 0.5 and 1.5
    jitter = random.uniform(0.5, 1.5)
    
    delay = int(exponential_delay * jitter)
    
    # Cap at 1 hour
    return min(delay, 3600)


@shared_task
def schedule_notification_retry(notification_id: str) -> dict:
    """
    Schedule a retry for a failed notification.
    
    Args:
        notification_id: UUID of the notification to retry
        
    Returns:
        Dict with scheduling status
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # Check if max retries exceeded
        if notification.retry_count >= MAX_RETRY_ATTEMPTS:
            logger.warning(f"Max retries exceeded for notification {notification_id}, moving to DLQ")
            move_to_dlq_task.delay(notification_id, "Max retry attempts exceeded")
            return {
                'status': 'moved_to_dlq',
                'notification_id': notification_id,
                'reason': 'Max retry attempts exceeded'
            }
        
        # Calculate next retry time
        delay_seconds = calculate_retry_delay(notification.retry_count)
        next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
        
        # Update notification
        notification.retry_count += 1
        notification.next_retry_at = next_retry_at
        notification.status = Notification.STATUS_PENDING
        notification.save(update_fields=['retry_count', 'next_retry_at', 'status', 'updated_at'])
        
        # Schedule the retry task
        process_single_notification_task.apply_async(
            args=[notification_id],
            countdown=delay_seconds
        )
        
        logger.info(f"Scheduled retry {notification.retry_count}/{MAX_RETRY_ATTEMPTS} "
                   f"for notification {notification_id} in {delay_seconds}s")
        
        return {
            'status': 'scheduled',
            'notification_id': notification_id,
            'attempt': notification.retry_count,
            'delay_seconds': delay_seconds,
            'next_retry_at': next_retry_at.isoformat()
        }
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found for retry scheduling")
        return {'status': 'error', 'reason': 'Notification not found'}
    except Exception as exc:
        logger.error(f"Error scheduling retry for {notification_id}: {str(exc)}")
        return {'status': 'error', 'reason': str(exc)}


@shared_task
def process_single_notification_task(notification_id: str) -> dict:
    """
    Process a single notification delivery.
    
    Args:
        notification_id: UUID of the notification to process
        
    Returns:
        Dict with processing result
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        service = NotificationService()
        
        # Check idempotency - already delivered
        if notification.status == Notification.STATUS_DELIVERED:
            logger.info(f"Notification {notification_id} already delivered, skipping")
            return {'status': 'skipped', 'reason': 'already_delivered'}
        
        # Route to appropriate channel
        result = False
        error_message = None
        
        try:
            if notification.channel == Notification.CHANNEL_EMAIL:
                result = service._send_email_notification(notification)
            elif notification.channel == Notification.CHANNEL_IN_APP:
                result = service._send_in_app_notification(notification)
            elif notification.channel == Notification.CHANNEL_PUSH:
                result = service._send_push_notification(notification)
            elif notification.channel == Notification.CHANNEL_SMS:
                result = service._send_sms_notification(notification)
            else:
                error_message = f"Unknown channel: {notification.channel}"
                
        except Exception as channel_exc:
            error_message = str(channel_exc)
            result = False
        
        if result:
            notification.status = Notification.STATUS_DELIVERED
            notification.delivered_at = timezone.now()
            notification.save(update_fields=['status', 'delivered_at', 'updated_at'])
            
            logger.info(f"Successfully delivered notification {notification_id}")
            return {'status': 'delivered', 'notification_id': notification_id}
        else:
            # Mark as failed and schedule retry
            notification.status = Notification.STATUS_FAILED
            notification.error_message = error_message or "Delivery failed"
            notification.save(update_fields=['status', 'error_message', 'updated_at'])
            
            # Schedule retry
            schedule_notification_retry.delay(notification_id)
            
            logger.warning(f"Failed to deliver notification {notification_id}, retry scheduled")
            return {
                'status': 'failed_retry_scheduled',
                'notification_id': notification_id,
                'error': error_message
            }
            
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return {'status': 'error', 'reason': 'Notification not found'}
    except Exception as exc:
        logger.error(f"Error processing notification {notification_id}: {str(exc)}")
        return {'status': 'error', 'reason': str(exc)}


@shared_task
def move_to_dlq_task(notification_id: str, reason: str = "") -> dict:
    """
    Move a failed notification to the Dead Letter Queue.
    
    Args:
        notification_id: UUID of the notification to move
        reason: Reason for moving to DLQ
        
    Returns:
        Dict with DLQ operation result
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # Create DLQ entry
        dlq_entry = NotificationDLQ.objects.create(
            idempotency_key=notification.idempotency_key or str(uuid.uuid4()),
            payload={
                'notification_id': str(notification.id),
                'user_id': str(notification.user_id) if notification.user else None,
                'title': notification.title,
                'message': notification.message,
                'channel': notification.channel,
                'category': notification.category,
                'priority': notification.priority,
                'data': notification.data,
                'action_url': notification.action_url,
            },
            channel=notification.channel,
            attempt_count=notification.retry_count,
            failed_at=timezone.now(),
            error_message=reason or notification.error_message or "Unknown error",
            error_trace=notification.error_message,
            original_notification=notification
        )
        
        # Update notification status
        notification.status = Notification.STATUS_FAILED
        notification.save(update_fields=['status', 'updated_at'])
        
        logger.info(f"Moved notification {notification_id} to DLQ: {dlq_entry.id}")
        
        return {
            'status': 'moved_to_dlq',
            'notification_id': notification_id,
            'dlq_id': str(dlq_entry.id),
            'reason': reason
        }
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found for DLQ move")
        return {'status': 'error', 'reason': 'Notification not found'}
    except Exception as exc:
        logger.error(f"Error moving notification {notification_id} to DLQ: {str(exc)}")
        return {'status': 'error', 'reason': str(exc)}


@shared_task
def process_dlq_task(batch_size: int = 50, max_age_hours: int = 168) -> dict:
    """
    Process notifications in the Dead Letter Queue.
    Can be used to retry DLQ items or clean up old entries.
    
    Args:
        batch_size: Number of DLQ entries to process
        max_age_hours: Maximum age in hours before permanent deletion
        
    Returns:
        Dict with processing statistics
    """
    from django.db.models import Q
    
    retry_count = 0
    delete_count = 0
    error_count = 0
    
    cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
    
    # Get DLQ entries that haven't been retried recently
    dlq_entries = NotificationDLQ.objects.filter(
        Q(last_retry_at__isnull=True) | 
        Q(last_retry_at__lt=timezone.now() - timedelta(hours=1))
    ).exclude(
        attempt_count__gte=10  # Max DLQ retries
    )[:batch_size]
    
    for entry in dlq_entries:
        try:
            # Attempt to retry the notification
            payload = entry.payload
            
            # Create a new notification from DLQ payload
            if entry.original_notification:
                # Reset the original notification for retry
                notification = entry.original_notification
                notification.status = Notification.STATUS_PENDING
                notification.retry_count = 0
                notification.error_message = None
                notification.next_retry_at = None
                notification.save()
                
                # Schedule immediate retry
                process_single_notification_task.delay(str(notification.id))
                
                entry.attempt_count += 1
                entry.last_retry_at = timezone.now()
                entry.save()
                
                retry_count += 1
            else:
                # No original notification, delete old entry
                if entry.failed_at < cutoff_time:
                    entry.delete()
                    delete_count += 1
                    
        except Exception as exc:
            error_count += 1
            logger.error(f"Error processing DLQ entry {entry.id}: {str(exc)}")
    
    # Clean up very old DLQ entries
    old_entries = NotificationDLQ.objects.filter(failed_at__lt=cutoff_time)
    old_deleted = old_entries.count()
    old_entries.delete()
    
    logger.info(f"DLQ processing completed: {retry_count} retried, "
                f"{delete_count} deleted, {old_deleted} old entries purged, "
                f"{error_count} errors")
    
    return {
        'retry_count': retry_count,
        'delete_count': delete_count + old_deleted,
        'error_count': error_count
    }


@shared_task
def retry_failed_notifications_task(max_retries: int = MAX_RETRY_ATTEMPTS) -> dict:
    """
    Celery task to retry failed notifications.
    
    Args:
        max_retries: Maximum number of retry attempts per notification
        
    Returns:
        Dict with retry statistics
    """
    service = NotificationService()
    success_count = service.retry_failed_notifications(max_retries)
    
    failed_count = Notification.objects.filter(
        status=Notification.STATUS_FAILED,
        retry_count__gte=max_retries
    ).count()
    
    logger.info(f"Retry task completed: {success_count} succeeded, {failed_count} still failed")
    
    return {
        'success_count': success_count,
        'failed_count': failed_count
    }


@shared_task
def cleanup_old_notifications_task(days: int = 90) -> dict:
    """
    Celery task to clean up old read notifications.
    
    Args:
        days: Age in days after which to delete read notifications
        
    Returns:
        Dict with cleanup statistics
    """
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete old read notifications
    old_notifications = Notification.objects.filter(
        is_read=True,
        read_at__lt=cutoff_date
    )
    
    deleted_count = old_notifications.count()
    old_notifications.delete()
    
    # Delete old digests
    old_digests = NotificationDigest.objects.filter(
        sent_at__lt=cutoff_date
    )
    
    digests_deleted = old_digests.count()
    old_digests.delete()
    
    # Delete old DLQ entries
    old_dlq = NotificationDLQ.objects.filter(
        failed_at__lt=cutoff_date
    )
    dlq_deleted = old_dlq.count()
    old_dlq.delete()
    
    # Delete old delivery logs
    old_logs = NotificationDeliveryLog.objects.filter(
        created_at__lt=cutoff_date
    )
    logs_deleted = old_logs.count()
    old_logs.delete()
    
    logger.info(f"Cleanup task completed: {deleted_count} notifications, "
                f"{digests_deleted} digests, {dlq_deleted} DLQ entries, "
                f"{logs_deleted} delivery logs deleted")
    
    return {
        'notifications_deleted': deleted_count,
        'digests_deleted': digests_deleted,
        'dlq_deleted': dlq_deleted,
        'logs_deleted': logs_deleted,
        'cutoff_date': cutoff_date.isoformat()
    }


@shared_task
def send_course_update_notification(course_id: str, update_type: str, affected_user_ids: Optional[List[str]] = None) -> dict:
    """
    Send notifications to users about course updates.
    
    Args:
        course_id: UUID of the course
        update_type: Type of update (content_added, schedule_changed, etc.)
        affected_user_ids: Optional list of user IDs to notify (defaults to enrolled users)
        
    Returns:
        Dict with notification statistics
    """
    from apps.courses.models import Course
    from apps.enrollment.models import Enrollment
    
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        logger.error(f"Course {course_id} not found")
        return {'error': 'Course not found'}
    
    # Get users to notify
    if affected_user_ids:
        users = User.objects.filter(id__in=affected_user_ids)
    else:
        # Get enrolled users
        enrolled_user_ids = Enrollment.objects.filter(
            course_id=course_id,
            status='active'
        ).values_list('user_id', flat=True)
        users = User.objects.filter(id__in=enrolled_user_ids)
    
    service = NotificationService()
    notification_count = 0
    
    update_messages = {
        'content_added': f"New content has been added to '{course.title}'",
        'schedule_changed': f"The schedule for '{course.title}' has been updated",
        'assignment_added': f"A new assignment has been added to '{course.title}'",
        'announcement': f"New announcement in '{course.title}'",
    }
    
    message = update_messages.get(update_type, f"Update in '{course.title}'")
    
    for user in users:
        try:
            # Check user preferences
            preference = getattr(user, 'notification_preferences', None)
            if preference and not preference.notify_on_course_updates:
                continue
            
            service.send_notification(
                user=user,
                title=f"Course Update: {course.title}",
                message=message,
                category=Notification.CATEGORY_COURSE,
                data={
                    'course_id': str(course_id),
                    'update_type': update_type
                },
                action_url=f"/courses/{course.slug}"
            )
            notification_count += 1
            
        except Exception as exc:
            logger.error(f"Error sending course update to {user.email}: {str(exc)}")
    
    logger.info(f"Course update notifications sent: {notification_count}")
    
    return {
        'course_id': course_id,
        'update_type': update_type,
        'notifications_sent': notification_count
    }


@shared_task
def send_assignment_reminder_task(assignment_id: str, reminder_type: str = 'due_soon') -> dict:
    """
    Send reminder notifications for assignments.
    
    Args:
        assignment_id: UUID of the assignment
        reminder_type: Type of reminder (due_soon, overdue)
        
    Returns:
        Dict with notification statistics
    """
    from apps.assessment.models import Assignment
    
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        logger.error(f"Assignment {assignment_id} not found")
        return {'error': 'Assignment not found'}
    
    # Get enrolled users who haven't submitted
    from apps.enrollment.models import Enrollment
    enrolled_user_ids = Enrollment.objects.filter(
        course=assignment.course,
        status='active'
    ).values_list('user_id', flat=True)
    
    # TODO: Filter out users who have already submitted
    users = User.objects.filter(id__in=enrolled_user_ids)
    
    service = NotificationService()
    notification_count = 0
    
    if reminder_type == 'due_soon':
        title = f"Assignment Due Soon: {assignment.title}"
        message = f"Your assignment '{assignment.title}' is due in 24 hours."
    else:
        title = f"Assignment Overdue: {assignment.title}"
        message = f"Your assignment '{assignment.title}' is now overdue."
    
    for user in users:
        try:
            preference = getattr(user, 'notification_preferences', None)
            if preference and not preference.notify_on_assignments:
                continue
            
            service.send_notification(
                user=user,
                title=title,
                message=message,
                category=Notification.CATEGORY_ASSIGNMENT,
                priority='high' if reminder_type == 'overdue' else 'normal',
                data={
                    'assignment_id': str(assignment_id),
                    'course_id': str(assignment.course_id),
                    'reminder_type': reminder_type
                },
                action_url=f"/courses/{assignment.course.slug}/assignments/{assignment_id}"
            )
            notification_count += 1
            
        except Exception as exc:
            logger.error(f"Error sending assignment reminder to {user.email}: {str(exc)}")
    
    logger.info(f"Assignment reminder notifications sent: {notification_count}")
    
    return {
        'assignment_id': assignment_id,
        'reminder_type': reminder_type,
        'notifications_sent': notification_count
    }


@shared_task
def send_forum_reply_notification(post_id: str, reply_author_id: str) -> dict:
    """
    Send notification when someone replies to a forum post.
    
    Args:
        post_id: UUID of the parent post
        reply_author_id: UUID of the user who replied
        
    Returns:
        Dict with notification status
    """
    from apps.forum.models import DiscussionPost
    
    try:
        parent_post = DiscussionPost.objects.select_related('author', 'forum').get(id=post_id)
        reply_author = User.objects.get(id=reply_author_id)
    except (DiscussionPost.DoesNotExist, User.DoesNotExist):
        logger.error(f"Post {post_id} or user {reply_author_id} not found")
        return {'error': 'Post or user not found'}
    
    # Don't notify if author replies to their own post
    if parent_post.author_id == reply_author_id:
        return {'status': 'skipped', 'reason': 'self_reply'}
    
    # Check if author wants notifications
    preference = getattr(parent_post.author, 'notification_preferences', None)
    if preference and not preference.notify_on_forum_replies:
        return {'status': 'skipped', 'reason': 'preferences'}
    
    service = NotificationService()
    
    service.send_notification(
        user=parent_post.author,
        title=f"New Reply: {parent_post.title or 'Your Post'}",
        message=f"{reply_author.get_full_name()} replied to your post in {parent_post.forum.course.title}.",
        category=Notification.CATEGORY_FORUM,
        data={
            'post_id': str(post_id),
            'reply_author_id': str(reply_author_id),
            'forum_id': str(parent_post.forum_id)
        },
        action_url=f"/courses/{parent_post.forum.course.slug}/forum/posts/{post_id}"
    )
    
    logger.info(f"Forum reply notification sent to {parent_post.author.email}")
    
    return {'status': 'sent', 'recipient': parent_post.author.email}


@shared_task
def send_certificate_notification(certificate_id: str) -> dict:
    """
    Send notification when a certificate is issued.
    
    Args:
        certificate_id: UUID of the certificate
        
    Returns:
        Dict with notification status
    """
    from apps.certificates.models import Certificate
    
    try:
        certificate = Certificate.objects.select_related('user', 'course').get(id=certificate_id)
    except Certificate.DoesNotExist:
        logger.error(f"Certificate {certificate_id} not found")
        return {'error': 'Certificate not found'}
    
    # Check user preferences
    preference = getattr(certificate.user, 'notification_preferences', None)
    if preference and not preference.notify_on_certificates:
        return {'status': 'skipped', 'reason': 'preferences'}
    
    service = NotificationService()
    
    service.send_notification(
        user=certificate.user,
        title=f"Certificate Earned: {certificate.course.title}",
        message=f"Congratulations! You've earned a certificate for completing '{certificate.course.title}'.",
        category=Notification.CATEGORY_CERTIFICATE,
        priority='high',
        data={
            'certificate_id': str(certificate_id),
            'course_id': str(certificate.course_id)
        },
        action_url=f"/certificates/{certificate_id}"
    )
    
    logger.info(f"Certificate notification sent to {certificate.user.email}")
    
    return {'status': 'sent', 'recipient': certificate.user.email}


@shared_task
def send_enrollment_notification(enrollment_id: str, notification_type: str = 'enrolled') -> dict:
    """
    Send notification for enrollment events.
    
    Args:
        enrollment_id: UUID of the enrollment
        notification_type: Type of enrollment notification
        
    Returns:
        Dict with notification status
    """
    from apps.enrollment.models import Enrollment
    
    try:
        enrollment = Enrollment.objects.select_related('user', 'course').get(id=enrollment_id)
    except Enrollment.DoesNotExist:
        logger.error(f"Enrollment {enrollment_id} not found")
        return {'error': 'Enrollment not found'}
    
    # Check user preferences
    preference = getattr(enrollment.user, 'notification_preferences', None)
    if preference and not preference.notify_on_enrollments:
        return {'status': 'skipped', 'reason': 'preferences'}
    
    service = NotificationService()
    
    if notification_type == 'enrolled':
        title = f"Welcome to {enrollment.course.title}"
        message = f"You've successfully enrolled in '{enrollment.course.title}'. Start learning now!"
    elif notification_type == 'completed':
        title = f"Course Completed: {enrollment.course.title}"
        message = f"Congratulations! You've completed '{enrollment.course.title}'."
    else:
        title = f"Enrollment Update: {enrollment.course.title}"
        message = f"Your enrollment in '{enrollment.course.title}' has been updated."
    
    service.send_notification(
        user=enrollment.user,
        title=title,
        message=message,
        category=Notification.CATEGORY_ENROLLMENT,
        data={
            'enrollment_id': str(enrollment_id),
            'course_id': str(enrollment.course_id),
            'notification_type': notification_type
        },
        action_url=f"/courses/{enrollment.course.slug}"
    )
    
    logger.info(f"Enrollment notification sent to {enrollment.user.email}")
    
    return {'status': 'sent', 'recipient': enrollment.user.email}


@shared_task
def process_notification_queue_task(batch_size: int = 100) -> dict:
    """
    Process pending notifications in queue.
    
    Args:
        batch_size: Number of notifications to process per batch
        
    Returns:
        Dict with processing statistics
    """
    pending_notifications = Notification.objects.filter(
        status=Notification.STATUS_PENDING
    )[:batch_size]
    
    service = NotificationService()
    processed_count = 0
    error_count = 0
    
    for notification in pending_notifications:
        try:
            if notification.channel == Notification.CHANNEL_EMAIL:
                service._send_email_notification(notification)
            elif notification.channel == Notification.CHANNEL_IN_APP:
                service._send_in_app_notification(notification)
            elif notification.channel == Notification.CHANNEL_PUSH:
                service._send_push_notification(notification)
            
            processed_count += 1
            
        except Exception as exc:
            error_count += 1
            logger.error(f"Error processing notification {notification.id}: {str(exc)}")
    
    logger.info(f"Notification queue processed: {processed_count} succeeded, {error_count} failed")
    
    return {
        'processed_count': processed_count,
        'error_count': error_count
    }


@shared_task
def retry_stuck_notifications_task(max_age_minutes: int = 30) -> dict:
    """
    Retry notifications that have been stuck in PROCESSING status.
    
    Args:
        max_age_minutes: Age in minutes after which a processing notification is considered stuck
        
    Returns:
        Dict with retry statistics
    """
    cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
    
    stuck_notifications = Notification.objects.filter(
        status=Notification.STATUS_PROCESSING,
        updated_at__lt=cutoff_time
    )
    
    retry_count = 0
    error_count = 0
    
    for notification in stuck_notifications:
        try:
            notification.status = Notification.STATUS_PENDING
            notification.save(update_fields=['status', 'updated_at'])
            
            # Schedule immediate retry
            process_single_notification_task.delay(str(notification.id))
            retry_count += 1
            
        except Exception as exc:
            error_count += 1
            logger.error(f"Error retrying stuck notification {notification.id}: {str(exc)}")
    
    logger.info(f"Stuck notifications retry: {retry_count} queued, {error_count} errors")
    
    return {
        'retry_count': retry_count,
        'error_count': error_count
    }
