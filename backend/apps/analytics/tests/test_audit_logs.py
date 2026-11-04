"""
Test Suite for Security Audit Logs
Tests tamper-evident logging, hash chain integrity, and audit trail compliance.
"""

import hashlib
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.analytics.models import SecurityAuditLog, AuditLogExport
from apps.analytics.services import (
    AuditLoggingService,
    AuditLogExportService,
    AuditLogQueryService,
)
from apps.users.models import Role

User = get_user_model()


class SecurityAuditLogModelTests(TestCase):
    """Tests for SecurityAuditLog model functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_audit_log_creation(self):
        """Test basic audit log creation."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success',
            ip_address='192.168.1.1',
            request_method='POST',
            request_path='/api/auth/login/'
        )
        
        self.assertIsNotNone(log.id)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_LOGIN_SUCCESS)
        self.assertEqual(log.event_category, SecurityAuditLog.CATEGORY_AUTHN)
        self.assertEqual(log.severity, SecurityAuditLog.SEVERITY_INFO)
        self.assertEqual(log.actor_user, self.user)
        self.assertEqual(log.outcome, 'success')
        self.assertEqual(str(log.ip_address), '192.168.1.1')
    
    def test_hash_chain_generation(self):
        """Test that hash chain is properly generated."""
        # Create first log
        log1 = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        # First log should have previous_hash as zeros
        self.assertEqual(log1.previous_hash, '0' * 64)
        self.assertIsNotNone(log1.current_hash)
        self.assertEqual(len(log1.current_hash), 64)
        
        # Create second log
        log2 = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGOUT,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        # Second log should reference first log's hash
        self.assertEqual(log2.previous_hash, log1.current_hash)
        self.assertNotEqual(log2.current_hash, log1.current_hash)
    
    def test_hash_calculation_consistency(self):
        """Test that hash calculation is consistent."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success',
            details={'key': 'value'}
        )
        
        # Calculate hash manually
        calculated_hash = log.calculate_hash()
        
        # Should match stored hash
        self.assertEqual(log.current_hash, calculated_hash)
    
    def test_verify_integrity_success(self):
        """Test integrity verification for unmodified log."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        self.assertTrue(log.verify_integrity())
    
    def test_verify_integrity_failure(self):
        """Test integrity verification detects tampering."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        # Tamper with the log
        log.outcome = 'failure'
        log.save(update_fields=['outcome'])
        
        # Integrity check should fail
        self.assertFalse(log.verify_integrity())
    
    def test_verify_chain_integrity(self):
        """Test chain integrity verification."""
        # Create multiple logs
        for i in range(5):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.user,
                outcome='success',
                details={'iteration': i}
            )
        
        # Verify entire chain
        is_valid, broken_at = SecurityAuditLog.verify_chain_integrity()
        self.assertTrue(is_valid)
        self.assertIsNone(broken_at)
    
    def test_verify_chain_integrity_with_tampering(self):
        """Test chain integrity detects tampering."""
        logs = []
        for i in range(5):
            log = SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.user,
                outcome='success',
                details={'iteration': i}
            )
            logs.append(log)
        
        # Tamper with middle log
        logs[2].outcome = 'tampered'
        logs[2].save(update_fields=['outcome'])
        
        # Chain verification should fail at tampered log
        is_valid, broken_at = SecurityAuditLog.verify_chain_integrity()
        self.assertFalse(is_valid)
        self.assertEqual(broken_at, logs[2].id)
    
    def test_log_event_with_all_fields(self):
        """Test log_event factory method with all fields."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=self.user,
            actor_email='test@example.com',
            target_resource='course',
            target_resource_id='123e4567-e89b-12d3-a456-426614174000',
            outcome='denied',
            reason='Insufficient permissions',
            details={'required_role': 'instructor'},
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0',
            request_method='GET',
            request_path='/api/courses/123/',
            response_time_ms=150
        )
        
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_ACCESS_DENIED)
        self.assertEqual(log.event_category, SecurityAuditLog.CATEGORY_AUTHZ)
        self.assertEqual(log.severity, SecurityAuditLog.SEVERITY_WARNING)
        self.assertEqual(log.target_resource, 'course')
        self.assertEqual(log.reason, 'Insufficient permissions')
        self.assertEqual(log.response_time_ms, 150)
    
    def test_log_event_without_user(self):
        """Test logging events without a user (anonymous)."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=None,
            actor_email='unknown@example.com',
            outcome='failure',
            reason='Invalid credentials'
        )
        
        self.assertIsNone(log.actor_user)
        self.assertEqual(log.actor_email, 'unknown@example.com')
    
    def test_string_representation(self):
        """Test string representation of audit log."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        expected = f"login_success by {self.user.email} at {log.timestamp}"
        self.assertEqual(str(log), expected)


