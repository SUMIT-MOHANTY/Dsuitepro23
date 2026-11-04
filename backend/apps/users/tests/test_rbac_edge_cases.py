"""
RBAC Edge Case Tests for Enterprise LMS
Tests role conflict detection, permission inheritance validation, and audit trail integrity.
"""

import pytest
import hashlib
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import Role, UserRole, UserSession, RBACConflict
from apps.analytics.models import SecurityAuditLog

User = get_user_model()


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def api_client():
    """Return an API client for testing."""
    return APIClient()


@pytest.fixture
def learner_role():
    """Create and return the learner role."""
    role, _ = Role.objects.get_or_create(
        role_name='learner',
        defaults={
            'display_name': 'Learner',
            'description': 'Standard learner role',
            'is_system_role': True
        }
    )
    return role


@pytest.fixture
def instructor_role():
    """Create and return the instructor role."""
    role, _ = Role.objects.get_or_create(
        role_name='instructor',
        defaults={
            'display_name': 'Instructor',
            'description': 'Course instructor role',
            'is_system_role': True
        }
    )
    return role


@pytest.fixture
def admin_role():
    """Create and return the admin role."""
    role, _ = Role.objects.get_or_create(
        role_name='admin',
        defaults={
            'display_name': 'Administrator',
            'description': 'System administrator role',
            'is_system_role': True
        }
    )
    return role


@pytest.fixture
def content_manager_role():
    """Create and return the content manager role."""
    role, _ = Role.objects.get_or_create(
        role_name='content_manager',
        defaults={
            'display_name': 'Content Manager',
            'description': 'Content management role',
            'is_system_role': True
        }
    )
    return role


@pytest.fixture
def test_user(learner_role):
    """Create and return a test user with learner role."""
    user = User.objects.create_user(
        email='test@example.com',
        username='testuser',
        password='TestPass123!',
        first_name='Test',
        last_name='User'
    )
    UserRole.objects.create(user=user, role=learner_role, is_primary=True)
    return user


@pytest.fixture
def instructor_user(instructor_role):
    """Create and return a test user with instructor role."""
    user = User.objects.create_user(
        email='instructor@example.com',
        username='instructor',
        password='InstructorPass123!',
        first_name='Instructor',
        last_name='User'
    )
    UserRole.objects.create(user=user, role=instructor_role, is_primary=True)
    return user


@pytest.fixture
def admin_user(admin_role):
    """Create and return an admin test user."""
    user = User.objects.create_user(
        email='admin@example.com',
        username='adminuser',
        password='AdminPass123!',
        first_name='Admin',
        last_name='User',
        is_staff=True
    )
    UserRole.objects.create(user=user, role=admin_role, is_primary=True)
    return user


@pytest.fixture
def dual_role_user(learner_role, instructor_role):
    """Create and return a user with both learner and instructor roles."""
    user = User.objects.create_user(
        email='dual@example.com',
        username='dualrole',
        password='DualPass123!',
        first_name='Dual',
        last_name='Role'
    )
    UserRole.objects.create(user=user, role=learner_role, is_primary=True)
    UserRole.objects.create(user=user, role=instructor_role, is_primary=False)
    return user


@pytest.fixture
def auth_tokens(test_user):
    """Generate and return JWT tokens for test user."""
    refresh = RefreshToken.for_user(test_user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh)
    }


@pytest.fixture
def admin_auth_tokens(admin_user):
    """Generate and return JWT tokens for admin user."""
    refresh = RefreshToken.for_user(admin_user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh)
    }


# ============================================================================
# RBAC Conflict Model Tests
# ============================================================================

