"""
Notification Services for Enterprise LMS
Provides NotificationService with idempotency check, exponential backoff calculation,
channel routing, Jinja2 template rendering, and comprehensive delivery tracking.
"""

import uuid
import random
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from django.db import transaction
from django.utils import timezone
from django.template import Template, Context
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.core.models import TimestampedModel
from .models import (
    Notification, NotificationDLQ, NotificationDeliveryLog,
    NotificationPreference, EmailTemplate
)

User = get_user_model()
logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Notification channel types."""
    EMAIL = 'email'
    IN_APP = 'in_app'
    PUSH = 'push'
    SMS = 'sms'


class DeliveryStatus(Enum):
    """Delivery status enumeration."""
    PENDING = 'pending'
    QUEUED = 'queued'
    SENT = 'sent'
    DELIVERED = 'delivered'
    FAILED = 'failed'
    BOUNCED = 'bounced'
    COMPLAINED = 'complained'
    DEFERRED = 'deferred'


@dataclass
class DeliveryResult:
    """Result of a delivery attempt."""
    success: bool
    status: str
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    provider: Optional[str] = None
    response_data: Optional[Dict] = None


class IdempotencyChecker:
    """
    Idempotency checker for notifications.
    Prevents duplicate notifications within a 24-hour window.
    """
    
    IDEMPOTENCY_WINDOW_HOURS = 24
    
    @classmethod
    def generate_key(cls, user_id: int, notification_type: str, 
                     category: str, title: str, data: Dict = None) -> str:
        """
        Generate an idempotency key for a notification.
        
        Args:
            user_id: The user ID
            notification_type: Type of notification
            category: Category of notification
            title: Notification title
            data: Additional data to include in key generation
            
        Returns:
            A unique idempotency key
        """
        key_data = f"{user_id}:{notification_type}:{category}:{title}"
        if data:
            # Sort data for consistent hashing
            sorted_data = sorted(data.items()) if isinstance(data, dict) else str(data)
            key_data += f":{sorted_data}"
        
        # Generate hash
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:32]
        return key_hash
    
    @classmethod
    def check_duplicate(cls, idempotency_key: str, user_id: int) -> Optional[Notification]:
        """
        Check if a notification with this idempotency key already exists.
        
        Args:
            idempotency_key: The idempotency key to check
            user_id: The user ID
            
        Returns:
            Existing notification if found, None otherwise
        """
        if not idempotency_key:
            return None
            
        cutoff_time = timezone.now() - timedelta(hours=cls.IDEMPOTENCY_WINDOW_HOURS)
        
        try:
            existing = Notification.objects.filter(
                user_id=user_id,
                idempotency_key=idempotency_key,
                created_at__gte=cutoff_time
            ).first()
            return existing
        except Exception as e:
            logger.error(f"Error checking idempotency: {e}")
            return None


class RetryCalculator:
    """
    Calculates retry delays with exponential backoff and jitter.
    """
    
    MAX_RETRIES = 5
    BASE_DELAY_SECONDS = 60  # 1 minute
    MAX_DELAY_SECONDS = 3600  # 1 hour
    JITTER_FACTOR = 0.5  # 50% jitter
    
    @classmethod
    def calculate_delay(cls, attempt_number: int) -> int:
        """
        Calculate the delay for the next retry attempt.
        
        Uses exponential backoff: delay = base_delay * 2^attempt
        With jitter: delay * random.uniform(0.5, 1.5)
        
        Args:
            attempt_number: The current attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        if attempt_number >= cls.MAX_RETRIES:
            return 0
        
        # Exponential backoff: 60s, 120s, 240s, 480s, 960s
        base_delay = cls.BASE_DELAY_SECONDS * (2 ** attempt_number)
        
        # Cap at max delay
        base_delay = min(base_delay, cls.MAX_DELAY_SECONDS)
        
        # Add jitter: random.uniform(0.5, 1.5)
        jitter = random.uniform(
            1 - cls.JITTER_FACTOR, 
            1 + cls.JITTER_FACTOR
        )
        
        delay = int(base_delay * jitter)
        return delay
    
    @classmethod
    def calculate_next_retry_time(cls, attempt_number: int) -> datetime:
        """
        Calculate the next retry timestamp.
        
        Args:
            attempt_number: The current attempt number
            
        Returns:
            Datetime for next retry
        """
        delay = cls.calculate_delay(attempt_number)
        return timezone.now() + timedelta(seconds=delay)
    
    @classmethod
    def should_retry(cls, attempt_number: int, status: str) -> bool:
        """
        Determine if a notification should be retried.
        
        Args:
            attempt_number: Current attempt number
            status: Current delivery status
            
        Returns:
            True if should retry, False otherwise
        """
        if attempt_number >= cls.MAX_RETRIES:
            return False
        
        # Only retry these statuses
        retryable_statuses = [
            Notification.STATUS_FAILED,
            Notification.STATUS_DEFERRED,
            Notification.STATUS_PENDING
        ]
        
        return status in retryable_statuses


