"""
Django Admin configuration for SCORM app
"""

from django.contrib import admin
from .models import (
    SCORMRegistration,
    SCORMSession,
    SCORMRuntimeData,
    SCORMInteraction,
    SCORMObjective,
    SCORMCloudSyncLog,
    xAPIStatement,
)


@admin.register(SCORMRegistration)
class SCORMRegistrationAdmin(admin.ModelAdmin):
    """Admin configuration for SCORMRegistration model."""
    list_display = [
        'registration_id',
        'status',
        'user',
        'content_item',
        'score',
        'total_time',
        'created_at',
    ]
    list_filter = [
        'status',
        'completion_status',
        'created_at',
        'updated_at',
    ]
    search_fields = [
        'registration_id',
        'scorm_cloud_registration_id',
        'user__email',
        'user__username',
        'content_item__title',
    ]
    readonly_fields = [
        'id',
        'registration_id',
        'created_at',
        'updated_at',
        'last_accessed_at',
    ]
    raw_id_fields = ['user', 'content_item']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    fieldsets = (
        ('Registration Info', {
            'fields': (
                'id',
                'registration_id',
                'user',
                'content_item',
            )
        }),
        ('SCORM Cloud', {
            'fields': (
                'scorm_cloud_registration_id',
                'scorm_cloud_app_id',
            ),
            'classes': ('collapse',),
        }),
        ('Status & Progress', {
            'fields': (
                'status',
                'completion_status',
                'success_status',
                'score',
                'score_scaled',
            )
        }),
        ('Time Tracking', {
            'fields': (
                'total_time',
                'session_time',
                'last_accessed_at',
            )
        }),
        ('Suspend Data', {
            'fields': ('suspend_data',),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(SCORMSession)
class SCORMSessionAdmin(admin.ModelAdmin):
    """Admin configuration for SCORMSession model."""
    list_display = [
        'session_id',
        'registration',
        'is_active',
        'ip_address',
        'started_at',
        'last_activity_at',
    ]
    list_filter = [
        'is_active',
        'started_at',
        'last_activity_at',
    ]
    search_fields = [
        'session_id',
        'registration__registration_id',
        'user_agent',
    ]
    readonly_fields = [
        'id',
        'session_id',
        'started_at',
        'last_activity_at',
    ]
    raw_id_fields = ['registration']
    date_hierarchy = 'started_at'
    ordering = ['-started_at']

    fieldsets = (
        ('Session Info', {
            'fields': (
                'id',
                'session_id',
                'registration',
            )
        }),
        ('Status', {
            'fields': (
                'is_active',
                'started_at',
                'ended_at',
                'last_activity_at',
            )
        }),
        ('Client Info', {
            'fields': (
                'ip_address',
                'user_agent',
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(SCORMRuntimeData)
class SCORMRuntimeDataAdmin(admin.ModelAdmin):
    """Admin configuration for SCORMRuntimeData model."""
    list_display = [
        'registration',
        'lesson_location',
        'lesson_status',
        'score_raw',
        'updated_at',
    ]
    list_filter = [
        'lesson_status',
        'entry',
        'mode',
        'updated_at',
    ]
    search_fields = [
        'registration__registration_id',
        'lesson_location',
        'lesson_id',
    ]
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
    ]
    raw_id_fields = ['registration']
    date_hierarchy = 'updated_at'
    ordering = ['-updated_at']

    fieldsets = (
        ('Registration', {
            'fields': ('registration',)
        }),
        ('Core Data', {
            'fields': (
                'lesson_location',
                'lesson_status',
                'lesson_id',
            )
        }),
        ('Score', {
            'fields': (
                'score_raw',
                'score_max',
                'score_min',
                'score_scaled',
            )
        }),
        ('Session', {
            'fields': (
                'entry',
                'mode',
                'exit',
                'session_time',
            )
        }),
        ('Suspend Data', {
            'fields': ('suspend_data',),
            'classes': ('collapse',),
        }),
        ('Credit & Classification', {
            'fields': (
                'credit',
                'lesson_mode',
            )
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(SCORMInteraction)
class SCORMInteractionAdmin(admin.ModelAdmin):
    """Admin configuration for SCORMInteraction model."""
    list_display = [
        'registration',
        'interaction_id',
        'type',
        'result',
        'timestamp',
    ]
    list_filter = [
        'type',
        'result',
        'timestamp',
    ]
    search_fields = [
        'registration__registration_id',
        'interaction_id',
        'description',
    ]
    readonly_fields = [
        'id',
        'timestamp',
    ]
    raw_id_fields = ['registration']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    fieldsets = (
        ('Interaction Info', {
            'fields': (
                'registration',
                'interaction_id',
                'type',
            )
        }),
        ('Result', {
            'fields': (
                'result',
                'weighting',
                'latency',
            )
        }),
        ('Description', {
            'fields': ('description',),
        }),
        ('Responses', {
            'fields': (
                'learner_response',
                'correct_responses',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamp', {
            'fields': ('timestamp',),
        }),
    )


@admin.register(SCORMObjective)
class SCORMObjectiveAdmin(admin.ModelAdmin):
    """Admin configuration for SCORMObjective model."""
    list_display = [
        'registration',
        'objective_id',
        'status',
        'score_raw',
        'success_status',
    ]
    list_filter = [
        'status',
        'success_status',
        'created_at',
    ]
    search_fields = [
        'registration__registration_id',
        'objective_id',
        'description',
    ]
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
    ]
    raw_id_fields = ['registration']
    ordering = ['-created_at']

    fieldsets = (
        ('Objective Info', {
            'fields': (
                'registration',
                'objective_id',
                'description',
            )
        }),
        ('Status & Score', {
            'fields': (
                'status',
                'success_status',
                'score_raw',
                'score_max',
                'score_min',
                'score_scaled',
            )
        }),
        ('Progress', {
            'fields': ('progress_measure',),
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(SCORMCloudSyncLog)
class SCORMCloudSyncLogAdmin(admin.ModelAdmin):
    """Admin configuration for SCORMCloudSyncLog model."""
    list_display = [
        'registration',
        'sync_type',
        'status',
        'attempt_count',
        'created_at',
        'completed_at',
    ]
    list_filter = [
        'sync_type',
        'status',
        'created_at',
    ]
    search_fields = [
        'registration__registration_id',
        'error_message',
        'scorm_cloud_response',
    ]
    readonly_fields = [
        'id',
        'created_at',
        'completed_at',
    ]
    raw_id_fields = ['registration']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    fieldsets = (
        ('Sync Info', {
            'fields': (
                'registration',
                'sync_type',
                'status',
            )
        }),
        ('Timing', {
            'fields': (
                'created_at',
                'completed_at',
                'attempt_count',
            )
        }),
        ('Error Details', {
            'fields': (
                'error_message',
                'scorm_cloud_response',
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(xAPIStatement)
class xAPIStatementAdmin(admin.ModelAdmin):
    """Admin configuration for xAPIStatement model."""
    list_display = [
        'statement_id',
        'registration',
        'verb',
        'activity_type',
        'timestamp',
        'is_forwarded',
    ]
    list_filter = [
        'verb',
        'activity_type',
        'is_forwarded',
        'timestamp',
    ]
    search_fields = [
        'statement_id',
        'registration__registration_id',
        'actor',
        'object_id',
    ]
    readonly_fields = [
        'id',
        'statement_id',
        'timestamp',
        'stored',
    ]
    raw_id_fields = ['registration']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    fieldsets = (
        ('Statement Info', {
            'fields': (
                'statement_id',
                'registration',
            )
        }),
        ('xAPI Components', {
            'fields': (
                'actor',
                'verb',
                'object_id',
                'object_definition',
                'result',
                'context',
            )
        }),
        ('Classification', {
            'fields': (
                'activity_type',
                'activity_name',
            )
        }),
        ('Forwarding', {
            'fields': (
                'is_forwarded',
                'forwarded_at',
                'lrs_endpoint',
                'forward_error',
            ),
        }),
        ('Timestamps', {
            'fields': (
                'timestamp',
                'stored',
            ),
            'classes': ('collapse',),
        }),
    )
