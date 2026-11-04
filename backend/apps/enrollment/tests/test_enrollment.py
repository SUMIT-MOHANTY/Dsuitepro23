"""
Enrollment Tests for Enterprise LMS
Tests enrollment service, progress tracking, and learning path APIs.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.courses.models import Course, Module, Lesson
from apps.users.models import Role
from apps.enrollment.models import (
    Enrollment, LearningPath, LearningPathItem, LearningPathEnrollment,
    LessonProgress, PrerequisiteCourse, EnrollmentNote
)
from apps.enrollment.services import (
    EnrollmentService, CapacityExceededError, PrerequisiteNotMetError,
    PaymentRequiredError, AlreadyEnrolledError, EnrollmentNotActiveError,
    CapacityChecker, PrerequisiteValidator, PaymentGate
)

User = get_user_model()


class EnrollmentModelTests(TestCase):
    """Tests for Enrollment model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            status='published',
            price=0
        )
        self.enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
    
    def test_enrollment_creation(self):
        """Test enrollment creation."""
        self.assertEqual(self.enrollment.user, self.user)
        self.assertEqual(self.enrollment.course, self.course)
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_ACTIVE)
        self.assertEqual(self.enrollment.progress_percentage, Decimal('0.00'))
    
    def test_enrollment_str(self):
        """Test enrollment string representation."""
        self.assertEqual(str(self.enrollment), f"{self.user.email} - {self.course.title}")
    
    def test_is_active_property(self):
        """Test is_active property."""
        self.assertTrue(self.enrollment.is_active)
        self.enrollment.status = Enrollment.STATUS_PENDING
        self.assertFalse(self.enrollment.is_active)
    
    def test_is_completed_property(self):
        """Test is_completed property."""
        self.assertFalse(self.enrollment.is_completed)
        self.enrollment.mark_completed()
        self.assertTrue(self.enrollment.is_completed)
    
    def test_mark_completed(self):
        """Test marking enrollment as completed."""
        self.enrollment.mark_completed()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_COMPLETED)
        self.assertIsNotNone(self.enrollment.completed_at)
        self.assertEqual(self.enrollment.progress_percentage, Decimal('100.00'))
    
    def test_activate(self):
        """Test activating a pending enrollment."""
        pending_enrollment = Enrollment.objects.create(
            user=User.objects.create_user(email='pending@example.com', username='pendinguser', password='testpass123'),
            course=Course.objects.create(title='Pending Course', slug='pending-course', status='published'),
            status=Enrollment.STATUS_PENDING
        )
        pending_enrollment.activate()
        self.assertEqual(pending_enrollment.status, Enrollment.STATUS_ACTIVE)
    
    def test_update_progress(self):
        """Test updating progress percentage."""
        self.enrollment.update_progress(50.00)
        self.assertEqual(self.enrollment.progress_percentage, Decimal('50.00'))
        
        # Test completion at 100%
        self.enrollment.update_progress(100.00)
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_COMPLETED)
    
    def test_unique_together_constraint(self):
        """Test that user can only have one enrollment per course."""
        with self.assertRaises(Exception):
            Enrollment.objects.create(
                user=self.user,
                course=self.course,
                status=Enrollment.STATUS_ACTIVE
            )


class LearningPathModelTests(TestCase):
    """Tests for LearningPath model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='path@example.com',
            username='pathuser',
            password='testpass123'
        )
        self.learning_path = LearningPath.objects.create(
            title='Test Learning Path',
            slug='test-learning-path',
            description='A test learning path',
            category=LearningPath.CATEGORY_TECHNOLOGY,
            created_by=self.user,
            status=LearningPath.STATUS_PUBLISHED
        )
        self.course1 = Course.objects.create(
            title='Course 1',
            slug='course-1',
            status='published'
        )
        self.course2 = Course.objects.create(
            title='Course 2',
            slug='course-2',
            status='published'
        )
    
    def test_learning_path_creation(self):
        """Test learning path creation."""
        self.assertEqual(self.learning_path.title, 'Test Learning Path')
        self.assertEqual(self.learning_path.status, LearningPath.STATUS_PUBLISHED)
        self.assertTrue(self.learning_path.is_published)
    
    def test_course_count_property(self):
        """Test course_count property."""
        self.assertEqual(self.learning_path.course_count, 0)
        
        LearningPathItem.objects.create(
            path=self.learning_path,
            course=self.course1,
            order_index=1
        )
        self.assertEqual(self.learning_path.course_count, 1)
    
    def test_required_course_count_property(self):
        """Test required_course_count property."""
        LearningPathItem.objects.create(
            path=self.learning_path,
            course=self.course1,
            order_index=1,
            is_required=True
        )
        LearningPathItem.objects.create(
            path=self.learning_path,
            course=self.course2,
            order_index=2,
            is_required=False
        )
        self.assertEqual(self.learning_path.required_course_count, 1)


class LearningPathItemModelTests(TestCase):
    """Tests for LearningPathItem model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='item@example.com',
            username='itemuser',
            password='testpass123'
        )
        self.learning_path = LearningPath.objects.create(
            title='Test Path',
            slug='test-path',
            created_by=self.user,
            status=LearningPath.STATUS_PUBLISHED
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course-item',
            status='published'
        )
    
    def test_auto_order_index(self):
        """Test that order_index is auto-assigned."""
        item1 = LearningPathItem.objects.create(
            path=self.learning_path,
            course=self.course
        )
        self.assertEqual(item1.order_index, 1)
        
        course2 = Course.objects.create(title='Course 2', slug='course-2-item', status='published')
        item2 = LearningPathItem.objects.create(
            path=self.learning_path,
            course=course2
        )
        self.assertEqual(item2.order_index, 2)


