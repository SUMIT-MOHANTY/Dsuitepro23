"""
Enrollment Services for Enterprise LMS
Provides EnrollmentService with prerequisite validation, payment gating, and progress tracking.
"""

import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.users.models import User
from apps.courses.models import Course, Lesson, Module
from .models import (
    Enrollment, LearningPath, LearningPathItem, LearningPathEnrollment,
    LessonProgress, PrerequisiteCourse, EnrollmentNote
)

logger = logging.getLogger(__name__)


class CapacityExceededError(Exception):
    """Raised when course enrollment capacity is exceeded."""
    pass


class PrerequisiteNotMetError(Exception):
    """Raised when prerequisites are not met for enrollment."""
    pass


class PaymentRequiredError(Exception):
    """Raised when payment is required but not completed."""
    pass


class AlreadyEnrolledError(Exception):
    """Raised when user is already enrolled in the course."""
    pass


class EnrollmentNotActiveError(Exception):
    """Raised when enrollment is not active."""
    pass


class CapacityChecker:
    """Service for checking course enrollment capacity."""
    
    @staticmethod
    def check_capacity(course: Course) -> tuple[bool, int, Optional[int]]:
        """
        Check if course has available capacity.
        
        Args:
            course: Course to check capacity for
            
        Returns:
            Tuple of (has_capacity, current_count, max_enrollments)
        """
        current_count = Enrollment.objects.filter(
            course=course,
            status__in=[Enrollment.STATUS_PENDING, Enrollment.STATUS_ACTIVE]
        ).count()
        
        max_enrollments = course.max_enrollments
        
        if max_enrollments is None:
            return True, current_count, None
        
        has_capacity = current_count < max_enrollments
        return has_capacity, current_count, max_enrollments
    
    @staticmethod
    def get_remaining_slots(course: Course) -> Optional[int]:
        """
        Get remaining enrollment slots for a course.
        
        Args:
            course: Course to check
            
        Returns:
            Number of remaining slots, or None if unlimited
        """
        if course.max_enrollments is None:
            return None
        
        current_count = Enrollment.objects.filter(
            course=course,
            status__in=[Enrollment.STATUS_PENDING, Enrollment.STATUS_ACTIVE]
        ).count()
        
        return max(0, course.max_enrollments - current_count)


class PrerequisiteValidator:
    """Service for validating course prerequisites."""
    
    @staticmethod
    def get_prerequisites(course: Course) -> List[PrerequisiteCourse]:
        """Get all prerequisites for a course."""
        return list(course.prerequisites.select_related('prerequisite_course'))
    
    @staticmethod
    def validate_prerequisites(user: User, course: Course) -> tuple[bool, List[str]]:
        """
        Validate that user has met all prerequisites for a course.
        
        Args:
            user: User to validate
            course: Course to check prerequisites for
            
        Returns:
            Tuple of (is_valid, list of missing prerequisites)
        """
        prerequisites = PrerequisiteValidator.get_prerequisites(course)
        missing = []
        
        for prereq in prerequisites:
            prereq_course = prereq.prerequisite_course
            
            if prereq.is_strict:
                # Must be completed
                has_completed = Enrollment.objects.filter(
                    user=user,
                    course=prereq_course,
                    status=Enrollment.STATUS_COMPLETED
                ).exists()
                
                if not has_completed:
                    missing.append(f"Must complete '{prereq_course.title}'")
            else:
                # Just needs to be enrolled
                is_enrolled = Enrollment.objects.filter(
                    user=user,
                    course=prereq_course,
                    status__in=[Enrollment.STATUS_ACTIVE, Enrollment.STATUS_COMPLETED]
                ).exists()
                
                if not is_enrolled:
                    missing.append(f"Must be enrolled in '{prereq_course.title}'")
        
        return len(missing) == 0, missing
    
    @staticmethod
    def get_prerequisite_status(user: User, course: Course) -> Dict[str, Any]:
        """
        Get detailed prerequisite status for a user and course.
        
        Args:
            user: User to check
            course: Course to check prerequisites for
            
        Returns:
            Dictionary with prerequisite status details
        """
        prerequisites = PrerequisiteValidator.get_prerequisites(course)
        status_list = []
        
        for prereq in prerequisites:
            prereq_course = prereq.prerequisite_course
            
            enrollment = Enrollment.objects.filter(
                user=user,
                course=prereq_course
            ).first()
            
            status_list.append({
                'course_id': str(prereq_course.id),
                'course_title': prereq_course.title,
                'is_required': prereq.is_strict,
                'enrollment_status': enrollment.status if enrollment else None,
                'is_completed': enrollment.is_completed if enrollment else False,
                'is_met': (
                    enrollment and 
                    (enrollment.is_completed or (not prereq.is_strict and enrollment.is_active))
                )
            })
        
        all_met = all(s['is_met'] for s in status_list)
        
        return {
            'all_met': all_met,
            'prerequisites': status_list,
            'total_required': len([s for s in status_list if s['is_required']]),
            'completed_count': len([s for s in status_list if s['is_completed']])
        }


