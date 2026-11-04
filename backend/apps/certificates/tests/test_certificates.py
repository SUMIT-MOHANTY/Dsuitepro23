"""
Certificate Tests for Enterprise LMS
Tests for certificate models, PDF generation, async tasks, and verification API.
"""

import uuid
import hashlib
from datetime import timedelta
from unittest.mock import patch, MagicMock
from io import BytesIO

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from django.core.files.base import ContentFile
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.certificates.models import Certificate, CertificateTemplate, CertificateIssueEvent
from apps.certificates.services import CertificatePDFGenerator, CertificateService, CertificateGenerationError
from apps.certificates.tasks import generate_certificate_task, regenerate_certificate_task
from apps.courses.models import Course
from apps.enrollment.models import Enrollment

User = get_user_model()


class CertificateTemplateModelTests(TestCase):
    """Tests for CertificateTemplate model."""
    
    def setUp(self):
        self.template = CertificateTemplate.objects.create(
            name="Default Template",
            description="Standard certificate template",
            html_template="<html><body>{{ student_name }}</body></html>",
            css_styles="body { font-family: Arial; }",
            is_active=True
        )
    
    def test_template_creation(self):
        """Test certificate template creation."""
        self.assertEqual(self.template.name, "Default Template")
        self.assertTrue(self.template.is_active)
        self.assertIsNotNone(self.template.available_variables)
        self.assertIn("student_name", self.template.available_variables)
    
    def test_default_variables_auto_populated(self):
        """Test that default variables are auto-populated on save."""
        template = CertificateTemplate.objects.create(
            name="Test Template",
            html_template="<html></html>"
        )
        self.assertIsNotNone(template.available_variables)
        self.assertIn("student_name", template.available_variables)
        self.assertIn("course_name", template.available_variables)
    
    def test_get_default_variables(self):
        """Test getting default template variables."""
        defaults = self.template.get_default_variables()
        self.assertIn("student_name", defaults)
        self.assertIn("course_name", defaults)
        self.assertIn("certificate_number", defaults)
        self.assertEqual(defaults["student_name"]["type"], "string")


class CertificateModelTests(TestCase):
    """Tests for Certificate model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="A test course",
            status="published"
        )
        self.template = CertificateTemplate.objects.create(
            name="Test Template",
            html_template="<html></html>"
        )
        self.certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template
        )
    
    def test_certificate_creation(self):
        """Test certificate creation with auto-generated fields."""
        self.assertIsNotNone(self.certificate.certificate_number)
        self.assertTrue(self.certificate.certificate_number.startswith("CERT-"))
        self.assertIsNotNone(self.certificate.verification_hash)
        self.assertEqual(len(self.certificate.verification_hash), 64)  # SHA-256 hex
        self.assertEqual(self.certificate.generation_status, "pending")
    
    def test_certificate_number_uniqueness(self):
        """Test that certificate numbers are unique."""
        cert2 = Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template
        )
        self.assertNotEqual(
            self.certificate.certificate_number,
            cert2.certificate_number
        )
    
    def test_is_expired_property(self):
        """Test is_expired property."""
        # Not expired - no expiration
        self.assertFalse(self.certificate.is_expired)
        
        # Not expired - future expiration
        self.certificate.expires_at = timezone.now() + timedelta(days=30)
        self.certificate.save()
        self.assertFalse(self.certificate.is_expired)
        
        # Expired
        self.certificate.expires_at = timezone.now() - timedelta(days=1)
        self.certificate.save()
        self.assertTrue(self.certificate.is_expired)
    
    def test_is_valid_property(self):
        """Test is_valid property."""
        # Valid certificate
        self.certificate.generation_status = "completed"
        self.certificate.save()
        self.assertTrue(self.certificate.is_valid)
        
        # Revoked certificate
        self.certificate.revoke("Test revocation")
        self.assertFalse(self.certificate.is_valid)
    
    def test_status_property(self):
        """Test status property."""
        self.assertEqual(self.certificate.status, "pending")
        
        self.certificate.generation_status = "completed"
        self.certificate.save()
        self.assertEqual(self.certificate.status, "valid")
        
        self.certificate.revoke("Test")
        self.assertEqual(self.certificate.status, "revoked")
    
    def test_revoke_method(self):
        """Test certificate revocation."""
        admin_user = User.objects.create_user(
            email="admin@example.com",
            username="admin",
            password="admin123",
            is_staff=True
        )
        
        self.certificate.revoke("Academic dishonesty", revoked_by=admin_user)
        
        self.assertTrue(self.certificate.is_revoked)
        self.assertIsNotNone(self.certificate.revoked_at)
        self.assertEqual(self.certificate.revoked_reason, "Academic dishonesty")
        self.assertEqual(self.certificate.revoked_by, admin_user)
    
    def test_get_verification_url(self):
        """Test getting verification URL."""
        url = self.certificate.get_verification_url()
        self.assertIn(self.certificate.certificate_number, url)
        self.assertIn(self.certificate.verification_hash, url)
    
    def test_regenerate_hash(self):
        """Test hash regeneration."""
        old_hash = self.certificate.verification_hash
        self.certificate.regenerate_hash()
        self.assertNotEqual(old_hash, self.certificate.verification_hash)


class CertificatePDFGeneratorTests(TestCase):
    """Tests for CertificatePDFGenerator service."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123",
            first_name="John",
            last_name="Doe"
        )
        self.course = Course.objects.create(
            title="Python Programming",
            slug="python-programming",
            description="Learn Python",
            status="published",
            duration_minutes=600
        )
        self.template = CertificateTemplate.objects.create(
            name="Test Template",
            html_template="<html><body>{{ student_name }} - {{ course_name }}</body></html>"
        )
        self.certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template
        )
        self.generator = CertificatePDFGenerator()
    
    @patch('apps.certificates.services.HTML')
    def test_generate_pdf_success(self, mock_html_class):
        """Test successful PDF generation."""
        # Mock the HTML class and its methods
        mock_html = MagicMock()
        mock_html.write_pdf.return_value = b"PDF content"
        mock_html_class.return_value = mock_html
        
        pdf_buffer = self.generator.generate_pdf(self.certificate)
        
        self.assertIsInstance(pdf_buffer, BytesIO)
        self.assertEqual(pdf_buffer.read(), b"PDF content")
    
    def test_prepare_template_variables(self):
        """Test template variable preparation."""
        variables = self.generator._prepare_template_variables(self.certificate)
        
        self.assertEqual(variables["student_name"], "John Doe")
        self.assertEqual(variables["student_email"], "test@example.com")
        self.assertEqual(variables["course_name"], "Python Programming")
        self.assertEqual(variables["course_duration"], "10h")
        self.assertEqual(variables["certificate_number"], self.certificate.certificate_number)
    
    def test_prepare_variables_with_custom_data(self):
        """Test template variables with custom data."""
        custom_vars = {"custom_field": "custom_value"}
        variables = self.generator._prepare_template_variables(
            self.certificate,
            custom_variables=custom_vars
        )
        
        self.assertEqual(variables["custom_field"], "custom_value")


