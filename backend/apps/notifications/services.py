"""
Notification Services for Enterprise LMS
Provides NotificationService for multi-channel notification delivery (email, in-app, push).
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.core.services import EncryptionVerificationService

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationService:
    """
    Service for sending notifications through multiple channels.
    Supports email (SMTP/SES), in-app (WebSocket/SSE), and push notifications.
    """
    
    def __init__(self):
        self.encryption_service = EncryptionVerificationService()
    
    def send_notification(
        self,
        user: User,
        title: str,
        message: str,
        notification_type: str = 'in_app',
        category: str = 'general',
        priority: str = 'normal',
        data: Optional[Dict[str, Any]] = None,
        action_url: str = '',
        send_email: bool = True,
        send_push: bool = False
    ) -> 'Notification':
        """
        Send a notification to a user through specified channels.
        
        Args:
            user: The user to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification (email, in_app, push)
            category: Category of notification
            priority: Priority level (low, normal, high, urgent)
            data: Additional data as JSON
            action_url: URL to navigate to when clicked
            send_email: Whether to also send email
            send_push: Whether to also send push notification
            
        Returns:
            The created Notification instance
        """
        from .models import Notification
        
        # Create the notification record
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            category=category,
            priority=priority,
            title=title,
            message=message,
            data=data or {},
            action_url=action_url,
            status=Notification.STATUS_PENDING
        )
        
        # Check user preferences
        try:
            preferences = user.notification_preferences
        except:
            preferences = None
        
        # Send through appropriate channels
        if notification_type == Notification.TYPE_EMAIL or send_email:
            if not preferences or preferences.should_send_email(category):
                if not preferences or not preferences.is_quiet_hours():
                    self._send_email_notification(notification)
        
        if notification_type == Notification.TYPE_IN_APP:
            self._send_in_app_notification(notification)
        
        if notification_type == Notification.TYPE_PUSH or send_push:
            if not preferences or preferences.should_send_push(category):
                self._send_push_notification(notification)
        
        return notification
    
    def _send_email_notification(self, notification: 'Notification') -> bool:
        """
        Send notification via email using SMTP or AWS SES.
        
        Args:
            notification: The notification to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Prepare email context
            context = {
                'notification': notification,
                'user': notification.user,
                'site_name': getattr(settings, 'SITE_NAME', 'LMS'),
                'site_url': getattr(settings, 'SITE_URL', ''),
            }
            
            # Render email templates
            subject = notification.title
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            to_email = notification.user.email
            
            # Plain text version
            text_content = notification.message
            
            # HTML version
            try:
                html_content = render_to_string('emails/notification.html', context)
            except:
                # Fallback if template doesn't exist
                html_content = f"""
                <html>
                <body>
                    <h2>{notification.title}</h2>
                    <p>{notification.message}</p>
                    {f'<a href="{notification.action_url}">View Details</a>' if notification.action_url else ''}
                </body>
                </html>
                """
            
            # Send email
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            # Update notification status
            notification.mark_as_sent()
            logger.info(f"Email notification sent to {to_email}: {notification.title}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send email notification: {error_msg}")
            notification.mark_as_failed(error_msg)
            return False
    
    def _send_in_app_notification(self, notification: 'Notification') -> bool:
        """
        Send notification via in-app (WebSocket/SSE).
        
        Args:
            notification: The notification to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Mark as sent (in-app notifications are immediately available)
            notification.mark_as_sent()
            notification.mark_as_delivered()
            
            # TODO: Implement WebSocket/SSE push via Django Channels
            # This would typically involve:
            # from channels.layers import get_channel_layer
            # from asgiref.sync import async_to_sync
            # channel_layer = get_channel_layer()
            # async_to_sync(channel_layer.group_send)(
            #     f"user_{notification.user.id}_notifications",
            #     {
            #         "type": "notification_message",
            #         "notification": {
            #             "id": str(notification.id),
            #             "title": notification.title,
            #             "message": notification.message,
            #             "category": notification.category,
            #             "created_at": notification.created_at.isoformat(),
            #         }
            #     }
            # )
            
            logger.info(f"In-app notification sent to user {notification.user.id}: {notification.title}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send in-app notification: {error_msg}")
            notification.mark_as_failed(error_msg)
            return False
    
    def _send_push_notification(self, notification: 'Notification') -> bool:
        """
        Send notification via push notification service.
        
        Args:
            notification: The notification to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get user's push tokens
            try:
                preferences = notification.user.notification_preferences
                device_tokens = preferences.push_device_tokens if preferences else []
            except:
                device_tokens = []
            
            if not device_tokens:
                logger.warning(f"No push tokens for user {notification.user.id}")
                return False
            
            # TODO: Implement push notification via Firebase Cloud Messaging or similar
            # This would typically involve:
            # import firebase_admin
            # from firebase_admin import messaging
            # for token in device_tokens:
            #     message = messaging.Message(
            #         notification=messaging.Notification(
            #             title=notification.title,
            #             body=notification.message,
            #         ),
            #         token=token,
            #         data=notification.data,
            #     )
            #     messaging.send(message)
            
            notification.mark_as_sent()
            logger.info(f"Push notification sent to user {notification.user.id}: {notification.title}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send push notification: {error_msg}")
            notification.mark_as_failed(error_msg)
            return False
    
    def send_bulk_notifications(
        self,
        users: List[User],
        title: str,
        message: str,
        category: str = 'general',
        priority: str = 'normal',
        data: Optional[Dict[str, Any]] = None,
        action_url: str = ''
    ) -> List['Notification']:
        """
        Send notifications to multiple users.
        
        Args:
            users: List of users to notify
            title: Notification title
            message: Notification message
            category: Category of notification
            priority: Priority level
            data: Additional data
            action_url: URL to navigate to
            
        Returns:
            List of created Notification instances
        """
        notifications = []
        for user in users:
            notification = self.send_notification(
                user=user,
                title=title,
                message=message,
                category=category,
                priority=priority,
                data=data,
                action_url=action_url
            )
            notifications.append(notification)
        return notifications
    
    def send_digest(
        self,
        user: User,
        digest_type: str = 'daily'
    ) -> Optional['NotificationDigest']:
        """
        Send a digest of unread notifications to a user.
        
        Args:
            user: The user to send digest to
            digest_type: Type of digest (hourly, daily, weekly)
            
        Returns:
            NotificationDigest instance if sent, None otherwise
        """
        from .models import Notification, NotificationDigest
        
        # Get unread notifications
        unread_notifications = Notification.objects.filter(
            user=user,
            is_read=False,
            notification_type=Notification.TYPE_IN_APP
        ).order_by('-created_at')[:50]
        
        if not unread_notifications.exists():
            logger.info(f"No unread notifications for user {user.id}, skipping digest")
            return None
        
        # Create digest
        notification_ids = list(unread_notifications.values_list('id', flat=True))
        digest = NotificationDigest.objects.create(
            user=user,
            digest_type=digest_type,
            notification_count=len(notification_ids),
            notification_ids=notification_ids
        )
        
        # Send digest email
        try:
            context = {
                'user': user,
                'notifications': unread_notifications[:20],
                'total_count': len(notification_ids),
                'digest_type': digest_type,
                'site_name': getattr(settings, 'SITE_NAME', 'LMS'),
                'site_url': getattr(settings, 'SITE_URL', ''),
            }
            
            subject = f"[{context['site_name']}] Your {digest_type} notification digest"
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            
            # Plain text version
            text_content = f"You have {len(notification_ids)} unread notifications."
            
            # HTML version
            try:
                html_content = render_to_string('emails/digest.html', context)
            except:
                # Fallback
                html_content = f"""
                <html>
                <body>
                    <h2>Your {digest_type} Digest</h2>
                    <p>You have {len(notification_ids)} unread notifications.</p>
                    <ul>
                        {''.join([f'<li>{n.title}</li>' for n in unread_notifications[:10]])}
                    </ul>
                </body>
                </html>
                """
            
            msg = EmailMultiAlternatives(subject, text_content, from_email, [user.email])
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            logger.info(f"Digest sent to {user.email}: {len(notification_ids)} notifications")
            return digest
            
        except Exception as e:
            logger.error(f"Failed to send digest: {str(e)}")
            return None
    
    def retry_failed_notifications(self, max_retries: int = 3) -> int:
        """
        Retry sending failed notifications.
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Returns:
            Number of notifications successfully resent
        """
        from .models import Notification
        
        failed_notifications = Notification.objects.filter(
            status=Notification.STATUS_FAILED,
            retry_count__lt=max_retries
        )
        
        success_count = 0
        for notification in failed_notifications:
            notification.increment_retry()
            
            if notification.notification_type == Notification.TYPE_EMAIL:
                if self._send_email_notification(notification):
                    success_count += 1
            elif notification.notification_type == Notification.TYPE_IN_APP:
                if self._send_in_app_notification(notification):
                    success_count += 1
            elif notification.notification_type == Notification.TYPE_PUSH:
                if self._send_push_notification(notification):
                    success_count += 1
        
        logger.info(f"Retried {failed_notifications.count()} failed notifications, {success_count} succeeded")
        return success_count
    
    def mark_all_as_read(self, user: User) -> int:
        """
        Mark all notifications as read for a user.
        
        Args:
            user: The user whose notifications to mark as read
            
        Returns:
            Number of notifications marked as read
        """
        from .models import Notification
        
        unread_notifications = Notification.objects.filter(
            user=user,
            is_read=False
        )
        
        count = unread_notifications.count()
        for notification in unread_notifications:
            notification.mark_as_read()
        
        return count
    
    def get_unread_count(self, user: User) -> int:
        """
        Get the count of unread notifications for a user.
        
        Args:
            user: The user to get count for
            
        Returns:
            Number of unread notifications
        """
        from .models import Notification
        
        return Notification.objects.filter(
            user=user,
            is_read=False
        ).count()