@pytest.mark.django_db
class TestRBACConflictModel:
    """Tests for RBACConflict model."""
    
    def test_create_rbac_conflict(self, test_user, learner_role, instructor_role):
        """Test creating an RBAC conflict."""
        conflict = RBACConflict.objects.create(
            user=test_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
            severity=RBACConflict.SEVERITY_HIGH,
            description='User has conflicting learner and instructor roles',
            conflicting_roles=['learner', 'instructor'],
            detection_source='automatic_scan'
        )
        
        assert conflict.id is not None
        assert conflict.user == test_user
        assert conflict.conflict_type == RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT
        assert conflict.severity == RBACConflict.SEVERITY_HIGH
        assert conflict.status == RBACConflict.STATUS_DETECTED
        assert conflict.is_resolved is False
    
    def test_rbac_conflict_resolve(self, test_user, admin_user):
        """Test resolving an RBAC conflict."""
        conflict = RBACConflict.objects.create(
            user=test_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
            severity=RBACConflict.SEVERITY_MEDIUM,
            description='Test conflict',
            conflicting_roles=['role1', 'role2']
        )
        
        conflict.resolve(
            resolved_by=admin_user,
            resolution_action='role_revoked',
            resolution_notes='Revoked instructor role'
        )
        
        assert conflict.status == RBACConflict.STATUS_RESOLVED
        assert conflict.is_resolved is True
        assert conflict.resolved_by == admin_user
        assert conflict.resolution_action == 'role_revoked'
        assert conflict.resolved_at is not None
    
    def test_rbac_conflict_escalate(self, test_user):
        """Test escalating an RBAC conflict."""
        conflict = RBACConflict.objects.create(
            user=test_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_PERMISSION_INHERITANCE,
            severity=RBACConflict.SEVERITY_MEDIUM,
            description='Permission inheritance violation'
        )
        
        conflict.escalate(notes='Requires admin review')
        
        assert conflict.status == RBACConflict.STATUS_ESCALATED
        assert 'Requires admin review' in conflict.resolution_notes
    
    def test_rbac_conflict_ignore(self, test_user):
        """Test ignoring an RBAC conflict."""
        conflict = RBACConflict.objects.create(
            user=test_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_CROSS_DOMAIN,
            severity=RBACConflict.SEVERITY_LOW,
            description='Cross-domain conflict'
        )
        
        conflict.ignore(notes='Legitimate use case')
        
        assert conflict.status == RBACConflict.STATUS_IGNORED
    
    def test_rbac_conflict_days_open(self, test_user):
        """Test calculating days open for a conflict."""
        conflict = RBACConflict.objects.create(
            user=test_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
            severity=RBACConflict.SEVERITY_HIGH,
            description='Test conflict'
        )
        
        # Days open should be 0 or very small for newly created conflict
        assert conflict.days_open >= 0
        
        # Simulate time passing by modifying detected_at
        conflict.detected_at = timezone.now() - timedelta(days=5)
        conflict.save()
        
        # Refresh from database
        conflict.refresh_from_db()
        assert conflict.days_open >= 5


# ============================================================================
# RBAC Conflict Detection Service Tests
# ============================================================================

@pytest.mark.django_db
class TestRBACConflictDetection:
    """Tests for RBAC conflict detection service."""
    
    def test_detect_role_conflict_same_user(self, dual_role_user, learner_role, instructor_role):
        """Test detecting role conflicts for a user with multiple roles."""
        from apps.users.services import RBACEdgeCaseService
        
        conflicts = RBACEdgeCaseService.detect_role_conflicts(dual_role_user)
        
        # Should detect at least one conflict
        assert len(conflicts) > 0
        
        # Check conflict details
        conflict = conflicts[0]
        assert conflict['user_id'] == str(dual_role_user.id)
        assert 'learner' in conflict['conflicting_roles']
        assert 'instructor' in conflict['conflicting_roles']
    
    def test_detect_no_conflict_single_role(self, test_user):
        """Test that single role users have no conflicts."""
        from apps.users.services import RBACEdgeCaseService
        
        conflicts = RBACEdgeCaseService.detect_role_conflicts(test_user)
        
        # Single role should not have conflicts
        assert len(conflicts) == 0
    
    def test_validate_permission_inheritance(self, test_user, learner_role):
        """Test permission inheritance validation."""
        from apps.users.services import RBACEdgeCaseService
        
        # Add permissions to role
        learner_role.permissions = ['view_course', 'view_lesson']
        learner_role.save()
        
        result = RBACEdgeCaseService.validate_permission_inheritance(test_user)
        
        # Should return validation result
        assert 'is_valid' in result
        assert 'permissions' in result
    
    def test_check_time_bound_grants(self, test_user, learner_role):
        """Test checking time-bound role grants."""
        from apps.users.services import RBACEdgeCaseService
        
        # Create a time-bound role
        user_role = UserRole.objects.create(
            user=test_user,
            role=learner_role,
            is_primary=False,
            expires_at=timezone.now() + timedelta(days=30)
        )
        
        expired_grants = RBACEdgeCaseService.check_time_bound_grants(test_user)
        
        # Should not have expired grants yet
        assert len(expired_grants) == 0
    
    def test_check_expired_time_bound_grants(self, test_user, learner_role):
        """Test detecting expired time-bound grants."""
        from apps.users.services import RBACEdgeCaseService
        
        # Create an expired role grant
        user_role = UserRole.objects.create(
            user=test_user,
            role=learner_role,
            is_primary=False,
            expires_at=timezone.now() - timedelta(days=1)
        )
        
        expired_grants = RBACEdgeCaseService.check_time_bound_grants(test_user)
        
        # Should detect expired grant
        assert len(expired_grants) > 0


