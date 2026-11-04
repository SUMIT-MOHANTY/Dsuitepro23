"""
SCORM Views for Enterprise LMS
Provides API endpoints for SCORM 1.2 runtime, launch, and SCORM Cloud integration.
"""

import json
import uuid
from datetime import datetime

from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import status, generics, views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import BaseModel
from apps.courses.models import ContentItem
from apps.users.models import User

from .models import (
    SCORMRegistration,
    SCORMSession,
    SCORMRuntimeData,
    SCORMCloudSyncLog,
)
from .services import (
    SCORMRuntimeService,
    SCORMLaunchService,
    SCORMCloudService,
    SCORMDataTrackingService,
)


class LaunchView(APIView):
    """
    View for launching SCORM content.
    Creates a registration and returns HTML wrapper with API bridge.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        POST /api/v1/scorm/launch/
        
        Request Body:
            - content_item_id: UUID of the SCORM content item
            
        Returns:
            - HTML wrapper with embedded SCORM API bridge
        """
        content_item_id = request.data.get('content_item_id')
        
        if not content_item_id:
            return Response(
                {'error': 'content_item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            content_item = ContentItem.objects.get(
                id=content_item_id,
                content_type='scorm'
            )
        except ContentItem.DoesNotExist:
            return Response(
                {'error': 'SCORM content item not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create or get registration
        launch_service = SCORMLaunchService()
        registration = launch_service.create_registration(
            user=request.user,
            content_item=content_item
        )
        
        # Create session
        session = launch_service.create_session(
            registration=registration,
            request=request
        )
        
        # Generate launch HTML
        html_content = launch_service.generate_launch_html(
            registration=registration,
            session=session,
            content_item=content_item
        )
        
        return HttpResponse(html_content, content_type='text/html')


class LaunchDetailView(APIView):
    """
    View for launching SCORM content with registration ID.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, registration_id):
        """
        GET /api/v1/scorm/launch/{registration_id}/
        
        Returns HTML wrapper for existing registration.
        """
        try:
            registration = SCORMRegistration.objects.get(
                registration_id=registration_id,
                user=request.user
            )
        except SCORMRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        launch_service = SCORMLaunchService()
        
        # Create new session
        session = launch_service.create_session(
            registration=registration,
            request=request
        )
        
        # Generate launch HTML
        html_content = launch_service.generate_launch_html(
            registration=registration,
            session=session,
            content_item=registration.content_item
        )
        
        return HttpResponse(html_content, content_type='text/html')


@method_decorator(csrf_exempt, name='dispatch')
class RuntimeAPIView(APIView):
    """
    View for SCORM 1.2 Runtime API.
    Implements LMSInitialize, LMSFinish, LMSGetValue, LMSSetValue, LMSCommit.
    """
    permission_classes = [IsAuthenticated]
    
    # SCORM 1.2 Error Codes
    ERROR_NO_ERROR = "0"
    ERROR_GENERAL_EXCEPTION = "101"
    ERROR_INVALID_ARGUMENT = "201"
    ERROR_ELEMENT_CANNOT_HAVE_CHILDREN = "202"
    ERROR_ELEMENT_NOT_ARRAY = "203"
    ERROR_NOT_INITIALIZED = "301"
    ERROR_ALREADY_INITIALIZED = "302"
    ERROR_API_NOT_IMPLEMENTED = "401"
    
    def __init__(self):
        super().__init__()
        self.runtime_service = SCORMRuntimeService()
    
    def _get_session_from_request(self, request):
        """Extract session from request headers or body."""
        session_id = request.headers.get('X-SCORM-Session') or request.data.get('session_id')
        if session_id:
            try:
                return SCORMSession.objects.get(session_id=session_id, is_active=True)
            except SCORMSession.DoesNotExist:
                return None
        return None
    
    def post(self, request, action):
        """
        POST /api/v1/scorm/runtime/{action}/
        
        Actions:
            - init: LMSInitialize
            - finish: LMSFinish
            - getvalue: LMSGetValue
            - setvalue: LMSSetValue
            - commit: LMSCommit
            - getlasterror: LMSGetLastError
            - geterrorstring: LMSGetErrorString
            - getdiagnostic: LMSGetDiagnostic
        """
        session = self._get_session_from_request(request)
        
        if action == 'init':
            return self._handle_initialize(request, session)
        elif action == 'finish':
            return self._handle_finish(request, session)
        elif action == 'getvalue':
            return self._handle_getvalue(request, session)
        elif action == 'setvalue':
            return self._handle_setvalue(request, session)
        elif action == 'commit':
            return self._handle_commit(request, session)
        elif action == 'getlasterror':
            return self._handle_getlasterror(request, session)
        elif action == 'geterrorstring':
            return self._handle_geterrorstring(request)
        elif action == 'getdiagnostic':
            return self._handle_getdiagnostic(request)
        else:
            return Response(
                {'error': 'Unknown action'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _handle_initialize(self, request, session):
        """Handle LMSInitialize call."""
        if not session:
            return Response({
                'result': 'false',
                'errorCode': self.ERROR_NOT_INITIALIZED
            })
        
        result = self.runtime_service.initialize(session)
        
        return Response({
            'result': 'true' if result else 'false',
            'errorCode': self.ERROR_NO_ERROR if result else self.ERROR_GENERAL_EXCEPTION
        })
    
    def _handle_finish(self, request, session):
        """Handle LMSFinish call."""
        if not session:
            return Response({
                'result': 'false',
                'errorCode': self.ERROR_NOT_INITIALIZED
            })
        
        result = self.runtime_service.finish(session)
        
        return Response({
            'result': 'true' if result else 'false',
            'errorCode': self.ERROR_NO_ERROR if result else self.ERROR_GENERAL_EXCEPTION
        })
    
    def _handle_getvalue(self, request, session):
        """Handle LMSGetValue call."""
        element = request.data.get('element', '')
        
        if not session:
            return Response({
                'value': '',
                'errorCode': self.ERROR_NOT_INITIALIZED
            })
        
        if not element:
            return Response({
                'value': '',
                'errorCode': self.ERROR_INVALID_ARGUMENT
            })
        
        value, error_code = self.runtime_service.get_value(session, element)
        
        return Response({
            'value': value,
            'errorCode': error_code
        })
    
    def _handle_setvalue(self, request, session):
        """Handle LMSSetValue call."""
        element = request.data.get('element', '')
        value = request.data.get('value', '')
        
        if not session:
            return Response({
                'result': 'false',
                'errorCode': self.ERROR_NOT_INITIALIZED
            })
        
        if not element:
            return Response({
                'result': 'false',
                'errorCode': self.ERROR_INVALID_ARGUMENT
            })
        
        result, error_code = self.runtime_service.set_value(session, element, value)
        
        return Response({
            'result': 'true' if result else 'false',
            'errorCode': error_code
        })
    
    def _handle_commit(self, request, session):
        """Handle LMSCommit call."""
        if not session:
            return Response({
                'result': 'false',
                'errorCode': self.ERROR_NOT_INITIALIZED
            })
        
        result = self.runtime_service.commit(session)
        
        return Response({
            'result': 'true' if result else 'false',
            'errorCode': self.ERROR_NO_ERROR if result else self.ERROR_GENERAL_EXCEPTION
        })
    
    def _handle_getlasterror(self, request, session):
        """Handle LMSGetLastError call."""
        if not session:
            return Response({'errorCode': self.ERROR_NOT_INITIALIZED})
        
        error_code = self.runtime_service.get_last_error(session)
        return Response({'errorCode': error_code})
    
    def _handle_geterrorstring(self, request):
        """Handle LMSGetErrorString call."""
        error_code = request.data.get('errorCode', self.ERROR_GENERAL_EXCEPTION)
        error_string = self.runtime_service.get_error_string(error_code)
        return Response({'errorString': error_string})
    
    def _handle_getdiagnostic(self, request):
        """Handle LMSGetDiagnostic call."""
        error_code = request.data.get('errorCode', self.ERROR_GENERAL_EXCEPTION)
        diagnostic = self.runtime_service.get_diagnostic(error_code)
        return Response({'diagnostic': diagnostic})


class SCORMCloudWebhookView(APIView):
    """
    View for handling SCORM Cloud webhook callbacks.
    Receives progress updates from SCORM Cloud.
    """
    permission_classes = []  # Webhooks typically use signature verification
    
    def post(self, request):
        """
        POST /webhooks/scorm/
        
        Handles SCORM Cloud progress sync webhooks.
        """
        # Verify webhook signature if configured
        # TODO: Implement signature verification
        
        payload = request.data
        
        # Extract registration ID from webhook
        scorm_cloud_reg_id = payload.get('registrationId')
        
        if not scorm_cloud_reg_id:
            return Response(
                {'error': 'registrationId is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            registration = SCORMRegistration.objects.get(
                scorm_cloud_registration_id=scorm_cloud_reg_id
            )
        except SCORMRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Process the webhook data
        cloud_service = SCORMCloudService()
        
        try:
            cloud_service.handle_progress_webhook(registration, payload)
            return Response({'status': 'success'})
        except Exception as e:
            # Log the error
            SCORMCloudSyncLog.objects.create(
                registration=registration,
                sync_type='webhook',
                status='failed',
                error_message=str(e),
                scorm_cloud_response=json.dumps(payload)
            )
            return Response(
                {'error': 'Failed to process webhook'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegistrationListView(APIView):
    """
    View for listing user's SCORM registrations.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/v1/scorm/registrations/
        
        Returns list of SCORM registrations for the current user.
        """
        registrations = SCORMRegistration.objects.filter(
            user=request.user
        ).select_related('content_item', 'content_item__lesson')
        
        data = []
        for reg in registrations:
            data.append({
                'id': str(reg.id),
                'registration_id': reg.registration_id,
                'content_item': {
                    'id': str(reg.content_item.id),
                    'title': reg.content_item.title,
                },
                'status': reg.status,
                'completion_status': reg.completion_status,
                'score': str(reg.score) if reg.score else None,
                'total_time': reg.total_time,
                'last_accessed_at': reg.last_accessed_at.isoformat() if reg.last_accessed_at else None,
                'created_at': reg.created_at.isoformat(),
            })
        
        return Response({'results': data})


class RegistrationDetailView(APIView):
    """
    View for retrieving SCORM registration details.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, registration_id):
        """
        GET /api/v1/scorm/registrations/{registration_id}/
        
        Returns detailed information about a SCORM registration.
        """
        try:
            registration = SCORMRegistration.objects.get(
                registration_id=registration_id,
                user=request.user
            )
        except SCORMRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get runtime data
        runtime_data = None
        try:
            rt = SCORMRuntimeData.objects.get(registration=registration)
            runtime_data = {
                'lesson_location': rt.lesson_location,
                'lesson_status': rt.lesson_status,
                'score_raw': str(rt.score_raw) if rt.score_raw else None,
                'score_max': str(rt.score_max) if rt.score_max else None,
                'score_min': str(rt.score_min) if rt.score_min else None,
                'session_time': rt.session_time,
                'entry': rt.entry,
                'mode': rt.mode,
            }
        except SCORMRuntimeData.DoesNotExist:
            pass
        
        data = {
            'id': str(registration.id),
            'registration_id': registration.registration_id,
            'content_item': {
                'id': str(registration.content_item.id),
                'title': registration.content_item.title,
            },
            'status': registration.status,
            'completion_status': registration.completion_status,
            'success_status': registration.success_status,
            'score': str(registration.score) if registration.score else None,
            'score_scaled': str(registration.score_scaled) if registration.score_scaled else None,
            'total_time': registration.total_time,
            'suspend_data': registration.suspend_data,
            'last_accessed_at': registration.last_accessed_at.isoformat() if registration.last_accessed_at else None,
            'created_at': registration.created_at.isoformat(),
            'updated_at': registration.updated_at.isoformat(),
            'runtime_data': runtime_data,
        }
        
        return Response(data)


class RegistrationProgressView(APIView):
    """
    View for updating/retrieving SCORM registration progress.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, registration_id):
        """
        GET /api/v1/scorm/registrations/{registration_id}/progress/
        
        Returns progress data for a SCORM registration.
        """
        try:
            registration = SCORMRegistration.objects.get(
                registration_id=registration_id,
                user=request.user
            )
        except SCORMRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        tracking_service = SCORMDataTrackingService()
        progress = tracking_service.get_progress_summary(registration)
        
        return Response(progress)
    
    def post(self, request, registration_id):
        """
        POST /api/v1/scorm/registrations/{registration_id}/progress/
        
        Updates progress data for a SCORM registration.
        """
        try:
            registration = SCORMRegistration.objects.get(
                registration_id=registration_id,
                user=request.user
            )
        except SCORMRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        tracking_service = SCORMDataTrackingService()
        
        # Update from request data
        cmi_data = request.data.get('cmi', {})
        
        try:
            tracking_service.update_from_cmi_data(registration, cmi_data)
            return Response({'status': 'success'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SyncCloudProgressView(APIView):
    """
    View for manually triggering SCORM Cloud progress sync.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, registration_id):
        """
        POST /api/v1/scorm/registrations/{registration_id}/sync/
        
        Triggers a manual sync with SCORM Cloud.
        """
        try:
            registration = SCORMRegistration.objects.get(
                registration_id=registration_id,
                user=request.user
            )
        except SCORMRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        cloud_service = SCORMCloudService()
        
        try:
            result = cloud_service.sync_progress_from_cloud(registration)
            return Response({
                'status': 'success',
                'synced': result
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Legacy function-based views for backward compatibility

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def scorm_launch(request):
    """
    Legacy launch endpoint.
    """
    view = LaunchView()
    view.request = request
    view.kwargs = {}
    return view.post(request)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def scorm_runtime_config(request):
    """
    Get SCORM runtime configuration.
    """
    config = {
        'api_version': '1.2',
        'api_implementation': 'LMS',
        'error_codes': {
            '0': 'No error',
            '101': 'General exception',
            '201': 'Invalid argument error',
            '202': 'Element cannot have children',
            '203': 'Element is not an array',
            '301': 'Not initialized',
            '302': 'Already initialized',
            '401': 'API not implemented',
        }
    }
    return Response(config)
