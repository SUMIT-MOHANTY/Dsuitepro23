"""
Analytics Services for Enterprise LMS
Provides audit logging services for security events, compliance, and GDPR data handling.
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.analytics.models import (
    AuditLog,
    AuditLogExport,
    ReportJob,
    ReportStatus,
    ReportType,
    SecurityAuditLog,
    UserActivity,
)

User = get_user_model()


class JSONDiffGenerator:
    """
    Utility class for generating JSON diffs between two dictionaries.
    Used for tracking changes in audit logs.
    """
    
    @staticmethod
    def generate_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a JSON diff showing changes between two dictionaries.
        
        Args:
            before: Dictionary representing the state before changes
            after: Dictionary representing the state after changes
            
        Returns:
            Dictionary with 'added', 'removed', 'modified', and 'unchanged' keys
        """
        if before is None:
            before = {}
        if after is None:
            after = {}
            
        diff = {
            'added': {},
            'removed': {},
            'modified': {},
            'unchanged': {}
        }
        
        all_keys = set(before.keys()) | set(after.keys())
        
        for key in all_keys:
            before_val = before.get(key)
            after_val = after.get(key)
            
            if key not in before:
                diff['added'][key] = after_val
            elif key not in after:
                diff['removed'][key] = before_val
            elif before_val != after_val:
                diff['modified'][key] = {
                    'before': before_val,
                    'after': after_val
                }
            else:
                diff['unchanged'][key] = before_val
                
        return diff
    
    @staticmethod
    def serialize_model(instance) -> Dict[str, Any]:
        """
        Serialize a Django model instance to a dictionary.
        
        Args:
            instance: Django model instance
            
        Returns:
            Dictionary representation of the instance
        """
        if instance is None:
            return {}
            
        data = {}
        for field in instance._meta.fields:
            value = getattr(instance, field.name)
            
            # Handle datetime fields
            if isinstance(value, datetime):
                value = value.isoformat()
            # Handle related fields (ForeignKey, OneToOneField)
            elif field.is_relation and value is not None:
                if hasattr(value, 'pk'):
                    value = str(value.pk)
                else:
                    value = str(value)
            # Handle UUID fields
            elif hasattr(value, 'hex'):
                value = str(value)
            # Handle other non-serializable types
            elif not isinstance(value, (str, int, float, bool, type(None), list, dict)):
                value = str(value)
                
            data[field.name] = value
            
        return data


