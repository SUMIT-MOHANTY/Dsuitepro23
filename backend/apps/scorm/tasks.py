"""
SCORM Tasks for Enterprise LMS
Provides Celery tasks for SCORM session cleanup, async operations, and analytics archival.
"""

import logging
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from apps.analytics.models import UserActivity
from .models import SCORMRegistration, SCORMSession, SCORMRuntimeData

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def archive_stale_scorm_sessions(self, days_stale: int = 30):
    """
    Archive SCORM sessions that have been inactive for more than the specified days.
    Moves session data to analytics audit trail and marks sessions for cleanup.
    
    Args:
        days_stale: Number of days of inactivity before archiving (default: 30)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days_stale)
        
        # Find stale sessions
        stale_sessions = SCORMSession.objects.filter(
            is_active=True,
            last_activity_at__lt=cutoff_date
        ).select_related('registration', 'registration__user', 'registration__content_item')
        
        archived_count = 0
        
        for session in stale_sessions:
            try:
                with transaction.atomic():
                    # Create audit log entry
                    UserActivity.objects.create(
                        user=session.registration.user,
                        action='scorm_session_archived',
                        details={
                            'session_id': str(session.session_id),
                            'registration_id': str(session.registration.registration_id),
                            'content_item_id': str(session.registration.content_item_id),
                            'launch_time': session.launch_time.isoformat() if session.launch_time else None,
                            'last_activity_at': session.last_activity_at.isoformat() if session.last_activity_at else None,
                            'total_time_accumulated': session.total_time_accumulated,
                            'suspend_data_preview': session.suspend_data[:100] if session.suspend_data else None,
                        },
                        ip_address=session.ip_address,
                        user_agent=session.user_agent,
                    )
                    
                    # Mark session as archived
                    session.is_active = False
                    session.current_state = 'archived'
                    session.ended_at = timezone.now()
                    session.save(update_fields=['is_active', 'current_state', 'ended_at'])
                    
                    # Update registration status if still active
                    if session.registration.status == 'in_progress':
                        session.registration.status = 'suspended'
                        session.registration.exit_status = 'timeout'
                        session.registration.save(update_fields=['status', 'exit_status'])
                    
                    archived_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to archive session {session.session_id}: {e}")
                continue
        
        logger.info(f"Archived {archived_count} stale SCORM sessions (older than {days_stale} days)")
        return {'archived_count': archived_count, 'days_stale': days_stale}
        
    except Exception as e:
        logger.error(f"Error archiving stale SCORM sessions: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def cleanup_inactive_registrations(self, days_inactive: int = 90):
    """
    Clean up SCORM registrations that have been inactive for an extended period.
    Soft deletes registrations and their associated data.
    
    Args:
        days_inactive: Number of days of inactivity before cleanup (default: 90)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days_inactive)
        
        # Find inactive registrations
        inactive_registrations = SCORMRegistration.objects.filter(
            status__in=['suspended', 'not_attempted'],
            updated_at__lt=cutoff_date,
            is_deleted=False
        )
        
        cleaned_count = 0
        
        for registration in inactive_registrations:
            try:
                with transaction.atomic():
                    # Archive to analytics before soft delete
                    UserActivity.objects.create(
                        user=registration.user,
                        action='scorm_registration_cleaned',
                        details={
                            'registration_id': str(registration.registration_id),
                            'content_item_id': str(registration.content_item_id),
                            'status': registration.status,
                            'completion_status': registration.completion_status,
                            'score_raw': str(registration.score_raw) if registration.score_raw else None,
                            'total_time': registration.total_time,
                            'last_launched_at': registration.last_launched_at.isoformat() if registration.last_launched_at else None,
                        }
                    )
                    
                    # Soft delete
                    registration.is_deleted = True
                    registration.deleted_at = timezone.now()
                    registration.save(update_fields=['is_deleted', 'deleted_at'])
                    
                    cleaned_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to clean up registration {registration.registration_id}: {e}")
                continue
        
        logger.info(f"Cleaned up {cleaned_count} inactive SCORM registrations (older than {days_inactive} days)")
        return {'cleaned_count': cleaned_count, 'days_inactive': days_inactive}
        
    except Exception as e:
        logger.error(f"Error cleaning up inactive registrations: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def sync_scorm_cloud_progress(self, registration_id: str):
    """
    Sync SCORM registration progress with SCORM Cloud.
    
    Args:
        registration_id: UUID of the SCORM registration to sync
    """
    try:
        from .services import SCORMCloudService
        
        registration = SCORMRegistration.objects.get(registration_id=registration_id)
        
        if not registration.scorm_cloud_registration_id:
            logger.warning(f"Registration {registration_id} has no SCORM Cloud ID")
            return {'status': 'skipped', 'reason': 'no_cloud_id'}
        
        cloud_service = SCORMCloudService()
        result = cloud_service.sync_registration_progress(registration)
        
        logger.info(f"Synced SCORM Cloud progress for registration {registration_id}: {result}")
        return result
        
    except SCORMRegistration.DoesNotExist:
        logger.error(f"Registration {registration_id} not found")
        return {'status': 'error', 'reason': 'registration_not_found'}
    except Exception as e:
        logger.error(f"Error syncing SCORM Cloud progress: {e}")
        raise self.retry(exc=e)


@shared_task
def generate_scorm_completion_report(course_id: Optional[str] = None, 
                                      start_date: Optional[str] = None,
                                      end_date: Optional[str] = None):
    """
    Generate a completion report for SCORM registrations.
    
    Args:
        course_id: Optional course ID to filter by
        start_date: Optional start date (ISO format)
        end_date: Optional end date (ISO format)
    """
    try:
        from django.db.models import Count, Avg, Q
        
        queryset = SCORMRegistration.objects.filter(is_deleted=False)
        
        if course_id:
            queryset = queryset.filter(content_item__lesson__module__course_id=course_id)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        stats = queryset.aggregate(
            total_registrations=Count('id'),
            completed_count=Count('id', filter=Q(status='completed')),
            passed_count=Count('id', filter=Q(status='passed')),
            failed_count=Count('id', filter=Q(status='failed')),
            in_progress_count=Count('id', filter=Q(status='in_progress')),
            suspended_count=Count('id', filter=Q(status='suspended')),
            avg_score=Avg('score_raw', filter=Q(score_raw__isnull=False))
        )
        
        report = {
            'generated_at': timezone.now().isoformat(),
            'filters': {
                'course_id': course_id,
                'start_date': start_date,
                'end_date': end_date,
            },
            'statistics': stats
        }
        
        logger.info(f"Generated SCORM completion report: {report}")
        return report
        
    except Exception as e:
        logger.error(f"Error generating SCORM completion report: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task
def process_scorm_batch_operations(operation_type: str, registration_ids: list):
    """
    Process batch operations on SCORM registrations.
    
    Args:
        operation_type: Type of operation ('reset', 'delete', 'export')
        registration_ids: List of registration UUIDs to process
    """
    try:
        results = []
        
        for reg_id in registration_ids:
            try:
                registration = SCORMRegistration.objects.get(registration_id=reg_id)
                
                if operation_type == 'reset':
                    # Reset progress
                    registration.status = 'not_attempted'
                    registration.completion_status = 'not attempted'
                    registration.score_raw = None
                    registration.score_min = None
                    registration.score_max = None
                    registration.total_time = ''
                    registration.session_time = ''
                    registration.lesson_location = ''
                    registration.suspend_data = ''
                    registration.exit_status = ''
                    registration.entry = 'ab-initio'
                    registration.completed_at = None
                    registration.save()
                    
                    # Delete runtime data
                    SCORMRuntimeData.objects.filter(registration=registration).delete()
                    
                    results.append({'registration_id': reg_id, 'status': 'reset'})
                    
                elif operation_type == 'delete':
                    registration.delete()
                    results.append({'registration_id': reg_id, 'status': 'deleted'})
                    
                elif operation_type == 'export':
                    # Export data (placeholder for export logic)
                    results.append({'registration_id': reg_id, 'status': 'exported'})
                    
            except SCORMRegistration.DoesNotExist:
                results.append({'registration_id': reg_id, 'status': 'not_found'})
            except Exception as e:
                results.append({'registration_id': reg_id, 'status': 'error', 'message': str(e)})
        
        logger.info(f"Processed batch operation '{operation_type}' on {len(registration_ids)} registrations")
        return {'operation': operation_type, 'results': results}
        
    except Exception as e:
        logger.error(f"Error processing batch operations: {e}")
        return {'status': 'error', 'message': str(e)}
