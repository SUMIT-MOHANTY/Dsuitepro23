"""
Certificates Serializers for Enterprise LMS
Provides serializers for CertificateTemplate and Certificate models.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from apps.certificates.models import CertificateTemplate, Certificate, CertificateIssueEvent
from apps.users.serializers import UserListSerializer
from apps.courses.serializers import CourseListSerializer

User = get_user_model()


class CertificateTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for CertificateTemplate model.
    Used for CRUD operations on certificate templates.
    """
    
    class Meta:
        model = CertificateTemplate
        fields = [
            'id', 'name', 'description', 'html_template', 'css_styles',
            'available_variables', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CertificateTemplateListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing certificate templates.
    Excludes large fields like html_template.
    """
    
    class Meta:
        model = CertificateTemplate
        fields = [
            'id', 'name', 'description', 'is_active',
            'created_at', 'updated_at'
        ]


class CertificateSerializer(serializers.ModelSerializer):
    """
    Serializer for Certificate model.
    Includes nested user and course information.
    """
    user = UserListSerializer(read_only=True)
    course = CourseListSerializer(read_only=True)
    template = CertificateTemplateListSerializer(read_only=True)
    status = serializers.CharField(source='status', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    download_url = serializers.SerializerMethodField()
    verification_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_number', 'user', 'course', 'template',
            'issued_at', 'expires_at', 'is_revoked', 'revoked_at',
            'revoked_reason', 'pdf_url', 'pdf_file', 'verification_hash',
            'generation_status', 'generated_at', 'status', 'is_valid',
            'is_expired', 'download_url', 'verification_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'certificate_number', 'verification_hash',
            'issued_at', 'created_at', 'updated_at'
        ]

    def get_download_url(self, obj):
        """Get the download URL for the certificate PDF."""
        if obj.pdf_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.pdf_file.url)
            return obj.pdf_file.url
        return obj.pdf_url

    def get_verification_url(self, obj):
        """Get the public verification URL for this certificate."""
        request = self.context.get('request')
        url = obj.get_verification_url()
        if request:
            return request.build_absolute_uri(url)
        return url


class CertificateListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing certificates.
    Used for user's certificate list view.
    """
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_slug = serializers.CharField(source='course.slug', read_only=True)
    course_thumbnail = serializers.URLField(source='course.thumbnail_url', read_only=True)
    student_name = serializers.CharField(source='user.get_full_name', read_only=True)
    status = serializers.CharField(source='status', read_only=True)
    download_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_number', 'course_title', 'course_slug',
            'course_thumbnail', 'student_name', 'issued_at', 'expires_at',
            'is_revoked', 'status', 'generation_status', 'download_url'
        ]

    def get_download_url(self, obj):
        """Get the download URL for the certificate PDF."""
        if obj.pdf_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.pdf_file.url)
            return obj.pdf_file.url
        return obj.pdf_url


class CertificateCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating certificates.
    Only accepts user, course, and template fields.
    """
    user_id = serializers.UUIDField(write_only=True)
    course_id = serializers.UUIDField(write_only=True)
    template_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = Certificate
        fields = [
            'user_id', 'course_id', 'template_id', 'expires_at'
        ]

    def validate(self, data):
        """Validate certificate creation data."""
        # Check if user already has a certificate for this course
        user_id = data.get('user_id')
        course_id = data.get('course_id')
        
        existing = Certificate.objects.filter(
            user_id=user_id,
            course_id=course_id,
            is_revoked=False
        ).exists()
        
        if existing:
            raise serializers.ValidationError(
                "User already has an active certificate for this course."
            )
        
        return data


class CertificateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating certificates.
    Only allows updating certain fields.
    """
    
    class Meta:
        model = Certificate
        fields = ['expires_at', 'template']


class CertificateRegenerateSerializer(serializers.Serializer):
    """
    Serializer for certificate regeneration requests.
    """
    template_id = serializers.UUIDField(required=False, allow_null=True)
    notify_user = serializers.BooleanField(default=True)


class CertificateRevokeSerializer(serializers.Serializer):
    """
    Serializer for certificate revocation requests.
    """
    reason = serializers.CharField(required=True, min_length=10)


class CertificateVerifySerializer(serializers.Serializer):
    """
    Serializer for certificate verification requests.
    """
    certificate_number = serializers.CharField(required=True, max_length=100)
    verification_hash = serializers.CharField(required=True, max_length=64)


class CertificateVerifyResponseSerializer(serializers.Serializer):
    """
    Serializer for certificate verification responses.
    """
    valid = serializers.BooleanField()
    certificate_number = serializers.CharField(required=False)
    student_name = serializers.CharField(required=False)
    course_name = serializers.CharField(required=False)
    issued_at = serializers.DateTimeField(required=False)
    expires_at = serializers.DateTimeField(required=False)
    is_revoked = serializers.BooleanField(required=False)
    message = serializers.CharField(required=False)


class CertificateIssueEventSerializer(serializers.ModelSerializer):
    """
    Serializer for CertificateIssueEvent model.
    Tracks certificate issuance events.
    """
    performed_by_name = serializers.CharField(
        source='performed_by.get_full_name',
        read_only=True
    )
    
    class Meta:
        model = CertificateIssueEvent
        fields = [
            'id', 'event_type', 'performed_by_name', 'ip_address',
            'user_agent', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CertificateStatsSerializer(serializers.Serializer):
    """
    Serializer for certificate statistics.
    """
    total_certificates = serializers.IntegerField()
    active_certificates = serializers.IntegerField()
    revoked_certificates = serializers.IntegerField()
    expired_certificates = serializers.IntegerField()
    pending_generation = serializers.IntegerField()
    failed_generation = serializers.IntegerField()
    certificates_this_month = serializers.IntegerField()
    certificates_this_year = serializers.IntegerField()
