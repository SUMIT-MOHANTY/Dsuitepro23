# Generated migration for SCORM 1.2 Runtime - Suspend/Resume Data Handling & Completion Tracking

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('courses', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # SCORM Registration Model
        migrations.CreateModel(
            name='SCORMRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('registration_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('scorm_cloud_registration_id', models.CharField(blank=True, max_length=255)),
                ('scorm_cloud_course_id', models.CharField(blank=True, max_length=255)),
                ('launch_url', models.URLField(blank=True)),
                ('status', models.CharField(choices=[('not_attempted', 'Not Attempted'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('passed', 'Passed'), ('failed', 'Failed'), ('suspended', 'Suspended')], db_index=True, default='not_attempted', max_length=20)),
                ('completion_status', models.CharField(choices=[('not attempted', 'Not Attempted'), ('incomplete', 'Incomplete'), ('completed', 'Completed'), ('passed', 'Passed'), ('failed', 'Failed')], db_index=True, default='not attempted', max_length=20)),
                ('exit_status', models.CharField(blank=True, choices=[('timeout', 'Timeout'), ('suspend', 'Suspend'), ('logout', 'Logout'), ('', 'Normal')], default='', max_length=20)),
                ('score_raw', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('score_max', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('score_min', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('total_time', models.CharField(blank=True, max_length=20)),
                ('session_time', models.CharField(blank=True, max_length=20)),
                ('lesson_location', models.CharField(blank=True, max_length=255)),
                ('suspend_data', models.TextField(blank=True)),
                ('credit', models.CharField(default='credit', max_length=20)),
                ('lesson_mode', models.CharField(default='normal', max_length=20)),
                ('entry', models.CharField(default='ab-initio', max_length=20)),
                ('launch_count', models.PositiveIntegerField(default=0)),
                ('last_launched_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('sync_status', models.CharField(choices=[('pending', 'Pending'), ('synced', 'Synced'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('content_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scorm_registrations', to='courses.contentitem')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scorm_registrations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'SCORM Registration',
                'verbose_name_plural': 'SCORM Registrations',
                'ordering': ['-created_at'],
            },
        ),
        # SCORM Session Model
        migrations.CreateModel(
            name='SCORMSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('completed', 'Completed'), ('suspended', 'Suspended'), ('timeout', 'Timeout'), ('error', 'Error')], default='active', max_length=20)),
                ('user_agent', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('launch_time', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('last_activity_at', models.DateTimeField(blank=True, null=True)),
                ('commit_time', models.DateTimeField(blank=True, null=True)),
                ('api_initialized', models.BooleanField(default=False)),
                ('last_error_code', models.CharField(default='0', max_length=10)),
                ('error_diagnostic', models.TextField(blank=True)),
                ('total_time_accumulated', models.CharField(blank=True, default='0000:00:00', max_length=20)),
                ('suspend_data', models.TextField(blank=True)),
                ('current_state', models.CharField(choices=[('not_initialized', 'Not Initialized'), ('initialized', 'Initialized'), ('suspended', 'Suspended'), ('completed', 'Completed'), ('failed', 'Failed')], default='not_initialized', max_length=20)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='scorm.scormregistration')),
            ],
            options={
                'verbose_name': 'SCORM Session',
                'verbose_name_plural': 'SCORM Sessions',
                'ordering': ['-created_at'],
            },
        ),
        # SCORM Runtime Data Model
        migrations.CreateModel(
            name='SCORMRuntimeData',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('data_type', models.CharField(choices=[('current', 'Current'), ('snapshot', 'Snapshot'), ('commit', 'Commit')], default='current', max_length=20)),
                ('lesson_location', models.CharField(blank=True, max_length=255)),
                ('suspend_data', models.TextField(blank=True)),
                ('lesson_status', models.CharField(blank=True, max_length=50)),
                ('score_raw', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('score_max', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('score_min', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('total_time', models.CharField(blank=True, max_length=20)),
                ('session_time', models.CharField(blank=True, max_length=20)),
                ('entry', models.CharField(blank=True, max_length=20)),
                ('mode', models.CharField(blank=True, max_length=20)),
                ('exit', models.CharField(blank=True, max_length=20)),
                ('credit', models.CharField(blank=True, max_length=20)),
                ('extra_data', models.JSONField(blank=True, default=dict)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='runtime_data', to='scorm.scormregistration')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='runtime_data', to='scorm.scormsession')),
            ],
            options={
                'verbose_name': 'SCORM Runtime Data',
                'verbose_name_plural': 'SCORM Runtime Data',
                'ordering': ['-created_at'],
            },
        ),
        # SCORM Interaction Model
        migrations.CreateModel(
            name='SCORMInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('interaction_id', models.CharField(max_length=255)),
                ('interaction_type', models.CharField(choices=[('true-false', 'True/False'), ('choice', 'Multiple Choice'), ('fill-in', 'Fill In'), ('matching', 'Matching'), ('performance', 'Performance'), ('sequencing', 'Sequencing'), ('likert', 'Likert'), ('numeric', 'Numeric'), ('other', 'Other')], max_length=20)),
                ('objectives', models.JSONField(blank=True, default=list)),
                ('timestamp', models.DateTimeField(blank=True, null=True)),
                ('correct_responses', models.JSONField(blank=True, default=list)),
                ('weighting', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('student_response', models.TextField(blank=True)),
                ('result', models.CharField(blank=True, choices=[('correct', 'Correct'), ('wrong', 'Wrong'), ('unanticipated', 'Unanticipated'), ('neutral', 'Neutral'), ('', 'Not Set')], default='', max_length=20)),
                ('latency', models.CharField(blank=True, max_length=20)),
                ('interaction_index', models.PositiveIntegerField(default=0)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interactions', to='scorm.scormregistration')),
            ],
            options={
                'verbose_name': 'SCORM Interaction',
                'verbose_name_plural': 'SCORM Interactions',
                'ordering': ['registration', 'interaction_index'],
                'unique_together': {('registration', 'interaction_id')},
            },
        ),
        # SCORM Objective Model
        migrations.CreateModel(
            name='SCORMObjective',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('objective_id', models.CharField(max_length=255)),
                ('score_raw', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('score_max', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('score_min', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('status', models.CharField(blank=True, choices=[('passed', 'Passed'), ('completed', 'Completed'), ('failed', 'Failed'), ('incomplete', 'Incomplete'), ('not attempted', 'Not Attempted'), ('browsed', 'Browsed')], max_length=20)),
                ('objective_index', models.PositiveIntegerField(default=0)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='objectives', to='scorm.scormregistration')),
            ],
            options={
                'verbose_name': 'SCORM Objective',
                'verbose_name_plural': 'SCORM Objectives',
                'ordering': ['registration', 'objective_index'],
                'unique_together': {('registration', 'objective_id')},
            },
        ),
        # SCORM Cloud Sync Log Model
        migrations.CreateModel(
            name='SCORMCloudSyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sync_type', models.CharField(choices=[('launch', 'Launch'), ('progress', 'Progress'), ('completion', 'Completion'), ('webhook', 'Webhook')], max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('in_progress', 'In Progress'), ('success', 'Success'), ('failed', 'Failed')], max_length=20)),
                ('error_message', models.TextField(blank=True)),
                ('scorm_cloud_response', models.JSONField(blank=True, default=dict)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cloud_sync_logs', to='scorm.scormregistration')),
            ],
            options={
                'verbose_name': 'SCORM Cloud Sync Log',
                'verbose_name_plural': 'SCORM Cloud Sync Logs',
                'ordering': ['-created_at'],
            },
        ),
        # xAPI Statement Model
        migrations.CreateModel(
            name='xAPIStatement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('statement_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('actor', models.JSONField()),
                ('verb', models.JSONField()),
                ('object', models.JSONField()),
                ('result', models.JSONField(blank=True, default=dict)),
                ('context', models.JSONField(blank=True, default=dict)),
                ('timestamp', models.DateTimeField(blank=True, null=True)),
                ('stored', models.DateTimeField(blank=True, null=True)),
                ('voided', models.BooleanField(default=False)),
                ('lrs_endpoint', models.URLField(blank=True)),
                ('lrs_response', models.JSONField(blank=True, default=dict)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('sync_status', models.CharField(choices=[('pending', 'Pending'), ('synced', 'Synced'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('registration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='xapi_statements', to='scorm.scormregistration')),
            ],
            options={
                'verbose_name': 'xAPI Statement',
                'verbose_name_plural': 'xAPI Statements',
                'ordering': ['-created_at'],
            },
        ),
        # Add indexes for performance
        migrations.AddIndex(
            model_name='scormregistration',
            index=models.Index(fields=['user', 'content_item'], name='scorm_reg_user_content_idx'),
        ),
        migrations.AddIndex(
            model_name='scormregistration',
            index=models.Index(fields=['registration_id'], name='scorm_reg_id_idx'),
        ),
        migrations.AddIndex(
            model_name='scormregistration',
            index=models.Index(fields=['scorm_cloud_registration_id'], name='scorm_reg_cloud_idx'),
        ),
        migrations.AddIndex(
            model_name='scormregistration',
            index=models.Index(fields=['status', 'completion_status'], name='scorm_reg_status_idx'),
        ),
        migrations.AddIndex(
            model_name='scormsession',
            index=models.Index(fields=['registration', 'is_active'], name='scorm_sess_reg_active_idx'),
        ),
        migrations.AddIndex(
            model_name='scormsession',
            index=models.Index(fields=['session_id'], name='scorm_sess_id_idx'),
        ),
        migrations.AddIndex(
            model_name='scormruntimedata',
            index=models.Index(fields=['registration', '-created_at'], name='scorm_rt_reg_created_idx'),
        ),
        migrations.AddIndex(
            model_name='scormruntimedata',
            index=models.Index(fields=['session', 'data_type'], name='scorm_rt_sess_type_idx'),
        ),
        migrations.AddIndex(
            model_name='scorminteraction',
            index=models.Index(fields=['registration', 'interaction_index'], name='scorm_int_reg_idx_idx'),
        ),
        migrations.AddIndex(
            model_name='scorminteraction',
            index=models.Index(fields=['interaction_id'], name='scorm_int_id_idx'),
        ),
    ]
