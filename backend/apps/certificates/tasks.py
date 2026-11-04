"""
Certificate Tasks for Enterprise LMS
Provides async Celery tasks for certificate PDF generation with retry logic.
"""

import logging
from typing import Optional

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.certificates.models import Certificate, CertificateTemplate
from apps.certificates.services import CertificateService, CertificateGenerationError
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute initial delay
    time_limit=300,  # 5 minutes hard limit
    soft_time_limit=240,  # 4 minutes soft limit
)
def generate_certificate_task(self, certificate_id: str, triggered_by_user_id: Optional[str] = None):
    """
    Async task to generate a certificate PDF.
    
    Args:
        certificate_id: UUID of the Certificate to generate
        triggered_by_user_id: Optional UUID of user who triggered generation
        
    Returns:
        dict with success status and certificate details
    """
    try:
        # Fetch certificate
        try:
            certificate = Certificate.objects.get(id=certificate_id)
        except Certificate.DoesNotExist:
            logger.error(f"Certificate not found: {certificate_id}")
            return {
                'success': False,
                'error': f'Certificate not found: {certificate_id}',
                'certificate_id': str(certificate_id)
            }
        
        # Get triggering user if provided
        triggered_by = None
        if triggered_by_user_id:
            try:
                triggered_by = User.objects.get(id=triggered_by_user_id)
            except User.DoesNotExist:
                logger.warning(f"Triggering user not found: {triggered_by_user_id}")
        
        # Initialize service and generate
        service = CertificateService()
        
        logger.info(f"Starting certificate generation for {certificate.certificate_number}")
        
        success = service.generate_certificate_pdf(
            certificate=certificate,
            performed_by=triggered_by
        )
        
        if success:
            logger.info(f"Certificate generated successfully: {certificate.certificate_number}")
            
            # Send success notification to user
            _send_certificate_notification(
                certificate=certificate,
                success=True,
                error_message=None
            )
            
            return {
                'success': True,
                'certificate_id': str(certificate.id),
                'certificate_number': certificate.certificate_number,
                'pdf_url': certificate.get_download_url(),
                'message': 'Certificate generated successfully'
            }
        else:
            # Generation failed but no exception - retry
            error_msg = f"Certificate generation failed for {certificate.certificate_number}"
            logger.error(error_msg)
            
            # Check if we should retry
            if certificate.generation_attempts < 3:
                logger.info(f"Retrying certificate generation (attempt {certificate.generation_attempts})")
                raise self.retry(countdown=self._get_retry_delay())
            else:
                # Max retries reached
                _send_certificate_notification(
                    certificate=certificate,
                    success=False,
                    error_message="Maximum retry attempts exceeded"
                )
                return {
                    'success': False,
                    'certificate_id': str(certificate.id),
                    'certificate_number': certificate.certificate_number,
                    'error': 'Maximum retry attempts exceeded',
                    'attempts': certificate.generation_attempts
                }
                
    except SoftTimeLimitExceeded:
        logger.error(f"Certificate generation timed out for {certificate_id}")
        _handle_generation_failure(certificate_id, "Generation timed out")
        raise self.retry(countdown=self._get_retry_delay())
        
    except CertificateGenerationError as e:
        logger.error(f"Certificate generation error: {e}")
        _handle_generation_failure(certificate_id, str(e))
        
        # Retry with exponential backoff
        try:
            raise self.retry(countdown=self._get_retry_delay())
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for certificate {certificate_id}")
            _send_certificate_notification(
                certificate_id=certificate_id,
                success=False,
                error_message=f"Failed after {self.max_retries} attempts: {str(e)}"
            )
            return {
                'success': False,
                'certificate_id': str(certificate_id),
                'error': f"Failed after {self.max_retries} attempts: {str(e)}"
            }
            
    except Exception as e:
        logger.exception(f"Unexpected error generating certificate: {e}")
        _handle_generation_failure(certificate_id, str(e))
        
        # Retry on unexpected errors
        try:
            raise self.retry(countdown=self._get_retry_delay())
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for certificate {certificate_id}")
            _send_certificate_notification(
                certificate_id=certificate_id,
                success=False,
                error_message=f"Failed after {self.max_retries} attempts: {str(e)}"
            )
            return {
                'success': False,
                'certificate_id': str(certificate_id),
                'error': f"Failed after {self.max_retries} attempts: {str(e)}"
            }


def _get_retry_delay(self):
    """Calculate retry delay with exponential backoff."""
    return 60 * (2 ** self.request.retries)  # 60s, 120s, 240s


def _handle_generation_failure(certificate_id: str, error_message: str):
    """
    Update certificate status on generation failure.
    
    Args:
        certificate_id: UUID of the certificate
        error_message: Error message to store
    """
    try:
        certificate = Certificate.objects.get(id=certificate_id)
        certificate.generation_status = 'failed'
        certificate.generation_error = error_message[:500]
        certificate.save(update_fields=['generation_status', 'generation_error', 'updated_at'])
    except Certificate.DoesNotExist:
        logger.error(f"Could not update failure status - certificate not found: {certificate_id}")