class PaymentGate:
    """Service for handling payment-related enrollment checks."""
    
    @staticmethod
    def is_payment_required(course: Course) -> bool:
        """Check if payment is required for a course."""
        return course.price > 0
    
    @staticmethod
    def get_payment_status(user: User, course: Course) -> Dict[str, Any]:
        """
        Get payment status for a user and course.
        
        Args:
            user: User to check
            course: Course to check payment for
            
        Returns:
            Dictionary with payment status details
        """
        is_required = PaymentGate.is_payment_required(course)
        
        # Check for existing enrollment (may be pending payment)
        enrollment = Enrollment.objects.filter(
            user=user,
            course=course
        ).first()
        
        return {
            'is_required': is_required,
            'amount': str(course.price) if is_required else '0.00',
            'currency': course.currency,
            'has_pending_enrollment': enrollment is not None and enrollment.status == Enrollment.STATUS_PENDING,
            'is_paid': enrollment is not None and enrollment.status != Enrollment.STATUS_PENDING if not is_required else False
        }
    
    @staticmethod
    def verify_payment(user: User, course: Course, payment_reference: Optional[str] = None) -> bool:
        """
        Verify that payment has been completed for a course.
        
        This is a placeholder for actual payment verification.
        In production, this would integrate with payment gateway.
        
        Args:
            user: User to verify payment for
            course: Course to verify payment for
            payment_reference: Optional payment reference/transaction ID
            
        Returns:
            True if payment is verified, False otherwise
        """
        # Free courses don't require payment
        if not PaymentGate.is_payment_required(course):
            return True
        
        # TODO: Integrate with actual payment gateway
        # For now, assume payment is verified if reference provided
        if payment_reference:
            logger.info(f"Payment verified for user {user.id} in course {course.id}: {payment_reference}")
            return True
        
        return False


