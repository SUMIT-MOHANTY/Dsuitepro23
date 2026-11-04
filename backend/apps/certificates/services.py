"""
Certificate Services for Enterprise LMS
Provides PDF generation service using WeasyPrint with Jinja2 templating.
"""

import os
import logging
import hashlib
from io import BytesIO
from datetime import datetime
from typing import Dict, Any, Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from jinja2 import Template, Environment, BaseLoader
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

from apps.certificates.models import Certificate, CertificateTemplate, CertificateIssueEvent

logger = logging.getLogger(__name__)


class CertificatePDFGenerator:
    """
    Service for generating PDF certificates from HTML templates.
    Uses WeasyPrint for PDF generation and Jinja2 for templating.
    """
    
    # Default certificate template HTML
    DEFAULT_TEMPLATE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Certificate of Completion</title>
    <style>
        @page {
            size: A4 landscape;
            margin: 0;
        }
        
        body {
            margin: 0;
            padding: 0;
            font-family: 'Georgia', serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        }
        
        .certificate-container {
            width: 100%;
            height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px;
            box-sizing: border-box;
            background: white;
            border: 20px solid #2c5282;
            position: relative;
        }
        
        .certificate-border {
            position: absolute;
            top: 20px;
            left: 20px;
            right: 20px;
            bottom: 20px;
            border: 3px solid #d69e2e;
        }
        
        .certificate-header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .certificate-title {
            font-size: 48px;
            font-weight: bold;
            color: #2c5282;
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 8px;
        }
        
        .certificate-subtitle {
            font-size: 18px;
            color: #4a5568;
            margin-top: 10px;
        }
        
        .certificate-body {
            text-align: center;
            margin: 40px 0;
        }
        
        .recipient-label {
            font-size: 16px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 4px;
            margin-bottom: 20px;
        }
        
        .recipient-name {
            font-size: 42px;
            font-weight: bold;
            color: #1a202c;
            margin: 20px 0;
            border-bottom: 2px solid #d69e2e;
            padding-bottom: 10px;
            display: inline-block;
        }
        
        .course-label {
            font-size: 16px;
            color: #718096;
            margin-top: 30px;
            margin-bottom: 10px;
        }
        
        .course-name {
            font-size: 28px;
            font-weight: bold;
            color: #2c5282;
            margin: 10px 0;
        }
        
        .course-details {
            font-size: 14px;
            color: #4a5568;
            margin-top: 10px;
        }
        
        .certificate-footer {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            width: 100%;
            margin-top: 60px;
            padding: 0 40px;
        }
        
        .signature-section {
            text-align: center;
        }
        
        .signature-line {
            width: 200px;
            border-bottom: 1px solid #1a202c;
            margin-bottom: 10px;
        }
        
        .signature-label {
            font-size: 12px;
            color: #718096;
        }
        
        .date-section {
            text-align: center;
        }
        
        .date-line {
            font-size: 16px;
            color: #1a202c;
            border-bottom: 1px solid #1a202c;
            padding-bottom: 5px;
            margin-bottom: 10px;
        }
        
        .date-label {
            font-size: 12px;
            color: #718096;
        }
        
        .certificate-number {
            position: absolute;
            bottom: 40px;
            right: 60px;
            font-size: 11px;
            color: #a0aec0;
        }
        
        .organization-logo {
            max-width: 150px;
            max-height: 60px;
            margin-bottom: 20px;
        }
        
        .organization-name {
            font-size: 20px;
            font-weight: bold;
            color: #2c5282;
            margin-bottom: 5px;
        }
        
        .watermark {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-45deg);
            font-size: 120px;
            color: rgba(44, 82, 130, 0.05);
            font-weight: bold;
            pointer-events: none;
        }
    </style>
