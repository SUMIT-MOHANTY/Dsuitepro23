"""
Enrollment Signals for Enterprise LMS
Provides signal handlers for enrollment events, progress tracking, and certificate triggers.
"""

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import (
    Enrollment, LearningPathEnrollment, LessonProgress,
    LearningPath, LearningPathItem
)

User = get_user_model()


@receiver(post_save, sender=Enrollment)
def enrollment_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for enrollment post-save events.
    Triggers confirmation emails and certificate generation.
    """
    if created:
        # Send enrollment confirmation notification
        _send_enrollment_confirmation(instance)
    
    # Check if enrollment was just completed
    if instance.status == Enrollment.STATUS_COMPLETED and instance.completed_at:
        # Trigger certificate generation
        _trigger_certificate_generation(instance)
        
        # Update learning path progress if applicable
        _update_learning_path_progress(instance)


@receiver(pre_save, sender=Enrollment)
def enrollment_pre_save(sender, instance, **kwargs):
    """
    Signal handler for enrollment pre-save events.
    Tracks status changes and updates timestamps.
    """
    if instance.pk:
        try:
            old_instance = Enrollment.objects.get(pk=instance.pk)
            
            # Track when enrollment becomes active
            if old_instance.status == Enrollment.STATUS_PENDING and instance.status == Enrollment.STATUS_ACTIVE:
                instance.enrolled_at = timezone.now()
            
            # Track completion
            if old_instance.status != Enrollment.STATUS_COMPLETED and instance.status == Enrollment.STATUS_COMPLETED:
                instance.completed_at = timezone.now()
                instance.progress_percentage = 100.00
                
        except Enrollment.DoesNotExist:
            pass


@receiver(post_save, sender=LessonProgress)
def lesson_progress_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for lesson progress updates.
    Recalculates course completion percentage.
    """
    # Update enrollment progress
    enrollment = instance.enrollment
    _recalculate_enrollment_progress(enrollment)


@receiver(post_save, sender=LearningPathEnrollment)
def learning_path_enrollment_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for learning path enrollment.
    Cascades enrollment to all courses in the path.
    """
    if created:
        # Cascade enroll to all courses in the path
        _cascade_learning_path_enrollment(instance)
        
        # Send learning path enrollment confirmation
        _send_learning_path_enrollment_confirmation(instance)


@receiver(pre_save, sender=LearningPathEnrollment)
def learning_path_enrollment_pre_save(sender, instance, **kwargs):
    """
    Signal handler for learning path enrollment pre-save.
    Tracks status changes and completion.
    """
    if instance.pk:
        try:
            old_instance = LearningPathEnrollment.objects.get(pk=instance.pk)
            
            # Track completion
            if old_instance.status != LearningPathEnrollment.STATUS_COMPLETED and \
               instance.status == LearningPathEnrollment.STATUS_COMPLETED:
                instance.completed_at = timezone.now()
                
        except LearningPathEnrollment.DoesNotExist:
            pass


@receiver(post_delete, sender=LearningPathItem)
def learning_path_item_post_delete(sender, instance, **kwargs):
    """
    Signal handler for learning path item deletion.
    Reorders remaining items in the path.
    """
    # Reorder remaining items
    _reorder_learning_path_items(instance.path)


def _send_enrollment_confirmation(enrollment):
    """
    Send enrollment confirmation notification to user.
    This is a placeholder - actual implementation would use the notification service.
    """
    # TODO: Integrate with notification service
    # from apps.notifications.services import NotificationService
    # NotificationService.send_enrollment_confirmation(enrollment.user, enrollment.course)
    pass


def _trigger_certificate_generation(enrollment):
    """
    Trigger certificate generation for completed enrollment.
    This is a placeholder - actual implementation would use the certificate service.
    """
    if not enrollment.certificate_issued:
        # TODO: Integrate with certificate service
        # from apps.certificates.services import CertificateService
        # CertificateService.generate_certificate(enrollment)
        enrollment.certificate_issued = True
        enrollment.certificate_issued_at = timezone.now()
        enrollment.save(update_fields=['certificate_issued', 'certificate_issued_at'])


def _update_learning_path_progress(enrollment):
    """
    Update learning path progress when a course is completed.
    """
    # Find all learning path enrollments for this user that include this course
    path_items = LearningPathItem.objects.filter(course=enrollment.course)
    
    for item in path_items:
        path_enrollments = LearningPathEnrollment.objects.filter(
            user=enrollment.user,
            learning_path=item.path
        )
        
        for path_enrollment in path_enrollments:
            path_enrollment.calculate_progress()


def _recalculate_enrollment_progress(enrollment):
    """
    Recalculate course completion percentage based on lesson progress.
    """
    from apps.courses.models import Lesson
    
    # Get all lessons in the course
    course_lessons = Lesson.objects.filter(
        module__course=enrollment.course,
        is_required=True,
        status='published'
    )
    
    if not course_lessons.exists():
        # If no required lessons, check all lessons
        course_lessons = Lesson.objects.filter(
            module__course=enrollment.course,
            status='published'
        )
    
    total_lessons = course_lessons.count()
    
    if total_lessons == 0:
        return
    
    # Count completed lessons
    completed_lessons = enrollment.lesson_progress.filter(
        status=LessonProgress.STATUS_COMPLETED
    ).count()
    
    # Calculate percentage
    percentage = (completed_lessons / total_lessons) * 100
    enrollment.progress_percentage = round(percentage, 2)
    
    # Check if course is complete
    if enrollment.progress_percentage >= 100:
        enrollment.mark_completed()
    else:
        enrollment.save(update_fields=['progress_percentage', 'updated_at'])


def _cascade_learning_path_enrollment(path_enrollment):
    """
    Cascade learning path enrollment to all courses in the path.
    """
    path = path_enrollment.learning_path
    user = path_enrollment.user
    
    # Get all courses in the path
    path_items = path.items.all()
    
    for item in path_items:
        # Create enrollment for each course
        Enrollment.objects.get_or_create(
            user=user,
            course=item.course,
            defaults={
                'status': Enrollment.STATUS_PENDING,
                'notes': f'Auto-enrolled via learning path: {path.title}'
            }
        )


def _send_learning_path_enrollment_confirmation(path_enrollment):
    """
    Send learning path enrollment confirmation notification.
    """
    # TODO: Integrate with notification service
    # from apps.notifications.services import NotificationService
    # NotificationService.send_learning_path_enrollment_confirmation(
    #     path_enrollment.user, 
    #     path_enrollment.learning_path
    # )
    pass


def _reorder_learning_path_items(path):
    """
    Reorder learning path items after deletion.
    """
    items = LearningPathItem.objects.filter(path=path).order_by('order_index')
    
    for index, item in enumerate(items, start=1):
        if item.order_index != index:
            item.order_index = index
            item.save(update_fields=['order_index'])


@receiver(post_save, sender=LearningPath)
def learning_path_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for learning path post-save events.
    Updates estimated duration when path is modified.
    """
    if not created:
        # Recalculate estimated duration based on courses
        _update_learning_path_duration(instance)


def _update_learning_path_duration(path):
    """
    Update learning path estimated duration based on course durations.
    """
    total_duration = 0
    
    for item in path.items.all():
        if item.course.duration_minutes:
            total_duration += item.course.duration_minutes
    
    # Convert to hours
    path.estimated_duration_hours = total_duration // 60
    path.save(update_fields=['estimated_duration_hours'])