class AuditLoggingServiceTests(TestCase):
    """Tests for AuditLoggingService."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        
        # Mock request
        self.mock_request = MagicMock()
        self.mock_request.META = {
            'HTTP_X_FORWARDED_FOR': '192.168.1.1, 10.0.0.1',
            'HTTP_USER_AGENT': 'Mozilla/5.0 Test',
            'REMOTE_ADDR': '10.0.0.2'
        }
        self.mock_request.method = 'POST'
        self.mock_request.path = '/api/auth/login/'
    
    def test_get_client_ip_with_x_forwarded_for(self):
        """Test IP extraction from X-Forwarded-For header."""
        ip = AuditLoggingService._get_client_ip(self.mock_request)
        self.assertEqual(ip, '192.168.1.1')
    
    def test_get_client_ip_without_x_forwarded_for(self):
        """Test IP extraction from REMOTE_ADDR."""
        self.mock_request.META = {
            'HTTP_USER_AGENT': 'Mozilla/5.0',
            'REMOTE_ADDR': '10.0.0.2'
        }
        ip = AuditLoggingService._get_client_ip(self.mock_request)
        self.assertEqual(ip, '10.0.0.2')
    
    def test_log_login_success(self):
        """Test logging successful login."""
        log = AuditLoggingService.log_login_success(self.user, self.mock_request)
        
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_LOGIN_SUCCESS)
        self.assertEqual(log.actor_user, self.user)
        self.assertEqual(log.outcome, 'success')
        self.assertEqual(str(log.ip_address), '192.168.1.1')
    
    def test_log_login_failure(self):
        """Test logging failed login."""
        log = AuditLoggingService.log_login_failure(
            email='test@example.com',
            reason='Invalid password',
            request=self.mock_request
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_LOGIN_FAILURE)
        self.assertEqual(log.outcome, 'failure')
        self.assertEqual(log.reason, 'Invalid password')
    
    def test_log_logout(self):
        """Test logging logout."""
        log = AuditLoggingService.log_logout(self.user, self.mock_request)
        
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_LOGOUT)
        self.assertEqual(log.actor_user, self.user)
    
    def test_log_token_refresh(self):
        """Test logging token refresh."""
        log = AuditLoggingService.log_token_refresh(self.user, self.mock_request)
        
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_TOKEN_REFRESH)
        self.assertEqual(log.actor_user, self.user)
    
    def test_log_access_denied(self):
        """Test logging access denied."""
        log = AuditLoggingService.log_access_denied(
            user=self.user,
            resource='course',
            resource_id='123',
            reason='Not enrolled',
            request=self.mock_request
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_ACCESS_DENIED)
        self.assertEqual(log.target_resource, 'course')
        self.assertEqual(log.reason, 'Not enrolled')
    
    def test_log_bulk_export(self):
        """Test logging bulk export."""
        log = AuditLoggingService.log_bulk_export(
            user=self.user,
            record_count=1000,
            filters={'course_id': '123'},
            request=self.mock_request
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, SecurityAuditLog.EVENT_BULK_EXPORT)
        self.assertEqual(log.details.get('record_count'), 1000)


class AuditLogQueryServiceTests(TestCase):
    """Tests for AuditLogQueryService."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        
        # Create test logs
        for i in range(10):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.user,
                outcome='success'
            )
        
        for i in range(5):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
                event_category=SecurityAuditLog.CATEGORY_AUTHZ,
                severity=SecurityAuditLog.SEVERITY_WARNING,
                actor_user=self.user,
                outcome='denied'
            )
    
    def test_get_logs_by_category(self):
        """Test filtering logs by category."""
        logs = AuditLogQueryService.get_logs(
            event_category=SecurityAuditLog.CATEGORY_AUTHN
        )
        self.assertEqual(logs.count(), 10)
    
    def test_get_logs_by_severity(self):
        """Test filtering logs by severity."""
        logs = AuditLogQueryService.get_logs(
            severity=SecurityAuditLog.SEVERITY_WARNING
        )
        self.assertEqual(logs.count(), 5)
    
    def test_get_logs_by_user(self):
        """Test filtering logs by user."""
        logs = AuditLogQueryService.get_logs(user=self.user)
        self.assertEqual(logs.count(), 15)
    
    def test_get_logs_by_date_range(self):
        """Test filtering logs by date range."""
        start_date = timezone.now() - timedelta(days=1)
        end_date = timezone.now() + timedelta(days=1)
        
        logs = AuditLogQueryService.get_logs(
            start_date=start_date,
            end_date=end_date
        )
        self.assertEqual(logs.count(), 15)
    
    def test_get_logs_by_event_type(self):
        """Test filtering logs by event type."""
        logs = AuditLogQueryService.get_logs(
            event_types=[SecurityAuditLog.EVENT_LOGIN_SUCCESS]
        )
        self.assertEqual(logs.count(), 10)
    
    def test_get_logs_combined_filters(self):
        """Test filtering with multiple criteria."""
        logs = AuditLogQueryService.get_logs(
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            user=self.user
        )
        self.assertEqual(logs.count(), 10)
    
    def test_get_security_summary(self):
        """Test getting security summary."""
        summary = AuditLogQueryService.get_security_summary(
            days=1
        )
        
        self.assertIn('total_events', summary)
        self.assertIn('by_category', summary)
        self.assertIn('by_severity', summary)
        self.assertEqual(summary['total_events'], 15)
    
    def test_get_failed_login_attempts(self):
        """Test getting failed login attempts."""
        # Create failed login attempts
        for i in range(3):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_WARNING,
                actor_user=None,
                outcome='failure',
                ip_address='192.168.1.100'
            )
        
        attempts = AuditLogQueryService.get_failed_login_attempts(
            ip_address='192.168.1.100',
            minutes=60
        )
        self.assertEqual(attempts, 3)
    
    def test_get_user_activity_timeline(self):
        """Test getting user activity timeline."""
        timeline = AuditLogQueryService.get_user_activity_timeline(
            user=self.user,
            days=1
        )
        
        self.assertIn('timeline', timeline)
        self.assertIn('total_events', timeline)
        self.assertEqual(timeline['total_events'], 15)


