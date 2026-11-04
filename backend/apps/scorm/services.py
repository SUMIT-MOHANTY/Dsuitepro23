"""
SCORM Services for Enterprise LMS
Provides SCORM 1.2 runtime API implementation, launch services, data tracking,
SCORM Cloud integration, and xAPI statement building.
"""

import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache

from apps.courses.models import ContentItem
from apps.users.models import User
from .models import (
    SCORMRegistration,
    SCORMSession,
    SCORMRuntimeData,
    SCORMInteraction,
    SCORMObjective,
    SCORMCloudSyncLog,
    xAPIStatement,
)

logger = logging.getLogger(__name__)


# SCORM 1.2 Error Codes
SCORM_ERROR_CODES = {
    '0': 'No error',
    '101': 'General exception',
    '201': 'Invalid argument error',
    '202': 'Element cannot have children',
    '203': 'Element not an array - cannot have count',
    '301': 'Not initialized',
    '401': 'Not implemented error',
    '402': 'Invalid set value, element is a keyword',
    '403': 'Element is read only',
    '404': 'Element is write only',
    '405': 'Incorrect data type',
}

# SCORM 1.2 Data Model Elements
SCORM_DATA_ELEMENTS = {
    'cmi.core._children': 'read',
    'cmi.core.student_id': 'read',
    'cmi.core.student_name': 'read',
    'cmi.core.lesson_location': 'readwrite',
    'cmi.core.credit': 'read',
    'cmi.core.lesson_status': 'readwrite',
    'cmi.core.entry': 'read',
    'cmi.core.score_children': 'read',
    'cmi.core.score.raw': 'readwrite',
    'cmi.core.score.max': 'readwrite',
    'cmi.core.score.min': 'readwrite',
    'cmi.core.total_time': 'read',
    'cmi.core.lesson_mode': 'read',
    'cmi.core.exit': 'write',
    'cmi.core.session_time': 'write',
    'cmi.suspend_data': 'readwrite',
    'cmi.launch_data': 'read',
    'cmi.comments': 'readwrite',
    'cmi.comments_from_lms': 'read',
    'cmi.objectives._children': 'read',
    'cmi.objectives._count': 'read',
    'cmi.objectives.n.id': 'write',
    'cmi.objectives.n.score._children': 'read',
    'cmi.objectives.n.score.raw': 'readwrite',
    'cmi.objectives.n.score.max': 'readwrite',
    'cmi.objectives.n.score.min': 'readwrite',
    'cmi.objectives.n.status': 'readwrite',
    'cmi.student_data._children': 'read',
    'cmi.student_data.mastery_score': 'read',
    'cmi.student_data.max_time_allowed': 'read',
    'cmi.student_data.time_limit_action': 'read',
    'cmi.student_preference._children': 'read',
    'cmi.student_preference.audio': 'readwrite',
    'cmi.student_preference.language': 'readwrite',
    'cmi.student_preference.speed': 'readwrite',
    'cmi.student_preference.text': 'readwrite',
    'cmi.interactions._children': 'read',
    'cmi.interactions._count': 'read',
    'cmi.interactions.n.id': 'write',
    'cmi.interactions.n.objectives._count': 'read',
    'cmi.interactions.n.objectives.n.id': 'write',
    'cmi.interactions.n.time': 'write',
    'cmi.interactions.n.type': 'write',
    'cmi.interactions.n.correct_responses._count': 'read',
    'cmi.interactions.n.correct_responses.n.pattern': 'write',
    'cmi.interactions.n.weighting': 'write',
    'cmi.interactions.n.student_response': 'write',
    'cmi.interactions.n.result': 'write',
    'cmi.interactions.n.latency': 'write',
}