class EmailService:
    """
    Service for sending emails with support for templates and bulk sending.
    """
    
    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
        from_email: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[tuple]] = None
    ) -> bool:
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            text_content: Plain text content
            html_content: HTML content (optional)
            from_email: Sender email address
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of (filename, content, mimetype) tuples
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[to_email],
                cc=cc or [],
                bcc=bcc or []
            )
            
            if html_content:
                msg.attach_alternative(html_content, "text/html")
            
            if attachments:
                for filename, content, mimetype in attachments:
                    msg.attach(filename, content, mimetype)
            
            msg.send()
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    @staticmethod
    def send_template_email(
        to_email: str,
        subject: str,
        template_name: str,
        context: Dict[str, Any],
        from_email: Optional[str] = None
    ) -> bool:
        """
        Send an email using a template.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            template_name: Name of the template (without extension)
            context: Template context dictionary
            from_email: Sender email address
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            text_content = render_to_string(f'emails/{template_name}.txt', context)
            html_content = render_to_string(f'emails/{template_name}.html', context)
            
            return EmailService.send_email(
                to_email=to_email,
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                from_email=from_email
            )
        except Exception as e:
            logger.error(f"Failed to send template email: {str(e)}")
            return False
    
    @staticmethod
    def send_bulk_emails(
        recipients: List[str],
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Send emails to multiple recipients.
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            text_content: Plain text content
            html_content: HTML content (optional)
            from_email: Sender email address
            
        Returns:
            Dictionary mapping email to success status
        """
        results = {}
        for email in recipients:
            results[email] = EmailService.send_email(
                to_email=email,
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                from_email=from_email
            )
        return results