class EnrollmentService:
    """Main service for enrollment operations."""
    
    @staticmethod
    def enroll_user(
        user: User,
        course: Course,
        payment_reference: Optional[str] = None,
        skip_payment: bool = False,
        created_by: Optional[User] = None,
        notes: Optional[str] = None
    ) -> Enrollment:
        """
        Enroll a user in a course with full validation.
        
        Args:
            user: User to enroll
            course: Course to enroll in
            payment_reference: Optional payment transaction reference
            skip_payment: If True, skip payment validation (for admin/manual enrollments)
            created_by: User who created this enrollment (for audit)
            notes: Optional notes for the enrollment
            
        Returns:
            Created Enrollment instance
            
        Raises:
            AlreadyEnrolledError: If user is already enrolled
            CapacityExceededError: If course is at capacity
            PrerequisiteNotMetError: If prerequisites not met
            PaymentRequiredError: If payment is required but not provided
        """
        with transaction.atomic():
            # Check for existing enrollment
            existing = Enrollment.objects.filter(user=user, course=course).first()
            if existing:
                if existing.status in [Enrollment.STATUS_ACTIVE, Enrollment.STATUS_COMPLETED]:
                    raise AlreadyEnrolledError(f"User is already enrolled in '{course.title}'")
                elif existing.status == Enrollment.STATUS_PENDING:
                    # Check if we can activate pending enrollment
                    if PaymentGate.is_payment_required(course) and not skip_payment:
                        if not PaymentGate.verify_payment(user, course, payment_reference):
                            raise PaymentRequiredError(f"Payment required for '{course.title}'")
                    
                    existing.activate()
                    logger.info(f"Activated pending enrollment for user {user.id} in course {course.id}")
                    return existing
                elif existing.status == Enrollment.STATUS_CANCELLED:
                    # Re-enroll
                    existing.delete()
                else:
                    raise AlreadyEnrolledError(f"User has an existing enrollment in '{course.title}' with status: {existing.status}")
            
            # Check capacity
            has_capacity, current_count, max_enrollments = CapacityChecker.check_capacity(course)
            if not has_capacity:
                raise CapacityExceededError(
                    f"Course '{course.title}' is at capacity ({current_count}/{max_enrollments})"
                )
            
            # Validate prerequisites
            prereqs_met, missing = PrerequisiteValidator.validate_prerequisites(user, course)
            if not prereqs_met:
                raise PrerequisiteNotMetError(
                    f"Prerequisites not met for '{course.title}': {', '.join(missing)}"
                )
            
            # Check payment
            is_paid = True
            if PaymentGate.is_payment_required(course) and not skip_payment:
                if not PaymentGate.verify_payment(user, course, payment_reference):
                    is_paid = False
            
            # Create enrollment
            enrollment = Enrollment.objects.create(
                user=user,
                course=course,
                status=Enrollment.STATUS_ACTIVE if is_paid else Enrollment.STATUS_PENDING,
                notes=notes or '',
                created_by=created_by
            )
            
            # Create enrollment note for audit
            if payment_reference:
                EnrollmentNote.objects.create(
                    enrollment=enrollment,
                    note_type=EnrollmentNote.NOTE_TYPE_PAYMENT,
                    content=f"Payment reference: {payment_reference}",
                    created_by=created_by,
                    is_internal=True
                )
            
            # Update course enrollment count
            course.enrollment_count = Enrollment.objects.filter(
                course=course,
                status__in=[Enrollment.STATUS_ACTIVE, Enrollment.STATUS_COMPLETED]
            ).count()
            course.save(update_fields=['enrollment_count'])
            
            logger.info(f"Created enrollment for user {user.id} in course {course.id} with status {enrollment.status}")
            
            return enrollment
    
    @staticmethod
    def unenroll_user(
        user: User,
        course: Course,
        reason: Optional[str] = None,
        cancelled_by: Optional[User] = None
    ) -> bool:
        """
        Unenroll a user from a course.
        
        Args:
            user: User to unenroll
            course: Course to unenroll from
            reason: Optional reason for unenrollment
            cancelled_by: User who performed the unenrollment
            
        Returns:
            True if successful
        """
        with transaction.atomic():
            enrollment = Enrollment.objects.filter(
                user=user,
                course=course,
                status__in=[Enrollment.STATUS_PENDING, Enrollment.STATUS_ACTIVE]
            ).first()
            
            if not enrollment:
                logger.warning(f"No active enrollment found for user {user.id} in course {course.id}")
                return False
            
            # Add note before cancellation
            if reason:
                EnrollmentNote.objects.create(
                    enrollment=enrollment,
                    note_type=EnrollmentNote.NOTE_TYPE_ADMIN,
                    content=f"Unenrolled: {reason}",
                    created_by=cancelled_by,
                    is_internal=True
                )
            
            enrollment.status = Enrollment.STATUS_CANCELLED
            enrollment.save(update_fields=['status', 'updated_at'])
            
            # Update course enrollment count
            course.enrollment_count = Enrollment.objects.filter(
                course=course,
                status__in=[Enrollment.STATUS_ACTIVE, Enrollment.STATUS_COMPLETED]
            ).count()
            course.save(update_fields=['enrollment_count'])
            
            logger.info(f"User {user.id} unenrolled from course {course.id}")
            return True
    
    @staticmethod
    def get_user_enrollments(
        user: User,
        status: Optional[str] = None,
        include_progress: bool = True
    ) -> List[Enrollment]:
        """
        Get all enrollments for a user.
        
        Args:
            user: User to get enrollments for
            status: Optional status filter
            include_progress: Whether to prefetch progress data
            
        Returns:
            List of Enrollment instances
        """
        queryset = Enrollment.objects.filter(user=user)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if include_progress:
            queryset = queryset.prefetch_related('lesson_progress', 'last_accessed_lesson')
        
        return list(queryset.select_related('course').order_by('-enrolled_at'))
    
    @staticmethod
    def get_course_enrollments(
        course: Course,
        status: Optional[str] = None
    ) -> List[Enrollment]:
        """
        Get all enrollments for a course.
        
        Args:
            course: Course to get enrollments for
            status: Optional status filter
            
        Returns:
            List of Enrollment instances
        """
        queryset = Enrollment.objects.filter(course=course)
        
        if status:
            queryset = queryset.filter(status=status)
        
        return list(queryset.select_related('user').order_by('-enrolled_at'))