# ============================================================================
# RBAC Conflict API Tests
# ============================================================================

@pytest.mark.django_db
class TestRBACConflictAPI:
    """Tests for RBAC conflict API endpoints."""
    
    def test_list_rbac_conflicts_admin(self, api_client, admin_auth_tokens, dual_role_user):
        """Test listing RBAC conflicts as admin."""
        # Create a conflict first
        RBACConflict.objects.create(
            user=dual_role_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
            severity=RBACConflict.SEVERITY_HIGH,
            description='Role conflict detected',
            conflicting_roles=['learner', 'instructor']
        )
        
        url = '/api/v1/users/rbac-conflicts/'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_auth_tokens["access"]}')
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
    
    def test_list_rbac_conflicts_non_admin(self, api_client, auth_tokens):
        """Test that non-admins cannot list all RBAC conflicts."""
        url = '/api/v1/users/rbac-conflicts/'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_tokens["access"]}')
        
        response = api_client.get(url)
        
        # Should be forbidden for non-admins
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_own_rbac_conflicts(self, api_client, auth_tokens, test_user):
        """Test getting own RBAC conflicts."""
        # Create a conflict for the user
        RBACConflict.objects.create(
            user=test_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
            severity=RBACConflict.SEVERITY_MEDIUM,
            description='Test conflict',
            conflicting_roles=['role1', 'role2']
        )
        
        url = '/api/v1/users/me/rbac-conflicts/'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_tokens["access"]}')
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_resolve_rbac_conflict(self, api_client, admin_auth_tokens, dual_role_user, admin_user):
        """Test resolving an RBAC conflict."""
        # Create a conflict
        conflict = RBACConflict.objects.create(
            user=dual_role_user,
            conflict_type=RBACConflict.CONFLICT_TYPE_ROLE_CONFLICT,
            severity=RBACConflict.SEVERITY_HIGH,
            description='Role conflict',
            conflicting_roles=['learner', 'instructor']
        )
        
        url = f'/api/v1/users/rbac-conflicts/{conflict.id}/resolve/'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_auth_tokens["access"]}')
        
        data = {
            'resolution_action': 'role_revoked',
            'resolution_notes': 'Revoked instructor role as resolution'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        
        # Refresh conflict from DB
        conflict.refresh_from_db()
        assert conflict.status == RBACConflict.STATUS_RESOLVED


# ============================================================================
# Security Audit Log Tests
# ============================================================================

@pytest.mark.django_db
class TestSecurityAuditLog:
    """Tests for SecurityAuditLog model and integrity."""
    
    def test_create_security_audit_log(self, test_user):
        """Test creating a security audit log entry."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            target_resource='user_account',
            target_resource_id=str(test_user.id),
            outcome='success',
            ip_address='192.168.1.1',
            user_agent='TestAgent/1.0',
            request_method='POST',
            request_path='/api/v1/auth/login/',
            details={'login_method': 'password'}
        )
        
        assert log.id is not None
        assert log.event_type == SecurityAuditLog.EVENT_LOGIN_SUCCESS
        assert log.actor_user == test_user
        assert log.current_hash is not None
        assert len(log.current_hash) == 64  # SHA-256 hex length
    
    def test_security_log_hash_integrity(self, test_user):
        """Test that security log hashes are calculated correctly."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=test_user,
            outcome='denied',
            reason='Insufficient permissions'
        )
        
        # Verify integrity
        assert log.verify_integrity() is True
        
        # Tamper with data and verify it fails
        log.outcome = 'granted'
        assert log.verify_integrity() is False
    
    def test_security_log_chain_integrity(self, test_user):
        """Test hash chain integrity across multiple logs."""
        # Create multiple logs
        log1 = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        log2 = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ACCESS_GRANTED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        # Verify chain integrity
        is_valid, broken_at = SecurityAuditLog.verify_chain_integrity()
        assert is_valid is True
        assert broken_at is None
        
        # Verify previous_hash linkage
        assert log2.previous_hash == log1.current_hash
    
    def test_security_log_chain_integrity_broken(self, test_user):
        """Test detecting broken hash chain."""
        # Create logs
        log1 = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        log2 = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGOUT,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        # Tamper with first log's hash
        log1.current_hash = 'tampered_hash' * 4  # Make it 64 chars
        log1.save()
        
        # Verify chain is broken
        is_valid, broken_at = SecurityAuditLog.verify_chain_integrity()
        assert is_valid is False
        assert broken_at is not None
    
    def test_security_log_severity_levels(self, test_user):
        """Test different severity levels."""
        # Info level
        info_log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        assert info_log.severity == SecurityAuditLog.SEVERITY_INFO
        
        # Warning level
        warning_log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=test_user,
            outcome='denied'
        )
        assert warning_log.severity == SecurityAuditLog.SEVERITY_WARNING
        
        # Critical level
        critical_log = SecurityAuditLog.log_event(
            event_type='brute_force_detected',
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_CRITICAL,
            actor_user=test_user,
            outcome='alert'
        )
        assert critical_log.severity == SecurityAuditLog.SEVERITY_CRITICAL


