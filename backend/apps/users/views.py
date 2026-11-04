"""
Users Views for Enterprise LMS
Provides authentication and user management API endpoints.
"""

import logging
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.exceptions import ValidationError, NotFoundError, AuthenticationError

from .models import Role, UserRole, UserSession, RBACConflict
from .permissions import IsSelfOrAdmin, CanImpersonate
from .serializers import (
    CustomTokenObtainPairSerializer,
    ImpersonateSerializer,
    LogoutSerializer,
    MFAVerifySerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    RoleSerializer,
    TokenRefreshResponseSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    UserListSerializer,
    UserSessionSerializer,
    UserUpdateSerializer,
    RBACConflictSerializer,
    RBACConflictResolveSerializer,
)
from .services import (
    AuthenticationService,
    ImpersonationService,
    MFAService,
    PasswordResetService,
    SessionService,
    UserManagementService,
    RBACEdgeCaseService,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class AuthViewSet(viewsets.ViewSet):
    """
    Authentication ViewSet providing registration, login, logout,
    token refresh, password reset, and MFA endpoints.
    """
    permission_classes = [AllowAny]
    
    def get_permissions(self):
        """Instantiate and return the list of permissions."""
        if self.action in ['logout', 'change_password', 'mfa_setup', 'mfa_verify', 'mfa_disable']:
            return [IsAuthenticated()]
        return [AllowAny()]
    
    @action(detail=False, methods=['post'], url_path='register')
    def register(self, request):
        """
        Register a new user.
        POST /api/v1/auth/register/
        """
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid registration data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                user = serializer.save()
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                # Create session record
                SessionService.create_session(
                    user=user,
                    request=request,
                    session_key=str(refresh)
                )
                
                logger.info(f"User registered: {user.email}")
                
                return Response({
                    'user': UserDetailSerializer(user).data,
                    'tokens': {
                        'access': str(refresh.access_token),
                        'refresh': str(refresh)
                    }
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return Response(
                {
                    'code': 'REGISTRATION_FAILED',
                    'detail': 'Registration failed. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='login')
    def login(self, request):
        """
        Authenticate user and return JWT tokens.
        POST /api/v1/auth/login/
        """
        email = request.data.get('email')
        password = request.data.get('password')
        mfa_code = request.data.get('mfa_code')
        
        if not email or not password:
            return Response(
                {
                    'code': 'MISSING_CREDENTIALS',
                    'detail': 'Email and password are required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = AuthenticationService.authenticate(
                email=email,
                password=password,
                mfa_code=mfa_code,
                request=request
            )
            
            if result.get('mfa_required'):
                return Response({
                    'code': 'MFA_REQUIRED',
                    'detail': 'Multi-factor authentication required.',
                    'mfa_token': result.get('mfa_token')
                }, status=status.HTTP_202_ACCEPTED)
            
            logger.info(f"User logged in: {email}")
            
            return Response({
                'user': result['user'],
                'tokens': result['tokens']
            })
            
        except AuthenticationError as e:
            return Response(
                {'code': 'AUTHENTICATION_FAILED', 'detail': str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return Response(
                {
                    'code': 'LOGIN_FAILED',
                    'detail': 'Login failed. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='logout')
    def logout(self, request):
        """
        Logout user and blacklist refresh token.
        POST /api/v1/auth/logout/
        """
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid logout data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            refresh_token = serializer.validated_data.get('refresh')
            all_sessions = serializer.validated_data.get('all_sessions', False)
            
            # Blacklist the refresh token
            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                except TokenError:
                    pass
            
            # Revoke session(s)
            if all_sessions:
                SessionService.revoke_all_user_sessions(request.user, revoked_by=request.user)
            else:
                SessionService.revoke_session_by_token(request.user, refresh_token)
            
            logger.info(f"User logged out: {request.user.email}")
            
            return Response({'detail': 'Successfully logged out.'})
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return Response(
                {'code': 'LOGOUT_FAILED', 'detail': 'Logout failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='refresh')
    def refresh(self, request):
        """
        Refresh access token using refresh token.
        POST /api/v1/auth/refresh/
        """
        refresh_token = request.data.get('refresh')
        
        if not refresh_token:
            return Response(
                {
                    'code': 'MISSING_TOKEN',
                    'detail': 'Refresh token is required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            token = RefreshToken(refresh_token)
            user_id = token['user_id']
            
            user = User.objects.get(id=user_id)
            
            # Check if session is revoked
            if not SessionService.is_session_valid(user, refresh_token):
                return Response(
                    {
                        'code': 'SESSION_REVOKED',
                        'detail': 'Session has been revoked. Please login again.'
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Generate new tokens
            new_refresh = RefreshToken.for_user(user)
            
            # Update session
            SessionService.update_session_token(user, refresh_token, str(new_refresh))
            
            return Response({
                'access': str(new_refresh.access_token),
                'refresh': str(new_refresh)
            })
            
        except TokenError as e:
            return Response(
                {'code': 'INVALID_TOKEN', 'detail': 'Invalid or expired refresh token.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except User.DoesNotExist:
            return Response(
                {'code': 'USER_NOT_FOUND', 'detail': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return Response(
                {'code': 'REFRESH_FAILED', 'detail': 'Token refresh failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='password-reset-request')
    def password_reset_request(self, request):
        """
        Request password reset email.
        POST /api/v1/auth/password-reset-request/
        """
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid email.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            email = serializer.validated_data['email']
            PasswordResetService.request_reset(email)
            
            # Always return success to prevent email enumeration
            return Response({
                'detail': 'If an account exists with this email, a password reset link has been sent.'
            })
            
        except Exception as e:
            logger.error(f"Password reset request error: {str(e)}")
            # Still return success to prevent email enumeration
            return Response({
                'detail': 'If an account exists with this email, a password reset link has been sent.'
            })
    
    @action(detail=False, methods=['post'], url_path='password-reset-confirm')
    def password_reset_confirm(self, request):
        """
        Confirm password reset with token.
        POST /api/v1/auth/password-reset-confirm/
        """
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid reset data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = PasswordResetService.confirm_reset(
                uid=serializer.validated_data['uid'],
                token=serializer.validated_data['token'],
                new_password=serializer.validated_data['new_password']
            )
            
            if result:
                return Response({'detail': 'Password has been reset successfully.'})
            else:
                return Response(
                    {
                        'code': 'RESET_FAILED',
                        'detail': 'Invalid or expired reset token.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Password reset confirm error: {str(e)}")
            return Response(
                {
                    'code': 'RESET_FAILED',
                    'detail': 'Password reset failed. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='password-change')
    def change_password(self, request):
        """
        Change password for authenticated user.
        POST /api/v1/auth/password-change/
        """
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid password data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Revoke all sessions except current
            SessionService.revoke_all_user_sessions(user, keep_current=True)
            
            logger.info(f"Password changed for user: {user.email}")
            
            return Response({'detail': 'Password changed successfully.'})
            
        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            return Response(
                {'code': 'CHANGE_FAILED', 'detail': 'Password change failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='mfa/setup')
    def mfa_setup(self, request):
        """
        Setup MFA for authenticated user.
        POST /api/v1/auth/mfa/setup/
        """
        try:
            result = MFAService.setup_mfa(request.user)
            return Response(result)
        except Exception as e:
            logger.error(f"MFA setup error: {str(e)}")
            return Response(
                {'code': 'MFA_SETUP_FAILED', 'detail': 'MFA setup failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='mfa/verify')
    def mfa_verify(self, request):
        """
        Verify MFA code during login.
        POST /api/v1/auth/mfa/verify/
        """
        serializer = MFAVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid MFA code.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            code = serializer.validated_data['code']
            mfa_token = serializer.validated_data.get('token')
            
            result = MFAService.verify_mfa_login(
                mfa_token=mfa_token,
                code=code,
                request=request
            )
            
            if result:
                return Response({
                    'user': result['user'],
                    'tokens': result['tokens']
                })
            else:
                return Response(
                    {'code': 'MFA_INVALID', 'detail': 'Invalid MFA code.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
                
        except Exception as e:
            logger.error(f"MFA verify error: {str(e)}")
            return Response(
                {'code': 'MFA_VERIFY_FAILED', 'detail': 'MFA verification failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='mfa/disable')
    def mfa_disable(self, request):
        """
        Disable MFA for authenticated user.
        POST /api/v1/auth/mfa/disable/
        """
        try:
            MFAService.disable_mfa(request.user)
            return Response({'detail': 'MFA has been disabled.'})
        except Exception as e:
            logger.error(f"MFA disable error: {str(e)}")
            return Response(
                {'code': 'MFA_DISABLE_FAILED', 'detail': 'Failed to disable MFA.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserManagementViewSet(viewsets.ModelViewSet):
    """
    User Management ViewSet for admin operations.
    Provides list, retrieve, update, delete, and impersonate endpoints.
    """
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return UserListSerializer
        elif self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserDetailSerializer
    
    def get_permissions(self):
        """Instantiate and return the list of permissions."""
        if self.action in ['profile', 'update_profile']:
            return [IsAuthenticated()]
        if self.action == 'impersonate':
            return [IsAuthenticated(), CanImpersonate()]
        return [IsAuthenticated(), IsAdminUser()]
    
    @action(detail=False, methods=['get'], url_path='me')
    def profile(self, request):
        """
        Get current user profile.
        GET /api/v1/users/me/
        """
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'], url_path='me/update')
    def update_profile(self, request):
        """
        Update current user profile.
        PATCH /api/v1/users/me/update/
        """
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid profile data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer.save()
        
        # Return updated profile
        profile_serializer = ProfileSerializer(request.user)
        return Response(profile_serializer.data)
    
    @action(detail=False, methods=['post'], url_path='me/avatar')
    def upload_avatar(self, request):
        """
        Upload user avatar.
        POST /api/v1/users/me/avatar/
        """
        avatar = request.FILES.get('avatar')
        if not avatar:
            return Response(
                {'code': 'MISSING_FILE', 'detail': 'Avatar file is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Save avatar (in production, this would upload to cloud storage)
            user = request.user
            user.avatar_url = f"/media/avatars/{user.id}/{avatar.name}"
            user.save(update_fields=['avatar_url'])
            
            return Response({'avatar_url': user.avatar_url})
            
        except Exception as e:
            logger.error(f"Avatar upload error: {str(e)}")
            return Response(
                {'code': 'UPLOAD_FAILED', 'detail': 'Avatar upload failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='impersonate')
    def impersonate(self, request, pk=None):
        """
        Impersonate another user (admin only).
        POST /api/v1/users/{id}/impersonate/
        """
        serializer = ImpersonateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid impersonation data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            target_user = self.get_object()
            
            result = ImpersonationService.impersonate(
                admin_user=request.user,
                target_user=target_user,
                reason=serializer.validated_data.get('reason', '')
            )
            
            return Response({
                'tokens': result['tokens'],
                'impersonated_user': UserDetailSerializer(target_user).data,
                'original_user': {
                    'id': str(request.user.id),
                    'email': request.user.email
                }
            })
            
        except Exception as e:
            logger.error(f"Impersonation error: {str(e)}")
            return Response(
                {'code': 'IMPERSONATION_FAILED', 'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'], url_path='impersonate/stop')
    def stop_impersonation(self, request):
        """
        Stop impersonation and return to admin user.
        POST /api/v1/users/impersonate/stop/
        """
        try:
            result = ImpersonationService.stop_impersonation(request.user)
            
            return Response({
                'tokens': result['tokens'],
                'user': UserDetailSerializer(result['user']).data
            })
            
        except Exception as e:
            logger.error(f"Stop impersonation error: {str(e)}")
            return Response(
                {'code': 'STOP_IMPERSONATION_FAILED', 'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        """
        Activate a user account.
        POST /api/v1/users/{id}/activate/
        """
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        
        logger.info(f"User activated: {user.email} by {request.user.email}")
        
        return Response(UserDetailSerializer(user).data)
    
    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        """
        Deactivate a user account.
        POST /api/v1/users/{id}/deactivate/
        """
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        
        # Revoke all sessions
        SessionService.revoke_all_user_sessions(user, revoked_by=request.user)
        
        logger.info(f"User deactivated: {user.email} by {request.user.email}")
        
        return Response(UserDetailSerializer(user).data)
    
    @action(detail=True, methods=['get'], url_path='sessions')
    def list_sessions(self, request, pk=None):
        """
        List user sessions.
        GET /api/v1/users/{id}/sessions/
        """
        user = self.get_object()
        sessions = UserSession.objects.filter(user=user, is_revoked=False)
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='sessions/revoke-all')
    def revoke_all_sessions(self, request, pk=None):
        """
        Revoke all sessions for a user.
        POST /api/v1/users/{id}/sessions/revoke-all/
        """
        user = self.get_object()
        SessionService.revoke_all_user_sessions(user, revoked_by=request.user)
        
        logger.info(f"All sessions revoked for user: {user.email} by {request.user.email}")
        
        return Response({'detail': 'All sessions revoked.'})


class RoleViewSet(viewsets.ModelViewSet):
    """
    Role management ViewSet.
    """
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        """Filter out system roles for non-superusers."""
        queryset = Role.objects.all()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(is_system_role=False)
        return queryset


class SessionViewSet(viewsets.ViewSet):
    """
    Session management ViewSet for current user.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        List current user sessions.
        GET /api/v1/users/sessions/
        """
        sessions = UserSession.objects.filter(user=request.user, is_revoked=False)
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, request, pk=None):
        """
        Revoke a specific session.
        POST /api/v1/users/sessions/{id}/revoke/
        """
        try:
            session = UserSession.objects.get(id=pk, user=request.user)
            session.revoke(revoked_by=request.user)
            return Response({'detail': 'Session revoked.'})
        except UserSession.DoesNotExist:
            return Response(
                {'code': 'NOT_FOUND', 'detail': 'Session not found.'},
                status=status.HTTP_404_NOT_FOUND
            )


class RBACConflictViewSet(viewsets.ModelViewSet):
    """
    RBAC Conflict management ViewSet.
    Provides endpoints for listing and resolving RBAC conflicts.
    """
    queryset = RBACConflict.objects.all()
    serializer_class = RBACConflictSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        """Filter conflicts based on query parameters."""
        queryset = RBACConflict.objects.all()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by severity
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)
        
        # Filter by conflict type
        conflict_type = self.request.query_params.get('conflict_type')
        if conflict_type:
            queryset = queryset.filter(conflict_type=conflict_type)
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by course
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        return queryset.select_related('user', 'detected_by', 'resolved_by')
    
    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Get RBAC conflict summary statistics.
        GET /api/v1/users/rbac-conflicts/summary/
        """
        from django.db.models import Count, Q
        
        summary = {
            'total': RBACConflict.objects.count(),
            'by_status': dict(RBACConflict.objects.values_list('status').annotate(count=Count('id'))),
            'by_severity': dict(RBACConflict.objects.values_list('severity').annotate(count=Count('id'))),
            'by_type': dict(RBACConflict.objects.values_list('conflict_type').annotate(count=Count('id'))),
            'open_critical': RBACConflict.objects.filter(
                status=RBACConflict.STATUS_DETECTED,
                severity=RBACConflict.SEVERITY_CRITICAL
            ).count(),
            'open_high': RBACConflict.objects.filter(
                status=RBACConflict.STATUS_DETECTED,
                severity=RBACConflict.SEVERITY_HIGH
            ).count(),
        }
        
        return Response(summary)
    
    @action(detail=False, methods=['post'], url_path='scan')
    def scan(self, request):
        """
        Trigger RBAC conflict scan.
        POST /api/v1/users/rbac-conflicts/scan/
        """
        try:
            results = RBACEdgeCaseService.scan_all_conflicts(detected_by=request.user)
            return Response({
                'detail': f'Scan completed. {len(results)} conflicts detected.',
                'conflicts_detected': len(results),
                'conflicts': RBACConflictSerializer(results, many=True).data
            })
        except Exception as e:
            logger.error(f"RBAC scan error: {str(e)}")
            return Response(
                {'code': 'SCAN_FAILED', 'detail': 'Failed to scan for conflicts.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        """
        Resolve an RBAC conflict.
        POST /api/v1/users/rbac-conflicts/{id}/resolve/
        """
        conflict = self.get_object()
        
        serializer = RBACConflictResolveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'code': 'VALIDATION_ERROR',
                    'detail': 'Invalid resolution data.',
                    'field_errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            conflict.resolve(
                resolved_by=request.user,
                resolution_action=serializer.validated_data.get('resolution_action', ''),
                resolution_notes=serializer.validated_data.get('resolution_notes', '')
            )
            
            logger.info(f"RBAC conflict {pk} resolved by {request.user.email}")
            
            return Response(RBACConflictSerializer(conflict).data)
            
        except Exception as e:
            logger.error(f"Conflict resolution error: {str(e)}")
            return Response(
                {'code': 'RESOLUTION_FAILED', 'detail': 'Failed to resolve conflict.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='escalate')
    def escalate(self, request, pk=None):
        """
        Escalate an RBAC conflict.
        POST /api/v1/users/rbac-conflicts/{id}/escalate/
        """
        conflict = self.get_object()
        notes = request.data.get('notes', '')
        
        try:
            conflict.escalate(notes=notes)
            
            logger.info(f"RBAC conflict {pk} escalated by {request.user.email}")
            
            return Response(RBACConflictSerializer(conflict).data)
            
        except Exception as e:
            logger.error(f"Conflict escalation error: {str(e)}")
            return Response(
                {'code': 'ESCALATION_FAILED', 'detail': 'Failed to escalate conflict.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='ignore')
    def ignore(self, request, pk=None):
        """
        Ignore an RBAC conflict (mark as legitimate).
        POST /api/v1/users/rbac-conflicts/{id}/ignore/
        """
        conflict = self.get_object()
        notes = request.data.get('notes', '')
        
        try:
            conflict.ignore(notes=notes)
            
            logger.info(f"RBAC conflict {pk} ignored by {request.user.email}")
            
            return Response(RBACConflictSerializer(conflict).data)
            
        except Exception as e:
            logger.error(f"Conflict ignore error: {str(e)}")
            return Response(
                {'code': 'IGNORE_FAILED', 'detail': 'Failed to ignore conflict.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Custom JWT views using our serializers
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom token obtain pair view with additional user data.
    """
    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view.
    """
    pass
