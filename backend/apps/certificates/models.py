"""
Certificates Models for Enterprise LMS
Provides Certificate and CertificateTemplate models.
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from apps.courses.models import Course

User = get_user_model()


class CertificateTemplate(BaseModel):
    """
    Model representing a certificate template.
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


class Certificate(BaseModel):
    """
    Model representing an issued certificate.
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
    pdf_url = models.URLField(
        blank=True,
        help_text="URL to the generated PDF certificate"
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
    
    class Meta:
        verbose_name = "Certificate"
        verbose_name_plural = "Certificates"
        ordering = ['-issued_at']
    
    def __str__(self):
        return f"{self.certificate_number} - {self.user.email}"
