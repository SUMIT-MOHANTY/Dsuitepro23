"""
Analytics Views for Enterprise LMS
Provides API endpoints for audit logs, security events, and analytics data.
"""

import csv
import json
import logging
from datetime import datetime, timedelta
from io import StringIO

from django.db.models import Q, Count, Avg, Sum, F
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.pagination import StandardResultsSetPagination
from apps.users.models import User
from apps.courses.models import Course
from apps.enrollment.models import Enrollment
from apps.assessment.models import QuizAttempt, Grade
from apps.certificates.models import Certificate
from .models import (
    SecurityAuditLog, AuditLogExport, UserActivityLog,
    UserActivity, AuditLog, ReportJob
)
from .services import (
    AuditLoggingService, AuditLogExportService, AuditLogQueryService,
    UserActivityService, DataRetentionService, ReportGenerationService
)
from .reports import (
    GDPRDataExportService, SOC2ReportService, AnalyticsAggregationService
)

logger = logging.getLogger(__name__)


# =============================================================================
# Serializers
# =============================================================================

class SecurityAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for SecurityAuditLog model."""
    
    class Meta:
        model = SecurityAuditLog
        fields = [
            'id', 'timestamp', 'event_type', 'event_category', 'severity',
            'actor_user', 'actor_email', 'target_resource', 'target_resource_id',
            'outcome', 'reason', 'details', 'ip_address', 'user_agent',
            'request_method', 'request_path', 'response_time_ms',
            'current_hash', 'hash_verified'
        ]
        read_only_fields = fields


class AuditLogExportSerializer(serializers.ModelSerializer):
    """Serializer for AuditLogExport model."""
    requested_by_email = serializers.CharField(source='requested_by.email', read_only=True)
    
    class Meta:
        model = AuditLogExport
        fields = [
            'id', 'requested_by', 'requested_by_email', 'start_date', 'end_date',
            'event_categories', 'severity_levels', 'export_format', 'status',
            'file_path', 'file_size', 'record_count', 'error_message',
            'started_at', 'completed_at', 'created_at'
        ]
        read_only_fields = fields


class UserActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for UserActivityLog model."""
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = UserActivityLog
        fields = [
            'id', 'user', 'user_email', 'action', 'entity_type', 'entity_id',
            'metadata', 'ip_address', 'user_agent', 'created_at'
        ]
        read_only_fields = fields


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for UserActivity model."""
    actor_email = serializers.CharField(source='actor.email', read_only=True)
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'event_type', 'actor', 'actor_email', 'target_type',
            'target_id', 'metadata', 'ip_address', 'user_agent', 'created_at'
        ]
        read_only_fields = fields


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AuditLog model."""
    actor_email = serializers.CharField(source='actor.email', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'action', 'resource_type', 'resource_id', 'actor', 'actor_email',
            'changes', 'justification', 'ip_address', 'user_agent', 'created_at'
        ]
        read_only_fields = fields


class ReportJobSerializer(serializers.ModelSerializer):
    """Serializer for ReportJob model."""
    requested_by_email = serializers.CharField(source='requested_by.email', read_only=True)
    
    class Meta:
        model = ReportJob
        fields = [
            'id', 'report_type', 'status', 'requested_by', 'requested_by_email',
            'parameters', 'file_path', 'file_size', 'record_count',
            'started_at', 'completed_at', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'requested_by', 'file_path', 'file_size',
                          'record_count', 'started_at', 'completed_at', 'error_message', 'created_at']


class LearnerDashboardSerializer(serializers.Serializer):
    """Serializer for learner dashboard data."""
    enrolled_courses = serializers.IntegerField()
    completed_courses = serializers.IntegerField()
    in_progress_courses = serializers.IntegerField()
    average_progress = serializers.FloatField()
    certificates_earned = serializers.IntegerField()
    upcoming_deadlines = serializers.ListField()
    recent_activity = serializers.ListField()
    learning_streak = serializers.IntegerField()
    total_learning_time = serializers.IntegerField()


class InstructorDashboardSerializer(serializers.Serializer):
    """Serializer for instructor dashboard data."""
    total_courses = serializers.IntegerField()
    total_students = serializers.IntegerField()
    average_completion_rate = serializers.FloatField()
    average_assessment_score = serializers.FloatField()
    course_analytics = serializers.ListField()
    recent_submissions = serializers.ListField()
    student_engagement = serializers.DictField()


class AdminDashboardSerializer(serializers.Serializer):
    """Serializer for admin dashboard data."""
    system_health = serializers.DictField()
    user_analytics = serializers.DictField()
    content_analytics = serializers.DictField()
    compliance_metrics = serializers.DictField()


