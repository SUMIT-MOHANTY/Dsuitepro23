"""
Enrollment URL Configuration for Enterprise LMS
Provides URL routing for enrollment, learning paths, and progress tracking APIs.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EnrollmentViewSet,
    LearningPathViewSet,
    LearningPathItemViewSet,
    LearningPathEnrollmentViewSet,
    LessonProgressViewSet,
    PrerequisiteCourseViewSet,
    EnrollmentStatsView,
    EnrollmentNoteViewSet,
)

# Create router for ViewSets
router = DefaultRouter()

# Enrollment endpoints
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')

# Learning Path endpoints
router.register(r'learning-paths', LearningPathViewSet, basename='learning-path')
router.register(r'learning-path-items', LearningPathItemViewSet, basename='learning-path-item')
router.register(r'learning-path-enrollments', LearningPathEnrollmentViewSet, basename='learning-path-enrollment')

# Progress tracking endpoints
router.register(r'lesson-progress', LessonProgressViewSet, basename='lesson-progress')

# Prerequisite endpoints
router.register(r'prerequisites', PrerequisiteCourseViewSet, basename='prerequisite')

# Enrollment notes endpoints
router.register(r'enrollment-notes', EnrollmentNoteViewSet, basename='enrollment-note')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Additional enrollment endpoints
    path('enrollments/my/', EnrollmentViewSet.as_view({'get': 'my_enrollments'}), name='my-enrollments'),
    path('enrollments/<uuid:pk>/progress/', EnrollmentViewSet.as_view({'patch': 'update_progress'}), name='enrollment-progress'),
    path('enrollments/<uuid:pk>/unenroll/', EnrollmentViewSet.as_view({'post': 'unenroll'}), name='enrollment-unenroll'),
    path('enrollments/<uuid:pk>/certificate/', EnrollmentViewSet.as_view({'get': 'certificate_status'}), name='enrollment-certificate'),
    path('enrollments/bulk-create/', EnrollmentViewSet.as_view({'post': 'bulk_create'}), name='enrollment-bulk-create'),
    
    # Learning path additional endpoints
    path('learning-paths/<uuid:pk>/enroll/', LearningPathViewSet.as_view({'post': 'enroll'}), name='learning-path-enroll'),
    path('learning-paths/<uuid:pk>/items/', LearningPathViewSet.as_view({'get': 'items'}), name='learning-path-items'),
    path('learning-paths/<uuid:pk>/calculate-progress/', LearningPathViewSet.as_view({'post': 'calculate_progress'}), name='learning-path-calculate-progress'),
    path('learning-paths/featured/', LearningPathViewSet.as_view({'get': 'featured'}), name='learning-paths-featured'),
    path('learning-paths/by-category/<str:category>/', LearningPathViewSet.as_view({'get': 'by_category'}), name='learning-paths-by-category'),
    
    # Learning path enrollment endpoints
    path('learning-path-enrollments/my/', LearningPathEnrollmentViewSet.as_view({'get': 'my_enrollments'}), name='my-learning-path-enrollments'),
    path('learning-path-enrollments/<uuid:pk>/calculate-progress/', LearningPathEnrollmentViewSet.as_view({'post': 'calculate_progress'}), name='learning-path-enrollment-calculate-progress'),
    
    # Progress tracking endpoints
    path('lesson-progress/<uuid:pk>/mark-started/', LessonProgressViewSet.as_view({'post': 'mark_started'}), name='lesson-progress-mark-started'),
    path('lesson-progress/<uuid:pk>/mark-completed/', LessonProgressViewSet.as_view({'post': 'mark_completed'}), name='lesson-progress-mark-completed'),
    path('lesson-progress/by-enrollment/<uuid:enrollment_id>/', LessonProgressViewSet.as_view({'get': 'by_enrollment'}), name='lesson-progress-by-enrollment'),
    
    # Statistics endpoint
    path('stats/', EnrollmentStatsView.as_view(), name='enrollment-stats'),
    
    # Prerequisite check endpoint
    path('prerequisites/check/<uuid:course_id>/', PrerequisiteCourseViewSet.as_view({'get': 'check_prerequisites'}), name='check-prerequisites'),
    path('prerequisites/by-course/<uuid:course_id>/', PrerequisiteCourseViewSet.as_view({'get': 'by_course'}), name='prerequisites-by-course'),
]

# Main URL patterns that will be included in the project's urls.py
app_name = 'enrollment'