class CertificateServiceTests(TestCase):
    """Tests for CertificateService."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            status="published"
        )
        self.template = CertificateTemplate.objects.create(
            name="Test Template",
            html_template="<html></html>"
        )
        self.certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template
        )
        self.service = CertificateService()
    
    @patch('apps.certificates.services.CertificatePDFGenerator')
    def test_generate_certificate_pdf_success(self, mock_generator_class):
        """Test successful certificate PDF generation."""
        # Mock the generator
        mock_generator = MagicMock()
        mock_generator.generate_pdf.return_value = BytesIO(b"PDF content")
        mock_generator_class.return_value = mock_generator
        
        success = self.service.generate_certificate_pdf(self.certificate)
        
        self.assertTrue(success)
        self.assertEqual(self.certificate.generation_status, "completed")
        self.assertIsNotNone(self.certificate.generated_at)
    
    def test_verify_certificate_success(self):
        """Test successful certificate verification."""
        self.certificate.generation_status = "completed"
        self.certificate.save()
        
        result = self.service.verify_certificate(
            self.certificate.certificate_number,
            self.certificate.verification_hash
        )
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["student_name"], self.user.get_full_name())
        self.assertEqual(result["course_name"], self.course.title)
    
    def test_verify_certificate_not_found(self):
        """Test verification with invalid certificate."""
        result = self.service.verify_certificate(
            "INVALID-NUMBER",
            "invalidhash"
        )
        
        self.assertFalse(result["valid"])
        self.assertIn("not found", result["message"].lower())
    
    def test_verify_revoked_certificate(self):
        """Test verification of revoked certificate."""
        self.certificate.generation_status = "completed"
        self.certificate.revoke("Test revocation")
        
        result = self.service.verify_certificate(
            self.certificate.certificate_number,
            self.certificate.verification_hash
        )
        
        self.assertFalse(result["valid"])
        self.assertTrue(result["is_revoked"])
    
    def test_revoke_certificate(self):
        """Test certificate revocation via service."""
        admin_user = User.objects.create_user(
            email="admin@example.com",
            username="admin",
            password="admin123"
        )
        
        success = self.service.revoke_certificate(
            self.certificate,
            "Academic dishonesty",
            admin_user
        )
        
        self.assertTrue(success)
        self.certificate.refresh_from_db()
        self.assertTrue(self.certificate.is_revoked)
    
    def test_get_certificate_stats(self):
        """Test getting certificate statistics."""
        # Create additional certificates
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template,
            generation_status="completed"
        )
        
        stats = self.service.get_certificate_stats()
        
        self.assertIn("total_certificates", stats)
        self.assertIn("active_certificates", stats)
        self.assertIn("revoked_certificates", stats)
        self.assertGreaterEqual(stats["total_certificates"], 2)


class CertificateTaskTests(TestCase):
    """Tests for certificate Celery tasks."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            status="published"
        )
        self.template = CertificateTemplate.objects.create(
            name="Test Template",
            html_template="<html></html>"
        )
        self.certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template
        )
    
    @patch('apps.certificates.tasks.CertificateService')
    @patch('apps.certificates.tasks._send_certificate_notification')
    def test_generate_certificate_task_success(self, mock_notify, mock_service_class):
        """Test successful certificate generation task."""
        # Mock the service
        mock_service = MagicMock()
        mock_service.generate_certificate_pdf.return_value = True
        mock_service_class.return_value = mock_service
        
        # Mock self (the task)
        mock_task = MagicMock()
        mock_task.request.retries = 0
        
        result = generate_certificate_task.run(mock_task, str(self.certificate.id))
        
        self.assertTrue(result["success"])
        self.assertEqual(result["certificate_number"], self.certificate.certificate_number)
    
    def test_generate_certificate_task_certificate_not_found(self):
        """Test task with non-existent certificate."""
        fake_id = str(uuid.uuid4())
        
        mock_task = MagicMock()
        mock_task.request.retries = 0
        
        result = generate_certificate_task.run(mock_task, fake_id)
        
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())


