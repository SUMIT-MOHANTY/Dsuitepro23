"""
Analytics Views for Enterprise LMS
Provides API endpoints for audit logs, security events, and analytics data.
"""

import csv
import json
import logging
from datetime import datetime, timedelta
from io import StringIO

from django.db.models import Q, Count, Avg
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsAdminOrReadOnly
from .models import SecurityAuditLog, AuditLogExport, UserActivityLog
from .services import AuditLoggingService, AuditLogExportService, AuditLogQueryService

logger = logging.getLogger(__name__)


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
            user=request.user if hasattr(self, 'request') else None,
            action='audit_log_export',
            resource='SecurityAuditLog',
            details={
                'export_id': str(export_record.id),
                'record_count': record_count,
                'format': 'csv'
            },
            ip_address=self.request.META.get('REMOTE_ADDR') if hasattr(self, 'request') else None
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

    @action(detail=False, methods=['get'])
    def verify_integrity(self, request):
        """
        Verify the integrity of the audit log hash chain.
        """
        start_from = request.query_params.get('start_from')
        
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
            'integrity_verified': is_valid,
            'broken_at_entry': str(broken_at_id) if broken_at_id else None,
            'checked_from': start_from.isoformat() if start_from else 'beginning',
            'message': 'Hash chain integrity verified' if is_valid else f'Chain broken at entry {broken_at_id}'
        })


class AuditLogExportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing audit log exports.
    """
    queryset = AuditLogExport.objects.all()
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'export_format']
    ordering_fields = ['created_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Users can only see their own exports unless they're admin.
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


class AuditLogQueryView(APIView):
    """
    Advanced audit log query endpoint with flexible filtering.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        Query audit logs with complex filters.
        """
        filters_data = request.data.get('filters', {})
        date_range = request.data.get('date_range', {})
        aggregation = request.data.get('aggregation')
        
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


# Simple serializer for SecurityAuditLog
try:
    from rest_framework import serializers
    
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

except ImportError:
    # Serializers will be defined when DRF is available
    SecurityAuditLogSerializer = None
    AuditLogExportSerializer = None
    UserActivityLogSerializer = None
