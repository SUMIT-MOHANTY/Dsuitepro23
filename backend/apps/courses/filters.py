"""
Courses Filters for Enterprise LMS
Provides django-filter FilterSet classes for course catalog search and filtering.
"""

import django_filters
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import Course, Module, Lesson, ContentItem

User = get_user_model()


class CourseFilter(django_filters.FilterSet):
    """
    FilterSet for Course model.
    Supports search, category filtering, level filtering, price range, and instructor filtering.
    """
    search = django_filters.CharFilter(
        method='filter_search',
        help_text="Search in title, description, and tags"
    )
    category = django_filters.CharFilter(
        field_name='category',
        lookup_expr='iexact',
        help_text="Filter by category (case-insensitive)"
    )
    level = django_filters.CharFilter(
        field_name='level',
        lookup_expr='iexact',
        help_text="Filter by difficulty level"
    )
    min_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='gte',
        help_text="Minimum price filter"
    )
    max_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='lte',
        help_text="Maximum price filter"
    )
    instructor = django_filters.UUIDFilter(
        field_name='instructor__id',
        help_text="Filter by instructor UUID"
    )
    is_free = django_filters.BooleanFilter(
        method='filter_is_free',
        help_text="Filter for free courses only"
    )
    is_featured = django_filters.BooleanFilter(
        field_name='is_featured',
        help_text="Filter for featured courses"
    )
    status = django_filters.CharFilter(
        field_name='status',
        lookup_expr='iexact',
        help_text="Filter by course status"
    )
    visibility = django_filters.CharFilter(
        field_name='visibility',
        lookup_expr='iexact',
        help_text="Filter by visibility level"
    )
    
    class Meta:
        model = Course
        fields = [
            'category', 'level', 'instructor', 'status', 'visibility',
            'is_featured', 'currency',
        ]
    
    def filter_search(self, queryset, name, value):
        """
        Search across title, description, syllabus, and tags.
        Uses case-insensitive partial matching.
        """
        if not value:
            return queryset
        
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(syllabus__icontains=value) |
            Q(tags__icontains=value)
        )
    
    def filter_is_free(self, queryset, name, value):
        """
        Filter courses by free/paid status.
        """
        if value:
            return queryset.filter(price=0)
        else:
            return queryset.filter(price__gt=0)


class ModuleFilter(django_filters.FilterSet):
    """
    FilterSet for Module model.
    Supports filtering by course, status, and ordering.
    """
    course = django_filters.UUIDFilter(
        field_name='course__id',
        help_text="Filter by course UUID"
    )
    status = django_filters.CharFilter(
        field_name='status',
        lookup_expr='iexact',
        help_text="Filter by module status"
    )
    
    class Meta:
        model = Module
        fields = ['course', 'status']


class LessonFilter(django_filters.FilterSet):
    """
    FilterSet for Lesson model.
    Supports filtering by module, content type, status, and preview availability.
    """
    module = django_filters.UUIDFilter(
        field_name='module__id',
        help_text="Filter by module UUID"
    )
    course = django_filters.UUIDFilter(
        field_name='module__course__id',
        help_text="Filter by course UUID"
    )
    content_type = django_filters.CharFilter(
        field_name='content_type',
        lookup_expr='iexact',
        help_text="Filter by content type"
    )
    status = django_filters.CharFilter(
        field_name='status',
        lookup_expr='iexact',
        help_text="Filter by lesson status"
    )
    is_preview = django_filters.BooleanFilter(
        field_name='is_preview',
        help_text="Filter for preview lessons"
    )
    is_required = django_filters.BooleanFilter(
        field_name='is_required',
        help_text="Filter by required status"
    )
    
    class Meta:
        model = Lesson
        fields = ['module', 'content_type', 'status', 'is_preview', 'is_required']


class ContentItemFilter(django_filters.FilterSet):
    """
    FilterSet for ContentItem model.
    Supports filtering by lesson, content type, and primary status.
    """
    lesson = django_filters.UUIDFilter(
        field_name='lesson__id',
        help_text="Filter by lesson UUID"
    )
    module = django_filters.UUIDFilter(
        field_name='lesson__module__id',
        help_text="Filter by module UUID"
    )
    course = django_filters.UUIDFilter(
        field_name='lesson__module__course__id',
        help_text="Filter by course UUID"
    )
    content_type = django_filters.CharFilter(
        field_name='content_type',
        lookup_expr='iexact',
        help_text="Filter by content type"
    )
    is_primary = django_filters.BooleanFilter(
        field_name='is_primary',
        help_text="Filter for primary content items"
    )
    
    class Meta:
        model = ContentItem
        fields = ['lesson', 'content_type', 'is_primary']


class CatalogFilter:
    """
    Helper class for catalog filtering with sorting support.
    Provides static methods for common catalog operations.
    """
    
    SORT_OPTIONS = {
        'newest': '-created_at',
        'oldest': 'created_at',
        'price_asc': 'price',
        'price_desc': '-price',
        'popularity': '-enrollment_count',
        'rating': '-rating_average',
        'title_asc': 'title',
        'title_desc': '-title',
    }
    
    @classmethod
    def apply_sort(cls, queryset, sort_by):
        """
        Apply sorting to a course queryset.
        
        Args:
            queryset: Course queryset to sort
            sort_by: Sort option key
            
        Returns:
            Sorted queryset
        """
        sort_field = cls.SORT_OPTIONS.get(sort_by, '-created_at')
        return queryset.order_by(sort_field)
    
    @classmethod
    def get_sort_choices(cls):
        """
        Get available sort choices for API documentation.
        
        Returns:
            List of tuples with sort keys and display names
        """
        return [
            ('newest', 'Newest First'),
            ('oldest', 'Oldest First'),
            ('price_asc', 'Price: Low to High'),
            ('price_desc', 'Price: High to Low'),
            ('popularity', 'Most Popular'),
            ('rating', 'Highest Rated'),
            ('title_asc', 'Title: A-Z'),
            ('title_desc', 'Title: Z-A'),
        ]
    
    @classmethod
    def get_visible_courses(cls, queryset, user=None):
        """
        Filter courses based on visibility rules.
        
        Args:
            queryset: Course queryset to filter
            user: Current user (optional)
            
        Returns:
            Filtered queryset with only visible courses
        """
        # Base filter: published courses
        queryset = queryset.filter(status='published')
        
        if user and user.is_authenticated:
            # Authenticated users can see public, enrolled-only, and their own courses
            queryset = queryset.filter(
                Q(visibility='public') |
                Q(visibility='enrolled') |
                Q(instructor=user)
            )
        else:
            # Anonymous users can only see public courses
            queryset = queryset.filter(visibility='public')
        
        return queryset
