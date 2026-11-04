"""
Django Signals for Users App
Handles post-save and pre-delete operations for users.
"""

import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models import User, UserSession

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for User model.
    - Send welcome email for new users
    - Log user creation/updates
    """
    if created:
        logger.info(f"New user created: {instance.email}")
        # Welcome email would be sent here via Celery task
        # from apps.notifications.tasks import send_welcome_email
        # send_welcome_email.delay(instance.id)


@receiver(pre_delete, sender=User)
def user_pre_delete(sender, instance, **kwargs):
    """
    Handle pre-delete operations for User model.
    - Clean up user sessions before deletion
    - Log deletion for audit purposes
    """
    logger.info(f"User being deleted: {instance.email}")
    
    # Revoke all active sessions
    UserSession.objects.filter(
        user=instance,
        is_revoked=False
    ).update(is_revoked=True)


@receiver(post_save, sender=UserSession)
def session_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for UserSession model.
    - Log new session creation
    """
    if created:
        logger.info(f"New session created for user: {instance.user.email}")