def _send_certificate_notification(certificate=None, certificate_id=None, success=True, error_message=None):
    """
    Send notification to user about certificate generation status.
    
    Args:
        certificate: Certificate instance (or None if only ID available)
        certificate_id: Certificate UUID (used if certificate is None)
        success: Whether generation succeeded
        error_message: Error message if failed
    """
    try:
        # Fetch certificate if only ID provided
        if certificate is None and certificate_id:
            try:
                certificate = Certificate.objects.get(id=certificate_id)
            except Certificate.DoesNotExist:
                logger.error(f"Cannot send notification - certificate not found: {certificate_id}")
                return
        
        if certificate is None:
            logger.error("Cannot send notification - no certificate provided")
            return
        
        user = certificate.user
        course = certificate.course
        
        notification_service = NotificationService()
        
        if success:
            # Success notification
            notification_service.send_notification(
                user=user,
                notification_type='certificate_generated',
                title='Certificate Generated',
                message=f'Your certificate for "{course.title}" has been generated successfully.',
                data={
                    'certificate_id': str(certificate.id),
                    'certificate_number': certificate.certificate_number,
                    'course_id': str(course.id),
                    'course_title': course.title,
                    'download_url': certificate.get_download_url(),
                    'verification_url': certificate.get_verification_url()
                },
                send_email=True,
                send_in_app=True
            )
            logger.info(f"Success notification sent to {user.email} for certificate {certificate.certificate_number}")
        else:
            # Failure notification
            notification_service.send_notification(
                user=user,
                notification_type='certificate_generation_failed',
                title='Certificate Generation Failed',
                message=f'We encountered an issue generating your certificate for "{course.title}". Our team has been notified and will resolve this shortly.',
                data={
                    'certificate_id': str(certificate.id),
                    'course_id': str(course.id),
                    'course_title': course.title,
                    'error': error_message
                },
                send_email=True,
                send_in_app=True
            )
            logger.info(f"Failure notification sent to {user.email} for certificate {certificate.certificate_number}")
            
    except Exception as e:
        logger.exception(f"Failed to send certificate notification: {e}")


@shared_task
def regenerate_certificate_task(certificate_id: str, template_id: Optional[str] = None, triggered_by_user_id: Optional[str] = None):
    """
    Regenerate a certificate with optional template override.
    
    Args:
        certificate_id: UUID of the Certificate to regenerate
        template_id: Optional UUID of template to use
        triggered_by_user_id: Optional UUID of user who triggered regeneration
        
    Returns:
        dict with success status
    """
    try:
        certificate = Certificate.objects.get(id=certificate_id)
        
        # Get optional template
        template = None
        if template_id:
            try:
                template = CertificateTemplate.objects.get(id=template_id)
            except CertificateTemplate.DoesNotExist:
                logger.warning(f"Template not found: {template_id}, using default")
        
        # Get triggering user
        triggered_by = None
        if triggered_by_user_id:
            try:
                triggered_by = User.objects.get(id=triggered_by_user_id)
            except User.DoesNotExist:
                pass
        
        # Reset status and regenerate
        certificate.generation_status = 'pending'
        certificate.generation_error = ""
        certificate.save(update_fields=['generation_status', 'generation_error', 'updated_at'])
        
        # Queue generation task
        generate_certificate_task.delay(
            certificate_id=str(certificate.id),
            triggered_by_user_id=str(triggered_by.id) if triggered_by else None
        )
        
        return {
            'success': True,
            'message': 'Certificate regeneration queued',
            'certificate_id': str(certificate.id)
        }
        
    except Certificate.DoesNotExist:
        return {
            'success': False,
            'error': f'Certificate not found: {certificate_id}'
        }
    except Exception as e:
        logger.exception(f"Error queuing certificate regeneration: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task
def cleanup_failed_certificate_generations(days: int = 7):
    """
    Cleanup task to notify users about certificates stuck in failed state.
    
    Args:
        days: Number of days to look back for failed certificates
    """
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    failed_certificates = Certificate.objects.filter(
        generation_status='failed',
        updated_at__lt=cutoff_date,
        is_revoked=False
    ).select_related('user', 'course')
    
    count = 0
    for certificate in failed_certificates:
        try:
            # Send notification to admin
            notification_service = NotificationService()
            notification_service.send_admin_notification(
                title='Failed Certificate Generation',
                message=f'Certificate {certificate.certificate_number} for user {certificate.user.email} has been failed since {certificate.updated_at}',
                data={
                    'certificate_id': str(certificate.id),
                    'certificate_number': certificate.certificate_number,
                    'user_email': certificate.user.email,
                    'course_title': certificate.course.title,
                    'error': certificate.generation_error
                }
            )
            count += 1
        except Exception as e:
            logger.exception(f"Failed to send admin notification for certificate {certificate.id}: {e}")
    
    logger.info(f"Cleanup task notified admins about {count} failed certificates")
    return {'notified_count': count}


@shared_task
def process_pending_certificates():
    """
    Process certificates stuck in pending state.
    Useful for recovering from crashes or restarts.
    """
    pending_certificates = Certificate.objects.filter(
        generation_status='pending'
    ).select_related('user', 'course')
    
    queued_count = 0
    for certificate in pending_certificates:
        try:
            # Check if already being processed (older than 5 minutes)
            if certificate.updated_at < timezone.now() - timezone.timedelta(minutes=5):
                generate_certificate_task.delay(certificate_id=str(certificate.id))
                queued_count += 1
                logger.info(f"Queued pending certificate for generation: {certificate.certificate_number}")
        except Exception as e:
            logger.exception(f"Failed to queue pending certificate {certificate.id}: {e}")
    
    logger.info(f"Processed {queued_count} pending certificates")
    return {'queued_count': queued_count}
