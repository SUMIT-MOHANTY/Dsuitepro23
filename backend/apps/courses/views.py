"""
Courses Views for Enterprise LMS
Provides API endpoints for course management, catalog, and content upload.
"""

import uuid
from datetime import datetime, timedelta

from django.db.models import Q, Avg, Count, Sum
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.conf import settings

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from django_filters.rest_framework import DjangoFilterBackend

from apps.core.pagination import StandardResultsSetPagination
from apps.users.permissions import IsAdminOrReadOnly

from .models import Course, Module, Lesson, ContentItem
from .serializers import (
    CourseSerializer,
    CourseListSerializer,
    CourseDetailSerializer,
    CourseCreateUpdateSerializer,
    CoursePublishSerializer,
    ModuleSerializer,
    ModuleDetailSerializer,
    LessonSerializer,
    LessonDetailSerializer,
    ContentItemSerializer,
    ContentUploadUrlSerializer,
    ContentUploadUrlResponseSerializer,
    CatalogFilterSerializer,
)
from .filters import CourseFilter


class CourseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Course CRUD operations.
    Provides endpoints for instructors and admins to manage courses.
    """
    queryset = Course.objects.filter(is_deleted=False)
    serializer_class = CourseSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = CourseFilter
    search_fields = ['title', 'description', 'syllabus', 'tags']
    ordering_fields = ['created_at', 'updated_at', 'price', 'enrollment_count', 'rating_average', 'published_at']
    ordering = ['-created_at']
    lookup_field = 'pk'
    
    def get_permissions(self):
        """
        Instantiate and return the list of permissions.
        - List/Retrieve: Allow any (filtered by visibility in queryset)
        - Create/Update/Delete: Authenticated users only
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return CourseListSerializer
        elif self.action == 'retrieve':
            return CourseDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return CourseCreateUpdateSerializer
        return CourseSerializer
    
    def get_queryset(self):
        """
        Filter courses based on user permissions and query parameters.
        """
        user = self.request.user
        
        # Base queryset - exclude deleted courses
        queryset = Course.objects.filter(is_deleted=False)
        
        # Filter by visibility based on user authentication
        if not user.is_authenticated:
            # Anonymous users only see public published courses
            queryset = queryset.filter(status='published', visibility='public')
        elif not (user.is_staff or user.is_superuser):
            # Regular authenticated users see public published courses
            # Plus their own courses (as instructor) regardless of status
            queryset = queryset.filter(
                Q(status='published', visibility='public') |
                Q(instructor=user) |
                Q(visibility='enrolled')  # Enrolled visibility shown to authenticated
            ).distinct()
        # Admins/staff see all courses
        
        # Apply additional filters from query params
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        visibility_filter = self.request.query_params.get('visibility')
        if visibility_filter:
            queryset = queryset.filter(visibility=visibility_filter)
        
        # Optimize queries with select_related and prefetch_related
        queryset = queryset.select_related('instructor').prefetch_related('modules', 'modules__lessons')
        
        return queryset
    
    def perform_create(self, serializer):
        """Set the instructor to the current user on creation."""
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )
    
    def perform_update(self, serializer):
        """Update the updated_by field."""
        serializer.save(updated_by=self.request.user)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def publish(self, request, pk=None):
        """
        Publish a course.
        Validates that all requirements are met before publishing.
        """
        course = self.get_object()
        
        # Check if user is instructor or admin
        if course.instructor != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Only the course instructor or admins can publish this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = CoursePublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Validate publish requirements
        errors = []
        
        if not course.title:
            errors.append('Course title is required.')
        
        if not course.description:
            errors.append('Course description is required.')
        
        modules = course.modules.filter(is_deleted=False)
        if not modules.exists():
            errors.append('Course must have at least one module.')
        
        # Check each module has at least one lesson
        for module in modules:
            if not module.lessons.filter(is_deleted=False).exists():
                errors.append(f'Module "{module.title}" must have at least one lesson.')
        
        if errors:
            return Response(
                {'detail': 'Cannot publish course due to validation errors.', 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Publish the course
        course.status = 'published'
        course.published_at = datetime.now()
        course.updated_by = request.user
        course.save(update_fields=['status', 'published_at', 'updated_at', 'updated_by'])
        
        return Response(
            {'detail': 'Course published successfully.', 'status': course.status},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def archive(self, request, pk=None):
        """
        Archive a course.
        """
        course = self.get_object()
        
        # Check if user is instructor or admin
        if course.instructor != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Only the course instructor or admins can archive this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        course.status = 'archived'
        course.updated_by = request.user
        course.save(update_fields=['status', 'updated_at', 'updated_by'])
        
        return Response(
            {'detail': 'Course archived successfully.', 'status': course.status},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def duplicate(self, request, pk=None):
        """
        Duplicate a course with all its modules and lessons.
        """
        course = self.get_object()
        
        # Check if user is instructor or admin
        if course.instructor != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Only the course instructor or admins can duplicate this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create a copy of the course
        new_course = Course.objects.create(
            title=f"{course.title} (Copy)",
            slug=f"{course.slug}-copy-{uuid.uuid4().hex[:8]}",
            description=course.description,
            syllabus=course.syllabus,
            category=course.category,
            level=course.level,
            tags=course.tags,
            instructor=request.user,
            thumbnail=course.thumbnail,
            thumbnail_url=course.thumbnail_url,
            status='draft',
            visibility='private',
            price=course.price,
            currency=course.currency,
            duration_minutes=course.duration_minutes,
            max_enrollments=course.max_enrollments,
            start_date=course.start_date,
            end_date=course.end_date,
            metadata=course.metadata,
            created_by=request.user,
            updated_by=request.user,
        )
        
        # Copy modules and lessons
        for module in course.modules.filter(is_deleted=False):
            new_module = Module.objects.create(
                course=new_course,
                title=module.title,
                description=module.description,
                order_index=module.order_index,
                status='draft',
                duration_minutes=module.duration_minutes,
                created_by=request.user,
                updated_by=request.user,
            )
            
            for lesson in module.lessons.filter(is_deleted=False):
                Lesson.objects.create(
                    module=new_module,
                    title=lesson.title,
                    description=lesson.description,
                    content_type=lesson.content_type,
                    duration_minutes=lesson.duration_minutes,
                    order_index=lesson.order_index,
                    is_preview=lesson.is_preview,
                    is_required=lesson.is_required,
                    status='draft',
                    created_by=request.user,
                    updated_by=request.user,
                )
        
        serializer = CourseDetailSerializer(new_course)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """
        Get course statistics.
        """
        course = self.get_object()
        
        modules_count = course.modules.filter(is_deleted=False).count()
        lessons_count = Lesson.objects.filter(
            module__course=course,
            module__is_deleted=False,
            is_deleted=False
        ).count()
        
        content_items_count = ContentItem.objects.filter(
            lesson__module__course=course,
            lesson__module__is_deleted=False,
            lesson__is_deleted=False,
            is_deleted=False
        ).count()
        
        stats = {
            'course_id': str(course.id),
            'title': course.title,
            'modules_count': modules_count,
            'lessons_count': lessons_count,
            'content_items_count': content_items_count,
            'total_duration_minutes': course.duration_minutes,
            'enrollment_count': course.enrollment_count,
            'rating_average': str(course.rating_average),
            'rating_count': course.rating_count,
            'status': course.status,
            'is_published': course.is_published,
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def upload_url(self, request, pk=None):
        """
        Generate a presigned URL for uploading content to storage.
        Supports S3/MinIO presigned URL generation.
        """
        course = self.get_object()
        
        # Validate request data
        serializer = ContentUploadUrlSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        content_type = validated_data['content_type']
        filename = validated_data['filename']
        file_size = validated_data.get('file_size')
        
        # Generate unique storage key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        file_ext = filename.split('.')[-1] if '.' in filename else ''
        
        storage_key = f"courses/{course.id}/{content_type}/{timestamp}_{unique_id}.{file_ext}"
        
        # Generate presigned URL (mock implementation - replace with actual S3/MinIO client)
        # In production, use boto3 to generate presigned URLs
        upload_url = self._generate_presigned_url(storage_key, content_type, file_size)
        
        response_serializer = ContentUploadUrlResponseSerializer(data={
            'upload_url': upload_url,
            'storage_key': storage_key,
            'expires_in': 3600,  # 1 hour
            'fields': {},
            'headers': {
                'Content-Type': 'application/octet-stream',
            }
        })
        response_serializer.is_valid(raise_exception=True)
        
        return Response(response_serializer.data)
    
    def _generate_presigned_url(self, storage_key, content_type, file_size=None):
        """
        Generate a presigned URL for uploading content.
        This is a mock implementation - replace with actual S3/MinIO client.
        """
        # In production, use boto3:
        # import boto3
        # s3_client = boto3.client('s3')
        # url = s3_client.generate_presigned_url(
        #     'put_object',
        #     Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': storage_key},
        #     ExpiresIn=3600
        # )
        # return url
        
        # Mock URL for development
        base_url = getattr(settings, 'STORAGE_BASE_URL', 'http://localhost:9000/media')
        return f"{base_url}/{storage_key}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"


class CatalogView(APIView):
    """
    Public catalog API for browsing courses.
    Supports search, filter, sort, and pagination.
    """
    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination
    
    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        """
        List courses in the catalog with filtering and sorting.
        """
        # Validate filter parameters
        filter_serializer = CatalogFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data
        
        # Base queryset - only published, non-deleted courses
        queryset = Course.objects.filter(
            is_deleted=False,
            status='published'
        ).select_related('instructor')
        
        # Apply visibility filter
        if request.user.is_authenticated:
            # Authenticated users see public and enrolled-only courses
            queryset = queryset.filter(
                Q(visibility='public') | Q(visibility='enrolled')
            )
        else:
            # Anonymous users only see public courses
            queryset = queryset.filter(visibility='public')
        
        # Apply search filter
        search = filters.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(syllabus__icontains=search) |
                Q(tags__icontains=search)
            )
        
        # Apply category filter
        category = filters.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Apply level filter
        level = filters.get('level')
        if level:
            queryset = queryset.filter(level=level)
        
        # Apply price filters
        min_price = filters.get('min_price')
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)
        
        max_price = filters.get('max_price')
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)
        
        # Apply free filter
        is_free = filters.get('is_free')
        if is_free is not None:
            if is_free:
                queryset = queryset.filter(price=0)
            else:
                queryset = queryset.filter(price__gt=0)
        
        # Apply featured filter
        is_featured = filters.get('is_featured')
        if is_featured is not None:
            queryset = queryset.filter(is_featured=is_featured)
        
        # Apply instructor filter
        instructor = filters.get('instructor')
        if instructor:
            queryset = queryset.filter(instructor__id=instructor)
        
        # Apply sorting
        sort_by = filters.get('sort_by', 'newest')
        sort_mapping = {
            'newest': '-created_at',
            'oldest': 'created_at',
            'price_asc': 'price',
            'price_desc': '-price',
            'popularity': '-enrollment_count',
            'rating': '-rating_average',
        }
        queryset = queryset.order_by(sort_mapping.get(sort_by, '-created_at'))
        
        # Paginate results
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = CourseListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = CourseListSerializer(queryset, many=True)
        return Response(serializer.data)


class CourseDetailView(APIView):
    """
    Detailed course view with full module/lesson tree.
    """
    permission_classes = [AllowAny]
    
    def get(self, request, pk):
        """
        Get detailed course information with nested modules and lessons.
        """
        try:
            course = Course.objects.select_related('instructor').prefetch_related(
                'modules',
                'modules__lessons',
                'modules__lessons__content_items'
            ).get(pk=pk, is_deleted=False)
        except Course.DoesNotExist:
            return Response(
                {'detail': 'Course not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check visibility permissions
        if course.status != 'published':
            if not request.user.is_authenticated:
                return Response(
                    {'detail': 'Course not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            if course.instructor != request.user and not request.user.is_staff:
                return Response(
                    {'detail': 'Course not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        if course.visibility == 'private':
            if not request.user.is_authenticated:
                return Response(
                    {'detail': 'Course not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            if course.instructor != request.user and not request.user.is_staff:
                return Response(
                    {'detail': 'Course not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        serializer = CourseDetailSerializer(course)
        return Response(serializer.data)


class ModuleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Module CRUD operations.
    """
    queryset = Module.objects.filter(is_deleted=False)
    serializer_class = ModuleSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return ModuleDetailSerializer
        return ModuleSerializer
    
    def get_queryset(self):
        """
        Filter modules based on course.
        """
        queryset = Module.objects.filter(is_deleted=False)
        
        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course__id=course_id)
        
        return queryset.select_related('course').prefetch_related('lessons')
    
    def perform_create(self, serializer):
        """Set audit fields on creation."""
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )
    
    def perform_update(self, serializer):
        """Update audit fields."""
        serializer.save(updated_by=self.request.user)


class LessonViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Lesson CRUD operations.
    """
    queryset = Lesson.objects.filter(is_deleted=False)
    serializer_class = LessonSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return LessonDetailSerializer
        return LessonSerializer
    
    def get_queryset(self):
        """
        Filter lessons based on module and course.
        """
        queryset = Lesson.objects.filter(is_deleted=False)
        
        module_id = self.request.query_params.get('module')
        if module_id:
            queryset = queryset.filter(module__id=module_id)
        
        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(module__course__id=course_id)
        
        return queryset.select_related('module', 'module__course').prefetch_related('content_items')
    
    def perform_create(self, serializer):
        """Set audit fields on creation."""
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )
    
    def perform_update(self, serializer):
        """Update audit fields."""
        serializer.save(updated_by=self.request.user)


class ContentItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ContentItem CRUD operations.
    """
    queryset = ContentItem.objects.filter(is_deleted=False)
    serializer_class = ContentItemSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        """
        Filter content items based on lesson, module, or course.
        """
        queryset = ContentItem.objects.filter(is_deleted=False)
        
        lesson_id = self.request.query_params.get('lesson')
        if lesson_id:
            queryset = queryset.filter(lesson__id=lesson_id)
        
        module_id = self.request.query_params.get('module')
        if module_id:
            queryset = queryset.filter(lesson__module__id=module_id)
        
        course_id = self.request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(lesson__module__course__id=course_id)
        
        return queryset.select_related('lesson', 'lesson__module', 'lesson__module__course')
    
    def perform_create(self, serializer):
        """Set audit fields on creation."""
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )
    
    def perform_update(self, serializer):
        """Update audit fields."""
        serializer.save(updated_by=self.request.user)


class ContentUploadView(APIView):
    """
    API endpoint for generating presigned URLs for content uploads.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Generate a presigned URL for uploading content.
        """
        serializer = ContentUploadUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        content_type = validated_data['content_type']
        filename = validated_data['filename']
        file_size = validated_data.get('file_size')
        content_id = validated_data.get('content_id')
        
        # Generate unique storage key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        file_ext = filename.split('.')[-1] if '.' in filename else ''
        
        # Build storage key path
        if content_id:
            storage_key = f"content/{content_id}/{content_type}/{timestamp}_{unique_id}.{file_ext}"
        else:
            storage_key = f"uploads/{request.user.id}/{content_type}/{timestamp}_{unique_id}.{file_ext}"
        
        # Generate presigned URL
        upload_url = self._generate_presigned_url(storage_key, content_type, file_size)
        
        response_data = {
            'upload_url': upload_url,
            'storage_key': storage_key,
            'expires_in': 3600,
            'fields': {},
            'headers': {
                'Content-Type': 'application/octet-stream',
            }
        }
        
        response_serializer = ContentUploadUrlResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)
        
        return Response(response_serializer.data)
    
    def _generate_presigned_url(self, storage_key, content_type, file_size=None):
        """
        Generate a presigned URL for uploading content.
        Mock implementation - replace with actual S3/MinIO client.
        """
        base_url = getattr(settings, 'STORAGE_BASE_URL', 'http://localhost:9000/media')
        return f"{base_url}/{storage_key}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"


class CourseStatsView(APIView):
    """
    API endpoint for course statistics and analytics.
    """
    permission_classes = [IsAdminOrReadOnly]
    
    def get(self, request):
        """
        Get overall course statistics.
        """
        total_courses = Course.objects.filter(is_deleted=False).count()
        published_courses = Course.objects.filter(is_deleted=False, status='published').count()
        draft_courses = Course.objects.filter(is_deleted=False, status='draft').count()
        archived_courses = Course.objects.filter(is_deleted=False, status='archived').count()
        
        total_enrollments = Course.objects.filter(is_deleted=False).aggregate(
            total=Sum('enrollment_count')
        )['total'] or 0
        
        avg_rating = Course.objects.filter(is_deleted=False, rating_count__gt=0).aggregate(
            avg=Avg('rating_average')
        )['avg'] or 0
        
        # Courses by category
        courses_by_category = {}
        for category, _ in Course.CATEGORY_CHOICES:
            count = Course.objects.filter(is_deleted=False, category=category).count()
            if count > 0:
                courses_by_category[category] = count
        
        # Courses by level
        courses_by_level = {}
        for level, _ in Course.LEVEL_CHOICES:
            count = Course.objects.filter(is_deleted=False, level=level).count()
            if count > 0:
                courses_by_level[level] = count
        
        stats = {
            'total_courses': total_courses,
            'published_courses': published_courses,
            'draft_courses': draft_courses,
            'archived_courses': archived_courses,
            'total_enrollments': total_enrollments,
            'average_rating': round(avg_rating, 2),
            'courses_by_category': courses_by_category,
            'courses_by_level': courses_by_level,
        }
        
        return Response(stats)