class GDPRExportRequestSerializer(serializers.Serializer):
    """Serializer for GDPR export request."""
    user_id = serializers.UUIDField(required=False)
    email_when_ready = serializers.BooleanField(default=True)


class AuditLogQuerySerializer(serializers.Serializer):
    """Serializer for audit log query requests."""
    filters = serializers.DictField(required=False, default=dict)
    date_range = serializers.DictField(required=False, default=dict)
    aggregation = serializers.CharField(required=False, allow_blank=True)


# =============================================================================
# ViewSets
# =============================================================================

class SecurityAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for querying security audit logs.
    Provides endpoints for listing, filtering, and exporting audit logs.
    """
    queryset = SecurityAuditLog.objects.all()
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['event_category', 'severity', 'event_type', 'outcome']
    ordering_fields = ['timestamp', 'created_at', 'severity']
    ordering = ['-timestamp']
    search_fields = ['actor_email', 'target_resource', 'reason', 'details']

    def get_queryset(self):
        """
        Get queryset with optional date range filtering.
        """
        queryset = SecurityAuditLog.objects.all()
        
        # Date range filtering
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                queryset = queryset.filter(timestamp__gte=start)
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                queryset = queryset.filter(timestamp__lte=end)
            except ValueError:
                pass
        
        # Actor filtering
        actor_id = self.request.query_params.get('actor_id')
        if actor_id:
            queryset = queryset.filter(actor_user_id=actor_id)
        
        # IP address filtering
        ip_address = self.request.query_params.get('ip_address')
        if ip_address:
            queryset = queryset.filter(ip_address=ip_address)
        
        return queryset

    def list(self, request, *args, **kwargs):
        """
        List audit logs with filtering and pagination.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get summary statistics
        total_count = queryset.count()
        critical_count = queryset.filter(severity=SecurityAuditLog.SEVERITY_CRITICAL).count()
        warning_count = queryset.filter(severity=SecurityAuditLog.SEVERITY_WARNING).count()
        
        # Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response_data = {
                'results': serializer.data,
                'summary': {
                    'total': total_count,
                    'critical': critical_count,
                    'warning': warning_count,
                    'info': total_count - critical_count - warning_count
                }
            }
            return self.get_paginated_response(response_data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'summary': {
                'total': total_count,
                'critical': critical_count,
                'warning': warning_count,
                'info': total_count - critical_count - warning_count
            }
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get audit log summary statistics.
        """
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        queryset = SecurityAuditLog.objects.filter(timestamp__gte=start_date)
        
        # Event category distribution
        category_stats = queryset.values('event_category').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Severity distribution
        severity_stats = queryset.values('severity').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Daily event counts
        daily_stats = queryset.extra(
            select={'date': "DATE(timestamp)"}
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Top actors
        top_actors = queryset.exclude(actor_user=None).values(
            'actor_user__email'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Failed login attempts
        failed_logins = queryset.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        ).count()
        
        return Response({
            'period_days': days,
            'total_events': queryset.count(),
            'category_distribution': list(category_stats),
            'severity_distribution': list(severity_stats),
            'daily_counts': list(daily_stats),
            'top_actors': list(top_actors),
            'failed_login_attempts': failed_logins,
            'failed_login_trend': 'increasing' if failed_logins > 100 else 'stable'
        })

    @action(detail=False, methods=['post'])
    def export(self, request):
        """
        Export audit logs to file.
        POST /api/v1/analytics/audit-logs/export/
        """
        # Get export parameters
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')
        export_format = request.data.get('format', 'csv')
        event_categories = request.data.get('event_categories', [])
        severity_levels = request.data.get('severity_levels', [])
        
        # Validate dates
        try:
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            else:
                start_date = timezone.now() - timedelta(days=30)
            
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            else:
                end_date = timezone.now()
        except ValueError as e:
            return Response(
                {'error': 'Invalid date format. Use ISO 8601 format.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create export record
        export_record = AuditLogExport.objects.create(
            requested_by=request.user,
            start_date=start_date,
            end_date=end_date,
            event_categories=event_categories,
            severity_levels=severity_levels,
            export_format=export_format,
            status=AuditLogExport.STATUS_PROCESSING,
            started_at=timezone.now()
        )
        
        try:
            # Build queryset
            queryset = SecurityAuditLog.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date
            )
            
            if event_categories:
                queryset = queryset.filter(event_category__in=event_categories)
            if severity_levels:
                queryset = queryset.filter(severity__in=severity_levels)
            
            # Generate export based on format
            if export_format == 'csv':
                return self._export_csv(queryset, export_record)
            elif export_format == 'json':
                return self._export_json(queryset, export_record)
            else:
                return Response(
                    {'error': f'Unsupported format: {export_format}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Audit log export failed: {str(e)}")
            export_record.status = AuditLogExport.STATUS_FAILED
            export_record.error_message = str(e)
            export_record.completed_at = timezone.now()
            export_record.save()
            return Response(
                {'error': 'Export failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _export_csv(self, queryset, export_record):
        """
        Export audit logs as CSV.
        """
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="audit_logs_{export_record.id}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Timestamp', 'Event Type', 'Category', 'Severity',
            'Actor Email', 'Target Resource', 'Outcome',
            'Reason', 'IP Address', 'Request Method', 'Request Path',
            'Response Time (ms)', 'Details'
        ])
        
        # Write data
        record_count = 0
        for log in queryset.iterator(chunk_size=1000):
            writer.writerow([
                log.timestamp.isoformat(),
                log.event_type,
                log.event_category,
                log.severity,
                log.actor_email,
                log.target_resource,
                log.outcome,
                log.reason,
                log.ip_address,
                log.request_method,
                log.request_path,
                log.response_time_ms,
                json.dumps(log.details) if log.details else ''
            ])
            record_count += 1
        
        # Update export record
        export_record.status = AuditLogExport.STATUS_COMPLETED
        export_record.record_count = record_count
        export_record.completed_at = timezone.now()
        export_record.save()
        
        # Log the export
        AuditLoggingService.log_sensitive_data_access(
            event_type='audit_log_export',
            actor_user=self.request.user,
            target_resource='SecurityAuditLog',
            target_resource_id=str(export_record.id),
            details={
                'export_id': str(export_record.id),
                'record_count': record_count,
                'format': 'csv'
            },
            ip_address=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            request_path=self.request.path
        )
        
        return response

    def _export_json(self, queryset, export_record):
        """
        Export audit logs as JSON.
        """
        # Create JSON response
        response = HttpResponse(content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="audit_logs_{export_record.id}.json"'
        
        data = []
        record_count = 0
        for log in queryset.iterator(chunk_size=1000):
            data.append({
                'timestamp': log.timestamp.isoformat(),
                'event_type': log.event_type,
                'event_category': log.event_category,
                'severity': log.severity,
                'actor': {
                    'id': str(log.actor_user_id) if log.actor_user_id else None,
                    'email': log.actor_email
                },
                'target': {
                    'resource': log.target_resource,
                    'resource_id': log.target_resource_id
                },
                'outcome': log.outcome,
                'reason': log.reason,
                'request_context': {
                    'ip_address': str(log.ip_address) if log.ip_address else None,
                    'user_agent': log.user_agent,
                    'method': log.request_method,
                    'path': log.request_path
                },
                'response_time_ms': log.response_time_ms,
                'details': log.details,
                'hash': log.current_hash
            })
            record_count += 1
        
        response.write(json.dumps({
            'export_metadata': {
                'id': str(export_record.id),
                'generated_at': timezone.now().isoformat(),
                'record_count': record_count,
                'start_date': export_record.start_date.isoformat(),
                'end_date': export_record.end_date.isoformat()
            },
            'logs': data
        }, indent=2))
        
        # Update export record
        export_record.status = AuditLogExport.STATUS_COMPLETED
        export_record.record_count = record_count
        export_record.completed_at = timezone.now()
        export_record.save()
        
        return response

    @action(detail=False, methods=['post'])
    def verify_integrity(self, request):
        """
        Verify the integrity of the audit log hash chain.
        """
        start_from = request.data.get('start_from')
        
        if start_from:
            try:
                start_from = datetime.fromisoformat(start_from.replace('Z', '+00:00'))
            except ValueError:
                return Response(
                    {'error': 'Invalid start_from date format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        is_valid, broken_at_id = SecurityAuditLog.verify_chain_integrity(start_from)
        
        return Response({
            'is_valid': is_valid,
            'broken_at_id': str(broken_at_id) if broken_at_id else None,
            'message': 'Hash chain integrity verified' if is_valid else f'Hash chain broken at log {broken_at_id}'
        })


class AuditLogExportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing audit log exports.
    """
    queryset = AuditLogExport.objects.all()
    serializer_class = AuditLogExportSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'export_format']
    ordering_fields = ['created_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Superusers can see all exports, others only their own.
        """
        if self.request.user.is_superuser:
            return AuditLogExport.objects.all()
        return AuditLogExport.objects.filter(requested_by=self.request.user)


class UserActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user activity logs.
    """
    queryset = UserActivityLog.objects.all()
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['action', 'entity_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Users can only see their own activity logs unless they're admin.
        """
        if self.request.user.is_staff:
            return UserActivityLog.objects.all()
        return UserActivityLog.objects.filter(user=self.request.user)


class UserActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for UserActivity model (compliance-grade activity tracking).
    """
    queryset = UserActivity.objects.all()
    serializer_class = UserActivitySerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['event_type', 'target_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    search_fields = ['actor__email', 'target_type', 'metadata']

    def get_queryset(self):
        """Get queryset with filtering."""
        queryset = UserActivity.objects.all()
        
        # Date range filtering
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__gte=start)
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__lte=end)
            except ValueError:
                pass
        
        return queryset


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AuditLog model (administrative action tracking).
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['action', 'resource_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    search_fields = ['actor__email', 'resource_type', 'justification']

    def get_queryset(self):
        """Get queryset with filtering."""
        queryset = AuditLog.objects.all()
        
        # Date range filtering
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__gte=start)
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__lte=end)
            except ValueError:
                pass
        
        return queryset


class ReportJobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ReportJob model.
    """
    queryset = ReportJob.objects.all()
    serializer_class = ReportJobSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['report_type', 'status']
    ordering_fields = ['created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Superusers can see all jobs, others only their own.
        """
        if self.request.user.is_superuser:
            return ReportJob.objects.all()
        return ReportJob.objects.filter(requested_by=self.request.user)

    def perform_create(self, serializer):
        """Set the requesting user."""
        serializer.save(requested_by=self.request.user)


# =============================================================================
# Dashboard Views
# =============================================================================

class LearnerDashboardView(APIView):
    """
    Dashboard endpoint for learner analytics.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get learner dashboard data.
        """
        user = request.user
        
        # Get user's enrollments
        enrollments = Enrollment.objects.filter(user=user)
        
        # Calculate statistics
        total_enrolled = enrollments.count()
        completed = enrollments.filter(status='completed').count()
        in_progress = enrollments.filter(status='active').count()
        
        # Calculate average progress
        avg_progress = enrollments.aggregate(
            avg=Avg('progress_percent')
        )['avg'] or 0
        
        # Get certificates
        certificates_count = Certificate.objects.filter(user=user).count()
        
        # Get recent activity
        recent_activity = UserActivity.objects.filter(
            actor=user
        ).order_by('-created_at')[:10]
        
        activity_data = [
            {
                'event_type': act.event_type,
                'target_type': act.target_type,
                'created_at': act.created_at.isoformat(),
                'metadata': act.metadata
            }
            for act in recent_activity
        ]
        
        # Calculate learning streak (simplified)
        learning_streak = 5  # Placeholder - would calculate from actual activity
        
        # Total learning time (placeholder)
        total_learning_time = 1200  # minutes
        
        data = {
            'enrolled_courses': total_enrolled,
            'completed_courses': completed,
            'in_progress_courses': in_progress,
            'average_progress': round(avg_progress, 2),
            'certificates_earned': certificates_count,
            'upcoming_deadlines': [],  # Would populate from assignments
            'recent_activity': activity_data,
            'learning_streak': learning_streak,
            'total_learning_time': total_learning_time
        }
        
        serializer = LearnerDashboardSerializer(data)
        return Response(serializer.data)