class LearningPathEnrollmentModelTests(TestCase):
    """Tests for LearningPathEnrollment model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='lpenroll@example.com',
            username='lpenrolluser',
            password='testpass123'
        )
        self.learning_path = LearningPath.objects.create(
            title='Test Path',
            slug='test-path-enroll',
            status=LearningPath.STATUS_PUBLISHED
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course-lp',
            status='published'
        )
        LearningPathItem.objects.create(
            path=self.learning_path,
            course=self.course,
            order_index=1,
            is_required=True
        )
        self.lp_enrollment = LearningPathEnrollment.objects.create(
            user=self.user,
            learning_path=self.learning_path,
            status=LearningPathEnrollment.STATUS_ACTIVE
        )
    
    def test_calculate_progress(self):
        """Test progress calculation."""
        # Initially 0% progress
        progress = self.lp_enrollment.calculate_progress()
        self.assertEqual(progress, Decimal('0.00'))
        
        # Complete the course
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_COMPLETED
        )
        
        progress = self.lp_enrollment.calculate_progress()
        self.assertEqual(progress, Decimal('100.00'))
        self.assertEqual(self.lp_enrollment.status, LearningPathEnrollment.STATUS_COMPLETED)


class LessonProgressModelTests(TestCase):
    """Tests for LessonProgress model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='progress@example.com',
            username='progressuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course-progress',
            status='published'
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Test Module',
            order_index=1
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Test Lesson',
            order_index=1,
            status='published'
        )
        self.enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        self.lesson_progress = LessonProgress.objects.create(
            enrollment=self.enrollment,
            lesson=self.lesson,
            status=LessonProgress.STATUS_NOT_STARTED
        )
    
    def test_mark_started(self):
        """Test marking lesson as started."""
        self.lesson_progress.mark_started()
        self.assertEqual(self.lesson_progress.status, LessonProgress.STATUS_IN_PROGRESS)
        self.assertIsNotNone(self.lesson_progress.started_at)
    
    def test_mark_completed(self):
        """Test marking lesson as completed."""
        self.lesson_progress.mark_completed()
        self.assertEqual(self.lesson_progress.status, LessonProgress.STATUS_COMPLETED)
        self.assertIsNotNone(self.lesson_progress.completed_at)
        self.assertEqual(self.lesson_progress.progress_percentage, Decimal('100.00'))
        
        # Check enrollment's last accessed lesson is updated
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.last_accessed_lesson, self.lesson)


class PrerequisiteCourseModelTests(TestCase):
    """Tests for PrerequisiteCourse model."""
    
    def setUp(self):
        """Set up test data."""
        self.prereq_course = Course.objects.create(
            title='Prerequisite Course',
            slug='prereq-course',
            status='published'
        )
        self.main_course = Course.objects.create(
            title='Main Course',
            slug='main-course',
            status='published'
        )
        self.prereq = PrerequisiteCourse.objects.create(
            course=self.main_course,
            prerequisite_course=self.prereq_course,
            is_strict=True
        )
    
    def test_prerequisite_creation(self):
        """Test prerequisite creation."""
        self.assertEqual(self.prereq.course, self.main_course)
        self.assertEqual(self.prereq.prerequisite_course, self.prereq_course)
        self.assertTrue(self.prereq.is_strict)