class TemplateRenderer:
    """
    Jinja2 template renderer for email notifications.
    Supports HTML and text multipart generation.
    """
    
    @classmethod
    def render_email_template(cls, template_name: str, context: Dict) -> Tuple[str, str]:
        """
        Render email template with context.
        
        Args:
            template_name: Name of the template
            context: Template context variables
            
        Returns:
            Tuple of (html_content, text_content)
        """
        try:
            # Try to get template from database
            template_obj = EmailTemplate.objects.filter(
                name=template_name,
                is_active=True
            ).first()
            
            if template_obj:
                html_content = template_obj.render_html(context)
                text_content = template_obj.render_text(context)
            else:
                # Fallback to default templates
                html_content = cls._render_default_html(template_name, context)
                text_content = cls._render_default_text(template_name, context)
            
            return html_content, text_content
            
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            # Return simple fallback
            return cls._render_fallback(context)
    
    @classmethod
    def _render_default_html(cls, template_name: str, context: Dict) -> str:
        """Render default HTML template."""
        title = context.get('title', 'Notification')
        message = context.get('message', '')
        action_url = context.get('action_url', '')
        action_text = context.get('action_text', 'View Details')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1976d2; color: white; padding: 20px; text-align: center; }}
                .content {{ background: #f5f5f5; padding: 20px; margin: 20px 0; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #1976d2; 
                          color: white; text-decoration: none; border-radius: 4px; margin-top: 20px; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{title}</h1>
                </div>
                <div class="content">
                    <p>{message}</p>
                    {f'<a href="{action_url}" class="button">{action_text}</a>' if action_url else ''}
                </div>
                <div class="footer">
                    <p>This is an automated message from the LMS Platform.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    @classmethod
    def _render_default_text(cls, template_name: str, context: Dict) -> str:
        """Render default text template."""
        title = context.get('title', 'Notification')
        message = context.get('message', '')
        action_url = context.get('action_url', '')
        
        text = f"""{title}

{message}

{f"View details: {action_url}" if action_url else ""}

---
This is an automated message from the LMS Platform.
"""
        return text
    
    @classmethod
    def _render_fallback(cls, context: Dict) -> Tuple[str, str]:
        """Render fallback template when all else fails."""
        title = context.get('title', 'Notification')
        message = context.get('message', '')
        
        html = f"<html><body><h1>{title}</h1><p>{message}</p></body></html>"
        text = f"{title}\n\n{message}"
        
        return html, text


class NotificationService:
    """
    Main notification service with idempotency, retry logic, and delivery tracking.
    """
    
    def __init__(self):
        self.idempotency_checker = IdempotencyChecker()
        self.retry_calculator = RetryCalculator()
        self.template_renderer = TemplateRenderer()
    
    @transaction.atomic
    def create_notification(self, user_id: int, title: str, message: str,
                           channel: str = ChannelType.IN_APP.value,
                           category: str = Notification.CATEGORY_GENERAL,
                           priority: str = Notification.PRIORITY_NORMAL,
                           data: Dict = None,
                           action_url: str = '',
                           email_subject: str = '',
                           email_template: str = '',
                           scheduled_at: datetime = None,
                           idempotency_key: str = None) -> Tuple[Notification, bool]:
        """
        Create a notification with idempotency check.
        
        Args:
            user_id: Target user ID
            title: Notification title
            message: Notification message
            channel: Delivery channel
            category: Notification category
            priority: Priority level
            data: Additional data
            action_url: Action URL
            email_subject: Email subject (for email channel)
            email_template: Email template name
            scheduled_at: Scheduled delivery time
            idempotency_key: Optional idempotency key
            
        Returns:
            Tuple of (notification, created) where created is True if new
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = IdempotencyChecker.generate_key(
                user_id, channel, category, title, data
            )
        
        # Check for duplicates
        existing = IdempotencyChecker.check_duplicate(idempotency_key, user_id)
        if existing:
            logger.info(f"Duplicate notification detected: {idempotency_key}")
            return existing, False
        
        # Create notification
        notification = Notification.objects.create(
            user_id=user_id,
            channel=channel,
            notification_type=channel,  # Legacy field
            category=category,
            priority=priority,
            title=title,
            message=message,
            data=data or {},
            action_url=action_url,
            email_subject=email_subject or title,
            email_template=email_template,
            scheduled_at=scheduled_at,
            idempotency_key=idempotency_key,
            status=Notification.STATUS_PENDING
        )
        
        logger.info(f"Created notification {notification.id} for user {user_id}")
        return notification, True
    
    def send_notification(self, notification_id: int) -> DeliveryResult:
        """
        Send a notification through the appropriate channel.
        
        Args:
            notification_id: The notification ID
            
        Returns:
            DeliveryResult with status
        """
        try:
            notification = Notification.objects.select_related('user').get(id=notification_id)
        except Notification.DoesNotExist:
            return DeliveryResult(
                success=False,
                status=DeliveryStatus.FAILED.value,
                error_message=f"Notification {notification_id} not found"
            )
        
        # Record attempt
        notification.record_attempt()
        
        # Route to appropriate channel handler
        channel = notification.channel
        
        try:
            if channel == ChannelType.EMAIL.value:
                result = self._send_email(notification)
            elif channel == ChannelType.IN_APP.value:
                result = self._send_in_app(notification)
            elif channel == ChannelType.PUSH.value:
                result = self._send_push(notification)
            else:
                result = DeliveryResult(
                    success=False,
                    status=DeliveryStatus.FAILED.value,
                    error_message=f"Unknown channel: {channel}"
                )
            
            # Update notification status
            if result.success:
                if channel == ChannelType.EMAIL.value:
                    notification.mark_as_sent()
                    if result.message_id:
                        notification.provider_message_id = result.message_id
                        notification.provider = result.provider
                        notification.save(update_fields=['provider_message_id', 'provider'])
                else:
                    notification.mark_as_delivered()
            else:
                notification.mark_as_failed(result.error_message or 'Unknown error')
                
                # Check if should retry
                if RetryCalculator.should_retry(notification.delivery_attempts, notification.status):
                    self._schedule_retry(notification)
                else:
                    self._move_to_dlq(notification, result.error_message)
            
            # Log delivery attempt
            self._log_delivery_attempt(notification, result)
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Error sending notification {notification_id}: {error_msg}")
            
            notification.mark_as_failed(error_msg)
            
            # Check if should retry
            if RetryCalculator.should_retry(notification.delivery_attempts, notification.status):
                self._schedule_retry(notification)
            else:
                self._move_to_dlq(notification, error_msg)
            
            result = DeliveryResult(
                success=False,
                status=DeliveryStatus.FAILED.value,
                error_message=error_msg
            )
            
            self._log_delivery_attempt(notification, result)
            
            return result
    
    def _send_email(self, notification: Notification) -> DeliveryResult:
        """Send email notification."""
        try:
            user = notification.user
            
            # Check user preferences
            prefs = NotificationPreference.objects.filter(user=user).first()
            if prefs and not prefs.email_enabled:
                return DeliveryResult(
                    success=False,
                    status=DeliveryStatus.FAILED.value,
                    error_message="User has disabled email notifications"
                )
            
            # Prepare context
            context = {
                'title': notification.email_subject or notification.title,
                'message': notification.message,
                'user': user,
                'action_url': notification.action_url,
                'action_text': notification.data.get('action_text', 'View Details'),
                'notification': notification,
                **notification.data
            }
            
            # Render templates
            html_content, text_content = self.template_renderer.render_email_template(
                notification.email_template or 'default',
                context
            )
            
            # Send email
            subject = notification.email_subject or notification.title
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = user.email
            
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[to_email]
            )
            msg.attach_alternative(html_content, "text/html")
            
            # Send
            msg.send()
            
            return DeliveryResult(
                success=True,
                status=DeliveryStatus.SENT.value,
                provider='django_smtp',
                message_id=str(uuid.uuid4())
            )
            
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            return DeliveryResult(
                success=False,
                status=DeliveryStatus.FAILED.value,
                error_message=str(e)
            )
    
    def _send_in_app(self, notification: Notification) -> DeliveryResult:
        """Send in-app notification (mark as delivered)."""
        # In-app notifications are just created in the database
        # The frontend polls or uses WebSockets to fetch them
        return DeliveryResult(
            success=True,
            status=DeliveryStatus.DELIVERED.value,
            message_id=str(notification.id)
        )
    
    def _send_push(self, notification: Notification) -> DeliveryResult:
        """Send push notification."""
        # Placeholder for push notification implementation
        # Would integrate with Firebase Cloud Messaging, OneSignal, etc.
        logger.info(f"Push notification not implemented for {notification.id}")
        return DeliveryResult(
            success=False,
            status=DeliveryStatus.FAILED.value,
            error_message="Push notifications not implemented"
        )
    
    def _schedule_retry(self, notification: Notification):
        """Schedule a retry for a failed notification."""
        from .tasks import retry_notification_task
        
        delay = RetryCalculator.calculate_delay(notification.delivery_attempts)
        notification.scheduled_at = RetryCalculator.calculate_next_retry_time(
            notification.delivery_attempts - 1
        )
        notification.status = Notification.STATUS_PENDING
        notification.save(update_fields=['scheduled_at', 'status', 'updated_at'])
        
        # Schedule Celery task
        retry_notification_task.apply_async(
            args=[notification.id],
            countdown=delay
        )
        
        logger.info(f"Scheduled retry for notification {notification.id} in {delay}s")
    
    def _move_to_dlq(self, notification: Notification, error_message: str):
        """Move notification to Dead Letter Queue."""
        try:
            dlq_entry = NotificationDLQ.objects.create(
                original_notification=notification,
                user=notification.user,
                channel=notification.channel,
                title=notification.title,
                message=notification.message,
                payload={
                    'data': notification.data,
                    'action_url': notification.action_url,
                    'email_subject': notification.email_subject,
                    'email_template': notification.email_template,
                },
                attempt_count=notification.delivery_attempts,
                error_trace=error_message,
                idempotency_key=notification.idempotency_key,
                status=NotificationDLQ.STATUS_PENDING_REVIEW
            )
            
            logger.warning(f"Moved notification {notification.id} to DLQ: {dlq_entry.id}")
            
        except Exception as e:
            logger.error(f"Failed to move notification to DLQ: {e}")
    
    def _log_delivery_attempt(self, notification: Notification, result: DeliveryResult):
        """Log delivery attempt for audit tracking."""
        try:
            NotificationDeliveryLog.objects.create(
                notification=notification,
                user=notification.user,
                channel=notification.channel,
                attempt_number=notification.delivery_attempts,
                status=result.status,
                error_message=result.error_message or '',
                provider=result.provider or '',
                provider_message_id=result.message_id or '',
                webhook_response=result.response_data or {},
                delivered_at=timezone.now() if result.success else None
            )
        except Exception as e:
            logger.error(f"Failed to log delivery attempt: {e}")
    
    def retry_notification(self, notification_id: int) -> DeliveryResult:
        """
        Manually retry a notification.
        
        Args:
            notification_id: The notification ID
            
        Returns:
            DeliveryResult
        """
        try:
            notification = Notification.objects.get(id=notification_id)
            
            # Reset status
            notification.status = Notification.STATUS_PENDING
            notification.error_message = ''
            notification.save(update_fields=['status', 'error_message', 'updated_at'])
            
            # Send immediately
            return self.send_notification(notification_id)
            
        except Notification.DoesNotExist:
            return DeliveryResult(
                success=False,
                status=DeliveryStatus.FAILED.value,
                error_message=f"Notification {notification_id} not found"
            )
    
    def retry_dlq_entry(self, dlq_id: int) -> Tuple[bool, str]:
        """
        Retry a notification from the DLQ.
        
        Args:
            dlq_id: The DLQ entry ID
            
        Returns:
            Tuple of (success, message)
        """
        try:
            dlq_entry = NotificationDLQ.objects.get(id=dlq_id)
            
            if dlq_entry.status == NotificationDLQ.STATUS_RESOLVED:
                return False, "DLQ entry already resolved"
            
            # Create new notification
            payload = dlq_entry.payload
            notification, created = self.create_notification(
                user_id=dlq_entry.user_id,
                title=dlq_entry.title,
                message=dlq_entry.message,
                channel=dlq_entry.channel,
                data=payload.get('data', {}),
                action_url=payload.get('action_url', ''),
                email_subject=payload.get('email_subject', ''),
                email_template=payload.get('email_template', ''),
                idempotency_key=f"{dlq_entry.idempotency_key}:retry:{timezone.now().timestamp()}"
            )
            
            # Update DLQ entry
            dlq_entry.status = NotificationDLQ.STATUS_REQUEUED
            dlq_entry.save(update_fields=['status', 'updated_at'])
            
            # Send immediately
            result = self.send_notification(notification.id)
            
            if result.success:
                dlq_entry.status = NotificationDLQ.STATUS_RESOLVED
                dlq_entry.save(update_fields=['status', 'updated_at'])
                return True, f"Notification retried successfully: {notification.id}"
            else:
                return False, f"Retry failed: {result.error_message}"
                
        except NotificationDLQ.DoesNotExist:
            return False, f"DLQ entry {dlq_id} not found"
        except Exception as e:
            logger.exception(f"Error retrying DLQ entry: {e}")
            return False, str(e)
    
    def get_delivery_status(self, notification_id: int) -> Dict[str, Any]:
        """
        Get comprehensive delivery status for a notification.
        
        Args:
            notification_id: The notification ID
            
        Returns:
            Dictionary with status information
        """
        try:
            notification = Notification.objects.get(id=notification_id)
            
            # Get delivery logs
            logs = NotificationDeliveryLog.objects.filter(
                notification=notification
            ).order_by('-attempt_number')
            
            return {
                'notification_id': notification.id,
                'status': notification.status,
                'channel': notification.channel,
                'delivery_attempts': notification.delivery_attempts,
                'max_attempts': RetryCalculator.MAX_RETRIES,
                'created_at': notification.created_at,
                'sent_at': notification.sent_at,
                'delivered_at': notification.delivered_at,
                'last_attempt_at': notification.last_attempt_at,
                'scheduled_at': notification.scheduled_at,
                'error_message': notification.error_message,
                'provider': notification.provider,
                'provider_message_id': notification.provider_message_id,
                'attempt_history': [
                    {
                        'attempt_number': log.attempt_number,
                        'status': log.status,
                        'error_message': log.error_message,
                        'provider': log.provider,
                        'delivered_at': log.delivered_at,
                        'created_at': log.created_at
                    }
                    for log in logs
                ]
            }
            
        except Notification.DoesNotExist:
            return {'error': f"Notification {notification_id} not found"}
    
    def process_scheduled_notifications(self):
        """
        Process notifications scheduled for delivery.
        Called by periodic task.
        """
        now = timezone.now()
        
        pending = Notification.objects.filter(
            status=Notification.STATUS_PENDING,
            scheduled_at__lte=now
        ).exclude(
            scheduled_at__isnull=True
        )[:100]  # Process in batches
        
        count = 0
        for notification in pending:
            self.send_notification(notification.id)
            count += 1
        
        logger.info(f"Processed {count} scheduled notifications")
        return count
    
    def cleanup_old_notifications(self, days: int = 90):
        """
        Clean up old delivered/read notifications.
        
        Args:
            days: Age in days to keep
        """
        cutoff = timezone.now() - timedelta(days=days)
        
        # Delete old delivered/read notifications
        old_notifications = Notification.objects.filter(
            models.Q(status=Notification.STATUS_DELIVERED) |
            models.Q(status=Notification.STATUS_READ),
            updated_at__lt=cutoff
        )
        
        count = old_notifications.count()
        old_notifications.delete()
        
        logger.info(f"Cleaned up {count} old notifications")
        return count


# Convenience functions
def send_notification_to_user(user_id: int, title: str, message: str,
                               channel: str = 'in_app', **kwargs) -> Tuple[Notification, bool]:
    """
    Convenience function to send notification to a user.
    
    Args:
        user_id: Target user ID
        title: Notification title
        message: Notification message
        channel: Delivery channel
        **kwargs: Additional notification parameters
        
    Returns:
        Tuple of (notification, created)
    """
    service = NotificationService()
    return service.create_notification(
        user_id=user_id,
        title=title,
        message=message,
        channel=channel,
        **kwargs
    )


def send_bulk_notifications(user_ids: List[int], title: str, message: str,
                            channel: str = 'in_app', **kwargs) -> List[Notification]:
    """
    Send notifications to multiple users.
    
    Args:
        user_ids: List of user IDs
        title: Notification title
        message: Notification message
        channel: Delivery channel
        **kwargs: Additional notification parameters
        
    Returns:
        List of created notifications
    """
    service = NotificationService()
    notifications = []
    
    for user_id in user_ids:
        notification, _ = service.create_notification(
            user_id=user_id,
            title=title,
            message=message,
            channel=channel,
            **kwargs
        )
        notifications.append(notification)
    
    return notifications
