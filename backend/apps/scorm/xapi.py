"""
xAPI (Experience API) Statement Builder for SCORM Data
Converts SCORM 1.2 runtime data to xAPI statements for LRS integration.

This is a Phase 1 stub implementation. Full xAPI/LRS integration will be
implemented in Phase 2.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from django.conf import settings

from .models import SCORMRegistration, SCORMSession, SCORMRuntimeData


class xAPIStatementBuilder:
    """
    Builder class for creating xAPI statements from SCORM data.
    
    xAPI (Experience API) is a specification for learning technology that
    enables the collection of data about learning experiences.
    
    This builder converts SCORM 1.2 cmi.* data to xAPI statement format
    compatible with Learning Record Stores (LRS).
    """
    
    # xAPI Verb URIs
    VERB_INITIALIZED = "http://adlnet.gov/expapi/verbs/initialized"
    VERB_COMPLETED = "http://adlnet.gov/expapi/verbs/completed"
    VERB_PASSED = "http://adlnet.gov/expapi/verbs/passed"
    VERB_FAILED = "http://adlnet.gov/expapi/verbs/failed"
    VERB_TERMINATED = "http://adlnet.gov/expapi/verbs/terminated"
    VERB_SUSPENDED = "http://adlnet.gov/expapi/verbs/suspended"
    VERB_RESUMED = "http://adlnet.gov/expapi/verbs/resumed"
    VERB_ANSWERED = "http://adlnet.gov/expapi/verbs/answered"
    VERB_INTERACTED = "http://adlnet.gov/expapi/verbs/interacted"
    VERB_PROGRESSED = "http://adlnet.gov/expapi/verbs/progressed"
    
    # xAPI Activity Type URIs
    ACTIVITY_TYPE_COURSE = "http://adlnet.gov/expapi/activities/course"
    ACTIVITY_TYPE_LESSON = "http://adlnet.gov/expapi/activities/lesson"
    ACTIVITY_TYPE_INTERACTION = "http://adlnet.gov/expapi/activities/interaction"
    ACTIVITY_TYPE_ASSESSMENT = "http://adlnet.gov/expapi/activities/assessment"
    
    def __init__(self):
        """Initialize the xAPI statement builder."""
        self.lrs_endpoint = getattr(settings, 'XAPI_LRS_ENDPOINT', None)
        self.lrs_key = getattr(settings, 'XAPI_LRS_KEY', None)
        self.lrs_secret = getattr(settings, 'XAPI_LRS_SECRET', None)
    
    def _generate_statement_id(self) -> str:
        """Generate a unique statement ID."""
        return str(uuid.uuid4())
    
    def _build_actor(self, registration: SCORMRegistration) -> Dict[str, Any]:
        """
        Build the actor component of an xAPI statement.
        
        Args:
            registration: SCORM registration containing user info
            
        Returns:
            Actor dictionary with mbox (email) identifier
        """
        user = registration.user
        return {
            "objectType": "Agent",
            "mbox": f"mailto:{user.email}",
            "name": user.get_full_name() or user.email
        }
    
    def _build_verb(self, verb_uri: str, display: Dict[str, str]) -> Dict[str, Any]:
        """
        Build the verb component of an xAPI statement.
        
        Args:
            verb_uri: The xAPI verb URI
            display: Display names in different languages
            
        Returns:
            Verb dictionary
        """
        return {
            "id": verb_uri,
            "display": display
        }
    
    def _build_object(self, registration: SCORMRegistration, 
                      activity_type: str = None,
                      additional_properties: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Build the object component of an xAPI statement.
        
        Args:
            registration: SCORM registration
            activity_type: xAPI activity type URI
            additional_properties: Additional object properties
            
        Returns:
            Object dictionary
        """
        content_item = registration.content_item
        
        obj = {
            "objectType": "Activity",
            "id": f"{settings.SITE_URL}/scorm/content/{content_item.id}",
            "definition": {
                "name": {
                    "en-US": content_item.title or "SCORM Content"
                },
                "description": {
                    "en-US": f"SCORM content for {content_item.lesson.title if content_item.lesson else 'Unknown Lesson'}"
                }
            }
        }
        
        if activity_type:
            obj["definition"]["type"] = activity_type
        
        if additional_properties:
            obj["definition"].update(additional_properties)
        
        return obj
    
    def _build_context(self, registration: SCORMRegistration,
                       session: SCORMSession = None,
                       parent_activity: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Build the context component of an xAPI statement.
        
        Args:
            registration: SCORM registration
            session: Optional SCORM session
            parent_activity: Optional parent activity for context
            
        Returns:
            Context dictionary
        """
        context = {
            "registration": str(registration.id),
            "contextActivities": {}
        }
        
        # Add course as parent activity if available
        if registration.content_item and registration.content_item.course:
            course = registration.content_item.course
            context["contextActivities"]["parent"] = [{
                "objectType": "Activity",
                "id": f"{settings.SITE_URL}/courses/{course.id}",
                "definition": {
                    "name": {"en-US": course.title},
                    "type": self.ACTIVITY_TYPE_COURSE
                }
            }]
        
        if parent_activity:
            context["contextActivities"]["parent"] = [parent_activity]
        
        # Add session info if available
        if session:
            context["session_id"] = session.session_id
        
        return context
    
    def _build_result(self, runtime_data: SCORMRuntimeData = None,
                      score: float = None,
                      success: bool = None,
                      completion: bool = None,
                      duration: str = None,
                      response: str = None) -> Dict[str, Any]:
        """
        Build the result component of an xAPI statement.
        
        Args:
            runtime_data: Optional SCORM runtime data
            score: Optional score value
            success: Optional success status
            completion: Optional completion status
            duration: Optional duration (ISO 8601 format)
            response: Optional learner response
            
        Returns:
            Result dictionary
        """
        result = {}
        
        if runtime_data:
            # Build score from runtime data
            if runtime_data.score_raw is not None:
                score_data = {
                    "raw": float(runtime_data.score_raw)
                }
                if runtime_data.score_min is not None:
                    score_data["min"] = float(runtime_data.score_min)
                if runtime_data.score_max is not None:
                    score_data["max"] = float(runtime_data.score_max)
                if runtime_data.score_scaled is not None:
                    score_data["scaled"] = float(runtime_data.score_scaled)
                result["score"] = score_data
            
            # Map SCORM lesson_status to xAPI success/completion
            if runtime_data.lesson_status:
                status = runtime_data.lesson_status.lower()
                if status == 'passed':
                    result["success"] = True
                    result["completion"] = True
                elif status == 'failed':
                    result["success"] = False
                    result["completion"] = True
                elif status == 'completed':
                    result["completion"] = True
                elif status == 'incomplete':
                    result["completion"] = False
            
            # Add duration
            if runtime_data.session_time:
                result["duration"] = self._scorm_time_to_iso8601(runtime_data.session_time)
        
        # Override with explicit values if provided
        if score is not None:
            if "score" not in result:
                result["score"] = {}
            result["score"]["raw"] = score
        
        if success is not None:
            result["success"] = success
        
        if completion is not None:
            result["completion"] = completion
        
        if duration:
            result["duration"] = duration
        
        if response:
            result["response"] = response
        
        return result if result else None
    
    def _scorm_time_to_iso8601(self, scorm_time: str) -> str:
        """
        Convert SCORM time format (HH:MM:SS.SS) to ISO 8601 duration.
        
        Args:
            scorm_time: Time string in SCORM format
            
        Returns:
            ISO 8601 duration string
        """
        try:
            # Parse SCORM time format: HH:MM:SS.SS or HHHH:MM:SS.SS
            parts = scorm_time.split(':')
            if len(parts) == 3:
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                total_seconds = hours * 3600 + minutes * 60 + seconds
                
                # Build ISO 8601 duration
                hours_int = int(total_seconds // 3600)
                minutes_int = int((total_seconds % 3600) // 60)
                seconds_int = int(total_seconds % 60)
                
                duration = "PT"
                if hours_int > 0:
                    duration += f"{hours_int}H"
                if minutes_int > 0:
                    duration += f"{minutes_int}M"
                if seconds_int > 0 or (hours_int == 0 and minutes_int == 0):
                    duration += f"{seconds_int}S"
                
                return duration
        except (ValueError, IndexError):
            pass
        
        return "PT0S"
    
    def build_initialized_statement(self, registration: SCORMRegistration,
                                    session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM initialization.
        
        Args:
            registration: SCORM registration
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_INITIALIZED,
                {"en-US": "initialized"}
            ),
            "object": self._build_object(
                registration,
                activity_type=self.ACTIVITY_TYPE_LESSON
            ),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_completed_statement(self, registration: SCORMRegistration,
                                  runtime_data: SCORMRuntimeData = None,
                                  session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM completion.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_COMPLETED,
                {"en-US": "completed"}
            ),
            "object": self._build_object(
                registration,
                activity_type=self.ACTIVITY_TYPE_LESSON
            ),
            "result": self._build_result(runtime_data, completion=True),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_passed_statement(self, registration: SCORMRegistration,
                               runtime_data: SCORMRuntimeData = None,
                               session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM pass.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_PASSED,
                {"en-US": "passed"}
            ),
            "object": self._build_object(
                registration,
                activity_type=self.ACTIVITY_TYPE_ASSESSMENT
            ),
            "result": self._build_result(runtime_data, success=True, completion=True),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_failed_statement(self, registration: SCORMRegistration,
                               runtime_data: SCORMRuntimeData = None,
                               session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM fail.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_FAILED,
                {"en-US": "failed"}
            ),
            "object": self._build_object(
                registration,
                activity_type=self.ACTIVITY_TYPE_ASSESSMENT
            ),
            "result": self._build_result(runtime_data, success=False, completion=True),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_terminated_statement(self, registration: SCORMRegistration,
                                   runtime_data: SCORMRuntimeData = None,
                                   session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM termination.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_TERMINATED,
                {"en-US": "terminated"}
            ),
            "object": self._build_object(registration),
            "result": self._build_result(runtime_data),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_suspended_statement(self, registration: SCORMRegistration,
                                  runtime_data: SCORMRuntimeData = None,
                                  session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM suspend.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_SUSPENDED,
                {"en-US": "suspended"}
            ),
            "object": self._build_object(registration),
            "result": self._build_result(runtime_data),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_resumed_statement(self, registration: SCORMRegistration,
                                session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM resume.
        
        Args:
            registration: SCORM registration
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_RESUMED,
                {"en-US": "resumed"}
            ),
            "object": self._build_object(registration),
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_interaction_statement(self, registration: SCORMRegistration,
                                    interaction_data: Dict[str, Any],
                                    session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for SCORM interaction.
        
        Args:
            registration: SCORM registration
            interaction_data: Dictionary containing interaction details
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        verb = self.VERB_ANSWERED if interaction_data.get('learner_response') else self.VERB_INTERACTED
        
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                verb,
                {"en-US": "answered" if verb == self.VERB_ANSWERED else "interacted"}
            ),
            "object": {
                "objectType": "Activity",
                "id": f"{settings.SITE_URL}/scorm/interaction/{interaction_data.get('interaction_id', 'unknown')}",
                "definition": {
                    "name": {"en-US": interaction_data.get('description', 'Interaction')},
                    "type": self.ACTIVITY_TYPE_INTERACTION,
                    "interactionType": interaction_data.get('type', 'other')
                }
            },
            "result": {
                "success": interaction_data.get('result') == 'correct',
                "response": interaction_data.get('learner_response', '')
            } if interaction_data.get('result') else None,
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def build_progressed_statement(self, registration: SCORMRegistration,
                                 progress_percent: float,
                                 session: SCORMSession = None) -> Dict[str, Any]:
        """
        Build an xAPI statement for progress update.
        
        Args:
            registration: SCORM registration
            progress_percent: Progress percentage (0-100)
            session: Optional SCORM session
            
        Returns:
            xAPI statement dictionary
        """
        return {
            "id": self._generate_statement_id(),
            "actor": self._build_actor(registration),
            "verb": self._build_verb(
                self.VERB_PROGRESSED,
                {"en-US": "progressed"}
            ),
            "object": self._build_object(registration),
            "result": {
                "extensions": {
                    "http://id.tincanapi.com/extension/progress": progress_percent / 100
                }
            },
            "context": self._build_context(registration, session),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


class xAPILRSClient:
    """
    Client for sending xAPI statements to a Learning Record Store (LRS).
    
    This is a stub implementation for Phase 1. Full LRS integration
    will be implemented in Phase 2.
    """
    
    def __init__(self):
        """Initialize the LRS client."""
        self.endpoint = getattr(settings, 'XAPI_LRS_ENDPOINT', None)
        self.auth = None
        
        if self.endpoint:
            key = getattr(settings, 'XAPI_LRS_KEY', None)
            secret = getattr(settings, 'XAPI_LRS_SECRET', None)
            if key and secret:
                import base64
                credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()
                self.auth = f"Basic {credentials}"
    
    def is_configured(self) -> bool:
        """Check if LRS is configured."""
        return self.endpoint is not None and self.auth is not None
    
    def send_statement(self, statement: Dict[str, Any]) -> bool:
        """
        Send a single xAPI statement to the LRS.
        
        Args:
            statement: xAPI statement dictionary
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured():
            # LRS not configured, log and return success (no-op)
            return True
        
        # TODO: Implement actual LRS POST request in Phase 2
        # For now, just log the statement
        print(f"[xAPI] Would send statement to LRS: {json.dumps(statement, indent=2)}")
        return True
    
    def send_statements(self, statements: List[Dict[str, Any]]) -> bool:
        """
        Send multiple xAPI statements to the LRS.
        
        Args:
            statements: List of xAPI statement dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured():
            return True
        
        # TODO: Implement batch POST in Phase 2
        for statement in statements:
            self.send_statement(statement)
        return True


class xAPIService:
    """
    Service class for xAPI operations.
    Provides high-level methods for converting SCORM events to xAPI statements.
    """
    
    def __init__(self):
        """Initialize the xAPI service."""
        self.builder = xAPIStatementBuilder()
        self.lrs_client = xAPILRSClient()
    
    def record_initialized(self, registration: SCORMRegistration,
                           session: SCORMSession = None) -> Optional[str]:
        """
        Record SCORM initialization as xAPI statement.
        
        Args:
            registration: SCORM registration
            session: Optional SCORM session
            
        Returns:
            Statement ID if successful, None otherwise
        """
        statement = self.builder.build_initialized_statement(registration, session)
        
        if self.lrs_client.send_statement(statement):
            return statement.get('id')
        return None
    
    def record_completed(self, registration: SCORMRegistration,
                       runtime_data: SCORMRuntimeData = None,
                       session: SCORMSession = None) -> Optional[str]:
        """
        Record SCORM completion as xAPI statement.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            Statement ID if successful, None otherwise
        """
        statement = self.builder.build_completed_statement(registration, runtime_data, session)
        
        if self.lrs_client.send_statement(statement):
            return statement.get('id')
        return None
    
    def record_passed(self, registration: SCORMRegistration,
                      runtime_data: SCORMRuntimeData = None,
                      session: SCORMSession = None) -> Optional[str]:
        """
        Record SCORM pass as xAPI statement.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            Statement ID if successful, None otherwise
        """
        statement = self.builder.build_passed_statement(registration, runtime_data, session)
        
        if self.lrs_client.send_statement(statement):
            return statement.get('id')
        return None
    
    def record_failed(self, registration: SCORMRegistration,
                    runtime_data: SCORMRuntimeData = None,
                    session: SCORMSession = None) -> Optional[str]:
        """
        Record SCORM fail as xAPI statement.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            Statement ID if successful, None otherwise
        """
        statement = self.builder.build_failed_statement(registration, runtime_data, session)
        
        if self.lrs_client.send_statement(statement):
            return statement.get('id')
        return None
    
    def record_terminated(self, registration: SCORMRegistration,
                         runtime_data: SCORMRuntimeData = None,
                         session: SCORMSession = None) -> Optional[str]:
        """
        Record SCORM termination as xAPI statement.
        
        Args:
            registration: SCORM registration
            runtime_data: Optional SCORM runtime data
            session: Optional SCORM session
            
        Returns:
            Statement ID if successful, None otherwise
        """
        statement = self.builder.build_terminated_statement(registration, runtime_data, session)
        
        if self.lrs_client.send_statement(statement):
            return statement.get('id')
        return None
    
    def convert_scorm_to_xapi(self, registration: SCORMRegistration,
                              cmi_data: Dict[str, Any],
                              session: SCORMSession = None) -> List[Dict[str, Any]]:
        """
        Convert SCORM CMI data to xAPI statements.
        
        Args:
            registration: SCORM registration
            cmi_data: SCORM CMI data dictionary
            session: Optional SCORM session
            
        Returns:
            List of xAPI statements
        """
        statements = []
        
        # Check for completion status changes
        lesson_status = cmi_data.get('core', {}).get('lesson_status', '').lower()
        
        if lesson_status == 'completed':
            statements.append(self.builder.build_completed_statement(registration, session=session))
        elif lesson_status == 'passed':
            statements.append(self.builder.build_passed_statement(registration, session=session))
        elif lesson_status == 'failed':
            statements.append(self.builder.build_failed_statement(registration, session=session))
        
        # Check for exit status
        exit_value = cmi_data.get('core', {}).get('exit', '').lower()
        if exit_value == 'suspend':
            statements.append(self.builder.build_suspended_statement(registration, session=session))
        
        return statements