class EnrollmentServiceTests(TestCase):
    """Tests for EnrollmentService."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='service@example.com',
            username='serviceuser',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Service Test Course',
            slug='service-test-course',
            status='published',
            price=0
        )
        self.service = EnrollmentService()
    
    def test_enroll_user_success(self):
        """Test successful enrollment."""
        enrollment = self.service.enroll_user(self.user, self.course)
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment.user, self.user)
        self.assertEqual(enrollment.course, self.course)
    
    def test_enroll_user_already_enrolled(self):
        """Test enrollment when already enrolled."""
        Enrollment.objects.create(user=self.user, course=self.course, status=Enrollment.STATUS_ACTIVE)
        
        with self.assertRaises(AlreadyEnrolledError):
            self.service.enroll_user(self.user, self.course)
    
    def test_enroll_user_course_not_published(self):
        """Test enrollment in unpublished course."""
        self.course.status = 'draft'
        self.course.save()
        
        with self.assertRaises(ValueError):
            self.service.enroll_user(self.user, self.course)
    
    def test_enroll_user_capacity_exceeded(self):
        """Test enrollment when capacity is exceeded."""
        self.course.max_enrollments = 1
        self.course.save()
        
        # Create another enrollment to fill capacity
        other_user = User.objects.create_user(
            email='other@example.com',
            username='otheruser',
            password='testpass123'
        )
        Enrollment.objects.create(user=other_user, course=self.course, status=Enrollment.STATUS_ACTIVE)
        
        with self.assertRaises(CapacityExceededError):
            self.service.enroll_user(self.user, self.course)
    
    def test_enroll_user_prerequisite_not_met(self):
        """Test enrollment when prerequisite not met."""
        prereq_course = Course.objects.create(
            title='Prerequisite',
            slug='prereq',
            status='published'
        )
        PrerequisiteCourse.objects.create(
            course=self.course,
            prerequisite_course=prereq_course,
            is_strict=True
        )
        
        with self.assertRaises(PrerequisiteNotMetError):
            self.service.enroll_user(self.user, self.course)
    
    def test_update_lesson_progress(self):
        """Test updating lesson progress."""
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        module = Module.objects.create(course=self.course, title='Module', order_index=1)
        lesson = Lesson.objects.create(module=module, title='Lesson', order_index=1, status='published')
        
        result = self.service.update_lesson_progress(enrollment, lesson, 'completed')
        self.assertIsNotNone(result)
        self.assertEqual(result.status, LessonProgress.STATUS_COMPLETED)
    
    def test_calculate_course_completion(self):
        """Test calculating course completion."""
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        module = Module.objects.create(course=self.course, title='Module', order_index=1)
        lesson1 = Lesson.objects.create(module=module, title='Lesson 1', order_index=1, status='published', is_required=True)
        lesson2 = Lesson.objects.create(module=module, title='Lesson 2', order_index=2, status='published', is_required=True)
        
        # Complete first lesson
        LessonProgress.objects.create(
            enrollment=enrollment,
            lesson=lesson1,
            status=LessonProgress.STATUS_COMPLETED
        )
        
        percentage = self.service.calculate_course_completion(enrollment)
        self.assertEqual(percentage, Decimal('50.00'))


class CapacityCheckerTests(TestCase):
    """Tests for CapacityChecker."""
    
    def setUp(self):
        """Set up test data."""
        self.course = Course.objects.create(
            title='Capacity Test Course',
            slug='capacity-test-course',
            status='published',
            max_enrollments=2
        )
        self.checker = CapacityChecker()
    
    def test_check_capacity_available(self):
        """Test capacity check when space available."""
        result = self.checker.check_capacity(self.course)
        self.assertTrue(result['available'])
        self.assertEqual(result['current_enrollments'], 0)
        self.assertEqual(result['max_enrollments'], 2)
    
    def test_check_capacity_full(self):
        """Test capacity check when full."""
        # Fill capacity
        for i in range(2):
            user = User.objects.create_user(
                email=f'user{i}@example.com',
                username=f'user{i}',
                password='testpass123'
            )
            Enrollment.objects.create(user=user, course=self.course, status=Enrollment.STATUS_ACTIVE)
        
        result = self.checker.check_capacity(self.course)
        self.assertFalse(result['available'])


class PrerequisiteValidatorTests(TestCase):
    """Tests for PrerequisiteValidator."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='prereq@example.com',
            username='prerequser',
            password='testpass123'
        )
        self.prereq_course = Course.objects.create(
            title='Prerequisite Course',
            slug='prereq-course-val',
            status='published'
        )
        self.main_course = Course.objects.create(
            title='Main Course',
            slug='main-course-val',
            status='published'
        )
        PrerequisiteCourse.objects.create(
            course=self.main_course,
            prerequisite_course=self.prereq_course,
            is_strict=True
        )
        self.validator = PrerequisiteValidator()
    
    def test_validate_prerequisites_not_met(self):
        """Test validation when prerequisites not met."""
        result = self.validator.validate_prerequisites(self.user, self.main_course)
        self.assertFalse(result['valid'])
        self.assertEqual(len(result['missing_prerequisites']), 1)
    
    def test_validate_prerequisites_met(self):
        """Test validation when prerequisites are met."""
        # Complete prerequisite course
        Enrollment.objects.create(
            user=self.user,
            course=self.prereq_course,
            status=Enrollment.STATUS_COMPLETED
        )
        
        result = self.validator.validate_prerequisites(self.user, self.main_course)
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['missing_prerequisites']), 0)