class CertificateAPITests(APITestCase):
    """Tests for Certificate API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create users
        self.user = User.objects.create_user(
            email="learner@example.com",
            username="learner",
            password="learner123",
            first_name="Jane",
            last_name="Learner"
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            username="admin",
            password="admin123",
            is_staff=True
        )
        
        # Create course
        self.course = Course.objects.create(
            title="API Test Course",
            slug="api-test-course",
            status="published"
        )
        
        # Create template
        self.template = CertificateTemplate.objects.create(
            name="API Test Template",
            html_template="<html></html>"
        )
        
        # Create certificate
        self.certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template,
            generation_status="completed"
        )
    
    def test_list_my_certificates(self):
        """Test listing user's certificates."""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/v1/certificates/my/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            response.data["results"][0]["course_title"],
            "API Test Course"
        )
    
    def test_list_certificates_admin(self):
        """Test admin listing all certificates."""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/v1/certificates/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)
    
    def test_create_certificate_admin_only(self):
        """Test that only admins can create certificates."""
        self.client.force_authenticate(user=self.user)
        
        data = {
            "user_id": str(self.user.id),
            "course_id": str(self.course.id),
            "template_id": str(self.template.id)
        }
        
        response = self.client.post('/api/v1/certificates/', data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_certificate_as_admin(self):
        """Test admin creating certificate."""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            "user_id": str(self.user.id),
            "course_id": str(self.course.id),
            "template_id": str(self.template.id)
        }
        
        with patch('apps.certificates.views.generate_certificate_task') as mock_task:
            mock_task.delay.return_value = None
            response = self.client.post('/api/v1/certificates/', data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_task.delay.assert_called_once()
    
    def test_download_certificate(self):
        """Test downloading certificate PDF."""
        self.client.force_authenticate(user=self.user)
        
        # Create a mock PDF file
        self.certificate.pdf_file.save(
            "test.pdf",
            ContentFile(b"PDF content"),
            save=True
        )
        
        response = self.client.get(
            f'/api/v1/certificates/{self.certificate.id}/download/'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
    
    def test_download_certificate_not_ready(self):
        """Test downloading certificate when PDF not ready."""
        self.client.force_authenticate(user=self.user)
        
        self.certificate.generation_status = "pending"
        self.certificate.pdf_file = None
        self.certificate.save()
        
        response = self.client.get(
            f'/api/v1/certificates/{self.certificate.id}/download/'
        )
        
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("not yet generated", response.data["message"].lower())
    
    def test_regenerate_certificate(self):
        """Test regenerating certificate."""
        self.client.force_authenticate(user=self.admin)
        
        with patch('apps.certificates.views.regenerate_certificate_task') as mock_task:
            mock_task.delay.return_value = None
            response = self.client.post(
                f'/api/v1/certificates/{self.certificate.id}/regenerate/',
                {}
            )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "queued")
        mock_task.delay.assert_called_once()
    
    def test_revoke_certificate(self):
        """Test revoking certificate."""
        self.client.force_authenticate(user=self.admin)
        
        data = {"reason": "Academic dishonesty detected"}
        
        response = self.client.post(
            f'/api/v1/certificates/{self.certificate.id}/revoke/',
            data
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "revoked")
        
        self.certificate.refresh_from_db()
        self.assertTrue(self.certificate.is_revoked)
    
    def test_verify_certificate_public(self):
        """Test public certificate verification."""
        # No authentication required
        response = self.client.get(
            f'/api/v1/certificates/verify/{self.certificate.certificate_number}/{self.certificate.verification_hash}/'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["student_name"], self.user.get_full_name())
    
    def test_verify_certificate_invalid(self):
        """Test verification with invalid data."""
        response = self.client.get(
            '/api/v1/certificates/verify/INVALID/INVALID/'
        )
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["valid"])
    
    def test_verify_certificate_post(self):
        """Test certificate verification via POST."""
        data = {
            "certificate_number": self.certificate.certificate_number,
            "verification_hash": self.certificate.verification_hash
        }
        
        response = self.client.post('/api/v1/certificates/verify/', data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
    
    def test_certificate_stats_admin_only(self):
        """Test that stats endpoint is admin-only."""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/v1/certificates/stats/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_certificate_stats(self):
        """Test getting certificate stats as admin."""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get('/api/v1/certificates/stats/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_certificates", response.data)
        self.assertIn("active_certificates", response.data)


class CertificateSignalTests(TestCase):
    """Tests for certificate signals."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123"
        )
        self.course = Course.objects.create(
            title="Signal Test Course",
            slug="signal-test-course",
            status="published"
        )
        self.template = CertificateTemplate.objects.create(
            name="Signal Test Template",
            html_template="<html></html>",
            is_active=True
        )
    
    @patch('apps.certificates.signals.generate_certificate_task')
    def test_certificate_created_on_enrollment_completion(self, mock_task):
        """Test that certificate is created when enrollment is completed."""
        mock_task.delay.return_value = None
        
        # Create enrollment
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        
        # No certificate yet
        self.assertEqual(Certificate.objects.filter(user=self.user, course=self.course).count(), 0)
        
        # Complete the enrollment
        enrollment.status = Enrollment.STATUS_COMPLETED
        enrollment.save()
        
        # Certificate should be created
        certificate = Certificate.objects.filter(user=self.user, course=self.course).first()
        self.assertIsNotNone(certificate)
        self.assertEqual(certificate.generation_status, "pending")
        
        # Task should be queued
        mock_task.delay.assert_called_once()
    
    def test_no_duplicate_certificate_on_recompletion(self):
        """Test that duplicate certificates are not created."""
        # Create existing certificate
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            template=self.template,
            generation_status="completed"
        )
        
        # Create and complete enrollment
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_COMPLETED
        )
        
        # Should still only have one certificate
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1
        )


class CertificateIntegrationTests(TestCase):
    """Integration tests for certificate workflow."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="integration@example.com",
            username="integration",
            password="testpass123",
            first_name="Integration",
            last_name="Test"
        )
        self.course = Course.objects.create(
            title="Integration Course",
            slug="integration-course",
            description="Course for integration testing",
            status="published",
            duration_minutes=480
        )
        self.template = CertificateTemplate.objects.create(
            name="Integration Template",
            html_template="<html><body>{{ student_name }} completed {{ course_name }}</body></html>",
            is_active=True
        )
    
    def test_full_certificate_lifecycle(self):
        """Test the complete certificate lifecycle."""
        # 1. Create enrollment
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.STATUS_ACTIVE
        )
        
        # 2. Complete enrollment (triggers certificate creation)
        with patch('apps.certificates.signals.generate_certificate_task') as mock_task:
            mock_task.delay.return_value = None
            enrollment.status = Enrollment.STATUS_COMPLETED
            enrollment.save()
        
        # 3. Verify certificate was created
        certificate = Certificate.objects.get(user=self.user, course=self.course)
        self.assertIsNotNone(certificate.certificate_number)
        self.assertIsNotNone(certificate.verification_hash)
        
        # 4. Verify the certificate
        service = CertificateService()
        result = service.verify_certificate(
            certificate.certificate_number,
            certificate.verification_hash
        )
        self.assertTrue(result["valid"])
        
        # 5. Revoke the certificate
        admin = User.objects.create_user(
            email="admin@example.com",
            username="admin2",
            password="admin123",
            is_staff=True
        )
        service.revoke_certificate(certificate, "Test revocation", admin)
        
        # 6. Verify it's revoked
        certificate.refresh_from_db()
        self.assertTrue(certificate.is_revoked)
        
        result = service.verify_certificate(
            certificate.certificate_number,
            certificate.verification_hash
        )
        self.assertFalse(result["valid"])
        self.assertTrue(result["is_revoked"])
