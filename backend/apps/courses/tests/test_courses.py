"""
Courses Tests for Enterprise LMS
Provides comprehensive test coverage for courses, modules, lessons, and content items.
"""

import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.users.models import Role
from ..models import Course, Module, Lesson, ContentItem

User = get_user_model()


class CourseModelTests(TestCase):
    """Test cases for Course model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            category='technology',
            level='beginner',
            price=Decimal('99.99'),
            currency='USD',
            instructor=self.instructor,
            status='draft'
        )
    
    def test_course_creation(self):
        """Test course can be created."""
        self.assertEqual(self.course.title, 'Test Course')
        self.assertEqual(self.course.slug, 'test-course')
        self.assertEqual(self.course.status, 'draft')
    
    def test_course_is_published_property(self):
        """Test is_published property."""
        self.assertFalse(self.course.is_published)
        self.course.status = 'published'
        self.course.save()
        self.assertTrue(self.course.is_published)
    
    def test_course_is_free_property(self):
        """Test is_free property."""
        self.assertFalse(self.course.is_free)
        self.course.price = 0
        self.course.save()
        self.assertTrue(self.course.is_free)
    
    def test_course_duration_display(self):
        """Test duration_display property."""
        self.course.duration_minutes = 125
        self.assertEqual(self.course.duration_display, '2h 5m')
        
        self.course.duration_minutes = 60
        self.assertEqual(self.course.duration_display, '1h')
        
        self.course.duration_minutes = 45
        self.assertEqual(self.course.duration_display, '45m')


class ModuleModelTests(TestCase):
    """Test cases for Module model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
    
    def test_module_creation(self):
        """Test module can be created."""
        module = Module.objects.create(
            course=self.course,
            title='Test Module',
            description='A test module',
            status='draft'
        )
        self.assertEqual(module.title, 'Test Module')
        self.assertEqual(module.course, self.course)
        self.assertEqual(module.order_index, 1)
    
    def test_module_auto_order_index(self):
        """Test module order_index is auto-assigned."""
        module1 = Module.objects.create(
            course=self.course,
            title='Module 1',
            status='draft'
        )
        self.assertEqual(module1.order_index, 1)
        
        module2 = Module.objects.create(
            course=self.course,
            title='Module 2',
            status='draft'
        )
        self.assertEqual(module2.order_index, 2)


class LessonModelTests(TestCase):
    """Test cases for Lesson model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Test Module',
            status='draft'
        )
    
    def test_lesson_creation(self):
        """Test lesson can be created."""
        lesson = Lesson.objects.create(
            module=self.module,
            title='Test Lesson',
            content_type='text',
            status='draft'
        )
        self.assertEqual(lesson.title, 'Test Lesson')
        self.assertEqual(lesson.module, self.module)
        self.assertEqual(lesson.order_index, 1)
    
    def test_lesson_course_property(self):
        """Test lesson course property."""
        lesson = Lesson.objects.create(
            module=self.module,
            title='Test Lesson',
            content_type='text',
            status='draft'
        )
        self.assertEqual(lesson.course, self.course)


class ContentItemModelTests(TestCase):
    """Test cases for ContentItem model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Test Module',
            status='draft'
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Test Lesson',
            content_type='text',
            status='draft'
        )
    
    def test_content_item_creation(self):
        """Test content item can be created."""
        content = ContentItem.objects.create(
            lesson=self.lesson,
            content_type='text',
            title='Test Content',
            storage_key='content/test.txt'
        )
        self.assertEqual(content.content_type, 'text')
        self.assertEqual(content.lesson, self.lesson)
    
    def test_content_item_metadata(self):
        """Test content item metadata methods."""
        content = ContentItem.objects.create(
            lesson=self.lesson,
            content_type='video',
            title='Test Video',
            storage_key='videos/test.mp4',
            metadata={'hls_url': 'https://cdn.example.com/video.m3u8', 'duration': 300}
        )
        
        self.assertEqual(content.get_metadata_value('hls_url'), 'https://cdn.example.com/video.m3u8')
        self.assertEqual(content.get_metadata_value('duration'), 300)
        self.assertIsNone(content.get_metadata_value('nonexistent'))
        
        content.set_metadata_value('resolution', '1080p')
        self.assertEqual(content.get_metadata_value('resolution'), '1080p')