class InstructorDashboardView(APIView):
    """
    Dashboard endpoint for instructor analytics.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get instructor dashboard data.
        """
        user = request.user
        
        # Get courses taught by this instructor
        courses = Course.objects.filter(instructor=user)
        total_courses = courses.count()
        
        # Get total unique students
        total_students = Enrollment.objects.filter(
            course__in=courses
        ).values('user').distinct().count()
        
        # Calculate completion rate
        course_enrollments = Enrollment.objects.filter(course__in=courses)
        completed_count = course_enrollments.filter(status='completed').count()
        total_enrollments = course_enrollments.count()
        avg_completion_rate = (completed_count / total_enrollments * 100) if total_enrollments > 0 else 0
        
        # Calculate average assessment score
        quiz_attempts = QuizAttempt.objects.filter(
            quiz__course__in=courses,
            status='completed'
        )
        avg_score = quiz_attempts.aggregate(avg=Avg('score'))['avg'] or 0
        
        # Course analytics
        course_analytics = []
        for course in courses:
            course_enrolls = Enrollment.objects.filter(course=course)
            course_stats = {
                'course_id': str(course.id),
                'course_title': course.title,
                'enrollment_count': course_enrolls.count(),
                'completion_rate': 0,
                'average_score': 0
            }
            if course_enrolls.count() > 0:
                completed = course_enrolls.filter(status='completed').count()
                course_stats['completion_rate'] = round(completed / course_enrolls.count() * 100, 2)
            course_analytics.append(course_stats)
        
        data = {
            'total_courses': total_courses,
            'total_students': total_students,
            'average_completion_rate': round(avg_completion_rate, 2),
            'average_assessment_score': round(avg_score, 2),
            'course_analytics': course_analytics,
            'recent_submissions': [],  # Would populate from submissions
            'student_engagement': {
                'active_today': 0,
                'active_this_week': 0,
                'active_this_month': 0
            }
        }
        
        serializer = InstructorDashboardSerializer(data)
        return Response(serializer.data)


