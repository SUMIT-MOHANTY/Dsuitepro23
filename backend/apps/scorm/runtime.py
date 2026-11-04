"""
SCORM 1.2 Runtime Implementation for Enterprise LMS
Provides the complete SCORM 1.2 RTE (Runtime Environment) API with:
- Full API adapter with all 8 mandatory methods
- Suspend/resume data persistence
- Completion state machine
- Error code handling
- Session management
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

from apps.core.models import TimestampedModel
from .models import (
    SCORMRegistration,
    SCORMSession,
    SCORMRuntimeData,
    SCORMInteraction,
    SCORMObjective,
    SCORMErrorCodes,
    SCORMLessonStatus,
    SCORMEntry,
    SCORMExit,
    SCORMCredit,
    SCORMLessonMode,
    SCORMRegistrationStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SCORM 1.2 Error Codes (RTE Specification)
# =============================================================================

class SCORM12ErrorCodes:
    """SCORM 1.2 RTE Error Codes per specification"""
    NO_ERROR = '0'
    GENERAL_EXCEPTION = '101'
    GENERAL_GET_FAILURE = '102'
    GENERAL_SET_FAILURE = '103'
    GENERAL_COMMIT_FAILURE = '104'
    INVALID_ARGUMENT = '201'
    ELEMENT_CANNOT_HAVE_CHILDREN = '202'
    ELEMENT_NOT_ARRAY = '203'
    NOT_INITIALIZED = '301'
    ALREADY_INITIALIZED = '302'
    API_NOT_IMPLEMENTED = '401'
    INVALID_SET_VALUE_KEYWORD = '402'
    ELEMENT_READ_ONLY = '403'
    ELEMENT_WRITE_ONLY = '404'
    INCORRECT_DATA_TYPE = '405'

    MESSAGES = {
        NO_ERROR: 'No error',
        GENERAL_EXCEPTION: 'General Exception',
        GENERAL_GET_FAILURE: 'General Get Failure',
        GENERAL_SET_FAILURE: 'General Set Failure',
        GENERAL_COMMIT_FAILURE: 'General Commit Failure',
        INVALID_ARGUMENT: 'Invalid Argument Error',
        ELEMENT_CANNOT_HAVE_CHILDREN: 'Element Cannot Have Children',
        ELEMENT_NOT_ARRAY: 'Element Not Array',
        NOT_INITIALIZED: 'Not Initialized',
        ALREADY_INITIALIZED: 'Already Initialized',
        API_NOT_IMPLEMENTED: 'Not Implemented Error',
        INVALID_SET_VALUE_KEYWORD: 'Invalid Set Value, Element is a Keyword',
        ELEMENT_READ_ONLY: 'Element is Read Only',
        ELEMENT_WRITE_ONLY: 'Element is Write Only',
        INCORRECT_DATA_TYPE: 'Incorrect Data Type',
    }


# =============================================================================
# SCORM 1.2 Data Model Elements
# =============================================================================

class SCORM12DataModel:
    """SCORM 1.2 CMI Data Model Elements with access permissions"""
    
    # Element access types
    READ = 'read'
    WRITE = 'write'
    READWRITE = 'readwrite'
    
    # Core elements
    CORE_ELEMENTS = {
        'cmi.core._children': READ,
        'cmi.core.student_id': READ,
        'cmi.core.student_name': READ,
        'cmi.core.lesson_location': READWRITE,
        'cmi.core.credit': READ,
        'cmi.core.lesson_status': READWRITE,
        'cmi.core.entry': READ,
        'cmi.core._children': READ,
        'cmi.core.score._children': READ,
        'cmi.core.score.raw': READWRITE,
        'cmi.core.score.max': READWRITE,
        'cmi.core.score.min': READWRITE,
        'cmi.core.total_time': READ,
        'cmi.core.lesson_mode': READ,
        'cmi.core.exit': WRITE,
        'cmi.core.session_time': WRITE,
    }
    
    # Suspend data
    SUSPEND_DATA = {
        'cmi.suspend_data': READWRITE,
    }
    
    # Launch data
    LAUNCH_DATA = {
        'cmi.launch_data': READ,
    }
    
    # Comments
    COMMENTS = {
        'cmi.comments': READWRITE,
        'cmi.comments_from_lms': READ,
    }
    
    # Objectives (indexed)
    OBJECTIVES = {
        'cmi.objectives._children': READ,
        'cmi.objectives._count': READ,
        'cmi.objectives.n.id': WRITE,
        'cmi.objectives.n._count': READ,
        'cmi.objectives.n.score._children': READ,
        'cmi.objectives.n.score.raw': READWRITE,
        'cmi.objectives.n.score.max': READWRITE,
        'cmi.objectives.n.score.min': READWRITE,
        'cmi.objectives.n.status': READWRITE,
    }
    
    # Student data
    STUDENT_DATA = {
        'cmi.student_data._children': READ,
        'cmi.student_data.mastery_score': READ,
        'cmi.student_data.max_time_allowed': READ,
        'cmi.student_data.time_limit_action': READ,
    }
    
    # Student preferences
    STUDENT_PREFERENCE = {
        'cmi.student_preference._children': READ,
        'cmi.student_preference.audio': READWRITE,
        'cmi.student_preference.language': READWRITE,
        'cmi.student_preference.speed': READWRITE,
        'cmi.student_preference.text': READWRITE,
    }
    
    # Interactions (indexed)
    INTERACTIONS = {
        'cmi.interactions._children': READ,
        'cmi.interactions._count': READ,
        'cmi.interactions.n.id': WRITE,
        'cmi.interactions.n.objectives._count': READ,
        'cmi.interactions.n.objectives.n.id': WRITE,
        'cmi.interactions.n.time': WRITE,
        'cmi.interactions.n.type': WRITE,
        'cmi.interactions.n.correct_responses._count': READ,
        'cmi.interactions.n.correct_responses.n.pattern': WRITE,
        'cmi.interactions.n.weighting': WRITE,
        'cmi.interactions.n.student_response': WRITE,
        'cmi.interactions.n.result': WRITE,
        'cmi.interactions.n.latency': WRITE,
    }
    
    @classmethod
    def get_all_elements(cls) -> Dict[str, str]:
        """Get all data model elements with their access types"""
        elements = {}
        elements.update(cls.CORE_ELEMENTS)
        elements.update(cls.SUSPEND_DATA)
        elements.update(cls.LAUNCH_DATA)
        elements.update(cls.COMMENTS)
        elements.update(cls.OBJECTIVES)
        elements.update(cls.STUDENT_DATA)
        elements.update(cls.STUDENT_PREFERENCE)
        elements.update(cls.INTERACTIONS)
        return elements
    
    @classmethod
    def is_valid_element(cls, element: str) -> bool:
        """Check if element is a valid SCORM 1.2 data model element"""
        # Check exact match
        if element in cls.get_all_elements():
            return True
        
        # Check indexed patterns (replace n with regex)
        indexed_patterns = [
            r'^cmi\.objectives\.\d+\.(id|score\._children|score\.raw|score\.max|score\.min|status)$',
            r'^cmi\.interactions\.\d+\.(id|objectives\._count|objectives\.\d+\.id|time|type|correct_responses\._count|correct_responses\.\d+\.pattern|weighting|student_response|result|latency)$',
        ]
        
        for pattern in indexed_patterns:
            if re.match(pattern, element):
                return True
        
        return False
    
    @classmethod
    def get_element_access(cls, element: str) -> Optional[str]:
        """Get access type for element (read/write/readwrite)"""
        all_elements = cls.get_all_elements()
        
        # Direct match
        if element in all_elements:
            return all_elements[element]
        
        # Indexed element match
        if re.match(r'^cmi\.objectives\.\d+\.', element):
            base = re.sub(r'\.\d+\.', '.n.', element)
            return all_elements.get(base)
        
        if re.match(r'^cmi\.interactions\.\d+\.', element):
            base = re.sub(r'\.\d+\.', '.n.', element)
            return all_elements.get(base)
        
        return None
    
    @classmethod
    def is_readonly(cls, element: str) -> bool:
        """Check if element is read-only"""
        access = cls.get_element_access(element)
        return access == cls.READ
    
    @classmethod
    def is_writeonly(cls, element: str) -> bool:
        """Check if element is write-only"""
        access = cls.get_element_access(element)
        return access == cls.WRITE


# =============================================================================
# SCORM 1.2 State Machine
# =============================================================================

class SCORM12StateMachine:
    """
    SCORM 1.2 Runtime State Machine
    Enforces: registered → initialized → [active] → [suspended/resumed] → finished
    """
    
    STATE_NOT_INITIALIZED = 'not_initialized'
    STATE_INITIALIZED = 'initialized'
    STATE_ACTIVE = 'active'
    STATE_SUSPENDED = 'suspended'
    STATE_FINISHED = 'finished'
    STATE_TERMINATED = 'terminated'
    
    VALID_TRANSITIONS = {
        STATE_NOT_INITIALIZED: [STATE_INITIALIZED],
        STATE_INITIALIZED: [STATE_ACTIVE, STATE_FINISHED, STATE_TERMINATED],
        STATE_ACTIVE: [STATE_SUSPENDED, STATE_FINISHED, STATE_TERMINATED],
        STATE_SUSPENDED: [STATE_INITIALIZED, STATE_TERMINATED],  # Resume re-initializes
        STATE_FINISHED: [STATE_INITIALIZED],  # Can re-launch
        STATE_TERMINATED: [STATE_INITIALIZED],  # Can re-launch
    }
    
    def __init__(self, initial_state: str = STATE_NOT_INITIALIZED):
        self._state = initial_state
        self._initialized = False
        self._finished = False
    
    @property
    def state(self) -> str:
        return self._state
    
    @property
    def is_initialized(self) -> bool:
        return self._state in (self.STATE_INITIALIZED, self.STATE_ACTIVE, self.STATE_SUSPENDED)
    
    @property
    def is_active(self) -> bool:
        return self._state == self.STATE_ACTIVE
    
    @property
    def is_finished(self) -> bool:
        return self._state in (self.STATE_FINISHED, self.STATE_TERMINATED)
    
    def can_initialize(self) -> bool:
        return self._state in (self.STATE_NOT_INITIALIZED, self.STATE_FINISHED, self.STATE_TERMINATED)
    
    def can_set_value(self) -> bool:
        return self._state in (self.STATE_INITIALIZED, self.STATE_ACTIVE)
    
    def can_commit(self) -> bool:
        return self._state in (self.STATE_INITIALIZED, self.STATE_ACTIVE)
    
    def can_finish(self) -> bool:
        return self._state in (self.STATE_INITIALIZED, self.STATE_ACTIVE)
    
    def transition_to(self, new_state: str) -> Tuple[bool, Optional[str]]:
        """
        Attempt state transition
        Returns: (success, error_message)
        """
        if new_state == self._state:
            return True, None
        
        valid_next = self.VALID_TRANSITIONS.get(self._state, [])
        if new_state not in valid_next:
            return False, f"Invalid transition from {self._state} to {new_state}"
        
        self._state = new_state
        return True, None
    
    def initialize(self) -> Tuple[bool, Optional[str]]:
        """Transition to initialized state"""
        if not self.can_initialize():
            return False, f"Cannot initialize from state: {self._state}"
        return self.transition_to(self.STATE_INITIALIZED)
    
    def activate(self) -> Tuple[bool, Optional[str]]:
        """Transition to active state"""
        return self.transition_to(self.STATE_ACTIVE)
    
    def suspend(self) -> Tuple[bool, Optional[str]]:
        """Transition to suspended state"""
        return self.transition_to(self.STATE_SUSPENDED)
    
    def finish(self) -> Tuple[bool, Optional[str]]:
        """Transition to finished state"""
        if not self.can_finish():
            return False, f"Cannot finish from state: {self._state}"
        return self.transition_to(self.STATE_FINISHED)
    
    def terminate(self) -> Tuple[bool, Optional[str]]:
        """Transition to terminated state"""
        return self.transition_to(self.STATE_TERMINATED)


# =============================================================================
# SCORM 1.2 Runtime Implementation
# =============================================================================

class SCORM12Runtime:
    """
    SCORM 1.2 Runtime Environment (RTE) Implementation
    
    Implements all 8 mandatory SCORM 1.2 API methods:
    - LMSInitialize
    - LMSFinish
    - LMSGetValue
    - LMSSetValue
    - LMSCommit
    - LMSGetLastError
    - LMSGetErrorString
    - LMSGetDiagnostic
    
    Features:
    - Full suspend/resume data persistence
    - Completion state machine
    - Session time tracking
    - Error code handling
    - CMI data validation
    """
    
    # Maximum suspend_data length per SCORM 1.2 spec
    MAX_SUSPEND_DATA_LENGTH = 4096
    
    # Session timeout (30 minutes of inactivity)
    SESSION_TIMEOUT_SECONDS = 1800
    
    def __init__(self, registration: SCORMRegistration, session: Optional[SCORMSession] = None):
        self.registration = registration
        self.session = session
        self.runtime_data: Optional[SCORMRuntimeData] = None
        
        # State machine
        self._state_machine = SCORM12StateMachine()
        
        # Error state
        self._error_code = SCORM12ErrorCodes.NO_ERROR
        self._error_diagnostic = ''
        
        # In-memory CMI data cache (before commit)
        self._cmi_cache: Dict[str, Any] = {}
        
        # Track modified elements since last commit
        self._modified_elements: set = set()
        
        # Session start time for tracking
        self._session_start_time: Optional[datetime] = None
        
        logger.debug(f"SCORM12Runtime initialized for registration {registration.registration_id}")
    
    # =====================================================================
    # SCORM 1.2 API Methods
    # =====================================================================
    
    def LMSInitialize(self, parameter: str = '') -> str:
        """
        LMSInitialize - Initialize the SCORM API
        
        Args:
            parameter: Must be empty string per SCORM 1.2 spec
            
        Returns:
            'true' on success, 'false' on failure
        """
        try:
            # Check if already initialized
            if self._state_machine.is_initialized:
                self._set_error(SCORM12ErrorCodes.ALREADY_INITIALIZED)
                return 'false'
            
            # Validate parameter (must be empty)
            if parameter != '':
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, 'Parameter must be empty string')
                return 'false'
            
            # Attempt state transition
            success, error = self._state_machine.initialize()
            if not success:
                self._set_error(SCORM12ErrorCodes.GENERAL_EXCEPTION, error)
                return 'false'
            
            # Initialize session
            with transaction.atomic():
                self._initialize_session()
                self._load_or_create_runtime_data()
                self._session_start_time = timezone.now()
            
            self._clear_error()
            logger.info(f"SCORM initialized for registration {self.registration.registration_id}")
            return 'true'
            
        except Exception as e:
            logger.exception("LMSInitialize failed")
            self._set_error(SCORM12ErrorCodes.GENERAL_EXCEPTION, str(e))
            return 'false'
    
    def LMSFinish(self, parameter: str = '') -> str:
        """
        LMSFinish - Terminate the SCORM session
        
        Args:
            parameter: Must be empty string per SCORM 1.2 spec
            
        Returns:
            'true' on success, 'false' on failure
        """
        try:
            # Check if initialized
            if not self._state_machine.is_initialized:
                self._set_error(SCORM12ErrorCodes.NOT_INITIALIZED)
                return 'false'
            
            # Validate parameter
            if parameter != '':
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, 'Parameter must be empty string')
                return 'false'
            
            # Check if can finish
            if not self._state_machine.can_finish():
                self._set_error(SCORM12ErrorCodes.GENERAL_EXCEPTION, 'Cannot finish in current state')
                return 'false'
            
            # Commit any pending data first
            commit_result = self.LMSCommit('')
            if commit_result == 'false':
                self._set_error(SCORM12ErrorCodes.GENERAL_COMMIT_FAILURE, 'Auto-commit before finish failed')
                return 'false'
            
            # Finish session
            with transaction.atomic():
                self._finish_session()
                
                # Update state machine
                success, error = self._state_machine.finish()
                if not success:
                    self._set_error(SCORM12ErrorCodes.GENERAL_EXCEPTION, error)
                    return 'false'
            
            self._clear_error()
            logger.info(f"SCORM finished for registration {self.registration.registration_id}")
            return 'true'
            
        except Exception as e:
            logger.exception("LMSFinish failed")
            self._set_error(SCORM12ErrorCodes.GENERAL_EXCEPTION, str(e))
            return 'false'
    
    def LMSGetValue(self, element: str) -> str:
        """
        LMSGetValue - Get the value of a CMI data element
        
        Args:
            element: The CMI element name (e.g., 'cmi.core.lesson_status')
            
        Returns:
            The element value, or empty string on error
        """
        try:
            # Check if initialized
            if not self._state_machine.is_initialized:
                self._set_error(SCORM12ErrorCodes.NOT_INITIALIZED)
                return ''
            
            # Validate element
            if not element or not isinstance(element, str):
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, 'Element must be non-empty string')
                return ''
            
            # Check if valid element
            if not SCORM12DataModel.is_valid_element(element):
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, f'Invalid element: {element}')
                return ''
            
            # Check if write-only
            if SCORM12DataModel.is_writeonly(element):
                self._set_error(SCORM12ErrorCodes.ELEMENT_WRITE_ONLY, f'Element is write-only: {element}')
                return ''
            
            # Get the value
            value = self._get_element_value(element)
            
            self._clear_error()
            return str(value) if value is not None else ''
            
        except Exception as e:
            logger.exception(f"LMSGetValue failed for element {element}")
            self._set_error(SCORM12ErrorCodes.GENERAL_GET_FAILURE, str(e))
            return ''
    
    def LMSSetValue(self, element: str, value: str) -> str:
        """
        LMSSetValue - Set the value of a CMI data element
        
        Args:
            element: The CMI element name
            value: The value to set
            
        Returns:
            'true' on success, 'false' on failure
        """
        try:
            # Check if initialized
            if not self._state_machine.is_initialized:
                self._set_error(SCORM12ErrorCodes.NOT_INITIALIZED)
                return 'false'
            
            # Check if can set values
            if not self._state_machine.can_set_value():
                self._set_error(SCORM12ErrorCodes.GENERAL_SET_FAILURE, 'Cannot set values in current state')
                return 'false'
            
            # Validate element
            if not element or not isinstance(element, str):
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, 'Element must be non-empty string')
                return 'false'
            
            # Check if valid element
            if not SCORM12DataModel.is_valid_element(element):
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, f'Invalid element: {element}')
                return 'false'
            
            # Check if read-only
            if SCORM12DataModel.is_readonly(element):
                self._set_error(SCORM12ErrorCodes.ELEMENT_READ_ONLY, f'Element is read-only: {element}')
                return 'false'
            
            # Validate value
            if not self._validate_value(element, value):
                self._set_error(SCORM12ErrorCodes.INCORRECT_DATA_TYPE, f'Invalid data type for {element}')
                return 'false'
            
            # Set the value in cache
            self._cmi_cache[element] = value
            self._modified_elements.add(element)
            
            # Handle special elements immediately
            self._handle_special_set(element, value)
            
            self._clear_error()
            return 'true'
            
        except Exception as e:
            logger.exception(f"LMSSetValue failed for element {element}")
            self._set_error(SCORM12ErrorCodes.GENERAL_SET_FAILURE, str(e))
            return 'false'
    
    def LMSCommit(self, parameter: str = '') -> str:
        """
        LMSCommit - Persist all CMI data to the database
        
        Args:
            parameter: Must be empty string per SCORM 1.2 spec
            
        Returns:
            'true' on success, 'false' on failure
        """
        try:
            # Check if initialized
            if not self._state_machine.is_initialized:
                self._set_error(SCORM12ErrorCodes.NOT_INITIALIZED)
                return 'false'
            
            # Validate parameter
            if parameter != '':
                self._set_error(SCORM12ErrorCodes.INVALID_ARGUMENT, 'Parameter must be empty string')
                return 'false'
            
            # Check if can commit
            if not self._state_machine.can_commit():
                self._set_error(SCORM12ErrorCodes.GENERAL_COMMIT_FAILURE, 'Cannot commit in current state')
                return 'false'
            
            # Persist data
            with transaction.atomic():
                self._persist_cmi_data()
                self._update_session_commit_time()
            
            # Clear modified elements
            self._modified_elements.clear()
            
            self._clear_error()
            logger.debug(f"SCORM commit successful for registration {self.registration.registration_id}")
            return 'true'
            
        except Exception as e:
            logger.exception("LMSCommit failed")
            self._set_error(SCORM12ErrorCodes.GENERAL_COMMIT_FAILURE, str(e))
            return 'false'
    
    def LMSGetLastError(self) -> str:
        """
        LMSGetLastError - Get the error code from the last operation
        
        Returns:
            The error code as a string (e.g., '0', '101', etc.)
        """
        return self._error_code
    
    def LMSGetErrorString(self, error_code: str) -> str:
        """
        LMSGetErrorString - Get the error message for a given error code
        
        Args:
            error_code: The SCORM error code
            
        Returns:
            The error message string
        """
        return SCORM12ErrorCodes.MESSAGES.get(error_code, 'Unknown error')
    
    def LMSGetDiagnostic(self, error_code: str) -> str:
        """
        LMSGetDiagnostic - Get diagnostic information for an error
        
        Args:
            error_code: The SCORM error code
            
        Returns:
            Diagnostic information string
        """
        if error_code == self._error_code:
            return self._error_diagnostic
        return ''
    
    # =====================================================================
    # Internal Methods
    # =====================================================================
    
    def _set_error(self, code: str, diagnostic: str = ''):
        """Set error state"""
        self._error_code = code
        self._error_diagnostic = diagnostic
        if code != SCORM12ErrorCodes.NO_ERROR:
            logger.warning(f"SCORM Error {code}: {SCORM12ErrorCodes.MESSAGES.get(code)} - {diagnostic}")
    
    def _clear_error(self):
        """Clear error state"""
        self._error_code = SCORM12ErrorCodes.NO_ERROR
        self._error_diagnostic = ''
    
    def _initialize_session(self):
        """Initialize or resume session"""
        if not self.session:
            # Create new session
            entry = SCORMEntry.RESUME if self.registration.suspend_data else SCORMEntry.AB_INITIO
            
            self.session = SCORMSession.objects.create(
                registration=self.registration,
                status=SCORMSession.SESSION_STATUS_ACTIVE,
                entry=entry,
                api_initialized=True,
                launch_time=timezone.now(),
            )
            
            # Update registration
            self.registration.launch_count += 1
            self.registration.last_launched_at = timezone.now()
            self.registration.entry = entry
            self.registration.save(update_fields=['launch_count', 'last_launched_at', 'entry', 'updated_at'])
        else:
            # Resume existing session
            self.session.status = SCORMSession.SESSION_STATUS_ACTIVE
            self.session.api_initialized = True
            self.session.save(update_fields=['status', 'api_initialized', 'updated_at'])
    
    def _load_or_create_runtime_data(self):
        """Load existing runtime data or create new"""
        # Try to get existing runtime data
        try:
            self.runtime_data = SCORMRuntimeData.objects.filter(
                registration=self.registration,
                data_type=SCORMRuntimeData.DATA_TYPE_CURRENT
            ).latest('created_at')
            
            # Load into cache
            self._load_runtime_data_to_cache()
            
        except SCORMRuntimeData.DoesNotExist:
            # Create new runtime data
            self.runtime_data = SCORMRuntimeData.objects.create(
                registration=self.registration,
                session=self.session,
                data_type=SCORMRuntimeData.DATA_TYPE_CURRENT,
                lesson_location=self.registration.lesson_location or '',
                suspend_data=self.registration.suspend_data or '',
                lesson_status=self.registration.completion_status or SCORMLessonStatus.NOT_ATTEMPTED,
                score_raw=self.registration.score_raw,
                score_max=self.registration.score_max,
                score_min=self.registration.score_min,
                total_time=self.registration.total_time or '',
            )
    
    def _load_runtime_data_to_cache(self):
        """Load runtime data into cache"""
        if not self.runtime_data:
            return
        
        self._cmi_cache['cmi.core.lesson_location'] = self.runtime_data.lesson_location or ''
        self._cmi_cache['cmi.suspend_data'] = self.runtime_data.suspend_data or ''
        self._cmi_cache['cmi.core.lesson_status'] = self.runtime_data.lesson_status or ''
        
        if self.runtime_data.score_raw is not None:
            self._cmi_cache['cmi.core.score.raw'] = str(self.runtime_data.score_raw)
        if self.runtime_data.score_max is not None:
            self._cmi_cache['cmi.core.score.max'] = str(self.runtime_data.score_max)
        if self.runtime_data.score_min is not None:
            self._cmi_cache['cmi.core.score.min'] = str(self.runtime_data.score_min)
    
    def _finish_session(self):
        """Finish the session and update registration"""
        if not self.session:
            return
        
        # Get exit value from cache
        exit_value = self._cmi_cache.get('cmi.core.exit', '')
        
        # Calculate session time
        session_time = self._calculate_session_time()
        
        # Update session
        self.session.is_active = False
        self.session.ended_at = timezone.now()
        self.session.status = SCORMSession.SESSION_STATUS_COMPLETED if exit_value != SCORMExit.SUSPEND else SCORMSession.SESSION_STATUS_SUSPENDED
        self.session.save(update_fields=['is_active', 'ended_at', 'status', 'updated_at'])
        
        # Update registration with final values
        self._update_registration_on_finish(exit_value, session_time)
    
    def _calculate_session_time(self) -> str:
        """Calculate session time in HHHH:MM:SS format"""
        if not self._session_start_time:
            return '0000:00:00'
        
        duration = timezone.now() - self._session_start_time
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        return f"{hours:04d}:{minutes:02d}:{seconds:02d}"
    
    def _update_registration_on_finish(self, exit_value: str, session_time: str):
        """Update registration when session finishes"""
        # Update session time
        self.registration.session_time = session_time
        
        # Handle suspend data
        if exit_value == SCORMExit.SUSPEND:
            self.registration.exit_status = SCORMExit.SUSPEND
            self.registration.status = SCORMRegistration.STATUS_SUSPENDED
            
            # Save suspend data
            suspend_data = self._cmi_cache.get('cmi.suspend_data', '')
            if len(suspend_data) > self.MAX_SUSPEND_DATA_LENGTH:
                suspend_data = suspend_data[:self.MAX_SUSPEND_DATA_LENGTH]
            self.registration.suspend_data = suspend_data
            
            # Save lesson location
            lesson_location = self._cmi_cache.get('cmi.core.lesson_location', '')
            self.registration.lesson_location = lesson_location
        else:
            self.registration.exit_status = exit_value or SCORMExit.NORMAL
            
            # Check completion status
            lesson_status = self._cmi_cache.get('cmi.core.lesson_status', '')
            if lesson_status in (SCORMLessonStatus.COMPLETED, SCORMLessonStatus.PASSED):
                self.registration.status = SCORMRegistration.STATUS_COMPLETED if lesson_status == SCORMLessonStatus.COMPLETED else SCORMRegistration.STATUS_PASSED
                self.registration.completion_status = lesson_status
                self.registration.completed_at = timezone.now()
            else:
                self.registration.status = SCORMRegistration.STATUS_IN_PROGRESS
                self.registration.completion_status = lesson_status or SCORMLessonStatus.INCOMPLETE
        
        # Update total time
        self._accumulate_total_time(session_time)
        
        # Update scores
        raw_score = self._cmi_cache.get('cmi.core.score.raw')
        if raw_score:
            try:
                self.registration.score_raw = Decimal(raw_score)
            except InvalidOperation:
                pass
        
        max_score = self._cmi_cache.get('cmi.core.score.max')
        if max_score:
            try:
                self.registration.score_max = Decimal(max_score)
            except InvalidOperation:
                pass
        
        min_score = self._cmi_cache.get('cmi.core.score.min')
        if min_score:
            try:
                self.registration.score_min = Decimal(min_score)
            except InvalidOperation:
                pass
        
        self.registration.save(update_fields=[
            'session_time', 'exit_status', 'status', 'completion_status',
            'suspend_data', 'lesson_location', 'total_time', 'completed_at',
            'score_raw', 'score_max', 'score_min', 'updated_at'
        ])
    
    def _accumulate_total_time(self, session_time: str):
        """Add session time to total time"""
        if not session_time or session_time == '0000:00:00':
            return
        
        # Parse session time
        try:
            parts = session_time.split(':')
            session_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, IndexError):
            return
        
        # Parse existing total time
        total_seconds = 0
        if self.registration.total_time:
            try:
                parts = self.registration.total_time.split(':')
                total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except (ValueError, IndexError):
                pass
        
        # Add and format
        total_seconds += session_seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        self.registration.total_time = f"{hours:04d}:{minutes:02d}:{seconds:02d}"
    
    def _get_element_value(self, element: str) -> Any:
        """Get value for a CMI element"""
        # Special elements
        if element == 'cmi.core._children':
            return 'student_id,student_name,lesson_location,credit,lesson_status,entry,score,total_time,lesson_mode,exit,session_time'
        
        if element == 'cmi.core.score._children':
            return 'raw,min,max'
        
        if element == 'cmi.core.student_id':
            return str(self.registration.user.id)
        
        if element == 'cmi.core.student_name':
            return self.registration.user.get_full_name() or self.registration.user.username
        
        if element == 'cmi.core.credit':
            return 'credit' if self.registration.credit == SCORMCredit.CREDIT else 'no-credit'
        
        if element == 'cmi.core.entry':
            return self.session.entry if self.session else SCORMEntry.AB_INITIO
        
        if element == 'cmi.core.total_time':
            return self.registration.total_time or '0000:00:00'
        
        if element == 'cmi.core.lesson_mode':
            return self.registration.lesson_mode or SCORMLessonMode.NORMAL
        
        if element == 'cmi.core.session_time':
            return self._calculate_session_time()
        
        if element == 'cmi.objectives._count':
            return str(SCORMObjective.objects.filter(registration=self.registration).count())
        
        if element == 'cmi.interactions._count':
            return str(SCORMInteraction.objects.filter(registration=self.registration).count())
        
        # Check cache first for modified values
        if element in self._cmi_cache:
            return self._cmi_cache[element]
        
        # Fall back to runtime data
        if self.runtime_data:
            if element == 'cmi.core.lesson_location':
                return self.runtime_data.lesson_location or ''
            if element == 'cmi.suspend_data':
                return self.runtime_data.suspend_data or ''
            if element == 'cmi.core.lesson_status':
                return self.runtime_data.lesson_status or SCORMLessonStatus.NOT_ATTEMPTED
            if element == 'cmi.core.score.raw':
                return str(self.runtime_data.score_raw) if self.runtime_data.score_raw is not None else ''
            if element == 'cmi.core.score.max':
                return str(self.runtime_data.score_max) if self.runtime_data.score_max is not None else ''
            if element == 'cmi.core.score.min':
                return str(self.runtime_data.score_min) if self.runtime_data.score_min is not None else ''
        
        return ''
    
    def _validate_value(self, element: str, value: str) -> bool:
        """Validate value for a CMI element"""
        if value is None:
            return True  # Allow clearing values
        
        value_str = str(value)
        
        # Validate suspend_data length
        if element == 'cmi.suspend_data':
            return len(value_str) <= self.MAX_SUSPEND_DATA_LENGTH
        
        # Validate lesson_status
        if element == 'cmi.core.lesson_status':
            valid_statuses = [s[0] for s in SCORMLessonStatus.CHOICES]
            return value_str in valid_statuses
        
        # Validate exit
        if element == 'cmi.core.exit':
            valid_exits = [e[0] for e in SCORMExit.CHOICES]
            return value_str in valid_exits
        
        # Validate score values
        if element in ('cmi.core.score.raw', 'cmi.core.score.max', 'cmi.core.score.min'):
            if value_str == '':
                return True
            try:
                score = Decimal(value_str)
                return 0 <= score <= 100
            except InvalidOperation:
                return False
        
        # Validate session_time format (HHHH:MM:SS)
        if element == 'cmi.core.session_time':
            if value_str == '':
                return True
            return bool(re.match(r'^\d{4}:\d{2}:\d{2}$', value_str))
        
        return True
    
    def _handle_special_set(self, element: str, value: str):
        """Handle special set operations"""
        # Track exit value
        if element == 'cmi.core.exit':
            if self.session:
                self.session.exit_value = value
                self.session.save(update_fields=['exit_value', 'updated_at'])
        
        # Update session time
        if element == 'cmi.core.session_time':
            if self.session:
                self.session.session_time = value
                self.session.save(update_fields=['session_time', 'updated_at'])
    
    def _persist_cmi_data(self):
        """Persist cached CMI data to database"""
        if not self.runtime_data:
            return
        
        # Update runtime data from cache
        if 'cmi.core.lesson_location' in self._modified_elements:
            self.runtime_data.lesson_location = self._cmi_cache.get('cmi.core.lesson_location', '')
        
        if 'cmi.suspend_data' in self._modified_elements:
            suspend_data = self._cmi_cache.get('cmi.suspend_data', '')
            if len(suspend_data) > self.MAX_SUSPEND_DATA_LENGTH:
                suspend_data = suspend_data[:self.MAX_SUSPEND_DATA_LENGTH]
            self.runtime_data.suspend_data = suspend_data
        
        if 'cmi.core.lesson_status' in self._modified_elements:
            self.runtime_data.lesson_status = self._cmi_cache.get('cmi.core.lesson_status', '')
        
        if 'cmi.core.score.raw' in self._modified_elements:
            raw = self._cmi_cache.get('cmi.core.score.raw', '')
            self.runtime_data.score_raw = Decimal(raw) if raw else None
        
        if 'cmi.core.score.max' in self._modified_elements:
            max_val = self._cmi_cache.get('cmi.core.score.max', '')
            self.runtime_data.score_max = Decimal(max_val) if max_val else None
        
        if 'cmi.core.score.min' in self._modified_elements:
            min_val = self._cmi_cache.get('cmi.core.score.min', '')
            self.runtime_data.score_min = Decimal(min_val) if min_val else None
        
        if 'cmi.core.session_time' in self._modified_elements:
            self.runtime_data.session_time = self._cmi_cache.get('cmi.core.session_time', '')
        
        # Store full CMI snapshot
        self.runtime_data.extra_data = dict(self._cmi_cache)
        self.runtime_data.save()
        
        # Create commit snapshot
        SCORMRuntimeData.objects.create(
            registration=self.registration,
            session=self.session,
            data_type=SCORMRuntimeData.DATA_TYPE_COMMIT,
            lesson_location=self.runtime_data.lesson_location,
            suspend_data=self.runtime_data.suspend_data,
            lesson_status=self.runtime_data.lesson_status,
            score_raw=self.runtime_data.score_raw,
            score_max=self.runtime_data.score_max,
            score_min=self.runtime_data.score_min,
            total_time=self.runtime_data.total_time,
            session_time=self.runtime_data.session_time,
            extra_data=dict(self._cmi_cache),
        )
    
    def _update_session_commit_time(self):
        """Update session commit timestamp"""
        if self.session:
            self.session.commit_time = timezone.now()
            self.session.save(update_fields=['commit_time', 'updated_at'])
    
    # =====================================================================
    # Public Utility Methods
    # =====================================================================
    
    def get_state(self) -> str:
        """Get current state machine state"""
        return self._state_machine.state
    
    def is_initialized(self) -> bool:
        """Check if runtime is initialized"""
        return self._state_machine.is_initialized
    
    def is_finished(self) -> bool:
        """Check if runtime is finished"""
        return self._state_machine.is_finished
    
    def get_cached_value(self, element: str) -> Any:
        """Get value from cache (without API call)"""
        return self._cmi_cache.get(element)
    
    def get_modified_elements(self) -> set:
        """Get set of modified elements since last commit"""
        return self._modified_elements.copy()
    
    def get_error_info(self) -> Dict[str, str]:
        """Get current error information"""
        return {
            'code': self._error_code,
            'string': SCORM12ErrorCodes.MESSAGES.get(self._error_code, 'Unknown'),
            'diagnostic': self._error_diagnostic,
        }


# =============================================================================
# SCORM 12 Runtime Factory
# =============================================================================

class SCORM12RuntimeFactory:
    """Factory for creating SCORM 1.2 runtime instances"""
    
    @staticmethod
    def create_runtime(registration_id: str) -> Optional[SCORM12Runtime]:
        """
        Create a SCORM 1.2 runtime instance for a registration
        
        Args:
            registration_id: The SCORM registration UUID
            
        Returns:
            SCORM12Runtime instance or None if registration not found
        """
        try:
            registration = SCORMRegistration.objects.get(registration_id=registration_id)
            
            # Get or create active session
            session = SCORMSession.objects.filter(
                registration=registration,
                is_active=True
            ).first()
            
            return SCORM12Runtime(registration, session)
            
        except SCORMRegistration.DoesNotExist:
            logger.error(f"SCORM registration not found: {registration_id}")
            return None
        except Exception as e:
            logger.exception(f"Failed to create SCORM runtime: {e}")
            return None
    
    @staticmethod
    def create_runtime_for_user(user_id: int, content_item_id: int) -> Tuple[Optional[SCORM12Runtime], Optional[SCORMRegistration]]:
        """
        Create or get runtime for a user and content item
        
        Returns:
            Tuple of (runtime, registration) or (None, None) on error
        """
        try:
            from apps.courses.models import ContentItem
            
            content_item = ContentItem.objects.get(id=content_item_id)
            
            # Get or create registration
            registration, created = SCORMRegistration.objects.get_or_create(
                user_id=user_id,
                content_item=content_item,
                defaults={
                    'status': SCORMRegistration.STATUS_NOT_ATTEMPTED,
                    'completion_status': SCORMLessonStatus.NOT_ATTEMPTED,
                }
            )
            
            # Get active session
            session = SCORMSession.objects.filter(
                registration=registration,
                is_active=True
            ).first()
            
            runtime = SCORM12Runtime(registration, session)
            return runtime, registration
            
        except ContentItem.DoesNotExist:
            logger.error(f"Content item not found: {content_item_id}")
            return None, None
        except Exception as e:
            logger.exception(f"Failed to create SCORM runtime: {e}")
            return None, None


# =============================================================================
# Legacy API Adapter (for backward compatibility)
# =============================================================================

class APIAdapter12:
    """
    Legacy SCORM 1.2 API Adapter
    Provides a simple interface for SCORM content to call
    """
    
    def __init__(self, runtime: SCORM12Runtime):
        self._runtime = runtime
    
    def LMSInitialize(self, parameter: str = '') -> str:
        return self._runtime.LMSInitialize(parameter)
    
    def LMSFinish(self, parameter: str = '') -> str:
        return self._runtime.LMSFinish(parameter)
    
    def LMSGetValue(self, element: str) -> str:
        return self._runtime.LMSGetValue(element)
    
    def LMSSetValue(self, element: str, value: str) -> str:
        return self._runtime.LMSSetValue(element, value)
    
    def LMSCommit(self, parameter: str = '') -> str:
        return self._runtime.LMSCommit(parameter)
    
    def LMSGetLastError(self) -> str:
        return self._runtime.LMSGetLastError()
    
    def LMSGetErrorString(self, error_code: str) -> str:
        return self._runtime.LMSGetErrorString(error_code)
    
    def LMSGetDiagnostic(self, error_code: str) -> str:
        return self._runtime.LMSGetDiagnostic(error_code)