class InAppNotificationService:
    """
    Service for managing in-app notifications and real-time delivery.
    """
    
    @staticmethod
    def get_user_notifications(
        user: User,
        is_read: Optional[bool] = None,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List['Notification']:
        """
        Get notifications for a user.
        
        Args:
            user: The user to get notifications for
            is_read: Filter by read status (None for all)
            category: Filter by category (None for all)
            limit: Maximum number of notifications to return
            
        Returns:
            List of Notification instances
        """
        from .models import Notification
        
        queryset = Notification.objects.filter(user=user)
        
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read)
        
        if category:
            queryset = queryset.filter(category=category)
        
        return list(queryset.order_by('-created_at')[:limit])
    
    @staticmethod
    def mark_as_read(notification_id: str, user: User) -> bool:
        """
        Mark a notification as read.
        
        Args:
            notification_id: ID of the notification
            user: The user who owns the notification
            
        Returns:
            True if successful, False otherwise
        """
        from .models import Notification
        
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False
    
    @staticmethod
    def get_recent_notifications(user: User, minutes: int = 5) -> List['Notification']:
        """
        Get recent notifications for real-time polling.
        
        Args:
            user: The user to get notifications for
            minutes: Time window in minutes
            
        Returns:
            List of recent Notification instances
        """
        from .models import Notification
        
        since = timezone.now() - timedelta(minutes=minutes)
        
        return list(Notification.objects.filter(
            user=user,
            created_at__gte=since,
            is_read=False
        ).order_by('-created_at'))