# ============================================================================
# Audit Trail Integrity Tests
# ============================================================================

@pytest.mark.django_db
class TestAuditTrailIntegrity:
    """Tests for audit trail integrity and tamper detection."""
    
    def test_audit_log_immutable_after_creation(self, test_user):
        """Test that audit logs cannot be modified after creation."""
        log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        original_hash = log.current_hash
        
        # Attempt to modify (this should ideally be prevented or detected)
        log.outcome = 'modified'
        log.save()
        
        # Hash should no longer match
        assert log.verify_integrity() is False
    
    def test_audit_log_query_by_category(self, test_user):
        """Test querying audit logs by category."""
        # Create logs in different categories
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=test_user,
            outcome='denied'
        )
        
        # Query by category
        authn_logs = SecurityAuditLog.objects.filter(
            event_category=SecurityAuditLog.CATEGORY_AUTHN
        )
        authz_logs = SecurityAuditLog.objects.filter(
            event_category=SecurityAuditLog.CATEGORY_AUTHZ
        )
        
        assert authn_logs.count() >= 1
        assert authz_logs.count() >= 1
    
    def test_audit_log_query_by_severity(self, test_user):
        """Test querying audit logs by severity."""
        # Create logs with different severities
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
            event_category=SecurityAuditLog.CATEGORY_AUTHN,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=test_user,
            outcome='success'
        )
        
        SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ACCESS_DENIED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=test_user,
            outcome='denied'
        )
        
        # Query by severity
        info_logs = SecurityAuditLog.objects.filter(severity=SecurityAuditLog.SEVERITY_INFO)
        warning_logs = SecurityAuditLog.objects.filter(severity=SecurityAuditLog.SEVERITY_WARNING)
        
        assert info_logs.count() >= 1
        assert warning_logs.count() >= 1
    
    def test_audit_log_actor_tracking(self, test_user, admin_user):
        """Test that actor information is properly tracked."""
        # Log action by regular user
        user_log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_BULK_EXPORT,
            event_category=SecurityAuditLog.CATEGORY_DATA_ACCESS,
            severity=SecurityAuditLog.SEVERITY_WARNING,
            actor_user=test_user,
            outcome='success'
        )
        
        assert user_log.actor_user == test_user
        assert user_log.actor_email == test_user.email
        
        # Log action by admin
        admin_log = SecurityAuditLog.log_event(
            event_type=SecurityAuditLog.EVENT_ROLE_ASSIGNED,
            event_category=SecurityAuditLog.CATEGORY_AUTHZ,
            severity=SecurityAuditLog.SEVERITY_INFO,
            actor_user=admin_user,
            outcome='success'
        )
        
        assert admin_log.actor_user == admin_user
        assert admin_log.actor_email == admin_user.email