class AuditLogService:
    """
    Service for immutable audit logging of CRUD operations.
    Provides structured logging with JSON diff generation for compliance.
    """
    
    @staticmethod
    def log_create(
        actor: User,
        resource_type: str,
        resource_id: str,
        new_data: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: str = '',
        justification: str = '',
        request_path: str = ''
    ) -> AuditLog:
        """
        Log a CREATE operation.
        
        Args:
            actor: User who performed the action
            resource_type: Type of resource created (e.g., 'course', 'user')
            resource_id: ID of the created resource
            new_data: Dictionary of the new resource data
            ip_address: IP address of the request
            user_agent: User agent string
            justification: Required justification for sensitive actions
            request_path: Request path
            
        Returns:
            Created AuditLog instance
        """
        return AuditLog.objects.create(
            action=AuditLog.ACTION_CREATE,
            actor=actor,
            actor_email=actor.email,
            resource_type=resource_type,
            resource_id=str(resource_id),
            changes={
                'before': None,
                'after': new_data,
                'diff': {
                    'added': new_data,
                    'removed': {},
                    'modified': {},
                    'unchanged': {}
                }
            },
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
            request_path=request_path,
            outcome='success'
        )
    
    @staticmethod
    def log_update(
        actor: User,
        resource_type: str,
        resource_id: str,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: str = '',
        justification: str = '',
        request_path: str = ''
    ) -> AuditLog:
        """
        Log an UPDATE operation with JSON diff.
        
        Args:
            actor: User who performed the action
            resource_type: Type of resource updated
            resource_id: ID of the updated resource
            before_data: Dictionary of the resource data before update
            after_data: Dictionary of the resource data after update
            ip_address: IP address of the request
            user_agent: User agent string
            justification: Required justification for sensitive actions
            request_path: Request path
            
        Returns:
            Created AuditLog instance
        """
        diff = JSONDiffGenerator.generate_diff(before_data, after_data)
        
        return AuditLog.objects.create(
            action=AuditLog.ACTION_UPDATE,
            actor=actor,
            actor_email=actor.email,
            resource_type=resource_type,
            resource_id=str(resource_id),
            changes={
                'before': before_data,
                'after': after_data,
                'diff': diff
            },
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
            request_path=request_path,
            outcome='success'
        )
    
    @staticmethod
    def log_delete(
        actor: User,
        resource_type: str,
        resource_id: str,
        deleted_data: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: str = '',
        justification: str = '',
        request_path: str = ''
    ) -> AuditLog:
        """
        Log a DELETE operation.
        
        Args:
            actor: User who performed the action
            resource_type: Type of resource deleted
            resource_id: ID of the deleted resource
            deleted_data: Dictionary of the resource data before deletion
            ip_address: IP address of the request
            user_agent: User agent string
            justification: Required justification for sensitive actions
            request_path: Request path
            
        Returns:
            Created AuditLog instance
        """
        return AuditLog.objects.create(
            action=AuditLog.ACTION_DELETE,
            actor=actor,
            actor_email=actor.email,
            resource_type=resource_type,
            resource_id=str(resource_id),
            changes={
                'before': deleted_data,
                'after': None,
                'diff': {
                    'added': {},
                    'removed': deleted_data,
                    'modified': {},
                    'unchanged': {}
                }
            },
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
            request_path=request_path,
            outcome='success'
        )
    
    @staticmethod
    def log_impersonation(
        actor: User,
        impersonated_user: User,
        action: str,  # 'start' or 'end'
        ip_address: Optional[str] = None,
        user_agent: str = '',
        justification: str = '',
        request_path: str = ''
    ) -> AuditLog:
        """
        Log an impersonation event.
        
        Args:
            actor: Admin user performing impersonation
            impersonated_user: User being impersonated
            action: 'start' or 'end'
            ip_address: IP address of the request
            user_agent: User agent string
            justification: Required justification for impersonation
            request_path: Request path
            
        Returns:
            Created AuditLog instance
        """
        action_type = AuditLog.ACTION_IMPERSONATE if action == 'start' else AuditLog.ACTION_IMPERSONATE_END
        
        return AuditLog.objects.create(
            action=action_type,
            actor=actor,
            actor_email=actor.email,
            resource_type='user',
            resource_id=str(impersonated_user.id),
            changes={
                'impersonated_user_id': str(impersonated_user.id),
                'impersonated_user_email': impersonated_user.email,
                'action': action
            },
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
            request_path=request_path,
            outcome='success'
        )
    
    @staticmethod
    def log_export(
        actor: User,
        export_type: str,
        filters: Dict[str, Any],
        record_count: int,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        justification: str = '',
        request_path: str = ''
    ) -> AuditLog:
        """
        Log a data export event (GDPR or bulk export).
        
        Args:
            actor: User who performed the export
            export_type: Type of export (e.g., 'gdpr', 'bulk', 'audit')
            filters: Filters applied to the export
            record_count: Number of records exported
            ip_address: IP address of the request
            user_agent: User agent string
            justification: Required justification for sensitive export
            request_path: Request path
            
        Returns:
            Created AuditLog instance
        """
        return AuditLog.objects.create(
            action=AuditLog.ACTION_EXPORT,
            actor=actor,
            actor_email=actor.email,
            resource_type='data_export',
            resource_id='',
            changes={
                'export_type': export_type,
                'filters': filters,
                'record_count': record_count
            },
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
            request_path=request_path,
            outcome='success'
        )
    
    @staticmethod
    def log_admin_action(
        actor: User,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: str = '',
        justification: str = '',
        request_path: str = ''
    ) -> AuditLog:
        """
        Log a generic administrative action.
        
        Args:
            actor: Admin user performing the action
            action: Action type (must be valid AuditLog.ACTION_CHOICE)
            resource_type: Type of resource affected
            resource_id: ID of the affected resource
            details: Additional action details
            ip_address: IP address of the request
            user_agent: User agent string
            justification: Required justification for sensitive actions
            request_path: Request path
            
        Returns:
            Created AuditLog instance
        """
        return AuditLog.objects.create(
            action=action,
            actor=actor,
            actor_email=actor.email,
            resource_type=resource_type,
            resource_id=str(resource_id),
            changes=details,
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
            request_path=request_path,
            outcome='success'
        )
    
    @staticmethod
    def requires_justification(action: str, resource_type: str) -> bool:
        """
        Determine if an action requires justification.
        
        Args:
            action: The action being performed
            resource_type: Type of resource being affected
            
        Returns:
            True if justification is required
        """
        sensitive_actions = [
            AuditLog.ACTION_DELETE,
            AuditLog.ACTION_IMPERSONATE,
            AuditLog.ACTION_EXPORT,
        ]
        
        sensitive_resources = [
            'user',
            'enrollment',
            'certificate',
            'audit_log',
            'gdpr_data'
        ]
        
        return action in sensitive_actions or resource_type in sensitive_resources
    
    @staticmethod
    def get_resource_history(
        resource_type: str,
        resource_id: str,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get audit history for a specific resource.
        
        Args:
            resource_type: Type of resource
            resource_id: ID of the resource
            limit: Maximum number of records to return
            
        Returns:
            List of AuditLog entries
        """
        return list(AuditLog.objects.filter(
            resource_type=resource_type,
            resource_id=str(resource_id)
        ).order_by('-timestamp')[:limit])
    
    @staticmethod
    def get_actor_history(
        actor: User,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get audit history for a specific actor.
        
        Args:
            actor: User to query
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of records to return
            
        Returns:
            List of AuditLog entries
        """
        queryset = AuditLog.objects.filter(actor=actor)
        
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
            
        return list(queryset.order_by('-timestamp')[:limit])


class UserActivityService:
    """
    Service for logging user activities across the platform.
    """
    
    @staticmethod
    def log_activity(
        user: User,
        event_type: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = ''
    ) -> UserActivity:
        """
        Log a user activity event.
        
        Args:
            user: User who performed the activity
            event_type: Type of event (login, logout, enroll, complete, etc.)
            target_type: Type of target resource
            target_id: ID of the target resource
            metadata: Additional event metadata
            ip_address: IP address of the request
            user_agent: User agent string
            
        Returns:
            Created UserActivity instance
        """
        return UserActivity.objects.create(
            user=user,
            event_type=event_type,
            target_type=target_type or '',
            target_id=str(target_id) if target_id else '',
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def log_login(user: User, ip_address: str, user_agent: str) -> UserActivity:
        """Log user login."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_LOGIN,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def log_logout(user: User, ip_address: str, user_agent: str) -> UserActivity:
        """Log user logout."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_LOGOUT,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def log_enrollment(user: User, enrollment_id: str, course_id: str, ip_address: str) -> UserActivity:
        """Log course enrollment."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_ENROLL,
            target_type='enrollment',
            target_id=enrollment_id,
            metadata={'course_id': course_id},
            ip_address=ip_address,
            user_agent=''
        )
    
    @staticmethod
    def log_course_completion(user: User, enrollment_id: str, course_id: str) -> UserActivity:
        """Log course completion."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_COMPLETE,
            target_type='enrollment',
            target_id=enrollment_id,
            metadata={'course_id': course_id, 'completed': True}
        )
    
    @staticmethod
    def log_assessment_attempt(user: User, attempt_id: str, quiz_id: str, score: float) -> UserActivity:
        """Log assessment attempt."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_ASSESS,
            target_type='quiz_attempt',
            target_id=attempt_id,
            metadata={'quiz_id': quiz_id, 'score': score}
        )
    
    @staticmethod
    def log_grade_received(user: User, grade_id: str, assessment_type: str, score: float) -> UserActivity:
        """Log grade received."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_GRADE,
            target_type='grade',
            target_id=grade_id,
            metadata={'assessment_type': assessment_type, 'score': score}
        )
    
    @staticmethod
    def log_certificate_issued(user: User, certificate_id: str, course_id: str) -> UserActivity:
        """Log certificate issuance."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_CERTIFY,
            target_type='certificate',
            target_id=certificate_id,
            metadata={'course_id': course_id}
        )
    
    @staticmethod
    def log_admin_action(user: User, action: str, resource_type: str, resource_id: str, details: Dict = None) -> UserActivity:
        """Log administrative action."""
        return UserActivityService.log_activity(
            user=user,
            event_type=UserActivity.EVENT_ADMIN_ACTION,
            target_type=resource_type,
            target_id=resource_id,
            metadata={'action': action, 'details': details or {}}
        )
    
    @staticmethod
    def get_user_timeline(
        user: User,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_types: Optional[List[str]] = None
    ) -> List[UserActivity]:
        """
        Get activity timeline for a user.
        
        Args:
            user: User to query
            start_date: Start of date range
            end_date: End of date range
            event_types: Filter by event types
            
        Returns:
            List of UserActivity entries
        """
        queryset = UserActivity.objects.filter(user=user)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        if event_types:
            queryset = queryset.filter(event_type__in=event_types)
            
        return list(queryset.order_by('-created_at'))


class DataRetentionService:
    """
    Service for managing data retention policies and GDPR compliance.
    """
    
    # Retention periods
    PII_ANONYMIZATION_YEARS = 7
    SOFT_DELETE_GRACE_DAYS = 30
    PERMANENT_DELETE_DAYS = 30
    
    @staticmethod
    def anonymize_pii(activity: UserActivity) -> None:
        """
        Anonymize PII in a UserActivity record.
        
        Args:
            activity: UserActivity instance to anonymize
        """
        # Hash the user email for anonymization
        if activity.user and activity.user.email:
            activity.actor_email_hash = hashlib.sha256(
                activity.user.email.encode('utf-8')
            ).hexdigest()
        
        # Clear IP address
        activity.ip_address = None
        
        # Clear user agent (may contain PII)
        activity.user_agent = '[REDACTED]'
        
        # Mark as anonymized
        activity.is_anonymized = True
        activity.anonymized_at = timezone.now()
        activity.save(update_fields=[
            'actor_email_hash', 'ip_address', 'user_agent',
            'is_anonymized', 'anonymized_at'
        ])
    
    @staticmethod
    def process_retention_policy() -> Dict[str, int]:
        """
        Process data retention policies.
        Anonymizes PII after 7 years, permanently deletes after 30-day grace.
        
        Returns:
            Dictionary with counts of processed records
        """
        results = {
            'anonymized': 0,
            'soft_deleted': 0,
            'permanently_deleted': 0
        }
        
        now = timezone.now()
        
        # Anonymize PII for records older than 7 years
        anonymization_cutoff = now - timedelta(days=365 * DataRetentionService.PII_ANONYMIZATION_YEARS)
        activities_to_anonymize = UserActivity.objects.filter(
            created_at__lt=anonymization_cutoff,
            is_anonymized=False
        )
        
        for activity in activities_to_anonymize:
            DataRetentionService.anonymize_pii(activity)
            results['anonymized'] += 1
        
        # Soft delete records that have been anonymized for 30 days
        soft_delete_cutoff = now - timedelta(days=DataRetentionService.SOFT_DELETE_GRACE_DAYS)
        activities_to_soft_delete = UserActivity.objects.filter(
            is_anonymized=True,
            anonymized_at__lt=soft_delete_cutoff,
            is_deleted=False
        )
        
        for activity in activities_to_soft_delete:
            activity.soft_delete()
            results['soft_deleted'] += 1
        
        # Permanently delete records that have been soft deleted for 30 days
        permanent_delete_cutoff = now - timedelta(days=DataRetentionService.PERMANENT_DELETE_DAYS)
        activities_to_delete = UserActivity.all_objects.filter(
            is_deleted=True,
            deleted_at__lt=permanent_delete_cutoff
        )
        
        count = activities_to_delete.count()
        activities_to_delete.hard_delete()
        results['permanently_deleted'] = count
        
        return results
    
    @staticmethod
    def get_gdpr_export_data(user: User) -> Dict[str, Any]:
        """
        Compile all user data for GDPR export.
        
        Args:
            user: User to export data for
            
        Returns:
            Dictionary containing all user data
        """
        from apps.users.models import UserRole, UserSession
        from apps.enrollment.models import Enrollment, LessonProgress
        from apps.assessment.models import QuizAttempt, Submission, Grade
        from apps.certificates.models import Certificate
        from apps.forum.models import DiscussionPost, PostVote
        
        export_data = {
            'user_info': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'date_joined': user.date_joined.isoformat() if user.date_joined else None,
                'last_login': user.last_login.isoformat() if user.last_login else None,
            },
            'activity_logs': [],
            'audit_logs': [],
            'enrollments': [],
            'progress': [],
            'assessments': [],
            'certificates': [],
            'forum_posts': [],
            'forum_votes': [],
            'sessions': [],
            'roles': []
        }
        
        # User Activity Logs
        for activity in UserActivity.objects.filter(user=user):
            export_data['activity_logs'].append({
                'id': str(activity.id),
                'event_type': activity.event_type,
                'target_type': activity.target_type,
                'target_id': activity.target_id,
                'metadata': activity.metadata,
                'created_at': activity.created_at.isoformat() if activity.created_at else None,
            })
        
        # Audit Logs where user is actor
        for log in AuditLog.objects.filter(actor=user):
            export_data['audit_logs'].append({
                'id': str(log.id),
                'action': log.action,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'changes': log.changes,
                'timestamp': log.timestamp.isoformat() if log.timestamp else None,
            })
        
        # Enrollments
        for enrollment in Enrollment.objects.filter(user=user):
            export_data['enrollments'].append({
                'id': str(enrollment.id),
                'course_id': str(enrollment.course_id) if enrollment.course_id else None,
                'status': enrollment.status,
                'enrolled_at': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
                'completed_at': enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            })
        
        # Lesson Progress
        for progress in LessonProgress.objects.filter(enrollment__user=user):
            export_data['progress'].append({
                'id': str(progress.id),
                'lesson_id': str(progress.lesson_id) if progress.lesson_id else None,
                'status': progress.status,
                'started_at': progress.started_at.isoformat() if progress.started_at else None,
                'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
            })
        
        # Quiz Attempts
        for attempt in QuizAttempt.objects.filter(user=user):
            export_data['assessments'].append({
                'type': 'quiz_attempt',
                'id': str(attempt.id),
                'quiz_id': str(attempt.quiz_id) if attempt.quiz_id else None,
                'score': attempt.score,
                'status': attempt.status,
                'started_at': attempt.started_at.isoformat() if attempt.started_at else None,
                'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
            })
        
        # Submissions
        for submission in Submission.objects.filter(student=user):
            export_data['assessments'].append({
                'type': 'submission',
                'id': str(submission.id),
                'assignment_id': str(submission.assignment_id) if submission.assignment_id else None,
                'status': submission.status,
                'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None,
            })
        
        # Grades
        for grade in Grade.objects.filter(student=user):
            export_data['assessments'].append({
                'type': 'grade',
                'id': str(grade.id),
                'score': grade.score,
                'max_points': grade.max_points,
                'graded_at': grade.graded_at.isoformat() if grade.graded_at else None,
            })
        
        # Certificates
        for cert in Certificate.objects.filter(user=user):
            export_data['certificates'].append({
                'id': str(cert.id),
                'course_id': str(cert.course_id) if cert.course_id else None,
                'issued_at': cert.issued_at.isoformat() if cert.issued_at else None,
                'certificate_number': cert.certificate_number,
            })
        
        # Forum Posts
        for post in DiscussionPost.objects.filter(author=user):
            export_data['forum_posts'].append({
                'id': str(post.id),
                'content': post.content,
                'created_at': post.created_at.isoformat() if post.created_at else None,
            })
        
        # Forum Votes
        for vote in PostVote.objects.filter(user=user):
            export_data['forum_votes'].append({
                'id': str(vote.id),
                'post_id': str(vote.post_id) if vote.post_id else None,
                'vote_type': vote.vote_type,
                'created_at': vote.created_at.isoformat() if vote.created_at else None,
            })
        
        # Sessions
        for session in UserSession.objects.filter(user=user):
            export_data['sessions'].append({
                'id': str(session.id),
                'ip_address': session.ip_address,
                'user_agent': session.user_agent,
                'created_at': session.created_at.isoformat() if session.created_at else None,
                'last_activity': session.last_activity.isoformat() if session.last_activity else None,
                'is_active': session.is_active,
            })
        
        # Roles
        for user_role in UserRole.objects.filter(user=user):
            export_data['roles'].append({
                'id': str(user_role.id),
                'role_name': user_role.role.name if user_role.role else None,
                'assigned_at': user_role.assigned_at.isoformat() if user_role.assigned_at else None,
            })
        
        return export_data


class ReportGenerationService:
    """
    Service for generating analytics reports.
    """
    
    @staticmethod
    def create_report_job(
        report_type: str,
        requested_by: User,
        parameters: Dict[str, Any],
        output_format: str = 'csv'
    ) -> ReportJob:
        """
        Create a new report generation job.
        
        Args:
            report_type: Type of report to generate
            requested_by: User requesting the report
            parameters: Report parameters
            output_format: Output format (csv, json, pdf)
            
        Returns:
            Created ReportJob instance
        """
        return ReportJob.objects.create(
            report_type=report_type,
            requested_by=requested_by,
            parameters=parameters,
            output_format=output_format,
            status=ReportStatus.PENDING
        )
    
    @staticmethod
    def generate_learner_progress_report(
        user: User,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate a learner progress report.
        
        Args:
            user: Learner to generate report for
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Dictionary with progress metrics
        """
        from apps.enrollment.models import Enrollment, LessonProgress
        from apps.assessment.models import QuizAttempt, Grade
        
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()
        
        enrollments = Enrollment.objects.filter(
            user=user,
            enrolled_at__gte=start_date,
            enrolled_at__lte=end_date
        )
        
        completed = enrollments.filter(status='completed').count()
        in_progress = enrollments.filter(status='active').count()
        
        # Calculate average progress
        total_progress = 0
        enrollment_count = enrollments.count()
        
        for enrollment in enrollments:
            total_progress += enrollment.progress_percent or 0
        
        avg_progress = total_progress / enrollment_count if enrollment_count > 0 else 0
        
        # Assessment scores
        attempts = QuizAttempt.objects.filter(
            user=user,
            completed_at__gte=start_date,
            completed_at__lte=end_date
        )
        
        avg_score = 0
        if attempts.exists():
            avg_score = sum(a.score or 0 for a in attempts) / attempts.count()
        
        return {
            'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
            'enrollments': {
                'total': enrollment_count,
                'completed': completed,
                'in_progress': in_progress,
                'completion_rate': (completed / enrollment_count * 100) if enrollment_count > 0 else 0
            },
            'progress': {
                'average_percent': round(avg_progress, 2)
            },
            'assessments': {
                'attempts': attempts.count(),
                'average_score': round(avg_score, 2)
            }
        }
    
    @staticmethod
    def generate_instructor_course_report(
        instructor: User,
        course_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an instructor course analytics report.
        
        Args:
            instructor: Instructor to generate report for
            course_id: Optional specific course ID
            
        Returns:
            Dictionary with course metrics
        """
        from apps.courses.models import Course
        from apps.enrollment.models import Enrollment
        from apps.assessment.models import Quiz, QuizAttempt
        
        courses = Course.objects.filter(instructor=instructor)
        if course_id:
            courses = courses.filter(id=course_id)
        
        course_data = []
        
        for course in courses:
            enrollments = Enrollment.objects.filter(course=course)
            total_enrolled = enrollments.count()
            completed = enrollments.filter(status='completed').count()
            
            # Average time to complete
            completion_times = []
            for enrollment in enrollments.filter(status='completed'):
                if enrollment.completed_at and enrollment.enrolled_at:
                    duration = (enrollment.completed_at - enrollment.enrolled_at).days
                    completion_times.append(duration)
            
            avg_completion_days = sum(completion_times) / len(completion_times) if completion_times else 0
            
            # Assessment scores
            quizzes = Quiz.objects.filter(course=course)
            attempts = QuizAttempt.objects.filter(quiz__in=quizzes, status='completed')
            
            avg_score = 0
            if attempts.exists():
                avg_score = sum(a.score or 0 for a in attempts) / attempts.count()
            
            course_data.append({
                'course_id': str(course.id),
                'title': course.title,
                'enrollments': {
                    'total': total_enrolled,
                    'completed': completed,
                    'completion_rate': (completed / total_enrolled * 100) if total_enrolled > 0 else 0
                },
                'avg_completion_days': round(avg_completion_days, 1),
                'avg_assessment_score': round(avg_score, 2)
            })
        
        return {
            'courses': course_data,
            'total_courses': len(course_data)
        }
    
    @staticmethod
    def generate_admin_system_report() -> Dict[str, Any]:
        """
        Generate admin system health report.
        
        Returns:
            Dictionary with system metrics
        """
        from django.contrib.auth import get_user_model
        from apps.courses.models import Course
        from apps.enrollment.models import Enrollment
        from apps.assessment.models import QuizAttempt
        
        User = get_user_model()
        
        now = timezone.now()
        
        # User metrics
        total_users = User.objects.filter(is_active=True).count()
        
        # DAU/MAU
        today = now.date()
        dau = UserActivity.objects.filter(
            event_type=UserActivity.EVENT_LOGIN,
            created_at__date=today
        ).values('user').distinct().count()
        
        thirty_days_ago = now - timedelta(days=30)
        mau = UserActivity.objects.filter(
            event_type=UserActivity.EVENT_LOGIN,
            created_at__gte=thirty_days_ago
        ).values('user').distinct().count()
        
        # Course metrics
        total_courses = Course.objects.filter(is_deleted=False).count()
        published_courses = Course.objects.filter(status='published', is_deleted=False).count()
        
        # Enrollment metrics
        total_enrollments = Enrollment.objects.filter(is_deleted=False).count()
        active_enrollments = Enrollment.objects.filter(status='active', is_deleted=False).count()
        completed_enrollments = Enrollment.objects.filter(status='completed', is_deleted=False).count()
        
        # Completion rate
        completion_rate = 0
        if total_enrollments > 0:
            completion_rate = (completed_enrollments / total_enrollments) * 100
        
        # Assessment metrics
        total_attempts = QuizAttempt.objects.filter(is_deleted=False).count()
        completed_attempts = QuizAttempt.objects.filter(status='completed', is_deleted=False).count()
        
        avg_score = 0
        if completed_attempts > 0:
            scores = QuizAttempt.objects.filter(
                status='completed',
                is_deleted=False
            ).values_list('score', flat=True)
            scores = [s for s in scores if s is not None]
            if scores:
                avg_score = sum(scores) / len(scores)
        
        # Security metrics
        failed_logins = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            timestamp__gte=thirty_days_ago
        ).count()
        
        password_resets = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_PASSWORD_RESET,
            timestamp__gte=thirty_days_ago
        ).count()
        
        return {
            'users': {
                'total_active': total_users,
                'dau': dau,
                'mau': mau,
                'dau_mau_ratio': round(dau / mau * 100, 2) if mau > 0 else 0
            },
            'courses': {
                'total': total_courses,
                'published': published_courses
            },
            'enrollments': {
                'total': total_enrollments,
                'active': active_enrollments,
                'completed': completed_enrollments,
                'completion_rate': round(completion_rate, 2)
            },
            'assessments': {
                'total_attempts': total_attempts,
                'completed_attempts': completed_attempts,
                'average_score': round(avg_score, 2)
            },
            'security': {
                'failed_logins_30d': failed_logins,
                'password_resets_30d': password_resets
            },
            'generated_at': now.isoformat()
        }


class AuditLoggingService:
    """
    Service for logging security events to the tamper-evident SecurityAuditLog.
    Provides structured logging for authentication, authorization, data access,
    and system events.
    """
    
    @staticmethod
    def log_auth_event(
        event_type: str,
        actor_user: Optional[User] = None,
        actor_email: str = '',
        outcome: str = 'success',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_path: str = '',
        response_time_ms: Optional[int] = None
    ) -> SecurityAuditLog:
        """
        Log an authentication event.
        
        Args:
            event_type: Type of authentication event
            actor_user: User who performed the action
            actor_email: Email of the actor
            outcome: 'success', 'failure', or 'blocked'
            reason: Reason for failure
            details: Additional event details
            ip_address: IP address of the request
            user_agent: User agent string
            request_path: Request path
            response_time_ms: Response time in milliseconds
            
        Returns:
            Created SecurityAuditLog instance
        """
        severity = SecurityAuditLog.SEVERITY_INFO
        if event_type in [SecurityAuditLog.EVENT_LOGIN_FAILURE, SecurityAuditLog.EVENT_MFA_FAILURE]:
            severity = SecurityAuditLog.SEVERITY_WARNING
        elif outcome == 'failure':
            severity = SecurityAuditLog.SEVERITY_WARNING
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_email or (actor_user.email if actor_user else ''),
            target_resource='authentication',
            target_resource_id='',
            outcome=outcome,
            reason=reason,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='POST',
            request_path=request_path,
            response_time_ms=response_time_ms
        )
    
    @staticmethod
    def log_authorization_decision(
        event_type: str,
        actor_user: Optional[User],
        target_resource: str,
        target_resource_id: str = '',
        outcome: str = 'granted',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_method: str = '',
        request_path: str = '',
        response_time_ms: Optional[int] = None
    ) -> SecurityAuditLog:
        """
        Log an authorization decision.
        
        Args:
            event_type: Type of authorization event
            actor_user: User attempting the action
            target_resource: Resource being accessed
            target_resource_id: ID of the target resource
            outcome: 'granted' or 'denied'
            reason: Reason for denial
            details: Additional event details
            ip_address: IP address
            user_agent: User agent string
            request_method: HTTP method
            request_path: Request path
            response_time_ms: Response time in milliseconds
            
        Returns:
            Created SecurityAuditLog instance
        """
        severity = SecurityAuditLog.SEVERITY_INFO
        if outcome == 'denied':
            severity = SecurityAuditLog.SEVERITY_WARNING
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_user.email if actor_user else '',
            target_resource=target_resource,
            target_resource_id=target_resource_id,
            outcome=outcome,
            reason=reason,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            response_time_ms=response_time_ms
        )
    
    @staticmethod
    def log_sensitive_data_access(
        event_type: str,
        actor_user: User,
        target_resource: str,
        target_resource_id: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_path: str = '',
        response_time_ms: Optional[int] = None
    ) -> SecurityAuditLog:
        """
        Log access to sensitive data.
        
        Args:
            event_type: Type of data access event
            actor_user: User accessing the data
            target_resource: Type of data accessed
            target_resource_id: ID of specific resource
            details: Additional details
            ip_address: IP address
            user_agent: User agent string
            request_path: Request path
            response_time_ms: Response time in milliseconds
            
        Returns:
            Created SecurityAuditLog instance
        """
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_DATA_ACCESS,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=actor_user,
            actor_email=actor_user.email,
            target_resource=target_resource,
            target_resource_id=target_resource_id,
            outcome='success',
            reason='',
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='GET',
            request_path=request_path,
            response_time_ms=response_time_ms
        )
    
    @staticmethod
    def log_session_event(
        event_type: str,
        actor_user: User,
        session_key: str = '',
        outcome: str = 'success',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = ''
    ) -> SecurityAuditLog:
        """
        Log session management events.
        
        Args:
            event_type: Type of session event
            actor_user: User whose session is affected
            session_key: Session identifier
            outcome: 'success' or 'failure'
            reason: Reason for revocation
            details: Additional event details
            ip_address: IP address
            user_agent: User agent string
            
        Returns:
            Created SecurityAuditLog instance
        """
        details = details or {}
        details['session_key_prefix'] = session_key[:8] if session_key else None
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_SESSION,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=actor_user,
            actor_email=actor_user.email,
            target_resource='session',
            target_resource_id=session_key[:16] if session_key else '',
            outcome=outcome,
            reason=reason,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='POST',
            request_path='/api/v1/auth/session/',
            response_time_ms=None
        )
    
    @staticmethod
    def log_impersonation_event(
        event_type: str,
        admin_user: User,
        impersonated_user: User,
        outcome: str = 'success',
        reason: str = '',
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: str = '',
        request_path: str = ''
    ) -> SecurityAuditLog:
        """
        Log admin impersonation events.
        
        Args:
            event_type: Type of impersonation event
            admin_user: Admin performing impersonation
            impersonated_user: User being impersonated
            outcome: 'success' or 'failure'
            reason: Reason for failure
            details: Additional event details
            ip_address: IP address
            user_agent: User agent string
            request_path: Request path
            
        Returns:
            Created SecurityAuditLog instance
        """
        details = details or {}
        details['impersonated_user_id'] = str(impersonated_user.id)
        details['impersonated_user_email'] = impersonated_user.email
        
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_IMPERSONATION,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=admin_user,
            actor_email=admin_user.email,
            target_resource='user',
            target_resource_id=str(impersonated_user.id),
            outcome=outcome,
            reason=reason,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method='POST',
            request_path=request_path,
            response_time_ms=None
        )
    
    @staticmethod
    def log_system_event(
        event_type: str,
        severity: str,
        details: Optional[Dict[str, Any]] = None,
        reason: str = '',
        actor_user: Optional[User] = None
    ) -> SecurityAuditLog:
        """
        Log system-level security events.
        
        Args:
            event_type: Type of system event
            severity: Severity level
            details: Additional event details
            reason: Reason or explanation
            actor_user: User associated with the event
            
        Returns:
            Created SecurityAuditLog instance
        """
        return SecurityAuditLog.log_event(
            event_type=event_type,
            event_category=SecurityAuditLog.CATEGORY_SYSTEM,
            severity=severity,
            actor_user=actor_user,
            actor_email=actor_user.email if actor_user else 'system',
            target_resource='system',
            target_resource_id='',
            outcome='success',
            reason=reason,
            details=details or {},
            ip_address=None,
            user_agent='',
            request_method='',
            request_path='',
            response_time_ms=None
        )


class AuditLogExportService:
    """
    Service for exporting audit logs in various formats.
    """
    
    @staticmethod
    def create_export_request(
        requested_by: User,
        start_date: datetime,
        end_date: datetime,
        event_categories: Optional[List[str]] = None,
        severity_levels: Optional[List[str]] = None,
        export_format: str = AuditLogExport.FORMAT_CSV
    ) -> AuditLogExport:
        """
        Create a new audit log export request.
        
        Args:
            requested_by: User requesting the export
            start_date: Start of date range
            end_date: End of date range
            event_categories: Filter by event categories
            severity_levels: Filter by severity levels
            export_format: Export format
            
        Returns:
            Created AuditLogExport instance
        """
        return AuditLogExport.objects.create(
            requested_by=requested_by,
            start_date=start_date,
            end_date=end_date,
            event_categories=event_categories or [],
            severity_levels=severity_levels or [],
            export_format=export_format,
            status=AuditLogExport.STATUS_PENDING
        )
    
    @staticmethod
    def process_export(export_id: str) -> bool:
        """
        Process an audit log export request.
        
        Args:
            export_id: ID of the export request
            
        Returns:
            True if export was successful
        """
        try:
            export = AuditLogExport.objects.get(id=export_id)
        except AuditLogExport.DoesNotExist:
            return False
        
        export.status = AuditLogExport.STATUS_PROCESSING
        export.started_at = timezone.now()
        export.save(update_fields=['status', 'started_at'])
        
        try:
            queryset = SecurityAuditLog.objects.filter(
                timestamp__gte=export.start_date,
                timestamp__lte=export.end_date
            )
            
            if export.event_categories:
                queryset = queryset.filter(event_category__in=export.event_categories)
            
            if export.severity_levels:
                queryset = queryset.filter(severity__in=export.severity_levels)
            
            export.record_count = queryset.count()
            
            if export.export_format == AuditLogExport.FORMAT_CSV:
                file_path = AuditLogExportService._export_to_csv(queryset, export_id)
            elif export.export_format == AuditLogExport.FORMAT_JSON:
                file_path = AuditLogExportService._export_to_json(queryset, export_id)
            else:
                raise NotImplementedError("PDF export not implemented")
            
            export.file_path = file_path
            export.status = AuditLogExport.STATUS_COMPLETED
            export.completed_at = timezone.now()
            export.save(update_fields=['file_path', 'status', 'completed_at', 'record_count'])
            
            return True
            
        except Exception as e:
            export.status = AuditLogExport.STATUS_FAILED
            export.error_message = str(e)
            export.completed_at = timezone.now()
            export.save(update_fields=['status', 'error_message', 'completed_at'])
            return False
    
    @staticmethod
    def _export_to_csv(queryset, export_id: str) -> str:
        """Export audit logs to CSV format."""
        export_dir = os.path.join(settings.MEDIA_ROOT, 'audit_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        file_path = os.path.join(export_dir, f'audit_export_{export_id}.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'event_type', 'event_category', 'severity',
                'actor_email', 'target_resource', 'target_resource_id',
                'outcome', 'reason', 'ip_address', 'request_method',
                'request_path', 'response_time_ms', 'details'
            ])
            
            for log in queryset.iterator():
                writer.writerow([
                    log.timestamp.isoformat() if log.timestamp else '',
                    log.event_type,
                    log.event_category,
                    log.severity,
                    log.actor_email,
                    log.target_resource,
                    log.target_resource_id,
                    log.outcome,
                    log.reason,
                    log.ip_address,
                    log.request_method,
                    log.request_path,
                    log.response_time_ms,
                    json.dumps(log.details)
                ])
        
        return file_path
    
    @staticmethod
    def _export_to_json(queryset, export_id: str) -> str:
        """Export audit logs to JSON format."""
        export_dir = os.path.join(settings.MEDIA_ROOT, 'audit_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        file_path = os.path.join(export_dir, f'audit_export_{export_id}.json')
        
        data = []
        for log in queryset.iterator():
            data.append({
                'timestamp': log.timestamp.isoformat() if log.timestamp else None,
                'event_type': log.event_type,
                'event_category': log.event_category,
                'severity': log.severity,
                'actor_email': log.actor_email,
                'target_resource': log.target_resource,
                'target_resource_id': log.target_resource_id,
                'outcome': log.outcome,
                'reason': log.reason,
                'ip_address': str(log.ip_address) if log.ip_address else None,
                'user_agent': log.user_agent,
                'request_method': log.request_method,
                'request_path': log.request_path,
                'response_time_ms': log.response_time_ms,
                'details': log.details,
                'current_hash': log.current_hash,
                'previous_hash': log.previous_hash,
            })
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        return file_path


class AuditLogQueryService:
    """
    Service for querying and analyzing audit logs.
    """
    
    @staticmethod
    def get_failed_login_attempts(
        ip_address: Optional[str] = None,
        email: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SecurityAuditLog]:
        """
        Get failed login attempts for security monitoring.
        
        Args:
            ip_address: Filter by IP address
            email: Filter by email
            since: Filter by time range
            limit: Maximum number of results
            
        Returns:
            List of SecurityAuditLog entries
        """
        queryset = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            outcome='failure'
        )
        
        if ip_address:
            queryset = queryset.filter(ip_address=ip_address)
        if email:
            queryset = queryset.filter(actor_email=email)
        if since:
            queryset = queryset.filter(timestamp__gte=since)
        
        return list(queryset.order_by('-timestamp')[:limit])
    
    @staticmethod
    def get_access_denials(
        user: Optional[User] = None,
        resource: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SecurityAuditLog]:
        """
        Get access denial events for security review.
        
        Args:
            user: Filter by user
            resource: Filter by resource type
            since: Filter by time range
            limit: Maximum number of results
            
        Returns:
            List of SecurityAuditLog entries
        """
        queryset = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            outcome='denied'
        )
        
        if user:
            queryset = queryset.filter(actor_user=user)
        if resource:
            queryset = queryset.filter(target_resource=resource)
        if since:
            queryset = queryset.filter(timestamp__gte=since)
        
        return list(queryset.order_by('-timestamp')[:limit])
    
    @staticmethod
    def get_user_activity(
        user: User,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_categories: Optional[List[str]] = None
    ) -> List[SecurityAuditLog]:
        """
        Get all activity for a specific user.
        
        Args:
            user: User to query
            start_date: Start of date range
            end_date: End of date range
            event_categories: Filter by categories
            
        Returns:
            List of SecurityAuditLog entries
        """
        queryset = SecurityAuditLog.objects.filter(actor_user=user)
        
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        if event_categories:
            queryset = queryset.filter(event_category__in=event_categories)
        
        return list(queryset.order_by('-timestamp'))
    
    @staticmethod
    def get_suspicious_activity(
        threshold: int = 5,
        time_window_minutes: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Detect suspicious activity patterns.
        
        Args:
            threshold: Number of failed attempts to flag
            time_window_minutes: Time window for counting attempts
            
        Returns:
            List of suspicious activity summaries
        """
        from django.db.models import Count
        
        since = timezone.now() - timedelta(minutes=time_window_minutes)
        
        suspicious_ips = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            timestamp__gte=since
        ).values('ip_address').annotate(
            failure_count=Count('id')
        ).filter(failure_count__gte=threshold)
        
        results = []
        for item in suspicious_ips:
            results.append({
                'type': 'brute_force_attempt',
                'ip_address': item['ip_address'],
                'failure_count': item['failure_count'],
                'time_window_minutes': time_window_minutes,
                'recommendation': 'Consider blocking IP or requiring CAPTCHA'
            })
        
        return results