class PaymentGateTests(TestCase):
    """Tests for PaymentGate."""
    
    def setUp(self):
        """Set up test data."""
        self.free_course = Course.objects.create(
            title='Free Course',
            slug='free-course',
            status='published',
            price=0
        )
        self.paid_course = Course.objects.create(
            title='Paid Course',
            slug='paid-course',
            status='published',
            price=99.99
        )
        self.gate = PaymentGate()
    
    def test_check_payment_free_course(self):
        """Test payment check for free course."""
        result = self.gate.check_payment(None, self.free_course)
        self.assertTrue(result['can_proceed'])
        self.assertFalse(result['payment_required'])
    
    def test_check_payment_paid_course(self):
        """Test payment check for paid course."""
        result = self.gate.check_payment(None, self.paid_course)
        self.assertFalse(result['can_proceed'])
        self.assertTrue(result['payment_required'])


class EnrollmentAPITests(APITestCase):
    """Tests for Enrollment API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        # Create roles
        self.learner_role, _ = Role.objects.get_or_create(
            role_name=Role.ROLE_LEARNER,
            defaults={'display_name': 'Learner'}
        )
        
        # Create users
        self.user = User.objects.create_user(
            email='api@example.com',
            username='apiuser',
            password='testpass123'
        )
        self.user.assigned_roles.add(self.learner_role)
        
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            username='adminuser',
            password='testpass123',
            is_staff=True
        )
        
        # Create course
        self.course = Course.objects.create(
            title='API Test Course',
            slug='api-test-course',
            description='Test course for API',
            status='published',
            price=0
        )
        
        # Authenticate
        self.client.force_authenticate(user=self.user)
    
    def test_list_enrollments(self):
        """Test listing enrollments."""
        Enrollment.objects.create(user=self.user, course=self.course, status=Enrollment.STATUS_ACTIVE)
        
        response = self.client.get('/api/v1/enrollments/enrollments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_my_enrollments(self):
        """Test getting my enrollments."""
        Enrollment.objects.create(user=self.user, course=self.course, status=Enrollment.STATUS_ACTIVE)
        
        response = self.client.get('/api/v1/enrollments/enrollments/my/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_create_enrollment(self):
        """Test creating enrollment."""
        data = {
            'course_id': str(self.course.id),
            'notes': 'Test enrollment'
        }
        response = self.client.post('/api/v1/enrollments/enrollments/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Enrollment.objects.count(), 1)
    
    def test_create_enrollment_duplicate(self):
        """Test creating duplicate enrollment."""
        Enrollment.objects.create(user=self.user, course=self.course, status=Enrollment.STATUS_ACTIVE)
        
        data = {
            'course_id': str(self.course.id)
        }
        response = self.client.post('/api/v1/enrollments/enrollments/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_progress(self):
        """Test updating enrollment progress."""
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        module = Module.objects.create(course=self.course, title='Module', order_index=1)
        lesson = Lesson.objects.create(module=module, title='Lesson', order_index=1, status='published')
        
        data = {
            'lesson_id': str(lesson.id),
            'status': 'completed'
        }
        response = self.client.patch(f'/api/v1/enrollments/enrollments/{enrollment.id}/progress/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_unenroll(self):
        """Test unenrolling from course."""
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        
        data = {
            'confirm': True,
            'reason': 'No longer interested'
        }
        response = self.client.post(f'/api/v1/enrollments/enrollments/{enrollment.id}/unenroll/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.STATUS_CANCELLED)


class LearningPathAPITests(APITestCase):
    """Tests for Learning Path API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            email='lpapi@example.com',
            username='lpapiuser',
            password='testpass123'
        )
        
        self.learning_path = LearningPath.objects.create(
            title='API Learning Path',
            slug='api-learning-path',
            description='Test learning path',
            status=LearningPath.STATUS_PUBLISHED
        )
        
        self.course = Course.objects.create(
            title='Path Course',
            slug='path-course',
            status='published'
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_list_learning_paths(self):
        """Test listing learning paths."""
        response = self.client.get('/api/v1/enrollments/learning-paths/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_retrieve_learning_path(self):
        """Test retrieving a learning path."""
        response = self.client.get(f'/api/v1/enrollments/learning-paths/{self.learning_path.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'API Learning Path')
    
    def test_enroll_in_learning_path(self):
        """Test enrolling in a learning path."""
        LearningPathItem.objects.create(
            path=self.learning_path,
            course=self.course,
            order_index=1
        )
        
        response = self.client.post(f'/api/v1/enrollments/learning-paths/{self.learning_path.id}/enroll/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that course enrollment was created
        self.assertTrue(Enrollment.objects.filter(user=self.user, course=self.course).exists())
    
    def test_featured_learning_paths(self):
        """Test getting featured learning paths."""
        self.learning_path.is_featured = True
        self.learning_path.save()
        
        response = self.client.get('/api/v1/enrollments/learning-paths/featured/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)


class LessonProgressAPITests(APITestCase):
    """Tests for Lesson Progress API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            email='progressapi@example.com',
            username='progressapiuser',
            password='testpass123'
        )
        
        self.course = Course.objects.create(
            title='Progress Course',
            slug='progress-course',
            status='published'
        )
        
        self.module = Module.objects.create(
            course=self.course,
            title='Module',
            order_index=1
        )
        
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Lesson',
            order_index=1,
            status='published'
        )
        
        self.enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        
        self.lesson_progress = LessonProgress.objects.create(
            enrollment=self.enrollment,
            lesson=self.lesson,
            status=LessonProgress.STATUS_NOT_STARTED
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_list_lesson_progress(self):
        """Test listing lesson progress."""
        response = self.client.get('/api/v1/enrollments/lesson-progress/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_mark_lesson_started(self):
        """Test marking lesson as started."""
        response = self.client.post(f'/api/v1/enrollments/lesson-progress/{self.lesson_progress.id}/mark-started/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.lesson_progress.refresh_from_db()
        self.assertEqual(self.lesson_progress.status, LessonProgress.STATUS_IN_PROGRESS)
    
    def test_mark_lesson_completed(self):
        """Test marking lesson as completed."""
        response = self.client.post(f'/api/v1/enrollments/lesson-progress/{self.lesson_progress.id}/mark-completed/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.lesson_progress.refresh_from_db()
        self.assertEqual(self.lesson_progress.status, LessonProgress.STATUS_COMPLETED)
    
    def test_get_progress_by_enrollment(self):
        """Test getting progress by enrollment."""
        response = self.client.get(f'/api/v1/enrollments/lesson-progress/by-enrollment/{self.enrollment.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EnrollmentStatsTests(APITestCase):
    """Tests for Enrollment Stats API."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        self.admin_user = User.objects.create_user(
            email='statsadmin@example.com',
            username='statsadmin',
            password='testpass123',
            is_staff=True
        )
        
        self.course = Course.objects.create(
            title='Stats Course',
            slug='stats-course',
            status='published'
        )
        
        # Create some enrollments
        for i in range(5):
            user = User.objects.create_user(
                email=f'stats{i}@example.com',
                username=f'statsuser{i}',
                password='testpass123'
            )
            status = Enrollment.STATUS_ACTIVE if i < 3 else Enrollment.STATUS_COMPLETED
            Enrollment.objects.create(user=user, course=self.course, status=status)
        
        self.client.force_authenticate(user=self.admin_user)
    
    def test_get_enrollment_stats(self):
        """Test getting enrollment statistics."""
        response = self.client.get('/api/v1/enrollments/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_enrollments', response.data)
        self.assertEqual(response.data['total_enrollments'], 5)


class PrerequisiteAPITests(APITestCase):
    """Tests for Prerequisite API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            email='prereqapi@example.com',
            username='prereqapiuser',
            password='testpass123'
        )
        
        self.prereq_course = Course.objects.create(
            title='Prereq API Course',
            slug='prereq-api-course',
            status='published'
        )
        
        self.main_course = Course.objects.create(
            title='Main API Course',
            slug='main-api-course',
            status='published'
        )
        
        self.prereq = PrerequisiteCourse.objects.create(
            course=self.main_course,
            prerequisite_course=self.prereq_course,
            is_strict=True
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_check_prerequisites(self):
        """Test checking prerequisites."""
        response = self.client.get(f'/api/v1/enrollments/prerequisites/check/{self.main_course.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_get_prerequisites_by_course(self):
        """Test getting prerequisites by course."""
        response = self.client.get(f'/api/v1/enrollments/prerequisites/by-course/{self.main_course.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
