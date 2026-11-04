"""
Django Admin configuration for Certificates app
"""

from django.contrib import admin
from django.utils.html import format_html

from apps.certificates.models import Certificate, CertificateTemplate, CertificateIssueEvent


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    """Admin configuration for CertificateTemplate model."""
    
    list_display = [
        'name',
        'is_active',
        'created_at',
        'updated_at',
        'certificate_count'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'available_variables_display']
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Template Content', {
            'fields': ('html_template', 'css_styles'),
            'classes': ('collapse',)
        }),
        ('Variables', {
            'fields': ('available_variables_display',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def certificate_count(self, obj):
        """Display number of certificates using this template."""
        count = obj.certificates.count()
        return format_html('<span style="font-weight: bold;">{}</span> certificates', count)
    certificate_count.short_description = 'Usage Count'
    
    def available_variables_display(self, obj):
        """Display available variables in a readable format."""
        if not obj.available_variables:
            return "No variables defined"
        
        html = "<ul>"
        for key, value in obj.available_variables.items():
            desc = value.get('description', '') if isinstance(value, dict) else str(value)
            html += f"<li><code>{{{{ {key} }}}}</code> - {desc}</li>"
        html += "</ul>"
        return format_html(html)
    available_variables_display.short_description = 'Available Template Variables'


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    """Admin configuration for Certificate model."""
    
    list_display = [
        'certificate_number',
        'user_email',
        'course_title',
        'status_badge',
        'generation_status',
        'issued_at',
        'is_revoked'
    ]
    list_filter = [
        'generation_status',
        'is_revoked',
        'issued_at',
        'created_at'
    ]
    search_fields = [
        'certificate_number',
        'user__email',
        'user__first_name',
        'user__last_name',
        'course__title'
    ]
    readonly_fields = [
        'certificate_number',
        'verification_hash',
        'issued_at',
        'generated_at',
        'revoked_at',
        'created_at',
        'updated_at'
    ]
    raw_id_fields = ['user', 'course', 'template', 'revoked_by']
    date_hierarchy = 'issued_at'
    
    fieldsets = (
        ('Certificate Information', {
            'fields': (
                'certificate_number',
                'verification_hash',
                'user',
                'course',
                'template'
            )
        }),
        ('Status', {
            'fields': (
                'generation_status',
                'generation_attempts',
                'generation_error'
            )
        }),
        ('Validity', {
            'fields': (
                'issued_at',
                'expires_at',
                'is_revoked',
                'revoked_at',
                'revoked_reason',
                'revoked_by'
            )
        }),
        ('Files', {
            'fields': ('pdf_file', 'pdf_url'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['regenerate_pdfs', 'revoke_certificates', 'mark_as_active']
    
    def user_email(self, obj):
        """Display user email."""
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def course_title(self, obj):
        """Display course title."""
        return obj.course.title
    course_title.short_description = 'Course'
    course_title.admin_order_field = 'course__title'
    
    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            'valid': 'green',
            'expired': 'orange',
            'revoked': 'red',
            'pending': 'blue',
            'generating': 'purple',
            'failed': 'darkred'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; text-transform: uppercase;">{}</span>',
            color,
            obj.status
        )
    status_badge.short_description = 'Status'
    
    def regenerate_pdfs(self, request, queryset):
        """Admin action to regenerate PDFs for selected certificates."""
        from apps.certificates.tasks import regenerate_certificate_task
        
        count = 0
        for certificate in queryset:
            regenerate_certificate_task.delay(
                certificate_id=str(certificate.id),
                triggered_by_user_id=str(request.user.id)
            )
            count += 1
        
        self.message_user(
            request,
            f"Queued PDF regeneration for {count} certificate(s)."
        )
    regenerate_pdfs.short_description = "Regenerate PDFs for selected certificates"
    
    def revoke_certificates(self, request, queryset):
        """Admin action to revoke selected certificates."""
        count = 0
        for certificate in queryset:
            if not certificate.is_revoked:
                certificate.revoke(
                    reason="Revoked via admin action",
                    revoked_by=request.user
                )
                count += 1
        
        self.message_user(
            request,
            f"Revoked {count} certificate(s)."
        )
    revoke_certificates.short_description = "Revoke selected certificates"
    
    def mark_as_active(self, request, queryset):
        """Admin action to mark certificates as active (unrevoke)."""
        count = queryset.filter(is_revoked=True).update(
            is_revoked=False,
            revoked_at=None,
            revoked_reason='',
            revoked_by=None
        )
        self.message_user(
            request,
            f"Marked {count} certificate(s) as active."
        )
    mark_as_active.short_description = "Mark selected certificates as active"


@admin.register(CertificateIssueEvent)
class CertificateIssueEventAdmin(admin.ModelAdmin):
    """Admin configuration for CertificateIssueEvent model."""
    
    list_display = [
        'event_type',
        'certificate_number',
        'performed_by_email',
        'ip_address',
        'created_at'
    ]
    list_filter = ['event_type', 'created_at']
    search_fields = [
        'certificate__certificate_number',
        'performed_by__email',
        'ip_address'
    ]
    readonly_fields = [
        'certificate',
        'event_type',
        'performed_by',
        'ip_address',
        'user_agent',
        'metadata',
        'created_at'
    ]
    date_hierarchy = 'created_at'
    
    def certificate_number(self, obj):
        """Display certificate number."""
        return obj.certificate.certificate_number
    certificate_number.short_description = 'Certificate'
    
    def performed_by_email(self, obj):
        """Display performer email."""
        return obj.performed_by.email if obj.performed_by else "System"
    performed_by_email.short_description = 'Performed By'
    
    def has_add_permission(self, request):
        """Disable manual creation of events."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Disable editing of events."""
        return False
