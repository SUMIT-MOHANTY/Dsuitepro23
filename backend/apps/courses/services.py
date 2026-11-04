"""
Courses Services for Enterprise LMS
Provides business logic services for course management, content upload, and validation.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Count, Avg, Sum
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from .models import Course, Module, Lesson, ContentItem

User = get_user_model()
logger = logging.getLogger(__name__)


class CourseService:
    """
    Service class for course-related business logic.
    Handles course lifecycle, statistics, and complex operations.
    """
    
    @staticmethod
    def get_course_stats(course_id: uuid.UUID) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a course.
        
        Args:
            course_id: UUID of the course
            
        Returns:
            Dictionary containing course statistics
        """
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise ValueError(f"Course with ID {course_id} does not exist")
        
        modules = course.modules.all()
        total_lessons = 0
        total_duration = course.duration_minutes
        
        for module in modules:
            module_lessons = module.lessons.count()
            total_lessons += module_lessons
            total_duration += module.duration_minutes
            for lesson in module.lessons.all():
                total_duration += lesson.duration_minutes
        
        return {
            'course_id': str(course_id),
            'title': course.title,
            'status': course.status,
            'modules_count': modules.count(),
            'lessons_count': total_lessons,
            'total_duration_minutes': total_duration,
            'enrollment_count': course.enrollment_count,
            'rating_average': float(course.rating_average),
            'rating_count': course.rating_count,
            'is_published': course.is_published,
            'is_free': course.is_free,
        }
    
    @staticmethod
    def get_catalog_stats() -> Dict[str, Any]:
        """
        Get statistics for the course catalog.
        
        Returns:
            Dictionary containing catalog-wide statistics
        """
        courses = Course.objects.filter(is_deleted=False)
        
        total_courses = courses.count()
        published_courses = courses.filter(status='published').count()
        draft_courses = courses.filter(status='draft').count()
        archived_courses = courses.filter(status='archived').count()
        
        total_enrollments = courses.aggregate(
            total=Sum('enrollment_count')
        )['total'] or 0
        
        avg_rating = courses.filter(rating_count__gt=0).aggregate(
            avg=Avg('rating_average')
        )['avg'] or 0.00
        
        # Courses by category
        courses_by_category = {}
        for category, _ in Course.CATEGORY_CHOICES:
            count = courses.filter(category=category).count()
            if count > 0:
                courses_by_category[category] = count
        
        # Courses by level
        courses_by_level = {}
        for level, _ in Course.LEVEL_CHOICES:
            count = courses.filter(level=level).count()
            if count > 0:
                courses_by_level[level] = count
        
        return {
            'total_courses': total_courses,
            'published_courses': published_courses,
            'draft_courses': draft_courses,
            'archived_courses': archived_courses,
            'total_enrollments': total_enrollments,
            'average_rating': round(float(avg_rating), 2),
            'courses_by_category': courses_by_category,
            'courses_by_level': courses_by_level,
        }
    
    @staticmethod
    @transaction.atomic
    def publish_course(course_id: uuid.UUID, user: User) -> Course:
        """
        Publish a course after validating requirements.
        
        Args:
            course_id: UUID of the course to publish
            user: User performing the action
            
        Returns:
            Published course instance
            
        Raises:
            ValueError: If course cannot be published
        """
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise ValueError(f"Course with ID {course_id} does not exist")
        
        if course.status == 'published':
            raise ValueError("Course is already published")
        
        if course.status == 'archived':
            raise ValueError("Cannot publish an archived course")
        
        # Validate requirements
        errors = CourseService.validate_publish_requirements(course)
        if errors:
            raise ValueError(f"Cannot publish course: {'; '.join(errors)}")
        
        # Update course status
        course.status = 'published'
        course.published_at = datetime.now()
        course.updated_by = user
        course.save(update_fields=['status', 'published_at', 'updated_by', 'updated_at'])
        
        logger.info(f"Course '{course.title}' published by {user.email}")
        return course
    
    @staticmethod
    @transaction.atomic
    def archive_course(course_id: uuid.UUID, user: User) -> Course:
        """
        Archive a course.
        
        Args:
            course_id: UUID of the course to archive
            user: User performing the action
            
        Returns:
            Archived course instance
        """
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise ValueError(f"Course with ID {course_id} does not exist")
        
        if course.status == 'archived':
            raise ValueError("Course is already archived")
        
        course.status = 'archived'
        course.updated_by = user
        course.save(update_fields=['status', 'updated_by', 'updated_at'])
        
        logger.info(f"Course '{course.title}' archived by {user.email}")
        return course
    
    @staticmethod
    def validate_publish_requirements(course: Course) -> list:
        """
        Validate that a course meets all requirements for publishing.
        
        Args:
            course: Course instance to validate
            
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Check title
        if not course.title or not course.title.strip():
            errors.append("Course title is required")
        
        # Check description
        if not course.description or not course.description.strip():
            errors.append("Course description is required")
        
        # Check instructor
        if not course.instructor:
            errors.append("Course must have an instructor assigned")
        
        # Check modules
        modules = course.modules.filter(is_deleted=False)
        if not modules.exists():
            errors.append("Course must have at least one module")
        
        # Check lessons in each module
        for module in modules:
            if not module.lessons.filter(is_deleted=False).exists():
                errors.append(f"Module '{module.title}' must have at least one lesson")
        
        return errors
    
    @staticmethod
    def search_courses(query: str, filters: Optional[Dict] = None) -> Course:
        """
        Search courses with full-text search and filters.
        
        Args:
            query: Search query string
            filters: Optional filter dictionary
            
        Returns:
            QuerySet of matching courses
        """
        queryset = Course.objects.filter(is_deleted=False, status='published')
        
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(syllabus__icontains=query) |
                Q(tags__icontains=query)
            )
        
        if filters:
            if 'category' in filters:
                queryset = queryset.filter(category=filters['category'])
            if 'level' in filters:
                queryset = queryset.filter(level=filters['level'])
            if 'instructor' in filters:
                queryset = queryset.filter(instructor_id=filters['instructor'])
            if 'is_free' in filters:
                if filters['is_free']:
                    queryset = queryset.filter(price=0)
                else:
                    queryset = queryset.filter(price__gt=0)
            if 'is_featured' in filters:
                queryset = queryset.filter(is_featured=filters['is_featured'])
            if 'min_price' in filters:
                queryset = queryset.filter(price__gte=filters['min_price'])
            if 'max_price' in filters:
                queryset = queryset.filter(price__lte=filters['max_price'])
        
        return queryset
    
    @staticmethod
    def reorder_modules(course_id: uuid.UUID, module_ids: list) -> bool:
        """
        Reorder modules within a course.
        
        Args:
            course_id: UUID of the course
            module_ids: Ordered list of module UUIDs
            
        Returns:
            True if successful
        """
        with transaction.atomic():
            for index, module_id in enumerate(module_ids, start=1):
                Module.objects.filter(id=module_id, course_id=course_id).update(
                    order_index=index
                )
        return True
    
    @staticmethod
    def reorder_lessons(module_id: uuid.UUID, lesson_ids: list) -> bool:
        """
        Reorder lessons within a module.
        
        Args:
            module_id: UUID of the module
            lesson_ids: Ordered list of lesson UUIDs
            
        Returns:
            True if successful
        """
        with transaction.atomic():
            for index, lesson_id in enumerate(lesson_ids, start=1):
                Lesson.objects.filter(id=lesson_id, module_id=module_id).update(
                    order_index=index
                )
        return True


class PrerequisiteValidator:
    """
    Validator for course prerequisites and enrollment requirements.
    """
    
    @staticmethod
    def validate_course_completion(user: User, course_id: uuid.UUID) -> Tuple[bool, list]:
        """
        Check if a user has completed a course.
        
        Args:
            user: User to check
            course_id: UUID of the course
            
        Returns:
            Tuple of (is_complete, missing_items)
        """
        from apps.enrollment.models import Enrollment
        
        try:
            enrollment = Enrollment.objects.get(user=user, course_id=course_id)
            return enrollment.is_completed, []
        except Exception:
            return False, ["Not enrolled in course"]
    
    @staticmethod
    def validate_lesson_prerequisites(user: User, lesson: Lesson) -> Tuple[bool, list]:
        """
        Check if a user can access a lesson based on prerequisites.
        
        Args:
            user: User to check
            lesson: Lesson to access
            
        Returns:
            Tuple of (can_access, blockers)
        """
        blockers = []
        
        # Check if lesson is preview (no prerequisites needed)
        if lesson.is_preview:
            return True, []
        
        # Check if user is enrolled in the course
        from apps.enrollment.models import Enrollment
        try:
            enrollment = Enrollment.objects.get(user=user, course=lesson.course)
            if not enrollment.is_active:
                blockers.append("Enrollment is not active")
        except Exception:
            blockers.append("Not enrolled in course")
        
        # Check previous lessons in module
        previous_lessons = Lesson.objects.filter(
            module=lesson.module,
            order_index__lt=lesson.order_index,
            is_required=True
        )
        
        for prev_lesson in previous_lessons:
            # Check if previous lesson is completed
            # This would integrate with progress tracking
            pass
        
        return len(blockers) == 0, blockers


class ContentUploadService:
    """
    Service for generating presigned URLs for content uploads.
    Supports S3, MinIO, and other S3-compatible storage backends.
    """
    
    DEFAULT_EXPIRATION = 3600  # 1 hour
    MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB
    
    CONTENT_TYPE_CONFIG = {
        'video': {
            'allowed_extensions': ['.mp4', '.mov', '.avi', '.mkv', '.webm'],
            'content_type': 'video/mp4',
            'max_size': 5 * 1024 * 1024 * 1024,  # 5GB
        },
        'pdf': {
            'allowed_extensions': ['.pdf'],
            'content_type': 'application/pdf',
            'max_size': 100 * 1024 * 1024,  # 100MB
        },
        'scorm': {
            'allowed_extensions': ['.zip'],
            'content_type': 'application/zip',
            'max_size': 500 * 1024 * 1024,  # 500MB
        },
        'image': {
            'allowed_extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
            'content_type': 'image/jpeg',
            'max_size': 10 * 1024 * 1024,  # 10MB
        },
        'document': {
            'allowed_extensions': ['.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx'],
            'content_type': 'application/octet-stream',
            'max_size': 50 * 1024 * 1024,  # 50MB
        },
        'audio': {
            'allowed_extensions': ['.mp3', '.wav', '.aac', '.ogg'],
            'content_type': 'audio/mpeg',
            'max_size': 100 * 1024 * 1024,  # 100MB
        },
    }
    
    @classmethod
    def generate_upload_url(
        cls,
        content_type: str,
        filename: str,
        file_size: Optional[int] = None,
        lesson_id: Optional[uuid.UUID] = None,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for direct-to-storage upload.
        
        Args:
            content_type: Type of content (video, pdf, scorm, etc.)
            filename: Original filename
            file_size: Size of file in bytes (optional)
            lesson_id: UUID of associated lesson (optional)
            user: User requesting the upload
            
        Returns:
            Dictionary with upload_url, storage_key, expires_in, etc.
        """
        # Validate content type
        if content_type not in cls.CONTENT_TYPE_CONFIG:
            raise ValueError(f"Invalid content type: {content_type}")
        
        config = cls.CONTENT_TYPE_CONFIG[content_type]
        
        # Validate extension
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        if ext not in config['allowed_extensions']:
            raise ValueError(
                f"Invalid file extension for {content_type}. "
                f"Allowed: {', '.join(config['allowed_extensions'])}"
            )
        
        # Validate file size
        if file_size and file_size > config['max_size']:
            raise ValueError(
                f"File size exceeds maximum allowed ({config['max_size']} bytes)"
            )
        
        # Generate unique storage key
        timestamp = datetime.now().strftime('%Y/%m/%d')
        unique_id = str(uuid.uuid4())[:8]
        safe_filename = cls._sanitize_filename(filename)
        storage_key = f"content/{content_type}/{timestamp}/{unique_id}_{safe_filename}"
        
        # Generate presigned URL based on storage backend
        storage_backend = cls._get_storage_backend()
        
        if storage_backend == 's3':
            return cls._generate_s3_presigned_url(
                storage_key=storage_key,
                content_type=config['content_type'],
                expiration=cls.DEFAULT_EXPIRATION
            )
        elif storage_backend == 'minio':
            return cls._generate_minio_presigned_url(
                storage_key=storage_key,
                content_type=config['content_type'],
                expiration=cls.DEFAULT_EXPIRATION
            )
        else:
            # Local storage - return placeholder for development
            return cls._generate_local_upload_url(
                storage_key=storage_key,
                content_type=config['content_type']
            )
    
    @staticmethod
    def _get_storage_backend() -> str:
        """
        Determine the storage backend from settings.
        
        Returns:
            Storage backend name (s3, minio, local)
        """
        default_storage = getattr(settings, 'DEFAULT_FILE_STORAGE', '')
        
        if 'S3' in default_storage or 's3' in default_storage:
            return 's3'
        elif 'minio' in default_storage.lower():
            return 'minio'
        return 'local'
    
    @classmethod
    def _generate_s3_presigned_url(
        cls,
        storage_key: str,
        content_type: str,
        expiration: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate AWS S3 presigned URL for upload.
        
        Args:
            storage_key: S3 object key
            content_type: MIME type of content
            expiration: URL expiration time in seconds
            
        Returns:
            Dictionary with upload details
        """
        try:
            import boto3
            from botocore.config import Config
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
                config=Config(signature_version='s3v4')
            )
            
            bucket = settings.AWS_STORAGE_BUCKET_NAME
            
            # Generate presigned POST for browser uploads
            presigned_post = s3_client.generate_presigned_post(
                Bucket=bucket,
                Key=storage_key,
                Fields={'Content-Type': content_type},
                Conditions=[
                    {'Content-Type': content_type},
                    ['content-length-range', 1, cls.MAX_FILE_SIZE]
                ],
                ExpiresIn=expiration
            )
            
            return {
                'upload_url': presigned_post['url'],
                'storage_key': storage_key,
                'expires_in': expiration,
                'fields': presigned_post['fields'],
                'headers': {},
                'method': 'POST',
            }
            
        except ImportError:
            logger.warning("boto3 not installed, falling back to local upload")
            return cls._generate_local_upload_url(storage_key, content_type)
        except Exception as e:
            logger.error(f"Error generating S3 presigned URL: {e}")
            raise ValueError(f"Failed to generate upload URL: {str(e)}")
    
    @classmethod
    def _generate_minio_presigned_url(
        cls,
        storage_key: str,
        content_type: str,
        expiration: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate MinIO presigned URL for upload.
        
        Args:
            storage_key: Object key
            content_type: MIME type of content
            expiration: URL expiration time in seconds
            
        Returns:
            Dictionary with upload details
        """
        try:
            from minio import Minio
            
            client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_USE_HTTPS
            )
            
            bucket = settings.MINIO_BUCKET_NAME
            
            # Ensure bucket exists
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            
            # Generate presigned PUT URL
            upload_url = client.presigned_put_object(
                bucket_name=bucket,
                object_name=storage_key,
                expires=timedelta(seconds=expiration)
            )
            
            return {
                'upload_url': upload_url,
                'storage_key': storage_key,
                'expires_in': expiration,
                'fields': {},
                'headers': {'Content-Type': content_type},
                'method': 'PUT',
            }
            
        except ImportError:
            logger.warning("minio not installed, falling back to local upload")
            return cls._generate_local_upload_url(storage_key, content_type)
        except Exception as e:
            logger.error(f"Error generating MinIO presigned URL: {e}")
            raise ValueError(f"Failed to generate upload URL: {str(e)}")
    
    @staticmethod
    def _generate_local_upload_url(
        storage_key: str,
        content_type: str
    ) -> Dict[str, Any]:
        """
        Generate local upload URL for development.
        
        Args:
            storage_key: File path
            content_type: MIME type of content
            
        Returns:
            Dictionary with upload details
        """
        return {
            'upload_url': f"/api/v1/upload/local/{storage_key}",
            'storage_key': storage_key,
            'expires_in': 3600,
            'fields': {},
            'headers': {'Content-Type': content_type},
            'method': 'POST',
            'note': 'Local development mode - configure S3 or MinIO for production',
        }
    
    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Sanitize filename for safe storage.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        import re
        # Remove path components and unsafe characters
        filename = filename.split('/')[-1].split('\\')[-1]
        filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        # Limit length
        if len(filename) > 200:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:200] + ('.' + ext if ext else '')
        return filename
    
    @classmethod
    def get_content_url(cls, storage_key: str, expiration: int = 3600) -> str:
        """
        Generate a presigned URL for accessing content.
        
        Args:
            storage_key: Storage key of the content
            expiration: URL expiration time in seconds
            
        Returns:
            Presigned URL for accessing the content
        """
        storage_backend = cls._get_storage_backend()
        
        if storage_backend == 's3':
            try:
                import boto3
                from botocore.config import Config
                
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME,
                    config=Config(signature_version='s3v4')
                )
                
                url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                        'Key': storage_key
                    },
                    ExpiresIn=expiration
                )
                return url
                
            except Exception as e:
                logger.error(f"Error generating S3 access URL: {e}")
                return f"{settings.MEDIA_URL}{storage_key}"
                
        elif storage_backend == 'minio':
            try:
                from minio import Minio
                
                client = Minio(
                    settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=settings.MINIO_USE_HTTPS
                )
                
                url = client.presigned_get_object(
                    bucket_name=settings.MINIO_BUCKET_NAME,
                    object_name=storage_key,
                    expires=timedelta(seconds=expiration)
                )
                return url
                
            except Exception as e:
                logger.error(f"Error generating MinIO access URL: {e}")
                return f"{settings.MEDIA_URL}{storage_key}"
        
        return f"{settings.MEDIA_URL}{storage_key}"