class ProgressService:
    """Service for tracking and updating learning progress."""
    
    @staticmethod
    def get_or_create_lesson_progress(
        enrollment: Enrollment,
        lesson: Lesson
    ) -> LessonProgress:
        """
        Get or create a lesson progress record.
        
        Args:
            enrollment: Enrollment instance
            lesson: Lesson instance
            
        Returns:
            LessonProgress instance
        """
        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={
                'status': LessonProgress.STATUS_NOT_STARTED,
                'progress_percentage': Decimal('0.00')
            }
        )
        return progress
    
    @staticmethod
    def update_lesson_progress(
        enrollment: Enrollment,
        lesson: Lesson,
        progress_percentage: Optional[Decimal] = None,
        time_spent_minutes: Optional[int] = None,
        mark_completed: bool = False,
        mark_started: bool = False
    ) -> LessonProgress:
        """
        Update progress for a specific lesson.
        
        Args:
            enrollment: Enrollment instance
            lesson: Lesson to update progress for
            progress_percentage: Optional progress percentage (0-100)
            time_spent_minutes: Optional time spent on lesson
            mark_completed: If True, mark lesson as completed
            mark_started: If True, mark lesson as started
            
        Returns:
            Updated LessonProgress instance
            
        Raises:
            EnrollmentNotActiveError: If enrollment is not active
        """
        if not enrollment.is_active:
            raise EnrollmentNotActiveError("Cannot update progress for inactive enrollment")
        
        with transaction.atomic():
            progress = ProgressService.get_or_create_lesson_progress(enrollment, lesson)
            
            # Mark as started if requested or if first access
            if mark_started or progress.status == LessonProgress.STATUS_NOT_STARTED:
                progress.mark_started()
            
            # Update progress percentage
            if progress_percentage is not None:
                progress.progress_percentage = min(Decimal('100.00'), max(Decimal('0.00'), progress_percentage))
                progress.save(update_fields=['progress_percentage', 'updated_at'])
            
            # Update time spent
            if time_spent_minutes:
                progress.time_spent_minutes += time_spent_minutes
                progress.save(update_fields=['time_spent_minutes', 'updated_at'])
                
                # Update enrollment total time
                enrollment.total_time_spent_minutes += time_spent_minutes
                enrollment.save(update_fields=['total_time_spent_minutes', 'updated_at'])
            
            # Mark as completed
            if mark_completed:
                progress.mark_completed()
            
            # Recalculate course completion
            ProgressService.calculate_course_completion(enrollment)
            
            return progress
    
    @staticmethod
    def calculate_course_completion(enrollment: Enrollment) -> Decimal:
        """
        Calculate and update course completion percentage.
        
        Args:
            enrollment: Enrollment to calculate completion for
            
        Returns:
            Updated completion percentage
        """
        # Get all lessons in the course
        lessons = Lesson.objects.filter(
            module__course=enrollment.course,
            status='published',
            is_required=True
        )
        
        total_lessons = lessons.count()
        
        if total_lessons == 0:
            # No required lessons, consider complete if any progress
            enrollment.progress_percentage = Decimal('100.00')
            enrollment.save(update_fields=['progress_percentage', 'updated_at'])
            return enrollment.progress_percentage
        
        # Count completed lessons
        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            lesson__in=lessons,
            status=LessonProgress.STATUS_COMPLETED
        ).count()
        
        # Calculate percentage
        completion = (completed_lessons / total_lessons) * 100
        enrollment.progress_percentage = Decimal(str(round(completion, 2)))
        
        # Check if course is complete
        if enrollment.progress_percentage >= 100:
            enrollment.mark_completed()
        else:
            enrollment.save(update_fields=['progress_percentage', 'updated_at'])
        
        return enrollment.progress_percentage
    
    @staticmethod
    def get_lesson_progress_details(enrollment: Enrollment) -> Dict[str, Any]:
        """
        Get detailed progress information for all lessons in a course.
        
        Args:
            enrollment: Enrollment to get progress for
            
        Returns:
            Dictionary with progress details
        """
        lessons = Lesson.objects.filter(
            module__course=enrollment.course
        ).select_related('module').order_by('module__order_index', 'order_index')
        
        progress_list = []
        total_lessons = 0
        completed_lessons = 0
        in_progress_lessons = 0
        
        for lesson in lessons:
            total_lessons += 1
            progress = LessonProgress.objects.filter(
                enrollment=enrollment,
                lesson=lesson
            ).first()
            
            if progress:
                if progress.status == LessonProgress.STATUS_COMPLETED:
                    completed_lessons += 1
                elif progress.status == LessonProgress.STATUS_IN_PROGRESS:
                    in_progress_lessons += 1
            
            progress_list.append({
                'lesson_id': str(lesson.id),
                'lesson_title': lesson.title,
                'module_title': lesson.module.title,
                'status': progress.status if progress else LessonProgress.STATUS_NOT_STARTED,
                'progress_percentage': str(progress.progress_percentage) if progress else '0.00',
                'time_spent_minutes': progress.time_spent_minutes if progress else 0,
                'completed_at': progress.completed_at.isoformat() if progress and progress.completed_at else None
            })
        
        return {
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'in_progress_lessons': in_progress_lessons,
            'not_started_lessons': total_lessons - completed_lessons - in_progress_lessons,
            'overall_percentage': str(enrollment.progress_percentage),
            'lessons': progress_list
        }