# Convenience functions for common logging operations

def log_login_success(user: User, ip_address: str, user_agent: str, request_path: str = '/api/v1/auth/login/'):
    """Log successful login."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
        actor_user=user,
        outcome='success',
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path
    )


def log_login_failure(email: str, ip_address: str, user_agent: str, reason: str = '', request_path: str = '/api/v1/auth/login/'):
    """Log failed login attempt."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
        actor_email=email,
        outcome='failure',
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path
    )


def log_logout(user: User, ip_address: str, user_agent: str):
    """Log user logout."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_LOGOUT,
        actor_user=user,
        outcome='success',
        ip_address=ip_address,
        user_agent=user_agent,
        request_path='/api/v1/auth/logout/'
    )


def log_token_refresh(user: User, ip_address: str, user_agent: str):
    """Log token refresh."""
    return AuditLoggingService.log_auth_event(
        event_type=SecurityAuditLog.EVENT_TOKEN_REFRESH,
        actor_user=user,
        outcome='success',
        ip_address=ip_address,
        user_agent=user_agent,
        request_path='/api/v1/auth/refresh/'
    )


def log_access_denied(user: User, resource: str, resource_id: str, reason: str, ip_address: str, request_path: str):
    """Log access denial."""
    return AuditLoggingService.log_authorization_decision(
        event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
        actor_user=user,
        target_resource=resource,
        target_resource_id=resource_id,
        outcome='denied',
        reason=reason,
        ip_address=ip_address,
        request_path=request_path
    )


def log_bulk_export(user: User, record_count: int, filters: Dict[str, Any], ip_address: str):
    """Log bulk data export."""
    return AuditLoggingService.log_sensitive_data_access(
        event_type=SecurityAuditLog.EVENT_BULK_EXPORT,
        actor_user=user,
        target_resource='data_export',
        details={'record_count': record_count, 'filters': filters},
        ip_address=ip_address,
        request_path='/api/v1/analytics/audit-logs/export/'
    )