class AuditLogExportTests(TestCase):
    """Tests for AuditLogExport model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_export_creation(self):
        """Test audit log export creation."""
        export = AuditLogExport.objects.create(
            requested_by=self.user,
            start_date=timezone.now() - timedelta(days=7),
            end_date=timezone.now(),
            export_format=AuditLogExport.FORMAT_CSV
        )
        
        self.assertIsNotNone(export.id)
        self.assertEqual(export.status, AuditLogExport.STATUS_PENDING)
        self.assertEqual(export.export_format, AuditLogExport.FORMAT_CSV)
    
    def test_export_string_representation(self):
        """Test string representation of export."""
        export = AuditLogExport.objects.create(
            requested_by=self.user,
            start_date=timezone.now() - timedelta(days=7),
            end_date=timezone.now(),
            export_format=AuditLogExport.FORMAT_CSV
        )
        
        expected = f"Export by {self.user.email}"
        self.assertIn(expected, str(export))


class AuditLogExportServiceTests(TestCase):
    """Tests for AuditLogExportService."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        
        # Create test logs
        for i in range(20):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.user,
                outcome='success'
            )
    
    def test_create_export_job(self):
        """Test creating an export job."""
        export = AuditLogExportService.create_export_job(
            requested_by=self.user,
            start_date=timezone.now() - timedelta(days=7),
            end_date=timezone.now(),
            export_format='csv'
        )
        
        self.assertIsNotNone(export)
        self.assertEqual(export.status, AuditLogExport.STATUS_PENDING)
    
    def test_process_export_csv(self):
        """Test processing CSV export."""
        export = AuditLogExport.objects.create(
            requested_by=self.user,
            start_date=timezone.now() - timedelta(days=7),
            end_date=timezone.now(),
            export_format=AuditLogExport.FORMAT_CSV
        )
        
        result = AuditLogExportService.process_export(export.id)
        
        self.assertTrue(result['success'])
        export.refresh_from_db()
        self.assertEqual(export.status, AuditLogExport.STATUS_COMPLETED)
        self.assertIsNotNone(export.file_path)
    
    def test_process_export_json(self):
        """Test processing JSON export."""
        export = AuditLogExport.objects.create(
            requested_by=self.user,
            start_date=timezone.now() - timedelta(days=7),
            end_date=timezone.now(),
            export_format=AuditLogExport.FORMAT_JSON
        )
        
        result = AuditLogExportService.process_export(export.id)
        
        self.assertTrue(result['success'])
        export.refresh_from_db()
        self.assertEqual(export.status, AuditLogExport.STATUS_COMPLETED)


