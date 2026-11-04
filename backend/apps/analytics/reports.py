"""
Analytics Reports Module for Enterprise LMS

Provides compliance reporting services including GDPR data export,
SOC 2 access log generation, and analytics aggregation pipelines.
"""

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from apps.analytics.models import AuditLog, ReportJob, UserActivity
from apps.assessment.models import Grade, QuizAttempt, Submission
from apps.certificates.models import Certificate
from apps.courses.models import Course
from apps.enrollment.models import Enrollment, LessonProgress
from apps.users.models import UserSession

User = get_user_model()
logger = logging.getLogger(__name__)


class GDPRDataExportService:
    """
    Service for compiling complete user data exports for GDPR compliance.
    Aggregates all user-related data across all apps into a structured export.
    """

    @staticmethod
    def compile_user_data(user_id: str) -> Dict[str, Any]:
        """
        Compile complete user data across all apps for GDPR export.

        Args:
            user_id: UUID of the user to export data for

        Returns:
            Dictionary containing all user data organized by domain
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} not found")

        export_data = {
            "export_metadata": {
                "user_id": str(user.id),
                "email": user.email,
                "export_generated_at": timezone.now().isoformat(),
                "export_version": "1.0",
            },
            "profile_data": GDPRDataExportService._get_profile_data(user),
            "enrollment_data": GDPRDataExportService._get_enrollment_data(user),
            "assessment_data": GDPRDataExportService._get_assessment_data(user),
            "certificate_data": GDPRDataExportService._get_certificate_data(user),
            "activity_data": GDPRDataExportService._get_activity_data(user),
            "session_data": GDPRDataExportService._get_session_data(user),
            "forum_data": GDPRDataExportService._get_forum_data(user),
            "notification_data": GDPRDataExportService._get_notification_data(user),
        }

        return export_data

    @staticmethod
    def _get_profile_data(user: User) -> Dict[str, Any]:
        """Extract user profile information."""
        return {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "is_staff": user.is_staff,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "roles": [
                {"id": str(role.id), "name": role.name}
                for role in user.roles.all()
            ],
        }

    @staticmethod
    def _get_enrollment_data(user: User) -> List[Dict[str, Any]]:
        """Extract enrollment and progress data."""
        enrollments = Enrollment.objects.filter(user=user).select_related("course")
        return [
            {
                "id": str(enrollment.id),
                "course_id": str(enrollment.course.id),
                "course_title": enrollment.course.title,
                "status": enrollment.status,
                "progress_percent": enrollment.progress_percent,
                "enrolled_at": enrollment.created_at.isoformat(),
                "completed_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
                "last_accessed_at": enrollment.last_accessed_at.isoformat() if enrollment.last_accessed_at else None,
            }
            for enrollment in enrollments
        ]

    @staticmethod
    def _get_assessment_data(user: User) -> Dict[str, Any]:
        """Extract quiz attempts and assignment submissions."""
        quiz_attempts = QuizAttempt.objects.filter(user=user).select_related("quiz")
        submissions = Submission.objects.filter(student=user).select_related("assignment")

        return {
            "quiz_attempts": [
                {
                    "id": str(attempt.id),
                    "quiz_id": str(attempt.quiz.id),
                    "quiz_title": attempt.quiz.title,
                    "score": attempt.score,
                    "max_score": attempt.max_score,
                    "status": attempt.status,
                    "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                    "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
                }
                for attempt in quiz_attempts
            ],
            "submissions": [
                {
                    "id": str(submission.id),
                    "assignment_id": str(submission.assignment.id),
                    "assignment_title": submission.assignment.title,
                    "status": submission.status,
                    "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
                }
                for submission in submissions
            ],
        }

    @staticmethod
    def _get_certificate_data(user: User) -> List[Dict[str, Any]]:
        """Extract certificate data."""
        certificates = Certificate.objects.filter(user=user).select_related("course")
        return [
            {
                "id": str(cert.id),
                "course_id": str(cert.course.id),
                "course_title": cert.course.title,
                "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
                "expires_at": cert.expires_at.isoformat() if cert.expires_at else None,
                "is_revoked": cert.is_revoked,
            }
            for cert in certificates
        ]

    @staticmethod
    def _get_activity_data(user: User) -> List[Dict[str, Any]]:
        """Extract user activity logs."""
        activities = UserActivity.objects.filter(actor=user).order_by("-created_at")[:1000]
        return [
            {
                "id": str(activity.id),
                "event_type": activity.event_type,
                "target_type": activity.target_type,
                "target_id": str(activity.target_id) if activity.target_id else None,
                "metadata": activity.metadata,
                "ip_address": GDPRDataExportService._anonymize_ip(activity.ip_address),
                "user_agent": activity.user_agent,
                "created_at": activity.created_at.isoformat(),
            }
            for activity in activities
        ]

    @staticmethod
    def _get_session_data(user: User) -> List[Dict[str, Any]]:
        """Extract session data."""
        sessions = UserSession.objects.filter(user=user).order_by("-created_at")[:100]
        return [
            {
                "id": str(session.id),
                "ip_address": GDPRDataExportService._anonymize_ip(session.ip_address),
                "user_agent": session.user_agent,
                "created_at": session.created_at.isoformat(),
                "last_activity_at": session.last_activity_at.isoformat() if session.last_activity_at else None,
                "is_active": session.is_active,
            }
            for session in sessions
        ]

    @staticmethod
    def _get_forum_data(user: User) -> Dict[str, Any]:
        """Extract forum participation data."""
        from apps.forum.models import DiscussionPost, PostVote

        posts = DiscussionPost.objects.filter(author=user)
        votes = PostVote.objects.filter(user=user)

        return {
            "posts": [
                {
                    "id": str(post.id),
                    "title": post.title,
                    "created_at": post.created_at.isoformat(),
                }
                for post in posts
            ],
            "votes": [
                {
                    "id": str(vote.id),
                    "post_id": str(vote.post.id),
                    "vote_type": vote.vote_type,
                    "created_at": vote.created_at.isoformat(),
                }
                for vote in votes
            ],
        }

    @staticmethod
    def _get_notification_data(user: User) -> List[Dict[str, Any]]:
        """Extract notification preferences and history."""
        from apps.notifications.models import Notification, NotificationPreference

        preferences = NotificationPreference.objects.filter(user=user).first()
        notifications = Notification.objects.filter(user=user).order_by("-created_at")[:100]

        return {
            "preferences": {
                "email_enabled": preferences.email_enabled if preferences else True,
                "push_enabled": preferences.push_enabled if preferences else True,
                "digest_frequency": preferences.digest_frequency if preferences else "daily",
            } if preferences else None,
            "notifications": [
                {
                    "id": str(notification.id),
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at.isoformat(),
                }
                for notification in notifications
            ],
        }

    @staticmethod
    def _anonymize_ip(ip_address: Optional[str]) -> Optional[str]:
        """Anonymize IP address by hashing it."""
        if not ip_address:
            return None
        return hashlib.sha256(ip_address.encode()).hexdigest()[:16]


class SOC2ReportService:
    """
    Service for generating SOC 2 compliance reports.
    Provides access logs, security event summaries, and control attestations.
    """

    @staticmethod
    def generate_access_log_report(
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate SOC 2 access log report for the specified period.

        Args:
            start_date: Start of reporting period
            end_date: End of reporting period
            user_id: Optional user ID to filter by

        Returns:
            Dictionary containing access log summary and details
        """
        queryset = AuditLog.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        )

        if user_id:
            queryset = queryset.filter(actor_id=user_id)

        # Aggregate by action type
        action_summary = list(
            queryset.values("action").annotate(count=Count("id")).order_by("-count")
        )

        # Aggregate by resource type
        resource_summary = list(
            queryset.values("resource_type").annotate(count=Count("id")).order_by("-count")
        )

        # Failed actions
        failed_actions = list(
            queryset.filter(success=False)
            .values("action", "resource_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Daily activity counts
        daily_counts = list(
            queryset.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        return {
            "report_metadata": {
                "report_type": "SOC2_ACCESS_LOG",
                "generated_at": timezone.now().isoformat(),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "user_filter": user_id,
            },
            "summary": {
                "total_actions": queryset.count(),
                "unique_users": queryset.values("actor_id").distinct().count(),
                "unique_resources": queryset.values("resource_type").distinct().count(),
                "failed_actions": queryset.filter(success=False).count(),
            },
            "action_breakdown": action_summary,
            "resource_breakdown": resource_summary,
            "failed_actions": failed_actions,
            "daily_activity": daily_counts,
        }

    @staticmethod
    def generate_security_event_report(
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """
        Generate security event summary for SOC 2 compliance.

        Args:
            start_date: Start of reporting period
            end_date: End of reporting period

        Returns:
            Dictionary containing security event summary
        """
        from apps.analytics.models import SecurityAuditLog

        queryset = SecurityAuditLog.objects.filter(
            timestamp__gte=start_date,
            timestamp__lte=end_date,
        )

        # Events by category
        category_summary = list(
            queryset.values("event_category").annotate(count=Count("id")).order_by("-count")
        )

        # Events by severity
        severity_summary = list(
            queryset.values("severity").annotate(count=Count("id")).order_by("-count")
        )

        # Failed login attempts
        failed_logins = queryset.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        ).count()

        # Access denied events
        access_denied = queryset.filter(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED
        ).count()

        # Impersonation events
        impersonation_events = queryset.filter(
            event_category=SecurityAuditLog.CATEGORY_IMPERSONATION
        ).count()

        return {
            "report_metadata": {
                "report_type": "SOC2_SECURITY_EVENTS",
                "generated_at": timezone.now().isoformat(),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
            },
            "summary": {
                "total_events": queryset.count(),
                "critical_events": queryset.filter(severity=SecurityAuditLog.SEVERITY_CRITICAL).count(),
                "warning_events": queryset.filter(severity=SecurityAuditLog.SEVERITY_WARNING).count(),
                "failed_login_attempts": failed_logins,
                "access_denied_events": access_denied,
                "impersonation_events": impersonation_events,
            },
            "category_breakdown": category_summary,
            "severity_breakdown": severity_summary,
        }


class AnalyticsAggregationService:
    """
    Service for computing analytics aggregations and materialized views.
    Provides efficient queries for dashboard metrics and reporting.
    """

    @staticmethod
    def get_daily_active_users(days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily active user counts for the specified period.

        Args:
            days: Number of days to look back

        Returns:
            List of daily DAU metrics
        """
        start_date = timezone.now() - timedelta(days=days)

        dau_data = (
            UserActivity.objects.filter(
                created_at__gte=start_date,
                event_type__in=["login", "page_view"],
            )
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                active_users=Count("actor_id", distinct=True),
                total_events=Count("id"),
            )
            .order_by("date")
        )

        return list(dau_data)

    @staticmethod
    def get_monthly_active_users(months: int = 12) -> List[Dict[str, Any]]:
        """
        Get monthly active user counts.

        Args:
            months: Number of months to look back

        Returns:
            List of monthly MAU metrics
        """
        start_date = timezone.now() - timedelta(days=30 * months)

        mau_data = (
            UserActivity.objects.filter(
                created_at__gte=start_date,
                event_type__in=["login", "page_view"],
            )
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(active_users=Count("actor_id", distinct=True))
            .order_by("month")
        )

        return list(mau_data)

    @staticmethod
    def get_course_completion_stats(course_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get course completion statistics.

        Args:
            course_id: Optional course ID to filter by

        Returns:
            Dictionary with completion metrics
        """
        queryset = Enrollment.objects.filter(status="completed")

        if course_id:
            queryset = queryset.filter(course_id=course_id)

        total_enrollments = Enrollment.objects.count()
        completed_count = queryset.count()
        in_progress_count = Enrollment.objects.filter(status="active").count()

        # Average time to complete
        completion_times = []
        for enrollment in queryset:
            if enrollment.completed_at and enrollment.created_at:
                completion_times.append(
                    (enrollment.completed_at - enrollment.created_at).days
                )

        avg_completion_days = sum(completion_times) / len(completion_times) if completion_times else 0

        return {
            "total_enrollments": total_enrollments,
            "completed_count": completed_count,
            "in_progress_count": in_progress_count,
            "completion_rate": (completed_count / total_enrollments * 100) if total_enrollments > 0 else 0,
            "average_completion_days": round(avg_completion_days, 2),
        }

    @staticmethod
    def get_assessment_score_distribution(quiz_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get assessment score distribution.

        Args:
            quiz_id: Optional quiz ID to filter by

        Returns:
            Dictionary with score distribution metrics
        """
        queryset = QuizAttempt.objects.filter(status="completed")

        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)

        scores = queryset.values_list("score", flat=True)
        score_list = list(scores)

        if not score_list:
            return {
                "total_attempts": 0,
                "average_score": 0,
                "median_score": 0,
                "score_distribution": {},
            }

        # Calculate distribution buckets
        buckets = {"0-25%": 0, "26-50%": 0, "51-75%": 0, "76-100%": 0}
        for score in score_list:
            if score <= 25:
                buckets["0-25%"] += 1
            elif score <= 50:
                buckets["26-50%"] += 1
            elif score <= 75:
                buckets["51-75%"] += 1
            else:
                buckets["76-100%"] += 1

        sorted_scores = sorted(score_list)
        n = len(sorted_scores)
        median = sorted_scores[n // 2] if n % 2 else (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2

        return {
            "total_attempts": len(score_list),
            "average_score": round(sum(score_list) / len(score_list), 2),
            "median_score": median,
            "min_score": min(score_list),
            "max_score": max(score_list),
            "score_distribution": buckets,
        }

    @staticmethod
    def get_instructor_course_analytics(instructor_id: str) -> Dict[str, Any]:
        """
        Get analytics for courses taught by an instructor.

        Args:
            instructor_id: UUID of the instructor

        Returns:
            Dictionary with instructor course metrics
        """
        courses = Course.objects.filter(instructor_id=instructor_id)
        course_ids = [str(c.id) for c in courses]

        total_enrollments = Enrollment.objects.filter(course_id__in=course_ids).count()
        active_enrollments = Enrollment.objects.filter(
            course_id__in=course_ids, status="active"
        ).count()
        completed_enrollments = Enrollment.objects.filter(
            course_id__in=course_ids, status="completed"
        ).count()

        # Average course rating (if ratings exist)
        avg_rating = 0  # Placeholder for rating system

        return {
            "total_courses": courses.count(),
            "total_enrollments": total_enrollments,
            "active_enrollments": active_enrollments,
            "completed_enrollments": completed_enrollments,
            "average_rating": avg_rating,
            "courses": [
                {
                    "id": str(course.id),
                    "title": course.title,
                    "enrollment_count": Enrollment.objects.filter(course=course).count(),
                    "completion_count": Enrollment.objects.filter(
                        course=course, status="completed"
                    ).count(),
                }
                for course in courses
            ],
        }

    @staticmethod
    def get_learner_progress_analytics(user_id: str) -> Dict[str, Any]:
        """
        Get detailed progress analytics for a learner.

        Args:
            user_id: UUID of the learner

        Returns:
            Dictionary with learner progress metrics
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} not found")

        enrollments = Enrollment.objects.filter(user=user)
        certificates = Certificate.objects.filter(user=user)

        # Calculate learning streak
        activity_dates = (
            UserActivity.objects.filter(
                actor=user,
                event_type__in=["lesson_complete", "quiz_complete"],
            )
            .annotate(date=TruncDate("created_at"))
            .values_list("date", flat=True)
            .distinct()
        )

        return {
            "user_id": str(user.id),
            "total_enrollments": enrollments.count(),
            "completed_courses": enrollments.filter(status="completed").count(),
            "in_progress_courses": enrollments.filter(status="active").count(),
            "certificates_earned": certificates.count(),
            "average_progress": enrollments.aggregate(avg=Avg("progress_percent"))["avg"] or 0,
            "learning_streak_days": len(set(activity_dates)),
            "last_activity": UserActivity.objects.filter(actor=user)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first(),
        }


class ReportGenerationService:
    """
    Service for generating and managing analytics reports.
    Handles async report generation with email delivery.
    """

    @staticmethod
    def create_report_job(
        report_type: str,
        parameters: Dict[str, Any],
        requested_by: User,
    ) -> ReportJob:
        """
        Create a new report generation job.

        Args:
            report_type: Type of report to generate
            parameters: Report parameters
            requested_by: User requesting the report

        Returns:
            Created ReportJob instance
        """
        job = ReportJob.objects.create(
            report_type=report_type,
            parameters=parameters,
            requested_by=requested_by,
            status="pending",
        )
        return job

    @staticmethod
    def generate_csv_report(
        job: ReportJob,
        data: List[Dict[str, Any]],
        filename: str,
    ) -> str:
        """
        Generate a CSV report from data.

        Args:
            job: ReportJob instance
            data: List of dictionaries containing report data
            filename: Output filename

        Returns:
            Path to generated file
        """
        if not data:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

        # In production, this would save to Azure Blob Storage
        # For now, return the CSV content
        return output.getvalue()

    @staticmethod
    def generate_system_health_metrics() -> Dict[str, Any]:
        """
        Generate system health metrics for admin dashboard.

        Returns:
            Dictionary with system health metrics
        """
        from apps.analytics.models import SecurityAuditLog

        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        # API metrics (placeholder - would integrate with monitoring)
        api_metrics = {
            "p50_latency_ms": 45,
            "p95_latency_ms": 120,
            "p99_latency_ms": 250,
            "error_rate_24h": 0.02,
        }

        # User metrics
        user_metrics = {
            "total_users": User.objects.count(),
            "active_24h": UserActivity.objects.filter(
                created_at__gte=last_24h
            ).values("actor_id").distinct().count(),
            "active_7d": UserActivity.objects.filter(
                created_at__gte=last_7d
            ).values("actor_id").distinct().count(),
            "new_users_24h": User.objects.filter(
                date_joined__gte=last_24h
            ).count(),
        }

        # Security metrics
        security_metrics = {
            "failed_logins_24h": SecurityAuditLog.objects.filter(
                timestamp__gte=last_24h,
                event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            ).count(),
            "access_denied_24h": SecurityAuditLog.objects.filter(
                timestamp__gte=last_24h,
                event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            ).count(),
        }

        # Content metrics
        content_metrics = {
            "total_courses": Course.objects.count(),
            "total_enrollments": Enrollment.objects.count(),
            "active_enrollments": Enrollment.objects.filter(status="active").count(),
        }

        return {
            "generated_at": now.isoformat(),
            "api_metrics": api_metrics,
            "user_metrics": user_metrics,
            "security_metrics": security_metrics,
            "content_metrics": content_metrics,
        }


class MaterializedViewService:
    """
    Service for managing materialized views for analytics.
    Provides efficient pre-computed aggregations.
    """

    @staticmethod
    def refresh_daily_stats() -> None:
        """
        Refresh daily statistics materialized view.
        Should be called by a scheduled task.
        """
        yesterday = timezone.now().date() - timedelta(days=1)

        # Calculate daily stats
        daily_stats = {
            "date": yesterday.isoformat(),
            "active_users": UserActivity.objects.filter(
                created_at__date=yesterday
            ).values("actor_id").distinct().count(),
            "new_enrollments": Enrollment.objects.filter(
                created_at__date=yesterday
            ).count(),
            "completed_courses": Enrollment.objects.filter(
                completed_at__date=yesterday
            ).count(),
            "certificates_issued": Certificate.objects.filter(
                issued_at__date=yesterday
            ).count(),
        }

        logger.info(f"Daily stats refreshed for {yesterday}: {daily_stats}")

    @staticmethod
    def get_dashboard_summary() -> Dict[str, Any]:
        """
        Get summary data for admin dashboard.

        Returns:
            Dictionary with dashboard summary metrics
        """
        now = timezone.now()
        last_30d = now - timedelta(days=30)

        return {
            "users": {
                "total": User.objects.count(),
                "active_30d": UserActivity.objects.filter(
                    created_at__gte=last_30d
                ).values("actor_id").distinct().count(),
            },
            "courses": {
                "total": Course.objects.count(),
                "published": Course.objects.filter(status="published").count(),
            },
            "enrollments": {
                "total": Enrollment.objects.count(),
                "active": Enrollment.objects.filter(status="active").count(),
                "completed": Enrollment.objects.filter(status="completed").count(),
            },
            "assessments": {
                "total_quiz_attempts": QuizAttempt.objects.count(),
                "average_score": QuizAttempt.objects.filter(
                    status="completed"
                ).aggregate(avg=Avg("score"))["avg"] or 0,
            },
        }