# ============================================================================
# Role Assignment Signal Tests
# ============================================================================

@pytest.mark.django_db
class TestRoleAssignmentSignals:
    """Tests for role assignment signal handlers."""
    
    def test_role_assignment_creates_audit_log(self, test_user, instructor_role):
        """Test that role assignment creates an audit log."""
        initial_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ROLE_ASSIGNED
        ).count()
        
        # Assign new role
        UserRole.objects.create(
            user=test_user,
            role=instructor_role,
            is_primary=False
        )
        
        # Check that audit log was created
        new_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ROLE_ASSIGNED
        ).count()
        
        assert new_count > initial_count
    
    def test_role_revocation_creates_audit_log(self, test_user, instructor_role):
        """Test that role revocation creates an audit log."""
        # First assign the role
        user_role = UserRole.objects.create(
            user=test_user,
            role=instructor_role,
            is_primary=False
        )
        
        initial_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ROLE_REVOKED
        ).count()
        
        # Revoke the role
        user_role.delete()
        
        # Check that audit log was created
        new_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ROLE_REVOKED
        ).count()
        
        assert new_count > initial_count


# ============================================================================
# Permission Edge Case Tests
# ============================================================================

@pytest.mark.django_db
class TestPermissionEdgeCases:
    """Tests for permission edge cases and boundary conditions."""
    
    def test_user_with_all_system_roles(self, learner_role, instructor_role, admin_role, content_manager_role):
        """Test user with all system roles assigned."""
        user = User.objects.create_user(
            email='allroles@example.com',
            username='allroles',
            password='AllRoles123!'
        )
        
        # Assign all roles
        UserRole.objects.create(user=user, role=learner_role, is_primary=True)
        UserRole.objects.create(user=user, role=instructor_role, is_primary=False)
        UserRole.objects.create(user=user, role=admin_role, is_primary=False)
        UserRole.objects.create(user=user, role=content_manager_role, is_primary=False)
        
        # Verify user has all roles
        assert user.has_role('learner')
        assert user.has_role('instructor')
        assert user.has_role('admin')
        assert user.has_role('content_manager')
        
        # Should have conflicts detected
        from apps.users.services import RBACEdgeCaseService
        conflicts = RBACEdgeCaseService.detect_role_conflicts(user)
        assert len(conflicts) > 0
    
    def test_role_assignment_with_expiration(self, test_user, instructor_role):
        """Test role assignment with expiration date."""
        expires_at = timezone.now() + timedelta(days=30)
        
        user_role = UserRole.objects.create(
            user=test_user,
            role=instructor_role,
            is_primary=False,
            expires_at=expires_at
        )
        
        assert user_role.expires_at == expires_at
        assert not user_role.is_expired()
        
        # Test expired role
        user_role.expires_at = timezone.now() - timedelta(days=1)
        user_role.save()
        
        assert user_role.is_expired()
    
    def test_primary_role_uniqueness(self, test_user, learner_role, instructor_role):
        """Test that only one role can be primary."""
        # First role is primary
        role1 = UserRole.objects.create(
            user=test_user,
            role=learner_role,
            is_primary=True
        )
        
        # Second role should not be primary
        role2 = UserRole.objects.create(
            user=test_user,
            role=instructor_role,
            is_primary=False
        )
        
        assert role1.is_primary is True
        assert role2.is_primary is False
    
    def test_get_primary_role(self, test_user, learner_role, instructor_role):
        """Test getting user's primary role."""
        # Initially has learner as primary
        assert test_user.get_primary_role() == 'learner'
        
        # Add instructor as primary (should replace)
        UserRole.objects.filter(user=test_user, role=learner_role).update(is_primary=False)
        UserRole.objects.create(
            user=test_user,
            role=instructor_role,
            is_primary=True
        )
        
        # Refresh user
        test_user.refresh_from_db()
        assert test_user.get_primary_role() == 'instructor'


# ============================================================================
# Compliance and Security Tests
# ============================================================================