class SecurityAuditLogAPITests(APITestCase):
    """API tests for Security Audit Log endpoints."""
    
    def setUp(self):
        """Set up test data."""
        # Create roles
        self.admin_role, _ = Role.objects.get_or_create(
            role_name='admin',
            defaults={'display_name': 'Administrator', 'is_system_role': True}
        )
        
        # Create users
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            username='admin',
            password='adminpass123'
        )
        self.admin_user.assigned_roles.add(self.admin_role)
        
        self.regular_user = User.objects.create_user(
            email='user@example.com',
            username='user',
            password='userpass123'
        )
        
        # Create test logs
        for i in range(10):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.regular_user,
                outcome='success'
            )
        
        self.client = APIClient()
    
    def test_list_audit_logs_as_admin(self):
        """Test listing audit logs as admin."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v1/analytics/audit-logs/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_list_audit_logs_as_regular_user(self):
        """Test listing audit logs as regular user (should fail)."""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/api/v1/analytics/audit-logs/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_list_audit_logs_unauthenticated(self):
        """Test listing audit logs without authentication."""
        response = self.client.get('/api/v1/analytics/audit-logs/')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_filter_audit_logs_by_category(self):
        """Test filtering audit logs by category."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(
            '/api/v1/analytics/audit-logs/',
            {'event_category': SecurityAuditLog.CATEGORY_AUTHN}
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_export_audit_logs(self):
        """Test exporting audit logs."""
        self.client.force_authenticate(user=self.admin_user)
        
        data = {
            'start_date': (timezone.now() - timedelta(days=7)).isoformat(),
            'end_date': timezone.now().isoformat(),
            'export_format': 'csv'
        }
        
        response = self.client.post(
            '/api/v1/analytics/audit-logs/export/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('export_id', response.data)
    
    def test_verify_chain_integrity_endpoint(self):
        """Test chain integrity verification endpoint."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/v1/analytics/audit-logs/verify-chain/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('is_valid', response.data)


class AuditLogComplianceTests(TestCase):
    """Tests for SOC 2 compliance requirements."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_all_auth_events_logged(self):
        """Test that all authentication events are logged."""
        # Login success
        AuditLoggingService.log_login_success(self.user, None)
        
        # Login failure
        AuditLoggingService.log_login_failure('test@example.com', 'Invalid', None)
        
        # Logout
        AuditLoggingService.log_logout(self.user, None)
        
        # Token refresh
        AuditLoggingService.log_token_refresh(self.user, None)
        
        # Verify all events exist
        auth_logs = SecurityAuditLog.objects.filter(
            event_category=SecurityAuditLog.CATEGORY_AUTHN
        )
        self.assertEqual(auth_logs.count(), 4)
    
    def test_access_denied_events_logged(self):
        """Test that access denied events are logged."""
        AuditLoggingService.log_access_denied(
            user=self.user,
            resource='course',
            resource_id='123',
            reason='Permission denied',
            request=None
        )
        
        log = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED
        ).first()
        
        self.assertIsNotNone(log)
        self.assertEqual(log.outcome, 'denied')
        self.assertEqual(log.reason, 'Permission denied')
    
    def test_sensitive_data_access_logged(self):
        """Test that sensitive data access is logged."""
        AuditLoggingService.log_bulk_export(
            user=self.user,
            record_count=100,
            filters={'contains_pii': True},
            request=None
        )
        
        log = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_BULK_EXPORT
        ).first()
        
        self.assertIsNotNone(log)
        self.assertEqual(log.details.get('record_count'), 100)
    
    def test_audit_logs_immutable(self):
        """Test that audit logs cannot be modified after creation."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        # Attempt to modify (this would break integrity)
        original_hash = log.current_hash
        log.outcome = 'tampered'
        log.save(update_fields=['outcome'])
        
        # Verify integrity check fails
        self.assertFalse(log.verify_integrity())
    
    def test_audit_log_retention(self):
        """Test audit log retention and querying."""
        # Create old log
        old_log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=self.user,
            outcome='success'
        )
        
        # Manually set timestamp to 90 days ago
        old_log.timestamp = timezone.now() - timedelta(days=90)
        old_log.save(update_fields=['timestamp'])
        
        # Query logs from last 30 days
        recent_logs = SecurityAuditLog.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=30)
        )
        
        # Should not include the old log
        self.assertNotIn(old_log, recent_logs)


class AuditLogPerformanceTests(TestCase):
    """Performance tests for audit logging."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_bulk_log_creation(self):
        """Test creating many audit logs efficiently."""
        import time
        
        start_time = time.time()
        
        for i in range(100):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.user,
                outcome='success',
                details={'iteration': i}
            )
        
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time (less than 10 seconds)
        self.assertLess(elapsed, 10)
        self.assertEqual(SecurityAuditLog.objects.count(), 100)
    
    def test_chain_verification_performance(self):
        """Test chain verification with many logs."""
        # Create 100 logs
        for i in range(100):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=self.user,
                outcome='success'
            )
        
        import time
        start_time = time.time()
        
        is_valid, broken_at = SecurityAuditLog.verify_chain_integrity()
        
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time
        self.assertLess(elapsed, 5)
        self.assertTrue(is_valid)
        self.assertIsNone(broken_at)