class LearningPathService:
    """Service for learning path operations."""
    
    @staticmethod
    def enroll_in_learning_path(
        user: User,
        learning_path: LearningPath,
        payment_reference: Optional[str] = None,
        skip_payment: bool = False,
        created_by: Optional[User] = None
    ) -> LearningPathEnrollment:
        """
        Enroll a user in a learning path and cascade to all courses.
        
        Args:
            user: User to enroll
            learning_path: Learning path to enroll in
            payment_reference: Optional payment reference
            skip_payment: If True, skip payment validation
            created_by: User who created this enrollment
            
        Returns:
            Created LearningPathEnrollment instance
        """
        with transaction.atomic():
            # Check for existing enrollment
            existing = LearningPathEnrollment.objects.filter(
                user=user,
                learning_path=learning_path
            ).first()
            
            if existing and existing.status in [
                LearningPathEnrollment.STATUS_ACTIVE,
                LearningPathEnrollment.STATUS_COMPLETED
            ]:
                raise AlreadyEnrolledError(f"User is already enrolled in '{learning_path.title}'")
            
            # Create learning path enrollment
            path_enrollment = LearningPathEnrollment.objects.create(
                user=user,
                learning_path=learning_path,
                status=LearningPathEnrollment.STATUS_ACTIVE,
                created_by=created_by
            )
            
            # Enroll in all courses in the path
            path_items = learning_path.items.select_related('course').all()
            enrolled_courses = []
            failed_courses = []
            
            for item in path_items:
                try:
                    enrollment = EnrollmentService.enroll_user(
                        user=user,
                        course=item.course,
                        payment_reference=payment_reference if not item.is_required else None,
                        skip_payment=skip_payment or not item.is_required,
                        created_by=created_by,
                        notes=f"Enrolled via learning path: {learning_path.title}"
                    )
                    enrolled_courses.append({
                        'course_id': str(item.course.id),
                        'course_title': item.course.title,
                        'enrollment_id': str(enrollment.id),
                        'is_required': item.is_required
                    })
                except Exception as e:
                    failed_courses.append({
                        'course_id': str(item.course.id),
                        'course_title': item.course.title,
                        'error': str(e),
                        'is_required': item.is_required
                    })
            
            # Store enrollment details in metadata
            path_enrollment.metadata = {
                'enrolled_courses': enrolled_courses,
                'failed_courses': failed_courses
            }
            path_enrollment.save(update_fields=['metadata'])
            
            logger.info(
                f"User {user.id} enrolled in learning path {learning_path.id}. "
                f"Enrolled: {len(enrolled_courses)}, Failed: {len(failed_courses)}"
            )
            
            return path_enrollment
    
    @staticmethod
    def update_learning_path_progress(path_enrollment: LearningPathEnrollment) -> Decimal:
        """
        Update progress for a learning path enrollment.
        
        Args:
            path_enrollment: LearningPathEnrollment to update
            
        Returns:
            Updated progress percentage
        """
        return path_enrollment.calculate_progress()
    
    @staticmethod
    def get_learning_path_progress(
        user: User,
        learning_path: LearningPath
    ) -> Dict[str, Any]:
        """
        Get detailed progress for a user in a learning path.
        
        Args:
            user: User to get progress for
            learning_path: Learning path to check
            
        Returns:
            Dictionary with progress details
        """
        path_enrollment = LearningPathEnrollment.objects.filter(
            user=user,
            learning_path=learning_path
        ).first()
        
        if not path_enrollment:
            return {
                'is_enrolled': False,
                'progress_percentage': '0.00',
                'status': None
            }
        
        # Get progress for each course in the path
        path_items = learning_path.items.select_related('course').all()
        course_progress = []
        
        for item in path_items:
            enrollment = Enrollment.objects.filter(
                user=user,
                course=item.course
            ).first()
            
            course_progress.append({
                'course_id': str(item.course.id),
                'course_title': item.course.title,
                'order_index': item.order_index,
                'is_required': item.is_required,
                'enrollment_status': enrollment.status if enrollment else None,
                'progress_percentage': str(enrollment.progress_percentage) if enrollment else '0.00',
                'is_completed': enrollment.is_completed if enrollment else False
            })
        
        return {
            'is_enrolled': True,
            'enrollment_id': str(path_enrollment.id),
            'status': path_enrollment.status,
            'progress_percentage': str(path_enrollment.progress_percentage),
            'enrolled_at': path_enrollment.enrolled_at.isoformat(),
            'completed_at': path_enrollment.completed_at.isoformat() if path_enrollment.completed_at else None,
            'courses': course_progress
        }
    
    @staticmethod
    def get_available_learning_paths(user: User) -> List[LearningPath]:
        """
        Get learning paths available for enrollment.
        
        Args:
            user: User to get paths for
            
        Returns:
            List of available LearningPath instances
        """
        enrolled_path_ids = LearningPathEnrollment.objects.filter(
            user=user,
            status__in=[
                LearningPathEnrollment.STATUS_ACTIVE,
                LearningPathEnrollment.STATUS_PENDING
            ]
        ).values_list('learning_path_id', flat=True)
        
        return list(LearningPath.objects.filter(
            status=LearningPath.STATUS_PUBLISHED
        ).exclude(
            id__in=enrolled_path_ids
        ).select_related('created_by'))
