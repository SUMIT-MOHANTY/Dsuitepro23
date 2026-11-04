"""
Courses Serializers for Enterprise LMS
Provides serializers for Course, Module, Lesson, and ContentItem models.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from apps.users.serializers import UserListSerializer
from .models import Course, Module, Lesson, ContentItem

User = get_user_model()


class ContentItemSerializer(serializers.ModelSerializer):
    """
    Serializer for ContentItem model.
    Handles content items within lessons (video, PDF, SCORM, text, etc.)
    """
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    module_id = serializers.UUIDField(source='module.id', read_only=True)
    course_id = serializers.UUIDField(source='course.id', read_only=True)
    
    class Meta:
        model = ContentItem
        fields = [
            'id', 'lesson', 'content_type', 'content_type_display',
            'title', 'storage_key', 'file_url', 'file_size',
            'duration_seconds', 'order_index', 'is_primary',
            'module_id', 'course_id', 'metadata',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class ContentItemListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for ContentItem list views.
    """
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    
    class Meta:
        model = ContentItem
        fields = [
            'id', 'content_type', 'content_type_display', 'title',
            'file_url', 'duration_seconds', 'order_index', 'is_primary',
        ]


class LessonSerializer(serializers.ModelSerializer):
    """
    Serializer for Lesson model.
    Handles lessons within modules with nested content items.
    """
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    course_id = serializers.UUIDField(source='course.id', read_only=True)
    content_items = ContentItemListSerializer(many=True, read_only=True)
    content_items_count = serializers.IntegerField(source='content_items.count', read_only=True)
    
    class Meta:
        model = Lesson
        fields = [
            'id', 'module', 'title', 'description',
            'content_type', 'content_type_display',
            'duration_minutes', 'order_index',
            'is_preview', 'is_required', 'status', 'status_display',
            'course_id', 'content_items', 'content_items_count',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class LessonDetailSerializer(LessonSerializer):
    """
    Detailed serializer for Lesson with full content items.
    """
    content_items = ContentItemSerializer(many=True, read_only=True)
    
    class Meta(LessonSerializer.Meta):
        fields = LessonSerializer.Meta.fields


class LessonListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for Lesson list views.
    """
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    content_items_count = serializers.IntegerField(source='content_items.count', read_only=True)
    
    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'content_type', 'content_type_display',
            'duration_minutes', 'order_index', 'is_preview', 'is_required',
            'status', 'content_items_count',
        ]


class ModuleSerializer(serializers.ModelSerializer):
    """
    Serializer for Module model.
    Handles modules within courses with nested lessons.
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    lessons = LessonListSerializer(many=True, read_only=True)
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)
    total_duration_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = Module
        fields = [
            'id', 'course', 'title', 'description',
            'order_index', 'status', 'status_display',
            'duration_minutes', 'total_duration_minutes',
            'course_title', 'lessons', 'lessons_count',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
    
    def get_total_duration_minutes(self, obj):
        """Calculate total duration including all lessons."""
        lessons_duration = sum(
            lesson.duration_minutes for lesson in obj.lessons.all()
        )
        return obj.duration_minutes + lessons_duration


class ModuleDetailSerializer(ModuleSerializer):
    """
    Detailed serializer for Module with full lessons.
    """
    lessons = LessonSerializer(many=True, read_only=True)
    
    class Meta(ModuleSerializer.Meta):
        fields = ModuleSerializer.Meta.fields


class ModuleListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for Module list views.
    """
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)
    
    class Meta:
        model = Module
        fields = [
            'id', 'title', 'description', 'order_index',
            'status', 'duration_minutes', 'lessons_count',
        ]


class CourseSerializer(serializers.ModelSerializer):
    """
    Base serializer for Course model.
    Provides common course fields and computed properties.
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    visibility_display = serializers.CharField(source='get_visibility_display', read_only=True)
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    currency_display = serializers.CharField(source='get_currency_display', read_only=True)
    
    instructor = UserListSerializer(read_only=True)
    instructor_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='instructor',
        write_only=True,
        required=False
    )
    
    modules_count = serializers.IntegerField(source='modules.count', read_only=True)
    total_lessons_count = serializers.SerializerMethodField()
    total_duration_display = serializers.CharField(source='duration_display', read_only=True)
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'description', 'syllabus',
            'category', 'category_display', 'level', 'level_display',
            'tags', 'instructor', 'instructor_id',
            'thumbnail', 'thumbnail_url',
            'status', 'status_display', 'visibility', 'visibility_display',
            'price', 'currency', 'currency_display',
            'duration_minutes', 'total_duration_display',
            'is_featured', 'max_enrollments',
            'enrollment_count', 'rating_average', 'rating_count',
            'published_at', 'start_date', 'end_date',
            'modules_count', 'total_lessons_count',
            'is_published', 'is_free',
            'metadata',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = [
            'id', 'slug', 'enrollment_count', 'rating_average', 'rating_count',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
    
    def get_total_lessons_count(self, obj):
        """Count total lessons across all modules."""
        return sum(module.lessons.count() for module in obj.modules.all())
    
    def validate(self, data):
        """
        Validate course data.
        """
        # Validate dates
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        # Validate price
        price = data.get('price', 0)
        if price < 0:
            raise serializers.ValidationError({
                'price': 'Price cannot be negative.'
            })
        
        return data


class CourseListSerializer(CourseSerializer):
    """
    Lightweight serializer for Course list/catalog views.
    Excludes detailed fields to improve performance.
    """
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'description',
            'category', 'category_display', 'level', 'level_display',
            'tags', 'instructor',
            'thumbnail', 'thumbnail_url',
            'status', 'visibility', 'price', 'currency',
            'duration_minutes', 'total_duration_display',
            'is_featured', 'enrollment_count', 'rating_average', 'rating_count',
            'published_at', 'modules_count', 'total_lessons_count',
            'is_free', 'created_at',
        ]