class AdminDashboardView(APIView):
    """
    Dashboard endpoint for admin system health and analytics.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get admin dashboard data.
        """
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        # System health metrics
        system_health = self._get_system_health(start_date)
        
        # User analytics
        user_analytics = self._get_user_analytics(start_date)
        
        # Content analytics
        content_analytics = self._get_content_analytics(start_date)
        
        # Compliance metrics
        compliance_metrics = self._get_compliance_metrics(start_date)
        
        data = {
            'system_health': system_health,
            'user_analytics': user_analytics,
            'content_analytics': content_analytics,
            'compliance_metrics': compliance_metrics
        }
        
        serializer = AdminDashboardSerializer(data)
        return Response(serializer.data)
    
    def _get_system_health(self, start_date):
        """Get system health metrics."""
        # Get API response times from audit logs
        api_logs = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            response_time_ms__isnull=False
        )
        
        response_times = api_logs.values_list('response_time_ms', flat=True)
        response_time_list = list(response_times)
        
        if response_time_list:
            sorted_times = sorted(response_time_list)
            p50_idx = len(sorted_times) // 2
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)
            
            p50 = sorted_times[min(p50_idx, len(sorted_times) - 1)]
            p95 = sorted_times[min(p95_idx, len(sorted_times) - 1)]
            p99 = sorted_times[min(p99_idx, len(sorted_times) - 1)]
        else:
            p50 = p95 = p99 = 0
        
        # Error rates
        total_requests = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date
        ).count()
        
        failed_requests = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            outcome='failure'
        ).count()
        
        error_rate = (failed_requests / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'api_response_times': {
                'p50_ms': p50,
                'p95_ms': p95,
                'p99_ms': p99
            },
            'error_rate_percent': round(error_rate, 2),
            'total_requests': total_requests,
            'failed_requests': failed_requests,
            'queue_depth': 0,  # Would integrate with Celery/Django Q
            'storage_utilization': {
                'used_gb': 0,
                'total_gb': 100,
                'percent_used': 0
            }
        }
    
    def _get_user_analytics(self, start_date):
        """Get user analytics metrics."""
        # DAU/MAU
        today = timezone.now().date()
        month_ago = today - timedelta(days=30)
        
        # Daily active users (from activity logs)
        dau = UserActivity.objects.filter(
            created_at__date=today
        ).values('actor').distinct().count()
        
        # Monthly active users
        mau = UserActivity.objects.filter(
            created_at__date__gte=month_ago
        ).values('actor').distinct().count()
        
        # Registration funnel
        total_users = User.objects.filter(is_active=True).count()
        new_users = User.objects.filter(
            date_joined__gte=start_date
        ).count()
        
        # Role distribution
        role_distribution = User.objects.filter(
            is_active=True
        ).values('role').annotate(
            count=Count('id')
        )
        
        return {
            'dau': dau,
            'mau': mau,
            'dau_mau_ratio': round(dau / mau, 2) if mau > 0 else 0,
            'total_users': total_users,
            'new_users': new_users,
            'registration_funnel': {
                'visitors': 0,  # Would track from analytics
                'signups': new_users,
                'activations': new_users  # Simplified
            },
            'role_distribution': list(role_distribution)
        }
    
    def _get_content_analytics(self, start_date):
        """Get content analytics metrics."""
        # Course enrollment counts
        total_courses = Course.objects.filter(status='published').count()
        total_enrollments = Enrollment.objects.count()
        
        # Completion rates
        completed_enrollments = Enrollment.objects.filter(status='completed').count()
        completion_rate = (completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0
        
        # Average time to complete (placeholder)
        avg_time_to_complete = 14  # days
        
        # Assessment score distributions
        score_distribution = QuizAttempt.objects.filter(
            status='completed',
            completed_at__gte=start_date
        ).aggregate(
            avg_score=Avg('score'),
            min_score=Min('score'),
            max_score=Max('score')
        )
        
        # Top courses
        top_courses = Course.objects.filter(
            status='published'
        ).annotate(
            enrollment_count=Count('enrollments')
        ).order_by('-enrollment_count')[:5]
        
        top_courses_data = [
            {
                'id': str(c.id),
                'title': c.title,
                'enrollments': c.enrollment_count
            }
            for c in top_courses
        ]
        
        return {
            'total_courses': total_courses,
            'total_enrollments': total_enrollments,
            'completion_rate': round(completion_rate, 2),
            'average_time_to_complete_days': avg_time_to_complete,
            'assessment_scores': {
                'average': round(score_distribution['avg_score'] or 0, 2),
                'min': score_distribution['min_score'] or 0,
                'max': score_distribution['max_score'] or 0
            },
            'top_courses': top_courses_data
        }
    
    def _get_compliance_metrics(self, start_date):
        """Get compliance metrics."""
        # Failed login attempts
        failed_logins = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        ).count()
        
        # Password reset frequency
        password_resets = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_type=SecurityAuditLog.EVENT_PASSWORD_RESET
        ).count()
        
        # Privilege escalation events
        privilege_events = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_type__in=[
                SecurityAuditLog.EVENT_ROLE_ASSIGNED,
                SecurityAuditLog.EVENT_ROLE_REVOKED
            ]
        ).count()
        
        # Impersonation events
        impersonation_events = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_category=SecurityAuditLog.CATEGORY_IMPERSONATION
        ).count()
        
        return {
            'failed_login_attempts': failed_logins,
            'password_reset_frequency': password_resets,
            'privilege_escalation_events': privilege_events,
            'impersonation_events': impersonation_events,
            'suspicious_activities': failed_logins > 100
        }