class SCORMRuntimeService:
    """
    Service implementing SCORM 1.2 Runtime API.
    Handles LMSInitialize, LMSFinish, LMSGetValue, LMSSetValue, LMSCommit,
    LMSGetLastError, LMSGetErrorString, and LMSGetDiagnostic.
    """
    
    def __init__(self, registration: SCORMRegistration, session: Optional[SCORMSession] = None):
        self.registration = registration
        self.session = session
        self.runtime_data = None
        self._error_code = '0'
        self._error_string = 'No error'
        self._diagnostic = ''
        self._initialized = False
        
    def _set_error(self, code: str, diagnostic: str = ''):
        """Set error state."""
        self._error_code = code
        self._error_string = SCORM_ERROR_CODES.get(code, 'Unknown error')
        self._diagnostic = diagnostic
        logger.warning(f"SCORM Error {code}: {self._error_string} - {diagnostic}")
        
    def _clear_error(self):
        """Clear error state."""
        self._error_code = '0'
        self._error_string = 'No error'
        self._diagnostic = ''
        
    def initialize(self) -> str:
        """
        LMSInitialize - Initialize the SCORM API for this registration.
        Returns 'true' or 'false'.
        """
        try:
            if self._initialized:
                self._set_error('101', 'Already initialized')
                return 'false'
            
            # Get or create runtime data
            self.runtime_data, created = SCORMRuntimeData.objects.get_or_create(
                registration=self.registration,
                defaults={
                    'entry': 'ab-initio' if not self.registration.total_time else 'resume',
                    'mode': self.registration.get_mode_display().lower(),
                }
            )
            
            # Update registration status
            self.registration.status = 'active'
            self.registration.save(update_fields=['status', 'updated_at'])
            
            # Create session if not exists
            if not self.session:
                self.session = SCORMSession.objects.create(
                    registration=self.registration,
                    user_agent='',
                    ip_address='',
                )
            
            self._initialized = True
            self._clear_error()
            
            logger.info(f"SCORM initialized for registration {self.registration.registration_id}")
            return 'true'
            
        except Exception as e:
            self._set_error('101', str(e))
            return 'false'
    
    def finish(self) -> str:
        """
        LMSFinish - Terminate the SCORM session.
        Returns 'true' or 'false'.
        """
        try:
            if not self._initialized:
                self._set_error('301', 'Not initialized')
                return 'false'
            
            with transaction.atomic():
                # Update runtime data
                if self.runtime_data:
                    self.runtime_data.exit = 'logout'
                    self.runtime_data.save()
                
                # Update registration with final status
                self.registration.status = 'completed' if self.registration.completion_status == 'completed' else 'suspended'
                
                # Calculate total time
                if self.runtime_data and self.runtime_data.session_time:
                    self._update_total_time(self.runtime_data.session_time)
                
                self.registration.save(update_fields=['status', 'total_time', 'updated_at'])
                
                # End session
                if self.session:
                    self.session.is_active = False
                    self.session.ended_at = timezone.now()
                    self.session.save(update_fields=['is_active', 'ended_at'])
                
                # Generate xAPI statement
                self._generate_completion_statement()
            
            self._initialized = False
            self._clear_error()
            
            logger.info(f"SCORM finished for registration {self.registration.registration_id}")
            return 'true'
            
        except Exception as e:
            self._set_error('101', str(e))
            return 'false'
    
    def get_value(self, element: str) -> str:
        """
        LMSGetValue - Get the value of a SCORM data element.
        Returns the value or empty string on error.
        """
        try:
            if not self._initialized:
                self._set_error('301', 'Not initialized')
                return ''
            
            if element not in SCORM_DATA_ELEMENTS:
                self._set_error('201', f'Invalid element: {element}')
                return ''
            
            access = SCORM_DATA_ELEMENTS[element]
            if access == 'write':
                self._set_error('403', f'Element is write-only: {element}')
                return ''
            
            value = self._get_element_value(element)
            self._clear_error()
            return str(value) if value is not None else ''
            
        except Exception as e:
            self._set_error('101', str(e))
            return ''
    
    def set_value(self, element: str, value: str) -> str:
        """
        LMSSetValue - Set the value of a SCORM data element.
        Returns 'true' or 'false'.
        """
        try:
            if not self._initialized:
                self._set_error('301', 'Not initialized')
                return 'false'
            
            if element not in SCORM_DATA_ELEMENTS:
                self._set_error('201', f'Invalid element: {element}')
                return 'false'
            
            access = SCORM_DATA_ELEMENTS[element]
            if access == 'read':
                self._set_error('403', f'Element is read-only: {element}')
                return 'false'
            
            if not self._validate_value(element, value):
                self._set_error('405', f'Incorrect data type for: {element}')
                return 'false'
            
            self._set_element_value(element, value)
            self._clear_error()
            return 'true'
            
        except Exception as e:
            self._set_error('101', str(e))
            return 'false'
    
    def commit(self) -> str:
        """
        LMSCommit - Persist SCORM data to the database.
        Returns 'true' or 'false'.
        """
        try:
            if not self._initialized:
                self._set_error('301', 'Not initialized')
                return 'false'
            
            with transaction.atomic():
                if self.runtime_data:
                    self.runtime_data.save()
                    
                    # Update registration from runtime data
                    self._sync_registration_from_runtime()
                
                # Update session activity
                if self.session:
                    self.session.last_activity_at = timezone.now()
                    self.session.save(update_fields=['last_activity_at'])
            
            self._clear_error()
            logger.debug(f"SCORM commit successful for registration {self.registration.registration_id}")
            return 'true'
            
        except Exception as e:
            self._set_error('101', str(e))
            return 'false'
    
    def get_last_error(self) -> str:
        """
        LMSGetLastError - Get the last error code.
        Returns the error code as a string.
        """
        return self._error_code
    
    def get_error_string(self, error_code: str) -> str:
        """
        LMSGetErrorString - Get the error string for a given error code.
        Returns the error description.
        """
        return SCORM_ERROR_CODES.get(error_code, 'Unknown error')
    
    def get_diagnostic(self, error_code: str) -> str:
        """
        LMSGetDiagnostic - Get diagnostic information for an error.
        Returns diagnostic message.
        """
        if error_code == self._error_code:
            return self._diagnostic
        return ''
    
    def _get_element_value(self, element: str) -> Any:
        """Get the value of a SCORM data element."""
        if not self.runtime_data:
            return None
        
        # Core elements
        if element == 'cmi.core._children':
            return 'student_id,student_name,lesson_location,credit,lesson_status,entry,score,total_time,lesson_mode,exit,session_time'
        
        if element == 'cmi.core.student_id':
            return str(self.registration.user.id)
        
        if element == 'cmi.core.student_name':
            return self.registration.user.get_full_name()
        
        if element == 'cmi.core.lesson_location':
            return self.runtime_data.lesson_location or ''
        
        if element == 'cmi.core.credit':
            return 'credit' if self.registration.credit else 'no-credit'
        
        if element == 'cmi.core.lesson_status':
            return self.runtime_data.lesson_status or 'not attempted'
        
        if element == 'cmi.core.entry':
            return self.runtime_data.entry or 'ab-initio'
        
        if element == 'cmi.core.score_children':
            return 'raw,max,min'
        
        if element == 'cmi.core.score.raw':
            return str(self.runtime_data.score_raw) if self.runtime_data.score_raw is not None else ''
        
        if element == 'cmi.core.score.max':
            return str(self.runtime_data.score_max) if self.runtime_data.score_max is not None else ''
        
        if element == 'cmi.core.score.min':
            return str(self.runtime_data.score_min) if self.runtime_data.score_min is not None else ''
        
        if element == 'cmi.core.total_time':
            return self.registration.total_time or '0000:00:00'
        
        if element == 'cmi.core.lesson_mode':
            return self.runtime_data.mode or 'normal'
        
        if element == 'cmi.core.exit':
            return self.runtime_data.exit or ''
        
        if element == 'cmi.core.session_time':
            return self.runtime_data.session_time or ''
        
        if element == 'cmi.suspend_data':
            return self.registration.suspend_data or ''
        
        if element == 'cmi.launch_data':
            return self.registration.launch_data or ''
        
        # Student data
        if element == 'cmi.student_data._children':
            return 'mastery_score,max_time_allowed,time_limit_action'
        
        if element == 'cmi.student_data.mastery_score':
            return str(self.registration.mastery_score) if self.registration.mastery_score else ''
        
        if element == 'cmi.student_data.max_time_allowed':
            return self.registration.max_time_allowed or ''
        
        if element == 'cmi.student_data.time_limit_action':
            return self.registration.time_limit_action or 'continue,no message'
        
        # Student preferences
        if element == 'cmi.student_preference._children':
            return 'audio,language,speed,text'
        
        if element == 'cmi.student_preference.audio':
            return self.runtime_data.audio_level or '0'
        
        if element == 'cmi.student_preference.language':
            return self.runtime_data.language or ''
        
        if element == 'cmi.student_preference.speed':
            return self.runtime_data.speed or '0'
        
        if element == 'cmi.student_preference.text':
            return self.runtime_data.text_preference or '0'
        
        # Objectives
        if element == 'cmi.objectives._children':
            return 'id,score,status'
        
        if element == 'cmi.objectives._count':
            return str(SCORMObjective.objects.filter(registration=self.registration).count())
        
        # Interactions
        if element == 'cmi.interactions._children':
            return 'id,objectives,time,type,correct_responses,weighting,student_response,result,latency'
        
        if element == 'cmi.interactions._count':
            return str(SCORMInteraction.objects.filter(registration=self.registration).count())
        
        return ''
    
    def _set_element_value(self, element: str, value: str):
        """Set the value of a SCORM data element."""
        if not self.runtime_data:
            return
        
        # Core elements
        if element == 'cmi.core.lesson_location':
            self.runtime_data.lesson_location = value[:255]
        
        elif element == 'cmi.core.lesson_status':
            valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
            if value.lower() in valid_statuses:
                self.runtime_data.lesson_status = value.lower()
                self.registration.completion_status = value.lower()
        
        elif element == 'cmi.core.score.raw':
            try:
                self.runtime_data.score_raw = Decimal(value)
                self.registration.score = Decimal(value)
            except:
                pass
        
        elif element == 'cmi.core.score.max':
            try:
                self.runtime_data.score_max = Decimal(value)
            except:
                pass
        
        elif element == 'cmi.core.score.min':
            try:
                self.runtime_data.score_min = Decimal(value)
            except:
                pass
        
        elif element == 'cmi.core.exit':
            valid_exits = ['time-out', 'suspend', 'logout', 'normal', '']
            if value in valid_exits:
                self.runtime_data.exit = value
        
        elif element == 'cmi.core.session_time':
            self.runtime_data.session_time = value[:20]
        
        elif element == 'cmi.suspend_data':
            self.registration.suspend_data = value
        
        elif element == 'cmi.student_preference.audio':
            self.runtime_data.audio_level = value[:10]
        
        elif element == 'cmi.student_preference.language':
            self.runtime_data.language = value[:10]
        
        elif element == 'cmi.student_preference.speed':
            self.runtime_data.speed = value[:10]
        
        elif element == 'cmi.student_preference.text':
            self.runtime_data.text_preference = value[:10]
        
        # Handle objectives
        elif element.startswith('cmi.objectives.') and element.endswith('.id'):
            idx = element.split('.')[2]
            objective, _ = SCORMObjective.objects.get_or_create(
                registration=self.registration,
                objective_id=value[:255],
                defaults={'index': int(idx) if idx.isdigit() else 0}
            )
        
        # Handle interactions
        elif element.startswith('cmi.interactions.') and element.endswith('.id'):
            idx = element.split('.')[2]
            interaction, _ = SCORMInteraction.objects.get_or_create(
                registration=self.registration,
                interaction_id=value[:255],
                defaults={'index': int(idx) if idx.isdigit() else 0}
            )
    
    def _validate_value(self, element: str, value: str) -> bool:
        """Validate the value for a SCORM data element."""
        # Add specific validation logic here
        return True
    
    def _update_total_time(self, session_time: str):
        """Update total time by adding session time."""
        try:
            # Parse session time (format: HHHH:MM:SS.SS)
            parts = session_time.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                session_seconds = hours * 3600 + minutes * 60 + seconds
                
                # Parse existing total time
                total_seconds = 0
                if self.registration.total_time:
                    total_parts = self.registration.total_time.split(':')
                    if len(total_parts) == 3:
                        total_seconds = int(total_parts[0]) * 3600 + int(total_parts[1]) * 60 + float(total_parts[2])
                
                # Add and format
                new_total = total_seconds + session_seconds
                new_hours = int(new_total // 3600)
                new_minutes = int((new_total % 3600) // 60)
                new_secs = new_total % 60
                
                self.registration.total_time = f"{new_hours:04d}:{new_minutes:02d}:{new_secs:05.2f}"
        except:
            pass
    
    def _sync_registration_from_runtime(self):
        """Sync registration fields from runtime data."""
        if self.runtime_data:
            if self.runtime_data.lesson_status:
                self.registration.completion_status = self.runtime_data.lesson_status
            if self.runtime_data.score_raw is not None:
                self.registration.score = self.runtime_data.score_raw
    
    def _generate_completion_statement(self):
        """Generate xAPI statement for completion."""
        try:
            xAPIStatement.objects.create(
                registration=self.registration,
                actor={
                    'objectType': 'Agent',
                    'mbox': f"mailto:{self.registration.user.email}",
                    'name': self.registration.user.get_full_name(),
                },
                verb='completed' if self.registration.completion_status == 'completed' else 'terminated',
                object_id=f"{settings.SCORM_CONTENT_BASE_URL}/content/{self.registration.content_item.id}",
                object_definition={
                    'name': {'en-US': self.registration.content_item.title},
                    'type': 'http://adlnet.gov/expapi/activities/course',
                },
                result={
                    'score': {
                        'raw': float(self.registration.score) if self.registration.score else 0,
                        'scaled': float(self.registration.score_scaled) if self.registration.score_scaled else 0,
                    },
                    'completion': self.registration.completion_status == 'completed',
                    'duration': self.registration.total_time,
                },
                activity_type='course',
                activity_name=self.registration.content_item.title,
            )
        except Exception as e:
            logger.error(f"Failed to generate xAPI statement: {e}")


class SCORMLaunchService:
    """
    Service for handling SCORM content launch.
    Creates registrations and generates launch URLs with HTML wrappers.
    """
    
    @staticmethod
    def create_registration(
        user: User,
        content_item: ContentItem,
        scorm_cloud_registration_id: Optional[str] = None,
    ) -> SCORMRegistration:
        """
        Create a new SCORM registration for a user and content item.
        """
        registration_id = str(uuid.uuid4())
        
        registration = SCORMRegistration.objects.create(
            user=user,
            content_item=content_item,
            registration_id=registration_id,
            scorm_cloud_registration_id=scorm_cloud_registration_id,
            status='initialized',
            credit=True,
            mode='normal',
        )
        
        logger.info(f"Created SCORM registration {registration_id} for user {user.email}")
        return registration
    
    @staticmethod
    def get_or_create_registration(
        user: User,
        content_item: ContentItem,
    ) -> SCORMRegistration:
        """
        Get existing registration or create a new one.
        """
        registration = SCORMRegistration.objects.filter(
            user=user,
            content_item=content_item,
        ).first()
        
        if not registration:
            registration = SCORMLaunchService.create_registration(user, content_item)
        
        return registration
    
    @staticmethod
    def generate_launch_context(registration: SCORMRegistration) -> Dict[str, Any]:
        """
        Generate launch context for the SCORM wrapper.
        """
        # Get content URL
        content_url = registration.content_item.file_url or ''
        if registration.content_item.storage_key:
            # Generate signed URL if using cloud storage
            content_url = SCORMLaunchService._get_signed_url(registration.content_item)
        
        return {
            'registration_id': registration.registration_id,
            'content_url': content_url,
            'api_base_url': f"{settings.SCORM_API_BASE_URL}/api/v1/scorm",
            'student_id': str(registration.user.id),
            'student_name': registration.user.get_full_name(),
            'launch_data': registration.launch_data or '',
            'suspend_data': registration.suspend_data or '',
        }
    
    @staticmethod
    def _get_signed_url(content_item: ContentItem) -> str:
        """Generate signed URL for content access."""
        # This would integrate with your cloud storage (Azure, AWS, etc.)
        # For now, return the file_url
        return content_item.file_url or ''


class SCORMCloudService:
    """
    Service for SCORM Cloud integration.
    Handles registration creation, progress sync, and webhook processing.
    """
    
    def __init__(self):
        self.app_id = getattr(settings, 'SCORM_CLOUD_APP_ID', None)
        self.secret_key = getattr(settings, 'SCORM_CLOUD_SECRET_KEY', None)
        self.base_url = getattr(settings, 'SCORM_CLOUD_API_URL', 'https://cloud.scorm.com/api/v2')
    
    def is_configured(self) -> bool:
        """Check if SCORM Cloud is configured."""
        return bool(self.app_id and self.secret_key)
    
    def create_registration(
        self,
        user: User,
        content_item: ContentItem,
        course_id: str,
    ) -> Optional[str]:
        """
        Create a registration in SCORM Cloud.
        Returns the SCORM Cloud registration ID or None.
        """
        if not self.is_configured():
            logger.warning("SCORM Cloud not configured")
            return None
        
        try:
            import requests
            
            registration_id = f"{self.app_id}-{uuid.uuid4().hex[:16]}"
            
            url = f"{self.base_url}/registrations"
            headers = {
                'Authorization': f"Bearer {self._get_access_token()}",
                'Content-Type': 'application/json',
            }
            data = {
                'courseId': course_id,
                'learner': {
                    'id': str(user.id),
                    'email': user.email,
                    'firstName': user.first_name,
                    'lastName': user.last_name,
                },
                'registrationId': registration_id,
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            logger.info(f"Created SCORM Cloud registration: {registration_id}")
            return registration_id
            
        except Exception as e:
            logger.error(f"Failed to create SCORM Cloud registration: {e}")
            return None
    
    def get_launch_url(
        self,
        scorm_cloud_registration_id: str,
        redirect_url: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get launch URL from SCORM Cloud.
        """
        if not self.is_configured():
            return None
        
        try:
            import requests
            
            url = f"{self.base_url}/registrations/{scorm_cloud_registration_id}/launchLink"
            headers = {
                'Authorization': f"Bearer {self._get_access_token()}",
            }
            params = {}
            if redirect_url:
                params['redirectOnExitUrl'] = redirect_url
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            return data.get('launchLink')
            
        except Exception as e:
            logger.error(f"Failed to get SCORM Cloud launch URL: {e}")
            return None
    
    def sync_progress(self, registration: SCORMRegistration) -> bool:
        """
        Sync progress from SCORM Cloud to local database.
        """
        if not self.is_configured() or not registration.scorm_cloud_registration_id:
            return False
        
        sync_log = SCORMCloudSyncLog.objects.create(
            registration=registration,
            sync_type='progress',
            status='pending',
        )
        
        try:
            import requests
            
            url = f"{self.base_url}/registrations/{registration.scorm_cloud_registration_id}"
            headers = {
                'Authorization': f"Bearer {self._get_access_token()}",
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Update registration
            registration.score = Decimal(str(data.get('score', 0)))
            registration.completion_status = data.get('registrationCompletion', 'unknown')
            registration.total_time = data.get('totalTime', '0000:00:00.00')
            registration.save()
            
            sync_log.status = 'success'
            sync_log.scorm_cloud_response = json.dumps(data)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            logger.info(f"Synced SCORM Cloud progress for {registration.registration_id}")
            return True
            
        except Exception as e:
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.save()
            logger.error(f"Failed to sync SCORM Cloud progress: {e}")
            return False
    
    def process_webhook(self, payload: Dict[str, Any]) -> bool:
        """
        Process SCORM Cloud webhook payload.
        """
        try:
            scorm_cloud_reg_id = payload.get('registrationId')
            if not scorm_cloud_reg_id:
                logger.warning("Webhook missing registrationId")
                return False
            
            registration = SCORMRegistration.objects.filter(
                scorm_cloud_registration_id=scorm_cloud_reg_id,
            ).first()
            
            if not registration:
                logger.warning(f"Registration not found for SCORM Cloud ID: {scorm_cloud_reg_id}")
                return False
            
            # Create sync log
            sync_log = SCORMCloudSyncLog.objects.create(
                registration=registration,
                sync_type='webhook',
                status='pending',
                scorm_cloud_response=json.dumps(payload),
            )
            
            # Update registration
            registration.score = Decimal(str(payload.get('score', 0)))
            registration.completion_status = payload.get('completion', 'unknown')
            registration.total_time = payload.get('totalTime', registration.total_time)
            
            if payload.get('completed'):
                registration.status = 'completed'
            
            registration.save()
            
            sync_log.status = 'success'
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            logger.info(f"Processed SCORM Cloud webhook for {registration.registration_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process SCORM Cloud webhook: {e}")
            return False
    
    def _get_access_token(self) -> str:
        """Get access token for SCORM Cloud API."""
        # Check cache first
        token = cache.get('scorm_cloud_access_token')
        if token:
            return token
        
        try:
            import requests
            
            url = f"{self.base_url}/oauth/token"
            auth = (self.app_id, self.secret_key)
            data = {'grant_type': 'client_credentials'}
            
            response = requests.post(url, auth=auth, data=data, timeout=30)
            response.raise_for_status()
            
            token_data = response.json()
            token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)
            
            # Cache token
            cache.set('scorm_cloud_access_token', token, expires_in - 300)
            
            return token
            
        except Exception as e:
            logger.error(f"Failed to get SCORM Cloud access token: {e}")
            raise


class xAPIService:
    """
    Service for xAPI (Tin Can API) statement building and forwarding.
    Converts SCORM data to xAPI statements.
    """
    
    def __init__(self):
        self.lrs_endpoint = getattr(settings, 'XAPI_LRS_ENDPOINT', None)
        self.lrs_key = getattr(settings, 'XAPI_LRS_KEY', None)
        self.lrs_secret = getattr(settings, 'XAPI_LRS_SECRET', None)
    
    def is_configured(self) -> bool:
        """Check if xAPI LRS is configured."""
        return bool(self.lrs_endpoint and self.lrs_key and self.lrs_secret)
    
    def build_statement(
        self,
        registration: SCORMRegistration,
        verb: str,
        result: Optional[Dict] = None,
        context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Build an xAPI statement from SCORM data.
        """
        statement_id = str(uuid.uuid4())
        
        statement = {
            'id': statement_id,
            'actor': {
                'objectType': 'Agent',
                'mbox': f"mailto:{registration.user.email}",
                'name': registration.user.get_full_name(),
            },
            'verb': {
                'id': f"http://adlnet.gov/expapi/verbs/{verb}",
                'display': {'en-US': verb},
            },
            'object': {
                'id': f"{settings.SCORM_CONTENT_BASE_URL}/content/{registration.content_item.id}",
                'objectType': 'Activity',
                'definition': {
                    'name': {'en-US': registration.content_item.title},
                    'type': 'http://adlnet.gov/expapi/activities/course',
                },
            },
            'timestamp': timezone.now().isoformat(),
        }
        
        if result:
            statement['result'] = result
        
        if context:
            statement['context'] = context
        
        return statement
    
    def convert_scorm_to_xapi(
        self,
        registration: SCORMRegistration,
        runtime_data: Optional[SCORMRuntimeData] = None,
    ) -> xAPIStatement:
        """
        Convert SCORM data to xAPI statement and save.
        """
        # Determine verb based on status
        verb = 'experienced'
        if registration.completion_status == 'completed':
            verb = 'completed'
        elif registration.completion_status == 'passed':
            verb = 'passed'
        elif registration.completion_status == 'failed':
            verb = 'failed'
        
        # Build result
        result = {
            'completion': registration.completion_status == 'completed',
            'success': registration.completion_status in ['passed', 'completed'],
        }
        
        if registration.score is not None:
            result['score'] = {
                'raw': float(registration.score),
                'scaled': float(registration.score_scaled) if registration.score_scaled else 0,
            }
        
        if registration.total_time:
            result['duration'] = registration.total_time
        
        # Build statement
        statement_data = self.build_statement(registration, verb, result)
        
        # Save to database
        statement = xAPIStatement.objects.create(
            registration=registration,
            statement_id=statement_data['id'],
            actor=statement_data['actor'],
            verb=verb,
            object_id=statement_data['object']['id'],
            object_definition=statement_data['object']['definition'],
            result=result,
            activity_type='course',
            activity_name=registration.content_item.title,
        )
        
        # Forward to LRS if configured
        if self.is_configured():
            self._forward_to_lrs(statement_data, statement)
        
        return statement
    
    def _forward_to_lrs(self, statement_data: Dict, statement_record: xAPIStatement):
        """Forward xAPI statement to external LRS."""
        try:
            import requests
            
            url = f"{self.lrs_endpoint}/statements"
            auth = (self.lrs_key, self.lrs_secret)
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(
                url,
                auth=auth,
                headers=headers,
                json=statement_data,
                timeout=30,
            )
            response.raise_for_status()
            
            statement_record.is_forwarded = True
            statement_record.forwarded_at = timezone.now()
            statement_record.save()
            
            logger.info(f"Forwarded xAPI statement {statement_record.statement_id} to LRS")
            
        except Exception as e:
            statement_record.forward_error = str(e)
            statement_record.save()
            logger.error(f"Failed to forward xAPI statement: {e}")
    
    def forward_pending_statements(self) -> int:
        """
        Forward any pending xAPI statements to LRS.
        Returns number of statements forwarded.
        """
        if not self.is_configured():
            return 0
        
        pending = xAPIStatement.objects.filter(
            is_forwarded=False,
            forward_error__isnull=True,
        )[:100]
        
        count = 0
        for statement in pending:
            statement_data = {
                'id': statement.statement_id,
                'actor': statement.actor,
                'verb': {
                    'id': f"http://adlnet.gov/expapi/verbs/{statement.verb}",
                    'display': {'en-US': statement.verb},
                },
                'object': {
                    'id': statement.object_id,
                    'definition': statement.object_definition,
                },
                'result': statement.result,
                'context': statement.context,
                'timestamp': statement.timestamp.isoformat(),
            }
            
            self._forward_to_lrs(statement_data, statement)
            count += 1
        
        return count


class SCORMDataTrackingService:
    """
    Service for tracking and persisting SCORM data.
    Handles cmi.core.*, cmi.suspend_data, and completion status.
    """
    
    @staticmethod
    def parse_cmi_data(data: Dict[str, str]) -> Dict[str, Any]:
        """
        Parse CMI data from SCORM API calls.
        """
        parsed = {
            'core': {},
            'suspend_data': '',
            'objectives': [],
            'interactions': [],
        }
        
        for key, value in data.items():
            if key.startswith('cmi.core.'):
                core_key = key.replace('cmi.core.', '')
                parsed['core'][core_key] = value
            elif key == 'cmi.suspend_data':
                parsed['suspend_data'] = value
            elif key.startswith('cmi.objectives.'):
                # Parse objective data
                pass
            elif key.startswith('cmi.interactions.'):
                # Parse interaction data
                pass
        
        return parsed
    
    @staticmethod
    def update_runtime_data(
        registration: SCORMRegistration,
        cmi_data: Dict[str, str],
    ) -> SCORMRuntimeData:
        """
        Update runtime data from CMI values.
        """
        runtime_data, _ = SCORMRuntimeData.objects.get_or_create(
            registration=registration,
            defaults={
                'entry': 'resume' if registration.total_time else 'ab-initio',
            }
        )
        
        parsed = SCORMDataTrackingService.parse_cmi_data(cmi_data)
        
        # Update core fields
        core = parsed.get('core', {})
        
        if 'lesson_location' in core:
            runtime_data.lesson_location = core['lesson_location'][:255]
        
        if 'lesson_status' in core:
            runtime_data.lesson_status = core['lesson_status'][:50]
            registration.completion_status = core['lesson_status'][:50]
        
        if 'score.raw' in core:
            try:
                runtime_data.score_raw = Decimal(core['score.raw'])
                registration.score = Decimal(core['score.raw'])
            except:
                pass
        
        if 'score.max' in core:
            try:
                runtime_data.score_max = Decimal(core['score.max'])
            except:
                pass
        
        if 'score.min' in core:
            try:
                runtime_data.score_min = Decimal(core['score.min'])
            except:
                pass
        
        if 'session_time' in core:
            runtime_data.session_time = core['session_time'][:20]
        
        if 'exit' in core:
            runtime_data.exit = core['exit'][:50]
        
        # Update suspend data
        if parsed.get('suspend_data'):
            registration.suspend_data = parsed['suspend_data']
        
        # Save changes
        runtime_data.save()
        registration.save(update_fields=['suspend_data', 'completion_status', 'score', 'updated_at'])
        
        return runtime_data
    
    @staticmethod
    def get_resume_data(registration: SCORMRegistration) -> Dict[str, str]:
        """
        Get data needed to resume a SCORM session.
        """
        runtime_data = SCORMRuntimeData.objects.filter(registration=registration).first()
        
        data = {
            'cmi.core.entry': 'resume' if registration.total_time else 'ab-initio',
            'cmi.core.lesson_location': '',
            'cmi.core.lesson_status': registration.completion_status or 'not attempted',
            'cmi.core.total_time': registration.total_time or '0000:00:00',
            'cmi.suspend_data': registration.suspend_data or '',
        }
        
        if runtime_data:
            data['cmi.core.lesson_location'] = runtime_data.lesson_location or ''
            if runtime_data.score_raw is not None:
                data['cmi.core.score.raw'] = str(runtime_data.score_raw)
            if runtime_data.score_max is not None:
                data['cmi.core.score.max'] = str(runtime_data.score_max)
            if runtime_data.score_min is not None:
                data['cmi.core.score.min'] = str(runtime_data.score_min)
        
        return data