class CourseContentService:
    """
    Service for managing course content structure.
    Handles content organization and hierarchy operations.
    """
    
    @staticmethod
    def duplicate_course(course_id: uuid.UUID, user: User) -> Course:
        """
        Create a duplicate of a course with all its content.
        
        Args:
            course_id: UUID of the course to duplicate
            user: User creating the duplicate
            
        Returns:
            New course instance
        """
        try:
            original = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise ValueError(f"Course with ID {course_id} does not exist")
        
        with transaction.atomic():
            # Create new course
            new_course = Course.objects.create(
                title=f"{original.title} (Copy)",
                slug=f"{original.slug}-copy-{uuid.uuid4().hex[:8]}",
                description=original.description,
                syllabus=original.syllabus,
                category=original.category,
                level=original.level,
                tags=original.tags,
                instructor=user,
                status='draft',
                visibility=original.visibility,
                price=original.price,
                currency=original.currency,
                duration_minutes=original.duration_minutes,
                max_enrollments=original.max_enrollments,
                created_by=user,
                updated_by=user,
            )
            
            # Copy modules and lessons
            for module in original.modules.filter(is_deleted=False):
                new_module = Module.objects.create(
                    course=new_course,
                    title=module.title,
                    description=module.description,
                    order_index=module.order_index,
                    status='draft',
                    duration_minutes=module.duration_minutes,
                    created_by=user,
                    updated_by=user,
                )
                
                for lesson in module.lessons.filter(is_deleted=False):
                    new_lesson = Lesson.objects.create(
                        module=new_module,
                        title=lesson.title,
                        description=lesson.description,
                        content_type=lesson.content_type,
                        duration_minutes=lesson.duration_minutes,
                        order_index=lesson.order_index,
                        is_preview=lesson.is_preview,
                        is_required=lesson.is_required,
                        status='draft',
                        created_by=user,
                        updated_by=user,
                    )
                    
                    # Copy content items
                    for item in lesson.content_items.filter(is_deleted=False):
                        ContentItem.objects.create(
                            lesson=new_lesson,
                            content_type=item.content_type,
                            title=item.title,
                            storage_key=item.storage_key,
                            file_url=item.file_url,
                            file_size=item.file_size,
                            duration_seconds=item.duration_seconds,
                            order_index=item.order_index,
                            is_primary=item.is_primary,
                            metadata=item.metadata,
                            created_by=user,
                            updated_by=user,
                        )
            
            logger.info(f"Course '{original.title}' duplicated by {user.email}")
            return new_course
    
    @staticmethod
    def calculate_course_duration(course_id: uuid.UUID) -> int:
        """
        Calculate total duration of a course in minutes.
        
        Args:
            course_id: UUID of the course
            
        Returns:
            Total duration in minutes
        """
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise ValueError(f"Course with ID {course_id} does not exist")
        
        total = course.duration_minutes
        
        for module in course.modules.filter(is_deleted=False):
            total += module.duration_minutes
            for lesson in module.lessons.filter(is_deleted=False):
                total += lesson.duration_minutes
        
        return total
    
    @staticmethod
    def update_course_duration(course_id: uuid.UUID) -> int:
        """
        Update the stored duration of a course based on its content.
        
        Args:
            course_id: UUID of the course
            
        Returns:
            Updated duration in minutes
        """
        duration = CourseContentService.calculate_course_duration(course_id)
        Course.objects.filter(id=course_id).update(duration_minutes=duration)
        return duration
