"""
Certificate Signals for Enterprise LMS
Listens for enrollment completion signals and triggers certificate generation.
"""

import logging
from typing import Optional

from django.db.models.signals import post_save
from django.dispatch import receiver, Signal

from apps.certificates.models import Certificate, CertificateTemplate
from apps.certificates.tasks import generate_certificate_task
from apps.enrollment.models import Enrollment

logger = logging.getLogger(__name__)


# Custom signal for certificate events
certificate_generated = Signal()
certificate_revoked = Signal()
certificate_regenerated = Signal()


@receiver(post_save, sender=Enrollment)
def handle_enrollment_completion(sender, instance: Enrollment, created: bool, **kwargs):
    """
    Signal handler that triggers certificate generation when an enrollment is completed.
    
    Args:
        sender: The Enrollment model class
        instance: The Enrollment instance that was saved
        created: Whether this is a new enrollment
    """
    # Only proceed if enrollment was just marked as completed
    if not created and instance.status == Enrollment.STATUS_COMPLETED:
        # Check if certificate already exists for this enrollment
        existing_certificate = Certificate.objects.filter(
            user=instance.user,
            course=instance.course,
            is_revoked=False
        ).first()
        
        if existing_certificate:
            logger.info(
                f"Certificate already exists for user {instance.user.email} "
                f"and course {instance.course.title}, skipping generation"
            )
            return
        
        # Create certificate and queue generation
        try:
            certificate = create_certificate_for_enrollment(instance)
            if certificate:
                logger.info(
                    f"Certificate created and queued for generation: "
                    f"{certificate.certificate_number} for user {instance.user.email}"
                )
        except Exception as e:
            logger.exception(
                f"Failed to create certificate for enrollment {instance.id}: {e}"
            )


def create_certificate_for_enrollment(enrollment: Enrollment) -> Optional[Certificate]:
    """
    Create a certificate for a completed enrollment.
    
    Args:
        enrollment: The completed enrollment
        
    Returns:
        The created Certificate instance or None if creation failed
    """
    try:
        # Get the active certificate template
        template = CertificateTemplate.objects.filter(is_active=True).first()
        
        # Create the certificate
        certificate = Certificate.objects.create(
            user=enrollment.user,
            course=enrollment.course,
            template=template,
            generation_status='pending'
        )
        
        # Update enrollment to mark certificate as issued
        enrollment.certificate_issued = True
        enrollment.certificate_issued_at = certificate.issued_at
        enrollment.save(update_fields=['certificate_issued', 'certificate_issued_at', 'updated_at'])
        
        # Queue async PDF generation
        generate_certificate_task.delay(
            certificate_id=str(certificate.id),
            triggered_by_user_id=None  # System-generated
        )
        
        # Send signal
        certificate_generated.send(
            sender=Certificate,
            certificate=certificate,
            enrollment=enrollment
        )
        
        return certificate
        
    except Exception as e:
        logger.exception(f"Error creating certificate for enrollment {enrollment.id}: {e}")
        return None


def queue_certificate_generation(certificate_id: str, triggered_by_user_id: Optional[str] = None):
    """
    Utility function to queue certificate generation.
    
    Args:
        certificate_id: UUID of the certificate to generate
        triggered_by_user_id: Optional UUID of the user who triggered generation
    """
    try:
        generate_certificate_task.delay(
            certificate_id=certificate_id,
            triggered_by_user_id=triggered_by_user_id
        )
        logger.info(f"Certificate generation queued for {certificate_id}")
    except Exception as e:
        logger.exception(f"Failed to queue certificate generation for {certificate_id}: {e}")


@receiver(certificate_generated)
def log_certificate_generation(sender, certificate: Certificate, enrollment: Enrollment, **kwargs):
    """
    Log certificate generation events for audit purposes.
    """
    logger.info(
        f"Certificate generated event: {certificate.certificate_number} "
        f"for user {certificate.user.email} in course {certificate.course.title}"
    )


@receiver(certificate_revoked)
def log_certificate_revocation(sender, certificate: Certificate, **kwargs):
    """
    Log certificate revocation events for audit purposes.
    """
    logger.info(
        f"Certificate revoked event: {certificate.certificate_number} "
        f"for user {certificate.user.email}"
    )
