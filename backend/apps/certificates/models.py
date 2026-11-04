"""
Certificates Models for Enterprise LMS
Provides Certificate and CertificateTemplate models with PDF generation support.
"""

import uuid
import hashlib
from datetime import timedelta

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class CertificateTemplate(BaseModel):
    """
    Model representing a certificate template.
    Supports Jinja2 templating for dynamic content generation.
    """
    name = models.CharField(
        max_length=255,
        help_text="Name of the template"
    )
    description = models.TextField(
        blank=True,
        help_text="Template description"
    )
    html_template = models.TextField(
        help_text="HTML template with Jinja2 syntax for certificate generation"
    )
    css_styles = models.TextField(
        blank=True,
        help_text="Custom CSS styles for the certificate"
    )
    available_variables = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON schema of available template variables"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this template is active"
    )
    
    class Meta:
        verbose_name = "Certificate Template"
        verbose_name_plural = "Certificate Templates"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_default_variables(self):
        """Return default template variables schema."""
        return {
            "student_name": {"type": "string", "description": "Full name of the student"},
            "course_name": {"type": "string", "description": "Name of the course"},
            "course_duration": {"type": "string", "description": "Duration of the course"},
            "completion_date": {"type": "string", "description": "Date of completion"},
            "certificate_number": {"type": "string", "description": "Unique certificate number"},
            "instructor_name": {"type": "string", "description": "Name of the instructor"},
            "organization_name": {"type": "string", "description": "Organization issuing the certificate"},
            "organization_logo": {"type": "string", "description": "URL to organization logo"},
        }
    
    def save(self, *args, **kwargs):
        """Auto-populate available_variables if empty."""
        if not self.available_variables:
            self.available_variables = self.get_default_variables()
        super().save(*args, **kwargs)


class Certificate(BaseModel):
    """
    Model representing an issued certificate.
    Supports PDF generation, verification, and revocation.
    """
    certificate_number = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique certificate identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='certificates',
        help_text="User who received the certificate"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='certificates',
        help_text="Course the certificate is for"
    )
    template = models.ForeignKey(
        CertificateTemplate,
        on_delete=models.SET_NULL,
        null=True,
        related_name='certificates',
        help_text="Template used for this certificate"
    )
    issued_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the certificate was issued"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the certificate expires (null for no expiration)"
    )
    pdf_url = models.URLField(
        blank=True,
        help_text="URL to the generated PDF certificate"
    )
    pdf_file = models.FileField(
        upload_to='certificates/pdfs/%Y/%m/',
        blank=True,
        null=True,
        help_text="Generated PDF file storage"
    )
    verification_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash for certificate verification"
    )
    is_revoked = models.BooleanField(
        default=False,
        help_text="Whether the certificate has been revoked"
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the certificate was revoked"
    )
    revoked_reason = models.TextField(
        blank=True,
        help_text="Reason for revocation"
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates_revoked',
        help_text="User who revoked this certificate"
    )
    
    # Generation tracking
    generation_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('generating', 'Generating'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending',
        help_text="Current PDF generation status"
    )
    generation_attempts = models.PositiveIntegerField(
        default=0,
        help_text="Number of generation attempts"
    )
    generation_error = models.TextField(
        blank=True,
        help_text="Error message if generation failed"
    )
    generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the PDF was successfully generated"
    )
    
    class Meta:
        verbose_name = "Certificate"
        verbose_name_plural = "Certificates"
        ordering = ['-issued_at']
        indexes = [
            models.Index(fields=['user', 'issued_at']),
            models.Index(fields=['course', 'issued_at']),
            models.Index(fields=['certificate_number', 'verification_hash']),
            models.Index(fields=['is_revoked', 'issued_at']),
            models.Index(fields=['generation_status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.certificate_number} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        """Generate certificate number and verification hash on creation."""
        if not self.certificate_number:
            self.certificate_number = self.generate_certificate_number()
        if not self.verification_hash:
            self.verification_hash = self.generate_verification_hash()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_certificate_number():
        """Generate a unique certificate number."""
        prefix = "CERT"
        timestamp = timezone.now().strftime("%Y%m%d")
        unique_id = uuid.uuid4().hex[:8].upper()
        return f"{prefix}-{timestamp}-{unique_id}"
    
    def generate_verification_hash(self):
        """Generate a verification hash for this certificate."""
        data = f"{self.certificate_number}:{self.user_id}:{self.course_id}:{uuid.uuid4().hex}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    @property
    def is_expired(self):
        """Check if the certificate has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    @property
    def is_valid(self):
        """Check if the certificate is valid (not revoked and not expired)."""
        return not self.is_revoked and not self.is_expired
    
    @property
    def status(self):
        """Get the current certificate status."""
        if self.is_revoked:
            return "revoked"
        if self.is_expired:
            return "expired"
        if self.generation_status == "completed":
            return "valid"
        return self.generation_status
    
    def revoke(self, reason="", revoked_by=None):
        """Revoke this certificate."""
        self.is_revoked = True
        self.revoked_at = timezone.now()
        self.revoked_reason = reason
        self.revoked_by = revoked_by
        self.save(update_fields=[
            'is_revoked', 'revoked_at', 'revoked_reason', 'revoked_by', 'updated_at'
        ])
    
    def regenerate_hash(self):
        """Regenerate the verification hash."""
        self.verification_hash = self.generate_verification_hash()
        self.save(update_fields=['verification_hash', 'updated_at'])
    
    def get_verification_url(self):
        """Get the public verification URL for this certificate."""
        from django.urls import reverse
        return reverse('certificates:verify-certificate', kwargs={
            'number': self.certificate_number,
            'hash': self.verification_hash
        })
    
    def get_download_url(self):
        """Get the download URL for the PDF."""
        if self.pdf_file:
            return self.pdf_file.url
        return self.pdf_url


class CertificateIssueEvent(BaseModel):
    """
    Audit log for certificate issuance events.
    Tracks when certificates are issued, regenerated, or revoked.
    """
    EVENT_TYPE_ISSUED = 'issued'
    EVENT_TYPE_REGENERATED = 'regenerated'
    EVENT_TYPE_REVOKED = 'revoked'
    EVENT_TYPE_DOWNLOADED = 'downloaded'
    EVENT_TYPE_VERIFIED = 'verified'
    
    EVENT_TYPE_CHOICES = [
        (EVENT_TYPE_ISSUED, 'Issued'),
        (EVENT_TYPE_REGENERATED, 'Regenerated'),
        (EVENT_TYPE_REVOKED, 'Revoked'),
        (EVENT_TYPE_DOWNLOADED, 'Downloaded'),
        (EVENT_TYPE_VERIFIED, 'Verified'),
    ]
    
    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name='events',
        help_text="Certificate this event relates to"
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        help_text="Type of event"
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificate_events',
        help_text="User who performed the action"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional event metadata"
    )
    
    class Meta:
        verbose_name = "Certificate Issue Event"
        verbose_name_plural = "Certificate Issue Events"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['certificate', 'event_type', 'created_at']),
            models.Index(fields=['performed_by', 'event_type']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.certificate.certificate_number}"
