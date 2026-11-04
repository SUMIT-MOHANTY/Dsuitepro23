"""
Core Views for Enterprise LMS
Provides healthcheck and system status endpoints.
"""

from django.db import connection
from django.db.utils import OperationalError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiResponse


class HealthCheckView(APIView):
    """
    Health check endpoint for monitoring and load balancer health checks.
    
    Returns system status including database connectivity.
    Used by monitoring tools and deployment health checks.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        summary="Health Check",
        description="Returns the current health status of the API and database connectivity.",
        responses={
            200: OpenApiResponse(
                description="Service is healthy",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "ok"},
                        "database": {"type": "string", "example": "connected"},
                    },
                },
            ),
            503: OpenApiResponse(
                description="Service is unhealthy",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "error"},
                        "database": {"type": "string", "example": "disconnected"},
                    },
                },
            ),
        },
        tags=["system"],
    )
    def get(self, request):
        """
        GET /api/health/
        
        Returns health status with database connectivity check.
        """
        health_status = {
            "status": "ok",
            "database": "connected",
        }
        status_code = status.HTTP_200_OK

        # Check database connectivity
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError:
            health_status["status"] = "error"
            health_status["database"] = "disconnected"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(health_status, status=status_code)


class SystemInfoView(APIView):
    """
    System information endpoint.
    
    Returns basic information about the API version and environment.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        summary="System Information",
        description="Returns API version and environment information.",
        responses={
            200: OpenApiResponse(
                description="System information",
                response={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "environment": {"type": "string"},
                    },
                },
            ),
        },
        tags=["system"],
    )
    def get(self, request):
        """
        GET /api/info/
        
        Returns system information.
        """
        from django.conf import settings
        
        info = {
            "name": "Enterprise LMS API",
            "version": "1.0.0",
            "environment": "development" if settings.DEBUG else "production",
        }
        
        return Response(info)