class SecurityDashboardView(APIView):
    """
    Security dashboard endpoint providing overview of security metrics.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get security dashboard data.
        """
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        # Recent security events
        recent_events = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date
        ).order_by('-timestamp')[:10]
        
        # Failed login attempts
        failed_logins = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        )
        
        # Suspicious IPs (multiple failed logins)
        suspicious_ips = failed_logins.values('ip_address').annotate(
            count=Count('id')
        ).filter(count__gte=5).order_by('-count')[:10]
        
        # Access denied events
        access_denied = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED
        ).count()
        
        # Critical events
        critical_events = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            severity=SecurityAuditLog.SEVERITY_CRITICAL
        ).count()
        
        # Impersonation events
        impersonation_events = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            event_category=SecurityAuditLog.CATEGORY_IMPERSONATION
        ).count()
        
        return Response({
            'period_days': days,
            'summary': {
                'total_events': SecurityAuditLog.objects.filter(timestamp__gte=start_date).count(),
                'failed_logins': failed_logins.count(),
                'access_denied': access_denied,
                'critical_events': critical_events,
                'impersonation_events': impersonation_events
            },
            'recent_events': [
                {
                    'id': str(event.id),
                    'timestamp': event.timestamp.isoformat(),
                    'event_type': event.event_type,
                    'severity': event.severity,
                    'actor': event.actor_email,
                    'outcome': event.outcome,
                    'reason': event.reason
                }
                for event in recent_events
            ],
            'suspicious_ips': [
                {
                    'ip_address': item['ip_address'],
                    'failed_attempts': item['count']
                }
                for item in suspicious_ips
            ],
            'recommendations': self._generate_recommendations(
                failed_logins.count(),
                access_denied,
                critical_events,
                suspicious_ips
            )
        })

    def _generate_recommendations(self, failed_logins, access_denied, critical_events, suspicious_ips):
        """
        Generate security recommendations based on metrics.
        """
        recommendations = []
        
        if failed_logins > 100:
            recommendations.append({
                'severity': 'high',
                'message': 'High number of failed login attempts detected. Consider enabling IP-based rate limiting.',
                'action': 'Review authentication settings'
            })
        
        if suspicious_ips:
            recommendations.append({
                'severity': 'medium',
                'message': f'{len(suspicious_ips)} IP addresses with multiple failed login attempts detected.',
                'action': 'Review and potentially block suspicious IPs'
            })
        
        if critical_events > 10:
            recommendations.append({
                'severity': 'critical',
                'message': 'Multiple critical security events detected. Immediate review required.',
                'action': 'Investigate critical events immediately'
            })
        
        if access_denied > 50:
            recommendations.append({
                'severity': 'low',
                'message': 'Elevated access denied events. Review permission configurations.',
                'action': 'Audit permission settings'
            })
        
        if not recommendations:
            recommendations.append({
                'severity': 'info',
                'message': 'No significant security concerns detected.',
                'action': 'Continue monitoring'
            })
        
        return recommendations


# =============================================================================
# Compliance Views
# =============================================================================

