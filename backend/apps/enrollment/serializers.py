"""
Enrollment Serializers for Enterprise LMS
Provides serializers for Enrollment, LearningPath, LearningPathItem, and ProgressUpdate.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.courses.models import Course, Lesson
from apps.courses.serializers import CourseListSerializer, CourseDetailSerializer, LessonListSerializer
from apps.users.serializers import UserListSerializer
from .models import (
    Enrollment, LearningPath, LearningPathItem, LearningPathEnrollment,
    LessonProgress, PrerequisiteCourse, EnrollmentNote
)

User = get_user_model()


class EnrollmentNoteSerializer(serializers.ModelSerializer):
    """Serializer for enrollment notes."""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = EnrollmentNote
        fields = [
            'id', 'enrollment', 'note_type', 'content', 'created_by',
            'created_by_name', 'is_internal', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_name']


class LessonProgressSerializer(serializers.ModelSerializer):
    """Serializer for lesson progress records."""
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    lesson_duration = serializers.IntegerField(source='lesson.duration_minutes', read_only=True)
    module_title = serializers.CharField(source='lesson.module.title', read_only=True)
    
    class Meta:
        model = LessonProgress
        fields = [
            'id', 'enrollment', 'lesson', 'lesson_title', 'lesson_duration',
            'module_title', 'status', 'started_at', 'completed_at',
            'time_spent_minutes', 'progress_percentage', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'lesson_title', 'module_title', 'lesson_duration']


class LessonProgressUpdateSerializer(serializers.Serializer):
    """Serializer for updating lesson progress."""
    lesson_id = serializers.UUIDField(required=True)
    status = serializers.ChoiceField(
        choices=[
            ('not_started', 'Not Started'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('skipped', 'Skipped'),
        ],
        required=False
    )
    progress_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False
    )
    time_spent_minutes = serializers.IntegerField(min_value=0, required=False)


class EnrollmentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for enrollment list views."""
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_thumbnail = serializers.URLField(source='course.thumbnail_url', read_only=True)
    course_instructor = serializers.CharField(source='course.instructor.get_full_name', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'user', 'user_name', 'course', 'course_title', 'course_thumbnail',
            'course_instructor', 'status', 'progress_percentage', 'enrolled_at',
            'completed_at', 'last_accessed_at', 'certificate_issued'
        ]
        read_only_fields = ['id', 'enrolled_at', 'user_name', 'course_title', 'course_thumbnail', 'course_instructor']


class EnrollmentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for enrollment with nested data."""
    course = CourseDetailSerializer(read_only=True)
    user = UserListSerializer(read_only=True)
    lesson_progress = LessonProgressSerializer(many=True, read_only=True)
    notes = EnrollmentNoteSerializer(many=True, read_only=True)
    last_accessed_lesson_detail = LessonListSerializer(source='last_accessed_lesson', read_only=True)
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'user', 'course', 'status', 'progress_percentage',
            'enrolled_at', 'completed_at', 'last_accessed_lesson',
            'last_accessed_lesson_detail', 'last_accessed_at',
            'total_time_spent_minutes', 'certificate_issued', 'certificate_issued_at',
            'notes', 'lesson_progress', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'enrolled_at', 'created_at', 'updated_at']


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new enrollments."""
    course_id = serializers.UUIDField(write_only=True)
    user_id = serializers.UUIDField(write_only=True, required=False)
    
    class Meta:
        model = Enrollment
        fields = ['course_id', 'user_id', 'notes']
    
    def validate_course_id(self, value):
        """Validate that the course exists and is published."""
        try:
            course = Course.objects.get(id=value)
            if not course.is_published:
                raise serializers.ValidationError("Course is not published.")
            return value
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course does not exist.")
    
    def create(self, validated_data):
        course_id = validated_data.pop('course_id')
        user_id = validated_data.pop('user_id', None)
        
        # Get user from request context or user_id
        if user_id:
            user = User.objects.get(id=user_id)
        else:
            user = self.context['request'].user
        
        course = Course.objects.get(id=course_id)
        
        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'status': Enrollment.STATUS_PENDING,
                'notes': validated_data.get('notes', '')
            }
        )
        
        if not created:
            raise serializers.ValidationError("User is already enrolled in this course.")
        
        return enrollment


class EnrollmentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating enrollment status and notes."""
    
    class Meta:
        model = Enrollment
        fields = ['status', 'notes', 'progress_percentage']
    
    def validate_status(self, value):
        """Validate status transitions."""
        valid_transitions = {
            Enrollment.STATUS_PENDING: [Enrollment.STATUS_ACTIVE, Enrollment.STATUS_CANCELLED],
            Enrollment.STATUS_ACTIVE: [Enrollment.STATUS_COMPLETED, Enrollment.STATUS_DROPPED, Enrollment.STATUS_SUSPENDED],
            Enrollment.STATUS_SUSPENDED: [Enrollment.STATUS_ACTIVE, Enrollment.STATUS_CANCELLED],
            Enrollment.STATUS_DROPPED: [Enrollment.STATUS_ACTIVE],
            Enrollment.STATUS_CANCELLED: [],
            Enrollment.STATUS_COMPLETED: [],
        }
        
        instance = self.instance
        if instance and value != instance.status:
            if value not in valid_transitions.get(instance.status, []):
                raise serializers.ValidationError(
                    f"Cannot transition from {instance.status} to {value}."
                )
        return value


class ProgressUpdateSerializer(serializers.Serializer):
    """Serializer for updating course progress."""
    lesson_id = serializers.UUIDField(required=True)
    status = serializers.ChoiceField(
        choices=[
            ('not_started', 'Not Started'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('skipped', 'Skipped'),
        ],
        required=True
    )
    progress_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False
    )
    time_spent_minutes = serializers.IntegerField(min_value=0, required=False, default=0)


class LearningPathItemSerializer(serializers.ModelSerializer):
    """Serializer for learning path items."""
    course = CourseListSerializer(read_only=True)
    course_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = LearningPathItem
        fields = [
            'id', 'path', 'course', 'course_id', 'order_index',
            'is_required', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LearningPathItemListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for learning path items in list views."""
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_thumbnail = serializers.URLField(source='course.thumbnail_url', read_only=True)
    course_duration = serializers.IntegerField(source='course.duration_minutes', read_only=True)
    
    class Meta:
        model = LearningPathItem
        fields = [
            'id', 'course', 'course_title', 'course_thumbnail',
            'course_duration', 'order_index', 'is_required', 'description'
        ]


class LearningPathListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for learning path list views."""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    course_count = serializers.IntegerField(read_only=True)
    required_course_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = LearningPath
        fields = [
            'id', 'title', 'slug', 'description', 'category',
            'created_by_name', 'status', 'thumbnail', 'estimated_duration_hours',
            'is_featured', 'course_count', 'required_course_count',
            'published_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'course_count', 'required_course_count']


class LearningPathDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for learning paths with nested items."""
    items = LearningPathItemListSerializer(many=True, read_only=True)
    created_by = UserListSerializer(read_only=True)
    course_count = serializers.IntegerField(read_only=True)
    required_course_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = LearningPath
        fields = [
            'id', 'title', 'slug', 'description', 'category',
            'created_by', 'status', 'thumbnail', 'estimated_duration_hours',
            'is_featured', 'prerequisites', 'items', 'course_count',
            'required_course_count', 'published_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'course_count', 'required_course_count']


class LearningPathCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating learning paths."""
    
    class Meta:
        model = LearningPath
        fields = [
            'title', 'slug', 'description', 'category',
            'thumbnail', 'estimated_duration_hours', 'prerequisites'
        ]
    
    def validate_slug(self, value):
        """Validate that the slug is unique."""
        if LearningPath.objects.filter(slug=value).exists():
            raise serializers.ValidationError("A learning path with this slug already exists.")
        return value


class LearningPathUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating learning paths."""
    
    class Meta:
        model = LearningPath
        fields = [
            'title', 'description', 'category', 'thumbnail',
            'estimated_duration_hours', 'is_featured', 'prerequisites', 'status'
        ]
    
    def validate_status(self, value):
        """Validate status transitions."""
        instance = self.instance
        if instance and value != instance.status:
            if instance.status == LearningPath.STATUS_ARCHIVED:
                raise serializers.ValidationError("Cannot change status of an archived learning path.")
            if value == LearningPath.STATUS_PUBLISHED and not instance.published_at:
                self.instance.published_at = timezone.now()
        return value


class LearningPathEnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for learning path enrollments."""
    learning_path = LearningPathListSerializer(read_only=True)
    user = UserListSerializer(read_only=True)
    
    class Meta:
        model = LearningPathEnrollment
        fields = [
            'id', 'user', 'learning_path', 'status', 'progress_percentage',
            'enrolled_at', 'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'enrolled_at', 'created_at', 'updated_at']


class LearningPathEnrollmentCreateSerializer(serializers.Serializer):
    """Serializer for creating learning path enrollments."""
    learning_path_id = serializers.UUIDField(required=True)
    
    def validate_learning_path_id(self, value):
        """Validate that the learning path exists and is published."""
        try:
            path = LearningPath.objects.get(id=value)
            if not path.is_published:
                raise serializers.ValidationError("Learning path is not published.")
            return value
        except LearningPath.DoesNotExist:
            raise serializers.ValidationError("Learning path does not exist.")


class PrerequisiteCourseSerializer(serializers.ModelSerializer):
    """Serializer for prerequisite courses."""
    course_title = serializers.CharField(source='course.title', read_only=True)
    prerequisite_course_title = serializers.CharField(source='prerequisite_course.title', read_only=True)
    course_id = serializers.UUIDField(write_only=True)
    prerequisite_course_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = PrerequisiteCourse
        fields = [
            'id', 'course', 'course_id', 'course_title',
            'prerequisite_course', 'prerequisite_course_id', 'prerequisite_course_title',
            'is_strict', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'course_title', 'prerequisite_course_title']


class EnrollmentStatsSerializer(serializers.Serializer):
    """Serializer for enrollment statistics."""
    total_enrollments = serializers.IntegerField()
    active_enrollments = serializers.IntegerField()
    completed_enrollments = serializers.IntegerField()
    pending_enrollments = serializers.IntegerField()
    completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_progress = serializers.DecimalField(max_digits=5, decimal_places=2)


class MyEnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for user's own enrollments with course details."""
    course = CourseListSerializer(read_only=True)
    last_accessed_lesson_title = serializers.CharField(source='last_accessed_lesson.title', read_only=True)
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'status', 'progress_percentage',
            'enrolled_at', 'completed_at', 'last_accessed_at',
            'last_accessed_lesson', 'last_accessed_lesson_title',
            'total_time_spent_minutes', 'certificate_issued'
        ]
        read_only_fields = ['id', 'enrolled_at']


class BulkEnrollmentSerializer(serializers.Serializer):
    """Serializer for bulk enrollment operations."""
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100
    )
    course_id = serializers.UUIDField(required=True)
    send_notification = serializers.BooleanField(default=True)
    
    def validate_course_id(self, value):
        """Validate that the course exists."""
        try:
            Course.objects.get(id=value)
            return value
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course does not exist.")
    
    def validate_user_ids(self, value):
        """Validate that all users exist."""
        existing_users = set(User.objects.filter(id__in=value).values_list('id', flat=True))
        invalid_ids = set(value) - existing_users
        if invalid_ids:
            raise serializers.ValidationError(f"Invalid user IDs: {list(invalid_ids)}")
        return value


class EnrollmentUnenrollSerializer(serializers.Serializer):
    """Serializer for unenrollment requests."""
    reason = serializers.CharField(required=False, allow_blank=True)
    confirm = serializers.BooleanField(required=True)
    
    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Must confirm unenrollment.")
        return value
