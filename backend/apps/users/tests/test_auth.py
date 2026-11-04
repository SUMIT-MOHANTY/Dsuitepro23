"""
Authentication Tests for Enterprise LMS
Tests user registration, login, token refresh, and password reset.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import Role, UserRole

User = get_user_model()


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
def test_user(learner_role):
    """Create and return a test user."""
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
def auth_tokens(test_user):
    """Generate and return JWT tokens for test user."""
    refresh = RefreshToken.for_user(test_user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh)
    }


@pytest.mark.django_db
class TestUserRegistration:
    """Tests for user registration endpoint."""
    
    def test_register_success(self, api_client, learner_role):
        """Test successful user registration."""
        url = '/api/v1/auth/register/'
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'NewPass123!',
            'password_confirm': 'NewPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert response.data['user']['email'] == 'newuser@example.com'
        assert 'access' in response.data['tokens']
        assert 'refresh' in response.data['tokens']
    
    def test_register_password_mismatch(self, api_client):
        """Test registration with mismatched passwords."""
        url = '/api/v1/auth/register/'
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'NewPass123!',
            'password_confirm': 'DifferentPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['code'] == 'VALIDATION_ERROR'
    
    def test_register_duplicate_email(self, api_client, test_user):
        """Test registration with duplicate email."""
        url = '/api/v1/auth/register/'
        data = {
            'email': test_user.email,  # Already exists
            'username': 'different',
            'password': 'NewPass123!',
            'password_confirm': 'NewPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUserLogin:
    """Tests for user login endpoint."""
    
    def test_login_success(self, api_client, test_user):
        """Test successful user login."""
        url = '/api/v1/auth/login/'
        data = {
            'email': test_user.email,
            'password': 'TestPass123!'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert response.data['user']['email'] == test_user.email
    
    def test_login_invalid_credentials(self, api_client, test_user):
        """Test login with invalid credentials."""
        url = '/api/v1/auth/login/'
        data = {
            'email': test_user.email,
            'password': 'WrongPassword!'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data['code'] == 'AUTHENTICATION_FAILED'
    
    def test_login_missing_credentials(self, api_client):
        """Test login with missing credentials."""
        url = '/api/v1/auth/login/'
        data = {
            'email': 'test@example.com'
            # Missing password
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['code'] == 'MISSING_CREDENTIALS'


@pytest.mark.django_db
class TestTokenRefresh:
    """Tests for token refresh endpoint."""
    
    def test_token_refresh_success(self, api_client, test_user, auth_tokens):
        """Test successful token refresh."""
        url = '/api/v1/auth/token/refresh/'
        data = {
            'refresh': auth_tokens['refresh']
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
    
    def test_token_refresh_invalid(self, api_client):
        """Test token refresh with invalid token."""
        url = '/api/v1/auth/token/refresh/'
        data = {
            'refresh': 'invalid.token.here'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserProfile:
    """Tests for user profile endpoint."""
    
    def test_get_profile_authenticated(self, api_client, test_user, auth_tokens):
        """Test getting profile when authenticated."""
        url = '/api/v1/users/me/'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_tokens["access"]}')
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == test_user.email
    
    def test_get_profile_unauthenticated(self, api_client):
        """Test getting profile when not authenticated."""
        url = '/api/v1/users/me/'
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPasswordReset:
    """Tests for password reset endpoints."""
    
    def test_password_reset_request(self, api_client, test_user):
        """Test password reset request."""
        url = '/api/v1/auth/password-reset-request/'
        data = {
            'email': test_user.email
        }
        
        response = api_client.post(url, data, format='json')
        
        # Always returns success to prevent email enumeration
        assert response.status_code == status.HTTP_200_OK
    
    def test_password_reset_request_nonexistent(self, api_client):
        """Test password reset request for non-existent email."""
        url = '/api/v1/auth/password-reset-request/'
        data = {
            'email': 'nonexistent@example.com'
        }
        
        response = api_client.post(url, data, format='json')
        
        # Still returns success to prevent email enumeration
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestUserLogout:
    """Tests for user logout endpoint."""
    
    def test_logout_success(self, api_client, test_user, auth_tokens):
        """Test successful logout."""
        url = '/api/v1/auth/logout/'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {auth_tokens["access"]}')
        data = {
            'refresh': auth_tokens['refresh']
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == 'Successfully logged out.'
    
    def test_logout_unauthenticated(self, api_client):
        """Test logout when not authenticated."""
        url = '/api/v1/auth/logout/'
        data = {
            'refresh': 'some.token.here'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