class GDPRExportView(APIView):
    """
    GDPR data export endpoint.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        Trigger GDPR data export for a user.
        """
        serializer = GDPRExportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user_id = serializer.validated_data.get('user_id')
        email_when_ready = serializer.validated_data.get('email_when_ready', True)
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            user = request.user
        
        # Create report job
        report_job = ReportJob.objects.create(
            report_type=ReportJob.TYPE_GDPR_EXPORT,
            requested_by=request.user,
            parameters={
                'target_user_id': str(user.id),
                'email_when_ready': email_when_ready
            },
            status=ReportJob.STATUS_PENDING
        )
        
        # Trigger async export task
        from .tasks import generate_gdpr_export
        generate_gdpr_export.delay(report_job.id)
        
        return Response({
            'message': 'GDPR export initiated',
            'job_id': str(report_job.id),
            'status': report_job.status
        }, status=status.HTTP_202_ACCEPTED)


class SOC2ReportView(APIView):
    """
    SOC 2 compliance report endpoint.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        Generate SOC 2 compliance report.
        """
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')
        
        try:
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            else:
                start_date = timezone.now() - timedelta(days=90)
            
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            else:
                end_date = timezone.now()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use ISO 8601 format.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create report job
        report_job = ReportJob.objects.create(
            report_type=ReportJob.TYPE_SOC2,
            requested_by=request.user,
            parameters={
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            status=ReportJob.STATUS_PENDING
        )
        
        # Trigger async report generation
        from .tasks import generate_soc2_report
        generate_soc2_report.delay(report_job.id)
        
        return Response({
            'message': 'SOC 2 report generation initiated',
            'job_id': str(report_job.id),
            'status': report_job.status
        }, status=status.HTTP_202_ACCEPTED)


class AuditLogQueryView(APIView):
    """
    Advanced audit log query endpoint with flexible filtering.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        Query audit logs with complex filters.
        """
        serializer = AuditLogQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        filters_data = serializer.validated_data.get('filters', {})
        date_range = serializer.validated_data.get('date_range', {})
        aggregation = serializer.validated_data.get('aggregation')
        
        # Build base queryset
        queryset = SecurityAuditLog.objects.all()
        
        # Apply date range
        if date_range.get('start'):
            try:
                start = datetime.fromisoformat(date_range['start'].replace('Z', '+00:00'))
                queryset = queryset.filter(timestamp__gte=start)
            except ValueError:
                pass
        
        if date_range.get('end'):
            try:
                end = datetime.fromisoformat(date_range['end'].replace('Z', '+00:00'))
                queryset = queryset.filter(timestamp__lte=end)
            except ValueError:
                pass
        
        # Apply filters
        if filters_data.get('event_types'):
            queryset = queryset.filter(event_type__in=filters_data['event_types'])
        
        if filters_data.get('categories'):
            queryset = queryset.filter(event_category__in=filters_data['categories'])
        
        if filters_data.get('severities'):
            queryset = queryset.filter(severity__in=filters_data['severities'])
        
        if filters_data.get('outcomes'):
            queryset = queryset.filter(outcome__in=filters_data['outcomes'])
        
        if filters_data.get('actor_ids'):
            queryset = queryset.filter(actor_user_id__in=filters_data['actor_ids'])
        
        if filters_data.get('ip_addresses'):
            queryset = queryset.filter(ip_address__in=filters_data['ip_addresses'])
        
        # Apply aggregation if requested
        if aggregation:
            if aggregation == 'by_category':
                results = queryset.values('event_category').annotate(
                    count=Count('id')
                ).order_by('-count')
                return Response({'aggregation': 'by_category', 'results': list(results)})
            
            elif aggregation == 'by_day':
                results = queryset.extra(
                    select={'day': "DATE(timestamp)"}
                ).values('day').annotate(
                    count=Count('id')
                ).order_by('day')
                return Response({'aggregation': 'by_day', 'results': list(results)})
            
            elif aggregation == 'by_hour':
                results = queryset.extra(
                    select={'hour': "DATE_TRUNC('hour', timestamp)"}
                ).values('hour').annotate(
                    count=Count('id')
                ).order_by('hour')
                return Response({'aggregation': 'by_hour', 'results': list(results)})
        
        # Return paginated results
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            data = [
                {
                    'id': str(log.id),
                    'timestamp': log.timestamp.isoformat(),
                    'event_type': log.event_type,
                    'event_category': log.event_category,
                    'severity': log.severity,
                    'actor': {
                        'id': str(log.actor_user_id) if log.actor_user_id else None,
                        'email': log.actor_email
                    },
                    'target': {
                        'resource': log.target_resource,
                        'resource_id': log.target_resource_id
                    },
                    'outcome': log.outcome,
                    'reason': log.reason,
                    'ip_address': str(log.ip_address) if log.ip_address else None,
                    'request_path': log.request_path,
                    'response_time_ms': log.response_time_ms
                }
                for log in page
            ]
            return paginator.get_paginated_response(data)
        
        return Response({'count': queryset.count(), 'results': []})


class DataRetentionView(APIView):
    """
    Data retention policy management endpoint.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get data retention status.
        """
        # Get counts of records by retention status
        from django.db.models import Q
        
        seven_years_ago = timezone.now() - timedelta(days=7*365)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        # UserActivity records pending anonymization
        pending_anonymization = UserActivity.objects.filter(
            created_at__lte=seven_years_ago,
            ip_address__isnull=False
        ).count()
        
        # Soft-deleted records pending purge
        # This would check is_deleted flags across models
        
        return Response({
            'retention_policy': {
                'pii_anonymization_years': 7,
                'soft_delete_grace_days': 30,
                'permanent_purge_after_days': 30
            },
            'pending_anonymization': pending_anonymization,
            'last_run': None,  # Would track from job logs
            'next_scheduled_run': None
        })

    def post(self, request):
        """
        Trigger data retention policy enforcement.
        """
        dry_run = request.data.get('dry_run', True)
        
        from .tasks import enforce_data_retention
        enforce_data_retention.delay(dry_run=dry_run)
        
        return Response({
            'message': 'Data retention enforcement initiated',
            'dry_run': dry_run,
            'status': 'queued'
        })


# =============================================================================
# Analytics Aggregation Views
# =============================================================================

class AnalyticsAggregationView(APIView):
    """
    View for analytics aggregation data (materialized views).
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get aggregated analytics data.
        """
        metric_type = request.query_params.get('metric', 'daily_active_users')
        days = int(request.query_params.get('days', 30))
        
        start_date = timezone.now() - timedelta(days=days)
        
        if metric_type == 'daily_active_users':
            data = self._get_daily_active_users(start_date)
        elif metric_type == 'course_completion_rates':
            data = self._get_course_completion_rates(start_date)
        elif metric_type == 'assessment_averages':
            data = self._get_assessment_averages(start_date)
        else:
            return Response(
                {'error': f'Unknown metric type: {metric_type}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'metric': metric_type,
            'period_days': days,
            'data': data
        })
    
    def _get_daily_active_users(self, start_date):
        """Get daily active users."""
        from django.db.models.functions import TruncDate
        
        daily_users = UserActivity.objects.filter(
            created_at__gte=start_date
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('actor', distinct=True)
        ).order_by('date')
        
        return [
            {
                'date': item['date'].isoformat(),
                'active_users': item['count']
            }
            for item in daily_users
        ]
    
    def _get_course_completion_rates(self, start_date):
        """Get course completion rates."""
        courses = Course.objects.filter(status='published').annotate(
            total_enrollments=Count('enrollments'),
            completed_enrollments=Count(
                'enrollments',
                filter=Q(enrollments__status='completed')
            )
        )
        
        return [
            {
                'course_id': str(c.id),
                'course_title': c.title,
                'total_enrollments': c.total_enrollments,
                'completed_enrollments': c.completed_enrollments,
                'completion_rate': round(
                    c.completed_enrollments / c.total_enrollments * 100, 2
                ) if c.total_enrollments > 0 else 0
            }
            for c in courses
        ]
    
    def _get_assessment_averages(self, start_date):
        """Get assessment score averages."""
        from django.db.models import Avg, Min, Max
        
        stats = QuizAttempt.objects.filter(
            status='completed',
            completed_at__gte=start_date
        ).aggregate(
            avg_score=Avg('score'),
            min_score=Min('score'),
            max_score=Max('score'),
            total_attempts=Count('id')
        )
        
        return {
            'average_score': round(stats['avg_score'] or 0, 2),
            'min_score': stats['min_score'] or 0,
            'max_score': stats['max_score'] or 0,
            'total_attempts': stats['total_attempts']
        }


# =============================================================================
# Function-Based Views (for URL compatibility)
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_audit_log_summary(request):
    """
    Get audit log summary statistics.
    """
    days = int(request.query_params.get('days', 7))
    start_date = timezone.now() - timedelta(days=days)
    
    queryset = SecurityAuditLog.objects.filter(timestamp__gte=start_date)
    
    return Response({
        'period_days': days,
        'total_events': queryset.count(),
        'failed_logins': queryset.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        ).count(),
        'critical_events': queryset.filter(
            severity=SecurityAuditLog.SEVERITY_CRITICAL
        ).count()
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def trigger_retention_policy(request):
    """
    Trigger data retention policy enforcement.
    """
    dry_run = request.data.get('dry_run', True)
    
    from .tasks import enforce_data_retention
    enforce_data_retention.delay(dry_run=dry_run)
    
    return Response({
        'message': 'Data retention enforcement initiated',
        'dry_run': dry_run
    })
