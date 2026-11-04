"""
Enrollment Views for Enterprise LMS
Provides API endpoints for Enrollment, LearningPath, and Progress tracking.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg, Count
from django.utils import timezone

from apps.core.pagination import StandardResultsSetPagination
from apps.users.permissions import IsAdminOrReadOnly
from .models import (
    Enrollment, LearningPath, LearningPathItem, LearningPathEnrollment,
    LessonProgress, PrerequisiteCourse, EnrollmentNote
)
from .serializers import (
    EnrollmentListSerializer, EnrollmentDetailSerializer,
    EnrollmentCreateSerializer, EnrollmentUpdateSerializer,
    ProgressUpdateSerializer, LessonProgressSerializer,
    LearningPathListSerializer, LearningPathDetailSerializer,
    LearningPathCreateSerializer, LearningPathUpdateSerializer,
    LearningPathItemSerializer, LearningPathEnrollmentSerializer,
    LearningPathEnrollmentCreateSerializer, PrerequisiteCourseSerializer,
    EnrollmentNoteSerializer, EnrollmentStatsSerializer,
    MyEnrollmentSerializer, BulkEnrollmentSerializer,
    EnrollmentUnenrollSerializer
)
from .services import EnrollmentService, PrerequisiteValidator


class EnrollmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing enrollments.
    Provides CRUD operations and custom actions for enrollment management.
    """
    queryset = Enrollment.objects.all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['status', 'course', 'user']
    ordering_fields = ['enrolled_at', 'updated_at', 'progress_percentage', 'completed_at']
    ordering = ['-enrolled_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'course__title']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return EnrollmentListSerializer
        elif self.action == 'create':
            return EnrollmentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return EnrollmentUpdateSerializer
        elif self.action == 'my_enrollments':
            return MyEnrollmentSerializer
        return EnrollmentDetailSerializer
    
    def get_permissions(self):
        """Define permissions based on action."""
        if self.action in ['create', 'my_enrollments', 'update_progress', 'unenroll']:
            permission_classes = [IsAuthenticated]
        elif self.action in ['list', 'retrieve', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminOrReadOnly]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """Create enrollment with current user."""
        serializer.save()
    
    @action(detail=False, methods=['get'], url_path='my')
    def my_enrollments(self, request):
        """
        Get current user's enrollments.
        GET /api/v1/enrollments/my/
        """
        enrollments = Enrollment.objects.filter(
            user=request.user,
            is_deleted=False
        ).select_related('course', 'last_accessed_lesson')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            enrollments = enrollments.filter(status=status_filter)
        
        # Filter by progress range
        min_progress = request.query_params.get('min_progress')
        max_progress = request.query_params.get('max_progress')
        if min_progress is not None:
            enrollments = enrollments.filter(progress_percentage__gte=min_progress)
        if max_progress is not None:
            enrollments = enrollments.filter(progress_percentage__lte=max_progress)
        
        page = self.paginate_queryset(enrollments)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(enrollments, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='progress')
    def update_progress(self, request, pk=None):
        """
        Update lesson progress for an enrollment.
        POST /api/v1/enrollments/{id}/progress/
        """
        enrollment = self.get_object()
        
        # Check if user owns this enrollment or is admin
        if enrollment.user != request.user and not request.user.is_admin():
            return Response(
                {'detail': 'You do not have permission to update this enrollment.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            result = EnrollmentService.update_lesson_progress(
                enrollment=enrollment,
                lesson_id=serializer.validated_data['lesson_id'],
                status=serializer.validated_data.get('status'),
                progress_percentage=serializer.validated_data.get('progress_percentage'),
                time_spent_minutes=serializer.validated_data.get('time_spent_minutes', 0)
            )
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'], url_path='lesson-progress')
    def lesson_progress(self, request, pk=None):
        """
        Get lesson progress for an enrollment.
        GET /api/v1/enrollments/{id}/lesson-progress/
        """
        enrollment = self.get_object()
        
        # Check permissions
        if enrollment.user != request.user and not request.user.is_admin():
            return Response(
                {'detail': 'You do not have permission to view this enrollment.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        progress = LessonProgress.objects.filter(
            enrollment=enrollment
        ).select_related('lesson', 'lesson__module')
        
        serializer = LessonProgressSerializer(progress, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='unenroll')
    def unenroll(self, request, pk=None):
        """
        Unenroll from a course.
        POST /api/v1/enrollments/{id}/unenroll/
        """
        enrollment = self.get_object()
        
        # Check if user owns this enrollment or is admin
        if enrollment.user != request.user and not request.user.is_admin():
            return Response(
                {'detail': 'You do not have permission to unenroll from this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = EnrollmentUnenrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Update enrollment status to cancelled
        enrollment.status = Enrollment.STATUS_CANCELLED
        enrollment.save(update_fields=['status', 'updated_at'])
        
        # Add note if reason provided
        reason = serializer.validated_data.get('reason', '')
        if reason:
            EnrollmentNote.objects.create(
                enrollment=enrollment,
                note_type=EnrollmentNote.NOTE_TYPE_GENERAL,
                content=f"Unenrolled: {reason}",
                created_by=request.user if request.user.is_authenticated else None,
                is_internal=False
            )
        
        return Response(
            {'detail': 'Successfully unenrolled from course.'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        """
        Get enrollment statistics.
        GET /api/v1/enrollments/{id}/stats/
        """
        enrollment = self.get_object()
        
        lesson_progress = LessonProgress.objects.filter(enrollment=enrollment)
        total_lessons = lesson_progress.count()
        completed_lessons = lesson_progress.filter(status=LessonProgress.STATUS_COMPLETED).count()
        in_progress_lessons = lesson_progress.filter(status=LessonProgress.STATUS_IN_PROGRESS).count()
        
        stats = {
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'in_progress_lessons': in_progress_lessons,
            'not_started_lessons': total_lessons - completed_lessons - in_progress_lessons,
            'completion_percentage': enrollment.progress_percentage,
            'total_time_spent_minutes': enrollment.total_time_spent_minutes,
            'days_since_enrollment': (timezone.now() - enrollment.enrolled_at).days if enrollment.enrolled_at else 0,
        }
        
        return Response(stats)
    
    @action(detail=False, methods=['post'], url_path='bulk-enroll')
    def bulk_enroll(self, request):
        """
        Bulk enroll users in a course.
        POST /api/v1/enrollments/bulk-enroll/
        """
        if not request.user.is_admin():
            return Response(
                {'detail': 'Admin permission required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = BulkEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        course_id = serializer.validated_data['course_id']
        user_ids = serializer.validated_data['user_ids']
        send_notification = serializer.validated_data.get('send_notification', True)
        
        from apps.courses.models import Course
        course = get_object_or_404(Course, id=course_id)
        
        results = {'created': [], 'existing': [], 'failed': []}
        
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                enrollment, created = Enrollment.objects.get_or_create(
                    user=user,
                    course=course,
                    defaults={'status': Enrollment.STATUS_ACTIVE}
                )
                
                if created:
                    results['created'].append(str(user_id))
                else:
                    results['existing'].append(str(user_id))
            except Exception as e:
                results['failed'].append({'user_id': str(user_id), 'error': str(e)})
        
        return Response(results, status=status.HTTP_200_OK)


class LearningPathViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing learning paths.
    Provides CRUD operations and enrollment functionality.
    """
    queryset = LearningPath.objects.filter(is_deleted=False)
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['status', 'category', 'is_featured', 'created_by']
    ordering_fields = ['created_at', 'published_at', 'title', 'estimated_duration_hours']
    ordering = ['-created_at']
    search_fields = ['title', 'description']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return LearningPathListSerializer
        elif self.action == 'create':
            return LearningPathCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LearningPathUpdateSerializer
        return LearningPathDetailSerializer
    
    def get_permissions(self):
        """Define permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'add_item', 'remove_item']:
            permission_classes = [IsAdminOrReadOnly]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter queryset based on user permissions."""
        queryset = LearningPath.objects.filter(is_deleted=False)
        
        # Non-admin users only see published paths
        if not self.request.user.is_authenticated or not self.request.user.is_admin():
            queryset = queryset.filter(status=LearningPath.STATUS_PUBLISHED)
        
        return queryset.select_related('created_by').prefetch_related('items', 'items__course')
    
    def perform_create(self, serializer):
        """Create learning path with current user as creator."""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'], url_path='enroll')
    def enroll(self, request, pk=None):
        """
        Enroll current user in a learning path.
        POST /api/v1/learning-paths/{id}/enroll/
        """
        learning_path = self.get_object()
        
        # Check if already enrolled
        existing = LearningPathEnrollment.objects.filter(
            user=request.user,
            learning_path=learning_path
        ).first()
        
        if existing:
            return Response(
                {'detail': 'Already enrolled in this learning path.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create learning path enrollment
        path_enrollment = LearningPathEnrollment.objects.create(
            user=request.user,
            learning_path=learning_path,
            status=LearningPathEnrollment.STATUS_ACTIVE
        )
        
        # Cascade enrollment to all courses in the path
        items = learning_path.items.all()
        enrolled_courses = []
        failed_courses = []
        
        for item in items:
            try:
                # Check prerequisites
                prereq_check = PrerequisiteValidator.check_prerequisites(
                    user=request.user,
                    course=item.course
                )
                
                if prereq_check['can_enroll']:
                    enrollment, created = Enrollment.objects.get_or_create(
                        user=request.user,
                        course=item.course,
                        defaults={'status': Enrollment.STATUS_ACTIVE}
                    )
                    if created:
                        enrolled_courses.append(item.course.title)
                else:
                    failed_courses.append({
                        'course': item.course.title,
                        'reason': 'Prerequisites not met'
                    })
            except Exception as e:
                failed_courses.append({
                    'course': item.course.title,
                    'reason': str(e)
                })
        
        serializer = LearningPathEnrollmentSerializer(path_enrollment)
        return Response({
            'enrollment': serializer.data,
            'enrolled_courses': enrolled_courses,
            'failed_courses': failed_courses
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path='add-item')
    def add_item(self, request, pk=None):
        """
        Add a course to a learning path.
        POST /api/v1/learning-paths/{id}/add-item/
        """
        learning_path = self.get_object()
        
        serializer = LearningPathItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set the learning path
        serializer.validated_data['path'] = learning_path
        item = LearningPathItem.objects.create(**serializer.validated_data)
        
        return Response(
            LearningPathItemSerializer(item).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'], url_path='remove-item')
    def remove_item(self, request, pk=None):
        """
        Remove a course from a learning path.
        POST /api/v1/learning-paths/{id}/remove-item/
        """
        learning_path = self.get_object()
        item_id = request.data.get('item_id')
        
        if not item_id:
            return Response(
                {'detail': 'item_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            item = LearningPathItem.objects.get(id=item_id, path=learning_path)
            item.delete()
            return Response(
                {'detail': 'Item removed successfully.'},
                status=status.HTTP_200_OK
            )
        except LearningPathItem.DoesNotExist:
            return Response(
                {'detail': 'Item not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'], url_path='items')
    def get_items(self, request, pk=None):
        """
        Get all items in a learning path.
        GET /api/v1/learning-paths/{id}/items/
        """
        learning_path = self.get_object()
        items = learning_path.items.all().select_related('course')
        
        serializer = LearningPathItemSerializer(items, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='my-paths')
    def my_paths(self, request):
        """
        Get learning paths the user is enrolled in.
        GET /api/v1/learning-paths/my-paths/
        """
        enrollments = LearningPathEnrollment.objects.filter(
            user=request.user
        ).select_related('learning_path')
        
        paths = [e.learning_path for e in enrollments]
        serializer = LearningPathListSerializer(paths, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='featured')
    def featured(self, request):
        """
        Get featured learning paths.
        GET /api/v1/learning-paths/featured/
        """
        paths = LearningPath.objects.filter(
            is_featured=True,
            status=LearningPath.STATUS_PUBLISHED,
            is_deleted=False
        )
        
        serializer = LearningPathListSerializer(paths, many=True)
        return Response(serializer.data)


class LearningPathItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing learning path items.
    """
    queryset = LearningPathItem.objects.all()
    serializer_class = LearningPathItemSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['path', 'course', 'is_required']
    ordering_fields = ['order_index', 'created_at']
    ordering = ['path', 'order_index']


class LearningPathEnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing learning path enrollments.
    """
    queryset = LearningPathEnrollment.objects.all()
    serializer_class = LearningPathEnrollmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'learning_path']
    ordering_fields = ['enrolled_at', 'progress_percentage', 'completed_at']
    ordering = ['-enrolled_at']
    
    def get_queryset(self):
        """Filter to user's own enrollments unless admin."""
        if self.request.user.is_admin():
            return LearningPathEnrollment.objects.all()
        return LearningPathEnrollment.objects.filter(user=self.request.user)


class LessonProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing lesson progress.
    """
    queryset = LessonProgress.objects.all()
    serializer_class = LessonProgressSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['enrollment', 'lesson', 'status']
    ordering_fields = ['created_at', 'completed_at', 'progress_percentage']
    ordering = ['enrollment', 'lesson__module__order_index', 'lesson__order_index']
    
    def get_queryset(self):
        """Filter to user's own progress unless admin."""
        if self.request.user.is_admin():
            return LessonProgress.objects.all()
        return LessonProgress.objects.filter(enrollment__user=self.request.user)


class PrerequisiteCourseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing prerequisite courses.
    """
    queryset = PrerequisiteCourse.objects.all()
    serializer_class = PrerequisiteCourseSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['course', 'prerequisite_course', 'is_strict']


class EnrollmentStatsView(viewsets.ViewSet):
    """
    ViewSet for enrollment statistics and analytics.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        Get overall enrollment statistics.
        GET /api/v1/enrollment-stats/
        """
        if not request.user.is_admin():
            return Response(
                {'detail': 'Admin permission required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        total = Enrollment.objects.filter(is_deleted=False).count()
        active = Enrollment.objects.filter(status=Enrollment.STATUS_ACTIVE).count()
        completed = Enrollment.objects.filter(status=Enrollment.STATUS_COMPLETED).count()
        pending = Enrollment.objects.filter(status=Enrollment.STATUS_PENDING).count()
        
        completion_rate = (completed / total * 100) if total > 0 else 0
        avg_progress = Enrollment.objects.filter(
            is_deleted=False
        ).aggregate(avg=Avg('progress_percentage'))['avg'] or 0
        
        stats = {
            'total_enrollments': total,
            'active_enrollments': active,
            'completed_enrollments': completed,
            'pending_enrollments': pending,
            'completion_rate': round(completion_rate, 2),
            'average_progress': round(avg_progress, 2)
        }
        
        serializer = EnrollmentStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='by-course')
    def by_course(self, request):
        """
        Get enrollment statistics grouped by course.
        GET /api/v1/enrollment-stats/by-course/
        """
        if not request.user.is_admin():
            return Response(
                {'detail': 'Admin permission required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.courses.models import Course
        courses = Course.objects.filter(is_deleted=False)
        
        stats = []
        for course in courses:
            course_stats = Enrollment.objects.filter(
                course=course,
                is_deleted=False
            ).aggregate(
                total=Count('id'),
                active=Count('id', filter=Q(status=Enrollment.STATUS_ACTIVE)),
                completed=Count('id', filter=Q(status=Enrollment.STATUS_COMPLETED)),
                avg_progress=Avg('progress_percentage')
            )
            
            stats.append({
                'course_id': str(course.id),
                'course_title': course.title,
                'total_enrollments': course_stats['total'],
                'active_enrollments': course_stats['active'],
                'completed_enrollments': course_stats['completed'],
                'average_progress': round(course_stats['avg_progress'] or 0, 2)
            })
        
        return Response(stats)
    
    @action(detail=False, methods=['get'], url_path='by-user')
    def by_user(self, request):
        """
        Get enrollment statistics for a specific user.
        GET /api/v1/enrollment-stats/by-user/?user_id={id}
        """
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {'detail': 'user_id query parameter required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Users can only view their own stats unless admin
        if str(request.user.id) != user_id and not request.user.is_admin():
            return Response(
                {'detail': 'You can only view your own statistics.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'detail': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        user_stats = Enrollment.objects.filter(
            user=user,
            is_deleted=False
        ).aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status=Enrollment.STATUS_ACTIVE)),
            completed=Count('id', filter=Q(status=Enrollment.STATUS_COMPLETED)),
            pending=Count('id', filter=Q(status=Enrollment.STATUS_PENDING)),
            avg_progress=Avg('progress_percentage')
        )
        
        completion_rate = (
            user_stats['completed'] / user_stats['total'] * 100
        ) if user_stats['total'] > 0 else 0
        
        stats = {
            'user_id': str(user.id),
            'user_name': user.get_full_name(),
            'total_enrollments': user_stats['total'],
            'active_enrollments': user_stats['active'],
            'completed_enrollments': user_stats['completed'],
            'pending_enrollments': user_stats['pending'],
            'completion_rate': round(completion_rate, 2),
            'average_progress': round(user_stats['avg_progress'] or 0, 2)
        }
        
        return Response(stats)


class EnrollmentNoteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing enrollment notes.
    """
    queryset = EnrollmentNote.objects.all()
    serializer_class = EnrollmentNoteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['enrollment', 'note_type', 'is_internal']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter notes based on user permissions."""
        queryset = EnrollmentNote.objects.all()
        
        # Non-admin users only see non-internal notes for their enrollments
        if not self.request.user.is_admin():
            queryset = queryset.filter(
                Q(is_internal=False) | 
                Q(enrollment__user=self.request.user)
            )
        
        return queryset.select_related('enrollment', 'created_by')
    
    def perform_create(self, serializer):
        """Set created_by to current user."""
        serializer.save(created_by=self.request.user)
