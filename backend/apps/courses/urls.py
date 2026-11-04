"""
Courses URL Configuration for Enterprise LMS
Provides URL routing for courses, modules, lessons, content items, and catalog endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CourseViewSet,
    CatalogView,
    CourseDetailView,
    ModuleViewSet,
    LessonViewSet,
    ContentItemViewSet,
    ContentUploadView,
    CourseStatsView,
)

# Create a router for viewsets
router = DefaultRouter()

# Register viewsets
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'modules', ModuleViewSet, basename='module')
router.register(r'lessons', LessonViewSet, basename='lesson')
router.register(r'content-items', ContentItemViewSet, basename='content-item')

# URL patterns
urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Catalog endpoints
    path('catalog/', CatalogView.as_view(), name='catalog-list'),
    path('catalog/<uuid:pk>/', CourseDetailView.as_view(), name='catalog-detail'),
    
    # Course-specific endpoints
    path('courses/<uuid:course_id>/upload-url/', 
         ContentUploadView.as_view(), 
         name='course-upload-url'),
    path('courses/<uuid:course_id>/stats/', 
         CourseStatsView.as_view(), 
         name='course-stats'),
    
    # Module-specific endpoints for a course
    path('courses/<uuid:course_id>/modules/', 
         ModuleViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='course-modules-list'),
    
    # Lesson-specific endpoints for a module
    path('modules/<uuid:module_id>/lessons/', 
         LessonViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='module-lessons-list'),
    
    # Content item endpoints for a lesson
    path('lessons/<uuid:lesson_id>/content-items/', 
         ContentItemViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='lesson-content-items-list'),
]