</head>
<body>
    <div class="certificate-container">
        <div class="certificate-border"></div>
        <div class="watermark">CERTIFIED</div>
        
        <div class="certificate-header">
            {% if organization_logo %}
            <img src="{{ organization_logo }}" alt="Organization Logo" class="organization-logo">
            {% endif %}
            {% if organization_name %}
            <div class="organization-name">{{ organization_name }}</div>
            {% endif %}
            <h1 class="certificate-title">Certificate</h1>
            <div class="certificate-subtitle">of Completion</div>
        </div>
        
        <div class="certificate-body">
            <div class="recipient-label">This is to certify that</div>
            <div class="recipient-name">{{ student_name }}</div>
            
            <div class="course-label">has successfully completed the course</div>
            <div class="course-name">{{ course_name }}</div>
            
            <div class="course-details">
                {% if course_duration %}Duration: {{ course_duration }}<br>{% endif %}
                Completed on {{ completion_date }}
            </div>
        </div>
        
        <div class="certificate-footer">
            <div class="date-section">
                <div class="date-line">{{ completion_date }}</div>
                <div class="date-label">Date of Issue</div>
            </div>
            
            <div class="signature-section">
                <div class="signature-line"></div>
                <div class="signature-label">
                    {% if instructor_name %}{{ instructor_name }}<br>{% endif %}
                    Instructor
                </div>
            </div>
        </div>
        
        <div class="certificate-number">
            Certificate #{{ certificate_number }}
        </div>
    </div>
</body>
</html>
"""
    
    def __init__(self):
        self.font_config = FontConfiguration()
        self.jinja_env = Environment(loader=BaseLoader())
    
    def generate_pdf(
        self,
        certificate: Certificate,
        template: Optional[CertificateTemplate] = None,
        custom_variables: Optional[Dict[str, Any]] = None
    ) -> BytesIO:
        """
        Generate a PDF certificate for the given certificate instance.
        
        Args:
            certificate: The Certificate model instance
            template: Optional CertificateTemplate to use (defaults to certificate.template)
            custom_variables: Optional additional template variables
            
        Returns:
            BytesIO containing the generated PDF
        """
        # Get the template to use
        cert_template = template or certificate.template
        
        # Get template HTML and CSS
        if cert_template:
            html_content = cert_template.html_template
            css_content = cert_template.css_styles or ""
        else:
            html_content = self.DEFAULT_TEMPLATE_HTML
            css_content = ""
        
        # Prepare template variables
        template_vars = self._prepare_template_variables(certificate, custom_variables)
        
        # Render HTML with Jinja2
        try:
            template_obj = self.jinja_env.from_string(html_content)
            rendered_html = template_obj.render(**template_vars)
        except Exception as e:
            logger.error(f"Template rendering failed for certificate {certificate.id}: {e}")
            # Fall back to default template
            template_obj = self.jinja_env.from_string(self.DEFAULT_TEMPLATE_HTML)
            rendered_html = template_obj.render(**template_vars)
        
        # Generate PDF
        try:
            html = HTML(string=rendered_html, base_url=settings.SITE_URL if hasattr(settings, 'SITE_URL') else None)
            
            if css_content:
                css = CSS(string=css_content, font_config=self.font_config)
                pdf_bytes = html.write_pdf(stylesheets=[css], font_config=self.font_config)
            else:
                pdf_bytes = html.write_pdf(font_config=self.font_config)
            
            return BytesIO(pdf_bytes)
            
        except Exception as e:
            logger.error(f"PDF generation failed for certificate {certificate.id}: {e}")
            raise CertificateGenerationError(f"Failed to generate PDF: {str(e)}")
    
    def _prepare_template_variables(
        self,
        certificate: Certificate,
        custom_variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Prepare variables for template rendering.
        
        Args:
            certificate: The Certificate model instance
            custom_variables: Optional additional variables
            
        Returns:
            Dictionary of template variables
        """
        user = certificate.user
        course = certificate.course
        
        # Format completion date
        completion_date = certificate.issued_at.strftime("%B %d, %Y")
        
        # Calculate course duration
        if hasattr(course, 'duration_minutes') and course.duration_minutes:
            hours = course.duration_minutes // 60
            minutes = course.duration_minutes % 60
            if hours > 0:
                course_duration = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            else:
                course_duration = f"{minutes}m"
        else:
            course_duration = "N/A"
        
        # Get instructor name
        instructor_name = ""
        if hasattr(course, 'instructor') and course.instructor:
            instructor_name = course.instructor.get_full_name() or course.instructor.email
        
        # Organization settings
        organization_name = getattr(settings, 'CERTIFICATE_ORGANIZATION_NAME', 'Enterprise LMS')
        organization_logo = getattr(settings, 'CERTIFICATE_ORGANIZATION_LOGO', '')
        
        # Build template variables
        variables = {
            'student_name': user.get_full_name() or user.email,
            'student_email': user.email,
            'course_name': course.title,
            'course_slug': getattr(course, 'slug', ''),
            'course_duration': course_duration,
            'completion_date': completion_date,
            'certificate_number': certificate.certificate_number,
            'verification_hash': certificate.verification_hash,
            'instructor_name': instructor_name,
            'organization_name': organization_name,
            'organization_logo': organization_logo,
            'issued_at': certificate.issued_at.isoformat(),
            'current_date': timezone.now().strftime("%B %d, %Y"),
        }
        
        # Add custom variables if provided
        if custom_variables:
            variables.update(custom_variables)
        
        return variables
    
    def save_pdf_to_storage(
        self,
        certificate: Certificate,
        pdf_buffer: BytesIO,
        filename: Optional[str] = None
    ) -> str:
        """
        Save the generated PDF to storage.
        
        Args:
            certificate: The Certificate model instance
            pdf_buffer: BytesIO containing the PDF
            filename: Optional custom filename
            
        Returns:
            Path to the saved file
        """
        if not filename:
            filename = f"{certificate.certificate_number}.pdf"
        
        # Ensure the buffer is at the beginning
        pdf_buffer.seek(0)
        
        # Save to model's FileField
        certificate.pdf_file.save(
            filename,
            ContentFile(pdf_buffer.read()),
            save=True
        )
        
        return certificate.pdf_file.path


