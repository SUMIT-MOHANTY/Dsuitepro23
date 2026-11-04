"""
Courses Signals for Enterprise LMS
Provides signal handlers for course-related events.
"""

import logging
from datetime import datetime

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

from .models import Course, Module, Lesson

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Course)
def course_pre_save(sender, instance, **kwargs):
    """
    Handle course pre-save operations.
    - Track status changes
    - Set published_at timestamp when course is published
    """
    if instance.pk:
        try:
            old_instance = Course.objects.get(pk=instance.pk)
            # Track status change to published
            if old_instance.status != 'published' and instance.status == 'published':
                instance.published_at = datetime.now()
                logger.info(f"Course {instance.title} is being published")
            # Track status change from published
            elif old_instance.status == 'published' and instance.status != 'published':
                instance.published_at = None
                logger.info(f"Course {instance.title} is being unpublished")
        except Course.DoesNotExist:
            pass
    else:
        # New course - set published_at if already published
        if instance.status == 'published':
            instance.published_at = datetime.now()


@receiver(post_save, sender=Course)
def course_post_save(sender, instance, created, **kwargs):
    """
    Handle course post-save operations.
    - Log creation and updates
    - Trigger thumbnail processing if needed
    """
    if created:
        logger.info(f"Course created: {instance.title} (ID: {instance.id})")
    else:
        logger.info(f"Course updated: {instance.title} (ID: {instance.id})")


@receiver(pre_save, sender=Module)
def module_pre_save(sender, instance, **kwargs):
    """
    Handle module pre-save operations.
    - Auto-assign order_index if not set
    """
    if not instance.pk and instance.order_index == 0:
        # Auto-assign order_index for new modules
        last_module = Module.objects.filter(course=instance.course).order_by('-order_index').first()
        instance.order_index = (last_module.order_index + 1) if last_module else 1


@receiver(post_save, sender=Module)
def module_post_save(sender, instance, created, **kwargs):
    """
    Handle module post-save operations.
    - Update course duration when module is saved
    """
    if created:
        logger.info(f"Module created: {instance.title} for course {instance.course.title}")
    
    # Update course duration
    instance.course.duration_minutes = sum(
        m.duration_minutes for m in instance.course.modules.all()
    )
    instance.course.save(update_fields=['duration_minutes', 'updated_at'])


@receiver(pre_save, sender=Lesson)
def lesson_pre_save(sender, instance, **kwargs):
    """
    Handle lesson pre-save operations.
    - Auto-assign order_index if not set
    """
    if not instance.pk and instance.order_index == 0:
        # Auto-assign order_index for new lessons
        last_lesson = Lesson.objects.filter(module=instance.module).order_by('-order_index').first()
        instance.order_index = (last_lesson.order_index + 1) if last_lesson else 1


@receiver(post_save, sender=Lesson)
def lesson_post_save(sender, instance, created, **kwargs):
    """
    Handle lesson post-save operations.
    - Update module and course duration when lesson is saved
    """
    if created:
        logger.info(f"Lesson created: {instance.title} in module {instance.module.title}")
    
    # Update module duration
    module = instance.module
    module.duration_minutes = sum(
        l.duration_minutes for l in module.lessons.all()
    )
    module.save(update_fields=['duration_minutes', 'updated_at'])
    
    # Update course duration
    course = module.course
    course.duration_minutes = sum(
        m.duration_minutes for m in course.modules.all()
    )
    course.save(update_fields=['duration_minutes', 'updated_at'])


@receiver(post_delete, sender=Module)
def module_post_delete(sender, instance, **kwargs):
    """
    Handle module deletion.
    - Update course duration
    - Reorder remaining modules
    """
    logger.info(f"Module deleted: {instance.title} from course {instance.course.title}")
    
    # Update course duration
    course = instance.course
    course.duration_minutes = sum(
        m.duration_minutes for m in course.modules.all()
    )
    course.save(update_fields=['duration_minutes', 'updated_at'])


@receiver(post_delete, sender=Lesson)
def lesson_post_delete(sender, instance, **kwargs):
    """
    Handle lesson deletion.
    - Update module and course duration
    """
    logger.info(f"Lesson deleted: {instance.title} from module {instance.module.title}")
    
    # Update module duration
    module = instance.module
    module.duration_minutes = sum(
        l.duration_minutes for l in module.lessons.all()
    )
    module.save(update_fields=['duration_minutes', 'updated_at'])
    
    # Update course duration
    course = module.course
    course.duration_minutes = sum(
        m.duration_minutes for m in course.modules.all()
    )
    course.save(update_fields=['duration_minutes', 'updated_at'])