class CourseDetailSerializer(CourseSerializer):
    """
    Detailed serializer for Course with full nested modules/lessons tree.
    Used for course detail views.
    """
    modules = ModuleListSerializer(many=True, read_only=True)
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'description', 'syllabus',
            'category', 'category_display', 'level', 'level_display',
            'tags', 'instructor',
            'thumbnail', 'thumbnail_url',
            'status', 'status_display', 'visibility', 'visibility_display',
            'price', 'currency', 'currency_display',
            'duration_minutes', 'total_duration_display',
            'is_featured', 'max_enrollments',
            'enrollment_count', 'rating_average', 'rating_count',
            'published_at', 'start_date', 'end_date',
            'modules', 'modules_count', 'total_lessons_count',
            'is_published', 'is_free', 'metadata',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = [
            'id', 'slug', 'enrollment_count', 'rating_average', 'rating_count',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating courses.
    Handles write operations with validation.
    """
    instructor_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='instructor',
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = Course
        fields = [
            'title', 'description', 'syllabus',
            'category', 'level', 'tags',
            'instructor_id', 'thumbnail', 'thumbnail_url',
            'status', 'visibility',
            'price', 'currency',
            'duration_minutes', 'is_featured', 'max_enrollments',
            'start_date', 'end_date', 'metadata',
        ]
    
    def validate_status(self, value):
        """
        Validate status transitions.
        """
        instance = getattr(self, 'instance', None)
        
        if instance and instance.status == 'archived' and value != 'archived':
            raise serializers.ValidationError(
                'Cannot change status of an archived course. Create a new course instead.'
            )
        
        return value
    
    def validate(self, data):
        """
        Validate course data.
        """
        # Validate dates
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        # Validate price
        price = data.get('price', 0)
        if price < 0:
            raise serializers.ValidationError({
                'price': 'Price cannot be negative.'
            })
        
        # Validate publish requirements
        status = data.get('status')
        if status == 'published':
            if not data.get('title'):
                raise serializers.ValidationError({
                    'title': 'Title is required to publish a course.'
                })
        
        return data


class CoursePublishSerializer(serializers.Serializer):
    """
    Serializer for publishing a course.
    Validates that all requirements are met before publishing.
    """
    confirm = serializers.BooleanField(required=True, write_only=True)
    
    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError('Must confirm publishing action.')
        return value


class CatalogFilterSerializer(serializers.Serializer):
    """
    Serializer for catalog filter parameters.
    Used for validating query parameters.
    """
    search = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    level = serializers.CharField(required=False, allow_blank=True)
    min_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0
    )
    max_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0
    )
    instructor = serializers.UUIDField(required=False)
    is_free = serializers.BooleanField(required=False)
    is_featured = serializers.BooleanField(required=False)
    sort_by = serializers.ChoiceField(
        choices=[
            ('newest', 'Newest'),
            ('oldest', 'Oldest'),
            ('price_asc', 'Price: Low to High'),
            ('price_desc', 'Price: High to Low'),
            ('popularity', 'Most Popular'),
            ('rating', 'Highest Rated'),
        ],
        required=False,
        default='newest'
    )


class ContentUploadUrlSerializer(serializers.Serializer):
    """
    Serializer for generating presigned upload URLs.
    """
    CONTENT_TYPES = [
        ('video', 'Video'),
        ('pdf', 'PDF Document'),
        ('scorm', 'SCORM Package'),
        ('image', 'Image'),
        ('document', 'Document'),
        ('audio', 'Audio'),
    ]
    
    content_type = serializers.ChoiceField(choices=CONTENT_TYPES)
    filename = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField(min_value=1, required=False)
    content_id = serializers.UUIDField(required=False)
    
    def validate_filename(self, value):
        """Validate filename has allowed extension."""
        allowed_extensions = {
            'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm'],
            'pdf': ['.pdf'],
            'scorm': ['.zip'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
            'document': ['.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx'],
            'audio': ['.mp3', '.wav', '.aac', '.ogg'],
        }
        
        content_type = self.initial_data.get('content_type')
        if content_type:
            ext = '.' + value.split('.')[-1].lower() if '.' in value else ''
            allowed = allowed_extensions.get(content_type, [])
            if allowed and ext not in allowed:
                raise serializers.ValidationError(
                    f'Invalid file extension for {content_type}. Allowed: {", ".join(allowed)}'
                )
        
        return value


class ContentUploadUrlResponseSerializer(serializers.Serializer):
    """
    Serializer for presigned upload URL response.
    """
    upload_url = serializers.URLField()
    storage_key = serializers.CharField()
    expires_in = serializers.IntegerField(help_text='URL expiration time in seconds')
    fields = serializers.DictField(required=False, help_text='Additional form fields for POST uploads')
    headers = serializers.DictField(required=False, help_text='Required headers for PUT uploads')


class CourseStatsSerializer(serializers.Serializer):
    """
    Serializer for course statistics.
    """
    total_courses = serializers.IntegerField()
    published_courses = serializers.IntegerField()
    draft_courses = serializers.IntegerField()
    archived_courses = serializers.IntegerField()
    total_enrollments = serializers.IntegerField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    courses_by_category = serializers.DictField()
    courses_by_level = serializers.DictField()