class CertificateGenerationError(Exception):
    """Exception raised when certificate generation fails."""
    pass


class CertificateService:
    """
    Service class for certificate operations.
    Provides methods for generation, verification, and management.
    """
    
    def __init__(self):
        self.pdf_generator = CertificatePDFGenerator()
    
    def generate_certificate_pdf(
        self,
        certificate: Certificate,
        template: Optional[CertificateTemplate] = None,
        performed_by=None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """
        Generate and save a PDF certificate.
        
        Args:
            certificate: The Certificate to generate PDF for
            template: Optional template override
            performed_by: User who triggered the generation
            ip_address: IP address of the request
            user_agent: User agent string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update status to generating
            certificate.generation_status = 'generating'
            certificate.generation_attempts += 1
            certificate.save(update_fields=['generation_status', 'generation_attempts', 'updated_at'])
            
            # Generate PDF
            pdf_buffer = self.pdf_generator.generate_pdf(certificate, template)
            
            # Save to storage
            filename = f"{certificate.certificate_number}.pdf"
            self.pdf_generator.save_pdf_to_storage(certificate, pdf_buffer, filename)
            
            # Update certificate status
            certificate.generation_status = 'completed'
            certificate.generated_at = timezone.now()
            certificate.generation_error = ""
            certificate.save(update_fields=['generation_status', 'generated_at', 'generation_error', 'updated_at'])
            
            # Log the event
            CertificateIssueEvent.objects.create(
                certificate=certificate,
                event_type=CertificateIssueEvent.EVENT_TYPE_REGENERATED if certificate.generation_attempts > 1 else CertificateIssueEvent.EVENT_TYPE_ISSUED,
                performed_by=performed_by,
                ip_address=ip_address,
                user_agent=user_agent or "",
                metadata={'attempt': certificate.generation_attempts}
            )
            
            logger.info(f"Certificate PDF generated successfully: {certificate.certificate_number}")
            return True
            
        except Exception as e:
            logger.error(f"Certificate generation failed: {e}")
            
            # Update certificate with error
            certificate.generation_status = 'failed'
            certificate.generation_error = str(e)[:500]  # Limit error message length
            certificate.save(update_fields=['generation_status', 'generation_error', 'updated_at'])
            
            return False
    
    def verify_certificate(self, certificate_number: str, verification_hash: str) -> Dict[str, Any]:
        """
        Verify a certificate by its number and hash.
        
        Args:
            certificate_number: The certificate number
            verification_hash: The verification hash
            
        Returns:
            Dictionary with verification result
        """
        try:
            certificate = Certificate.objects.get(
                certificate_number=certificate_number,
                verification_hash=verification_hash
            )
            
            # Log verification event
            CertificateIssueEvent.objects.create(
                certificate=certificate,
                event_type=CertificateIssueEvent.EVENT_TYPE_VERIFIED,
                metadata={'verification_method': 'public_api'}
            )
            
            return {
                'valid': certificate.is_valid,
                'certificate_number': certificate.certificate_number,
                'student_name': certificate.user.get_full_name() or certificate.user.email,
                'course_name': certificate.course.title,
                'issued_at': certificate.issued_at,
                'expires_at': certificate.expires_at,
                'is_revoked': certificate.is_revoked,
                'revoked_at': certificate.revoked_at,
                'revoked_reason': certificate.revoked_reason if certificate.is_revoked else None,
                'message': self._get_verification_message(certificate)
            }
            
        except Certificate.DoesNotExist:
            return {
                'valid': False,
                'message': 'Certificate not found or invalid verification code.'
            }
    
    def _get_verification_message(self, certificate: Certificate) -> str:
        """Get human-readable verification message."""
        if certificate.is_revoked:
            return "This certificate has been revoked."
        elif certificate.is_expired:
            return "This certificate has expired."
        elif certificate.generation_status != 'completed':
            return "This certificate is pending generation."
        else:
            return "This certificate is valid and authentic."
    
    def revoke_certificate(
        self,
        certificate: Certificate,
        reason: str,
        revoked_by,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """
        Revoke a certificate.
        
        Args:
            certificate: The Certificate to revoke
            reason: Reason for revocation
            revoked_by: User who is revoking the certificate
            ip_address: IP address of the request
            user_agent: User agent string
            
        Returns:
            True if successful
        """
        certificate.revoke(reason=reason, revoked_by=revoked_by)
        
        # Log the event
        CertificateIssueEvent.objects.create(
            certificate=certificate,
            event_type=CertificateIssueEvent.EVENT_TYPE_REVOKED,
            performed_by=revoked_by,
            ip_address=ip_address,
            user_agent=user_agent or "",
            metadata={'reason': reason}
        )
        
        logger.info(f"Certificate revoked: {certificate.certificate_number} by {revoked_by.email}")
        return True
    
    def get_certificate_stats(self) -> Dict[str, int]:
        """
        Get certificate statistics.
        
        Returns:
            Dictionary with certificate statistics
        """
        from django.db.models import Count, Q
        from django.utils import timezone
        
        now = timezone.now()
        
        # Get counts
        total = Certificate.objects.count()
        active = Certificate.objects.filter(
            is_revoked=False,
            expires_at__isnull=True
        ).count() + Certificate.objects.filter(
            is_revoked=False,
            expires_at__gt=now
        ).count()
        
        revoked = Certificate.objects.filter(is_revoked=True).count()
        expired = Certificate.objects.filter(
            is_revoked=False,
            expires_at__lt=now
        ).count()
        
        pending = Certificate.objects.filter(generation_status='pending').count()
        failed = Certificate.objects.filter(generation_status='failed').count()
        
        # This month/year
        this_month = Certificate.objects.filter(
            issued_at__year=now.year,
            issued_at__month=now.month
        ).count()
        
        this_year = Certificate.objects.filter(
            issued_at__year=now.year
        ).count()
        
        return {
            'total_certificates': total,
            'active_certificates': active,
            'revoked_certificates': revoked,
            'expired_certificates': expired,
            'pending_generation': pending,
            'failed_generation': failed,
            'certificates_this_month': this_month,
            'certificates_this_year': this_year
        }


# Convenience function for generating certificates
def generate_certificate_pdf(
    certificate: Certificate,
    template: Optional[CertificateTemplate] = None,
    **kwargs
) -> bool:
    """
    Convenience function to generate a certificate PDF.
    
    Args:
        certificate: The Certificate to generate
        template: Optional template override
        **kwargs: Additional arguments passed to CertificateService
        
    Returns:
        True if successful
    """
    service = CertificateService()
    return service.generate_certificate_pdf(certificate, template, **kwargs)
