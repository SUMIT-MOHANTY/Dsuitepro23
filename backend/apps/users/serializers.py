"""
Users Serializers for Enterprise LMS
Provides serializers for User model, authentication, and JWT token customization.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Role, UserRole, UserSession

User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model."""
    
    class Meta:
        model = Role
        fields = ['id', 'role_name', 'display_name', 'description', 'permissions', 'is_system_role']
        read_only_fields = ['id']


class UserRoleSerializer(serializers.ModelSerializer):
    """Serializer for UserRole through model."""
    role = RoleSerializer(read_only=True)
    role_id = serializers.UUIDField(write_only=True)
    assigned_by = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = UserRole
        fields = ['id', 'user', 'role', 'role_id', 'assigned_at', 'assigned_by', 'expires_at', 'is_primary']
        read_only_fields = ['id', 'assigned_at']


class UserSessionSerializer(serializers.ModelSerializer):
    """Serializer for UserSession model."""
    
    class Meta:
        model = UserSession
        fields = [
            'id', 'session_key', 'device_info', 'ip_address', 'location',
            'is_revoked', 'revoked_at', 'expires_at', 'last_activity_at', 'created_at'
        ]
        read_only_fields = ['id', 'session_key', 'revoked_at', 'last_activity_at', 'created_at']


class UserListSerializer(serializers.ModelSerializer):
    """Serializer for listing users (minimal data)."""
    primary_role = serializers.SerializerMethodField()
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'avatar_url', 'is_active', 'is_staff', 'primary_role', 'created_at'
        ]
    
    def get_primary_role(self, obj):
        """Get user's primary role name."""
        role = obj.get_primary_role()
        return role


class UserDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed user data."""
    assigned_roles = RoleSerializer(many=True, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'avatar_url', 'bio', 'phone', 'timezone', 'locale', 'date_of_birth',
            'is_active', 'is_staff', 'email_verified', 'mfa_enabled',
            'assigned_roles', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'email_verified', 'created_at', 'updated_at']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users."""
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)
    role = serializers.CharField(required=False, default='learner')
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name', 'password',
            'password_confirm', 'role', 'avatar_url', 'bio', 'phone',
            'timezone', 'locale', 'date_of_birth'
        ]
    
    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError(
                {'password_confirm': _('Passwords do not match.')}
            )
        return attrs
    
    def create(self, validated_data):
        """Create user with assigned role."""
        role_name = validated_data.pop('role', 'learner')
        password = validated_data.pop('password')
        
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        
        # Assign role
        try:
            role = Role.objects.get(role_name=role_name)
            UserRole.objects.create(user=user, role=role, is_primary=True)
        except Role.DoesNotExist:
            # Default to learner role
            role, _ = Role.objects.get_or_create(
                role_name='learner',
                defaults={'display_name': 'Learner'}
            )
            UserRole.objects.create(user=user, role=role, is_primary=True)
        
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user data."""
    
    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'avatar_url',
            'bio', 'phone', 'timezone', 'locale', 'date_of_birth'
        ]


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        """Validate new password confirmation."""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': _('New passwords do not match.')}
            )
        return attrs
    
    def validate_old_password(self, value):
        """Validate old password."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_('Old password is incorrect.'))
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""
    token = serializers.CharField(required=True)
    uid = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': _('Passwords do not match.')}
            )
        return attrs


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer with additional claims.
    Includes user_id, email, and role in the token.
    """
    
    def validate(self, attrs):
        """Validate and add custom claims to token."""
        data = super().validate(attrs)
        
        # Add custom claims to the token
        refresh = self.get_token(self.user)
        
        # Add user info to response
        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'username': self.user.username,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'full_name': self.user.get_full_name(),
            'role': self.user.get_primary_role(),
            'is_staff': self.user.is_staff,
            'mfa_enabled': self.user.mfa_enabled,
        }
        
        return data
    
    @classmethod
    def get_token(cls, user):
        """Get token with custom claims."""
        token = super().get_token(user)
        
        # Add custom claims
        token['user_id'] = str(user.id)
        token['email'] = user.email
        token['role'] = user.get_primary_role() or 'learner'
        token['is_staff'] = user.is_staff
        
        return token


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Serializer for token refresh response."""
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)


class LogoutSerializer(serializers.Serializer):
    """Serializer for logout - blacklists refresh token."""
    refresh = serializers.CharField(required=True)
    all_sessions = serializers.BooleanField(default=False)


class MFASetupSerializer(serializers.Serializer):
    """Serializer for MFA setup."""
    secret = serializers.CharField(read_only=True)
    qr_code_url = serializers.CharField(read_only=True)
    backup_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class MFAVerifySerializer(serializers.Serializer):
    """Serializer for MFA verification."""
    code = serializers.CharField(required=True, min_length=6, max_length=6)
    token = serializers.CharField(required=False)  # For completing login with MFA


class ImpersonateSerializer(serializers.Serializer):
    """Serializer for user impersonation."""
    user_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class ProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""
    assigned_roles = RoleSerializer(many=True, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'avatar_url', 'bio', 'phone', 'timezone', 'locale', 'date_of_birth',
            'is_active', 'email_verified', 'mfa_enabled', 'assigned_roles',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'email', 'email_verified', 'created_at', 'updated_at']