class CourseAPITests(APITestCase):
    """Test cases for Course API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create roles
        self.learner_role = Role.objects.create(
            role_name='learner',
            display_name='Learner',
            is_system_role=True
        )
        self.instructor_role = Role.objects.create(
            role_name='instructor',
            display_name='Instructor',
            is_system_role=True
        )
        
        # Create users
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.instructor.assigned_roles.add(self.instructor_role)
        
        self.learner = User.objects.create_user(
            email='learner@test.com',
            username='learner',
            password='testpass123'
        )
        self.learner.assigned_roles.add(self.learner_role)
        
        # Create courses
        self.draft_course = Course.objects.create(
            title='Draft Course',
            slug='draft-course',
            description='A draft course',
            category='technology',
            level='beginner',
            price=Decimal('0.00'),
            instructor=self.instructor,
            status='draft',
            visibility='public'
        )
        
        self.published_course = Course.objects.create(
            title='Published Course',
            slug='published-course',
            description='A published course about Python',
            category='technology',
            level='intermediate',
            price=Decimal('99.99'),
            currency='USD',
            instructor=self.instructor,
            status='published',
            visibility='public',
            enrollment_count=100,
            rating_average=Decimal('4.50')
        )
    
    def test_catalog_list_public(self):
        """Test catalog list returns published courses for anonymous users."""
        url = reverse('catalog-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Published Course')
    
    def test_catalog_search(self):
        """Test catalog search functionality."""
        url = reverse('catalog-list')
        response = self.client.get(url, {'search': 'Python'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Published Course')
    
    def test_catalog_filter_by_level(self):
        """Test catalog filter by level."""
        url = reverse('catalog-list')
        response = self.client.get(url, {'level': 'intermediate'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['level'], 'intermediate')
    
    def test_catalog_filter_by_category(self):
        """Test catalog filter by category."""
        url = reverse('catalog-list')
        response = self.client.get(url, {'category': 'technology'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_catalog_filter_free_courses(self):
        """Test catalog filter for free courses."""
        # Create a free published course
        Course.objects.create(
            title='Free Course',
            slug='free-course',
            description='A free course',
            category='technology',
            level='beginner',
            price=Decimal('0.00'),
            instructor=self.instructor,
            status='published',
            visibility='public'
        )
        
        url = reverse('catalog-list')
        response = self.client.get(url, {'is_free': 'true'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Free Course')
    
    def test_course_detail(self):
        """Test course detail endpoint."""
        url = reverse('catalog-detail', kwargs={'pk': self.published_course.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Published Course')
        self.assertIn('modules', response.data)
    
    def test_instructor_create_course(self):
        """Test instructor can create a course."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('course-list')
        data = {
            'title': 'New Course',
            'description': 'A new course',
            'category': 'business',
            'level': 'beginner',
            'price': '49.99',
            'currency': 'USD',
            'status': 'draft'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Course')
        self.assertEqual(response.data['status'], 'draft')
    
    def test_learner_cannot_create_course(self):
        """Test learner cannot create a course."""
        self.client.force_authenticate(user=self.learner)
        
        url = reverse('course-list')
        data = {
            'title': 'New Course',
            'description': 'A new course',
            'category': 'business',
            'level': 'beginner',
            'status': 'draft'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ModuleAPITests(APITestCase):
    """Test cases for Module API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        
        self.instructor_role = Role.objects.create(
            role_name='instructor',
            display_name='Instructor',
            is_system_role=True
        )
        
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.instructor.assigned_roles.add(self.instructor_role)
        
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
        
        self.module = Module.objects.create(
            course=self.course,
            title='Test Module',
            description='A test module',
            status='draft'
        )
    
    def test_list_modules(self):
        """Test listing modules."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('module-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_create_module(self):
        """Test creating a module."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('module-list')
        data = {
            'course': str(self.course.id),
            'title': 'New Module',
            'description': 'A new module',
            'status': 'draft'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Module')


class LessonAPITests(APITestCase):
    """Test cases for Lesson API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        
        self.instructor_role = Role.objects.create(
            role_name='instructor',
            display_name='Instructor',
            is_system_role=True
        )
        
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.instructor.assigned_roles.add(self.instructor_role)
        
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
        
        self.module = Module.objects.create(
            course=self.course,
            title='Test Module',
            status='draft'
        )
        
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Test Lesson',
            content_type='text',
            status='draft'
        )
    
    def test_list_lessons(self):
        """Test listing lessons."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('lesson-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_create_lesson(self):
        """Test creating a lesson."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('lesson-list')
        data = {
            'module': str(self.module.id),
            'title': 'New Lesson',
            'content_type': 'video',
            'duration_minutes': 30,
            'status': 'draft'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Lesson')


class ContentUploadTests(APITestCase):
    """Test cases for content upload functionality."""
    
    def setUp(self):
        self.client = APIClient()
        
        self.instructor_role = Role.objects.create(
            role_name='instructor',
            display_name='Instructor',
            is_system_role=True
        )
        
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.instructor.assigned_roles.add(self.instructor_role)
        
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
    
    def test_get_upload_url(self):
        """Test getting presigned upload URL."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('course-upload-url', kwargs={'course_id': self.course.id})
        data = {
            'content_type': 'video',
            'filename': 'test_video.mp4',
            'file_size': 10485760  # 10MB
        }
        response = self.client.post(url, data)
        
        # Should return upload URL or error if storage not configured
        self.assertIn(response.status_code, [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ])
    
    def test_upload_url_validation(self):
        """Test upload URL request validation."""
        self.client.force_authenticate(user=self.instructor)
        
        url = reverse('course-upload-url', kwargs={'course_id': self.course.id})
        data = {
            'content_type': 'video',
            'filename': 'test_video.txt',  # Invalid extension
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CourseFilterTests(TestCase):
    """Test cases for course filtering functionality."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        
        # Create courses with different attributes
        self.python_course = Course.objects.create(
            title='Python Programming',
            slug='python-programming',
            description='Learn Python programming',
            category='technology',
            level='beginner',
            price=Decimal('49.99'),
            instructor=self.instructor,
            status='published',
            visibility='public'
        )
        
        self.advanced_course = Course.objects.create(
            title='Advanced Django',
            slug='advanced-django',
            description='Master Django framework',
            category='technology',
            level='advanced',
            price=Decimal('149.99'),
            instructor=self.instructor,
            status='published',
            visibility='public'
        )
        
        self.business_course = Course.objects.create(
            title='Business Strategy',
            slug='business-strategy',
            description='Strategic business planning',
            category='business',
            level='intermediate',
            price=Decimal('99.99'),
            instructor=self.instructor,
            status='published',
            visibility='public'
        )
    
    def test_filter_by_category(self):
        """Test filtering courses by category."""
        from ..filters import CourseFilter
        
        queryset = Course.objects.all()
        filter_set = CourseFilter({'category': 'technology'}, queryset=queryset)
        
        self.assertEqual(filter_set.qs.count(), 2)
        self.assertIn(self.python_course, filter_set.qs)
        self.assertIn(self.advanced_course, filter_set.qs)
    
    def test_filter_by_level(self):
        """Test filtering courses by level."""
        from ..filters import CourseFilter
        
        queryset = Course.objects.all()
        filter_set = CourseFilter({'level': 'advanced'}, queryset=queryset)
        
        self.assertEqual(filter_set.qs.count(), 1)
        self.assertIn(self.advanced_course, filter_set.qs)
    
    def test_filter_by_price_range(self):
        """Test filtering courses by price range."""
        from ..filters import CourseFilter
        
        queryset = Course.objects.all()
        filter_set = CourseFilter(
            {'min_price': '50', 'max_price': '100'},
            queryset=queryset
        )
        
        self.assertEqual(filter_set.qs.count(), 1)
        self.assertIn(self.business_course, filter_set.qs)
    
    def test_search_filter(self):
        """Test search functionality."""
        from ..filters import CourseFilter
        
        queryset = Course.objects.all()
        filter_set = CourseFilter({'search': 'Python'}, queryset=queryset)
        
        self.assertEqual(filter_set.qs.count(), 1)
        self.assertIn(self.python_course, filter_set.qs)


class CourseSignalTests(TestCase):
    """Test cases for course signals."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='A test course',
            instructor=self.instructor,
            status='draft'
        )
    
    def test_published_at_set_on_publish(self):
        """Test published_at is set when course is published."""
        self.assertIsNone(self.course.published_at)
        
        self.course.status = 'published'
        self.course.save()
        
        self.course.refresh_from_db()
        self.assertIsNotNone(self.course.published_at)
    
    def test_duration_updated_on_module_save(self):
        """Test course duration is updated when module is saved."""
        module = Module.objects.create(
            course=self.course,
            title='Test Module',
            duration_minutes=30,
            status='draft'
        )
        
        self.course.refresh_from_db()
        self.assertEqual(self.course.duration_minutes, 30)
        
        # Add a lesson to the module
        Lesson.objects.create(
            module=module,
            title='Test Lesson',
            content_type='video',
            duration_minutes=45,
            status='draft'
        )
        
        self.course.refresh_from_db()
        self.assertEqual(self.course.duration_minutes, 75)  # 30 + 45