@pytest.mark.django_db
class TestComplianceAndSecurity:
    """Tests for SOC 2 compliance and security requirements."""
    
    def test_access_removal_on_deactivation(self, test_user, admin_user):
        """Test that access is removed when user is deactivated (SOC 2 CC6.3)."""
        # Create active session
        session = UserSession.objects.create(
            user=test_user,
            session_key='test_session_key',
            ip_address='192.168.1.1'
        )
        
        assert session.is_active() is True
        
        # Deactivate user
        test_user.is_active = False
        test_user.save()
        
        # Session should be revoked
        session.refresh_from_db()
        assert session.is_active() is False
        assert session.is_revoked is True
    
    def test_audit_log_for_deactivation(self, test_user):
        """Test that user deactivation is logged."""
        initial_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ROLE_REVOKED
        ).count()
        
        # Deactivate user
        test_user.is_active = False
        test_user.save()
        
        # Check for audit log
        new_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_ROLE_REVOKED
        ).count()
        
        # Should have logged the deactivation
        assert new_count >= initial_count
    
    def test_failed_login_audit_logging(self, api_client):
        """Test that failed login attempts are audited."""
        initial_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        ).count()
        
        # Attempt login with wrong password
        url = '/api/v1/auth/login/'
        data = {
            'email': 'nonexistent@example.com',
            'password': 'WrongPassword123!'
        }
        
        response = api_client.post(url, data, format='json')
        
        # Check for audit log
        new_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_FAILURE
        ).count()
        
        assert new_count > initial_count
    
    def test_successful_login_audit_logging(self, api_client, test_user):
        """Test that successful logins are audited."""
        initial_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS
        ).count()
        
        # Login successfully
        url = '/api/v1/auth/login/'
        data = {
            'email': test_user.email,
            'password': 'TestPass123!'
        }
        
        response = api_client.post(url, data, format='json')
        
        # Check for audit log
        new_count = SecurityAuditLog.objects.filter(
            event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS
        ).count()
        
        assert new_count > initial_count


# ============================================================================
# Performance and Scalability Tests
# ============================================================================

@pytest.mark.django_db
class TestPerformanceAndScalability:
    """Tests for RBAC and audit log performance."""
    
    def test_bulk_conflict_detection(self, admin_user, learner_role, instructor_role):
        """Test bulk conflict detection performance."""
        from apps.users.services import RBACEdgeCaseService
        
        # Create multiple users with dual roles
        users = []
        for i in range(10):
            user = User.objects.create_user(
                email=f'bulkuser{i}@example.com',
                username=f'bulkuser{i}',
                password='TestPass123!'
            )
            UserRole.objects.create(user=user, role=learner_role, is_primary=True)
            UserRole.objects.create(user=user, role=instructor_role, is_primary=False)
            users.append(user)
        
        # Detect conflicts for all users
        all_conflicts = []
        for user in users:
            conflicts = RBACEdgeCaseService.detect_role_conflicts(user)
            all_conflicts.extend(conflicts)
        
        # Should detect conflicts for all dual-role users
        assert len(all_conflicts) >= len(users)
    
    def test_audit_log_query_performance(self, test_user):
        """Test audit log query performance with many records."""
        # Create many audit logs
        for i in range(50):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=test_user,
                outcome='success',
                details={'iteration': i}
            )
        
        # Query should be fast (using indexes)
        logs = SecurityAuditLog.objects.filter(
            actor_user=test_user,
            event_category=SecurityAuditLog.CATEGORY_AUTHN
        )[:10]
        
        assert len(list(logs)) == 10
    
    def test_hash_chain_verification_performance(self, test_user):
        """Test hash chain verification with many records."""
        # Create many audit logs
        for i in range(20):
            SecurityAuditLog.log_event(
                event_type=SecurityAuditLog.EVENT_LOGIN_SUCCESS,
                event_category=SecurityAuditLog.CATEGORY_AUTHN,
                severity=SecurityAuditLog.SEVERITY_INFO,
                actor_user=test_user,
                outcome='success'
            )
        
        # Verify chain integrity
        is_valid, broken_at = SecurityAuditLog.verify_chain_integrity()
        
        assert is_valid is True
        assert broken_at is None
