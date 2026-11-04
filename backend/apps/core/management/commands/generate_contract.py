"""
Management command to generate OpenAPI 3.0 API contract for the Enterprise LMS.

This command generates a comprehensive API contract file at .agent/contracts/api_contract.json
that serves as the authoritative contract between backend and frontend teams.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    """
    Generate OpenAPI 3.0 API contract for the Enterprise LMS.
    
    Usage:
        python manage.py generate_contract
        python manage.py generate_contract --output /path/to/contract.json
    """
    
    help = 'Generate OpenAPI 3.0 API contract for the Enterprise LMS'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='.agent/contracts/api_contract.json',
            help='Output path for the API contract file'
        )
        parser.add_argument(
            '--indent',
            type=int,
            default=2,
            help='JSON indentation level (default: 2)'
        )
    
    def handle(self, *args, **options):
        output_path = options['output']
        indent = options['indent']
        
        self.stdout.write(self.style.NOTICE('Generating API contract...'))
        
        # Build the OpenAPI contract
        contract = self._build_contract()
        
        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the contract file
        with open(output_file, 'w') as f:
            json.dump(contract, f, indent=indent, ensure_ascii=False)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully generated API contract at {output_path}')
        )
        
        # Print summary
        self._print_summary(contract)
    
    def _build_contract(self) -> dict:
        """
        Build the complete OpenAPI 3.0 contract.
        
        Returns:
            dict: OpenAPI 3.0 specification
        """
        return {
            'openapi': '3.0.3',
            'info': self._build_info(),
            'servers': self._build_servers(),
            'security': self._build_security(),
            'tags': self._build_tags(),
            'paths': self._build_paths(),
            'components': self._build_components(),
        }
    
    def _build_info(self) -> dict:
        """Build the OpenAPI info section."""
        return {
            'title': 'Enterprise LMS API',
            'description': (
                'A comprehensive Learning Management System API providing endpoints for '
                'user management, course content, enrollment tracking, assessments, '
                'certificates, SCORM runtime, forums, notifications, and analytics.'
            ),
            'version': '1.0.0',
            'contact': {
                'name': 'Enterprise LMS Team',
                'email': 'api-support@lms-enterprise.com'
            },
            'license': {
                'name': 'Proprietary',
                'url': 'https://lms-enterprise.com/license'
            },
            'x-generated-at': datetime.utcnow().isoformat() + 'Z',
        }
    
    def _build_servers(self) -> list:
        """Build the OpenAPI servers section."""
        return [
            {
                'url': 'http://localhost:8000/api/v1',
                'description': 'Local development server'
            },
            {
                'url': 'https://api.lms-enterprise.com/api/v1',
                'description': 'Production server'
            },
            {
                'url': 'https://staging-api.lms-enterprise.com/api/v1',
                'description': 'Staging server'
            }
        ]
    
    def _build_security(self) -> list:
        """Build the OpenAPI security section."""
        return [
            {
                'bearerAuth': []
            }
        ]
    
    def _build_tags(self) -> list:
        """Build the OpenAPI tags section."""
        return [
            {
                'name': 'auth',
                'description': 'Authentication endpoints including login, register, logout, token refresh, and password reset'
            },
            {
                'name': 'users',
                'description': 'User management endpoints for profiles, avatars, and user-related data'
            },
            {
                'name': 'courses',
                'description': 'Course content management including catalog, modules, lessons, and content items'
            },
            {
                'name': 'enrollment',
                'description': 'Enrollment and progress tracking including learning paths and completion status'
            },
            {
                'name': 'assessment',
                'description': 'Quizzes, assignments, submissions, and grading endpoints'
            },
            {
                'name': 'certificates',
                'description': 'Certificate generation, download, and verification'
            },
            {
                'name': 'scorm',
                'description': 'SCORM 1.2/xAPI runtime for launching and tracking SCORM content'
            },
            {
                'name': 'forum',
                'description': 'Discussion forums, threads, posts, and moderation'
            },
            {
                'name': 'notifications',
                'description': 'Email and in-app notifications with delivery tracking'
            },
            {
                'name': 'analytics',
                'description': 'Reporting, dashboards, and audit logging'
            },
            {
                'name': 'system',
                'description': 'System health checks and information endpoints'
            }
        ]
    
    def _build_paths(self) -> dict:
        """Build the OpenAPI paths section with all endpoints."""
        paths = {}
        
        # System endpoints (already implemented)
        paths['/health/'] = self._build_health_endpoint()
        paths['/info/'] = self._build_info_endpoint()
        
        # Auth endpoints
        paths.update(self._build_auth_paths())
        
        # User endpoints
        paths.update(self._build_user_paths())
        
        # Course endpoints
        paths.update(self._build_course_paths())
        
        # Enrollment endpoints
        paths.update(self._build_enrollment_paths())
        
        # Assessment endpoints
        paths.update(self._build_assessment_paths())
        
        # Certificate endpoints
        paths.update(self._build_certificate_paths())
        
        # SCORM endpoints
        paths.update(self._build_scorm_paths())
        
        # Forum endpoints
        paths.update(self._build_forum_paths())
        
        # Notification endpoints
        paths.update(self._build_notification_paths())
        
        # Analytics endpoints
        paths.update(self._build_analytics_paths())
        
        return paths
    
    def _build_health_endpoint(self) -> dict:
        """Build the health check endpoint."""
        return {
            'get': {
                'summary': 'Health Check',
                'description': 'Returns the current health status of the API and database connectivity.',
                'operationId': 'healthCheck',
                'tags': ['system'],
                'security': [],
                'responses': {
                    '200': {
                        'description': 'Service is healthy',
                        'content': {
                            'application/json': {
                                'schema': {
                                    'type': 'object',
                                    'properties': {
                                        'status': {'type': 'string', 'example': 'ok'},
                                        'database': {'type': 'string', 'example': 'connected'}
                                    }
                                }
                            }
                        }
                    },
                    '503': {
                        'description': 'Service is unhealthy',
                        'content': {
                            'application/json': {
                                'schema': {
                                    'type': 'object',
                                    'properties': {
                                        'status': {'type': 'string', 'example': 'error'},
                                        'database': {'type': 'string', 'example': 'disconnected'}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _build_info_endpoint(self) -> dict:
        """Build the system info endpoint."""
        return {
            'get': {
                'summary': 'System Information',
                'description': 'Returns API version and environment information.',
                'operationId': 'systemInfo',
                'tags': ['system'],
                'security': [],
                'responses': {
                    '200': {
                        'description': 'System information',
                        'content': {
                            'application/json': {
                                'schema': {
                                    'type': 'object',
                                    'properties': {
                                        'name': {'type': 'string', 'example': 'Enterprise LMS API'},
                                        'version': {'type': 'string', 'example': '1.0.0'},
                                        'environment': {'type': 'string', 'example': 'development'}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _build_auth_paths(self) -> dict:
        """Build authentication-related paths."""
        return {
            '/auth/register/': {
                'post': {
                    'summary': 'User Registration',
                    'description': 'Register a new user account',
                    'operationId': 'registerUser',
                    'tags': ['auth'],
                    'security': [],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/UserRegistrationRequest'}
                            }
                        }
                    },
                    'responses': {
                        '201': {'description': 'User registered successfully'},
                        '400': {'description': 'Validation error'}
                    }
                }
            },
            '/auth/login/': {
                'post': {
                    'summary': 'User Login',
                    'description': 'Authenticate user and return JWT tokens',
                    'operationId': 'loginUser',
                    'tags': ['auth'],
                    'security': [],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/LoginRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Login successful'},
                        '401': {'description': 'Invalid credentials'}
                    }
                }
            },
            '/auth/refresh/': {
                'post': {
                    'summary': 'Token Refresh',
                    'description': 'Refresh access token using refresh token',
                    'operationId': 'refreshToken',
                    'tags': ['auth'],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/TokenRefreshRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Token refreshed successfully'},
                        '401': {'description': 'Invalid refresh token'}
                    }
                }
            },
            '/auth/logout/': {
                'post': {
                    'summary': 'User Logout',
                    'description': 'Logout user and blacklist token',
                    'operationId': 'logoutUser',
                    'tags': ['auth'],
                    'responses': {
                        '200': {'description': 'Logout successful'}
                    }
                }
            },
            '/auth/password-reset-request/': {
                'post': {
                    'summary': 'Request Password Reset',
                    'description': 'Send password reset email',
                    'operationId': 'requestPasswordReset',
                    'tags': ['auth'],
                    'security': [],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/PasswordResetRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Password reset email sent'}
                    }
                }
            },
            '/auth/password-reset-confirm/': {
                'post': {
                    'summary': 'Confirm Password Reset',
                    'description': 'Reset password with token',
                    'operationId': 'confirmPasswordReset',
                    'tags': ['auth'],
                    'security': [],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/PasswordResetConfirmRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Password reset successful'}
                    }
                }
            },
            '/auth/verify-email/': {
                'post': {
                    'summary': 'Verify Email',
                    'description': 'Verify user email address',
                    'operationId': 'verifyEmail',
                    'tags': ['auth'],
                    'security': [],
                    'responses': {
                        '200': {'description': 'Email verified successfully'}
                    }
                }
            },
            '/auth/resend-verification/': {
                'post': {
                    'summary': 'Resend Verification Email',
                    'description': 'Resend email verification link',
                    'operationId': 'resendVerification',
                    'tags': ['auth'],
                    'responses': {
                        '200': {'description': 'Verification email sent'}
                    }
                }
            },
            '/auth/oauth/providers/': {
                'get': {
                    'summary': 'List OAuth Providers',
                    'description': 'Get available OAuth providers',
                    'operationId': 'listOAuthProviders',
                    'tags': ['auth'],
                    'security': [],
                    'responses': {
                        '200': {'description': 'List of OAuth providers'}
                    }
                }
            },
            '/auth/oauth/callback/': {
                'post': {
                    'summary': 'OAuth Callback',
                    'description': 'Handle OAuth provider callback',
                    'operationId': 'oauthCallback',
                    'tags': ['auth'],
                    'security': [],
                    'responses': {
                        '200': {'description': 'OAuth authentication successful'}
                    }
                }
            }
        }
    
    def _build_user_paths(self) -> dict:
        """Build user-related paths."""
        return {
            '/users/me/': {
                'get': {
                    'summary': 'Get Current User',
                    'description': 'Get current user profile',
                    'operationId': 'getCurrentUser',
                    'tags': ['users'],
                    'responses': {
                        '200': {'description': 'User profile retrieved'}
                    }
                },
                'patch': {
                    'summary': 'Update Current User',
                    'description': 'Update current user profile',
                    'operationId': 'updateCurrentUser',
                    'tags': ['users'],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/UserUpdateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'User profile updated'}
                    }
                }
            },
            '/users/me/avatar/': {
                'post': {
                    'summary': 'Upload Avatar',
                    'description': 'Upload user avatar image',
                    'operationId': 'uploadAvatar',
                    'tags': ['users'],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'multipart/form-data': {
                                'schema': {'$ref': '#/components/schemas/AvatarUploadRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Avatar uploaded successfully'}
                    }
                }
            },
            '/users/me/enrollments/': {
                'get': {
                    'summary': 'Get User Enrollments',
                    'description': 'Get current user enrollments',
                    'operationId': 'getUserEnrollments',
                    'tags': ['users'],
                    'responses': {
                        '200': {'description': 'User enrollments retrieved'}
                    }
                }
            },
            '/users/me/progress/': {
                'get': {
                    'summary': 'Get User Progress',
                    'description': 'Get current user learning progress',
                    'operationId': 'getUserProgress',
                    'tags': ['users'],
                    'responses': {
                        '200': {'description': 'User progress retrieved'}
                    }
                }
            },
            '/users/me/certificates/': {
                'get': {
                    'summary': 'Get User Certificates',
                    'description': 'Get current user certificates',
                    'operationId': 'getUserCertificates',
                    'tags': ['users'],
                    'responses': {
                        '200': {'description': 'User certificates retrieved'}
                    }
                }
            },
            '/users/me/notifications/': {
                'get': {
                    'summary': 'Get User Notifications',
                    'description': 'Get current user notifications',
                    'operationId': 'getUserNotifications',
                    'tags': ['users'],
                    'responses': {
                        '200': {'description': 'User notifications retrieved'}
                    }
                }
            },
            '/users/me/notifications/{id}/read/': {
                'patch': {
                    'summary': 'Mark Notification Read',
                    'description': 'Mark a notification as read',
                    'operationId': 'markNotificationRead',
                    'tags': ['users'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Notification marked as read'}
                    }
                }
            },
            '/users/me/notifications/read-all/': {
                'post': {
                    'summary': 'Mark All Notifications Read',
                    'description': 'Mark all notifications as read',
                    'operationId': 'markAllNotificationsRead',
                    'tags': ['users'],
                    'responses': {
                        '200': {'description': 'All notifications marked as read'}
                    }
                }
            },
            '/users/me/sessions/{id}/': {
                'delete': {
                    'summary': 'Delete Session',
                    'description': 'Delete a user session',
                    'operationId': 'deleteSession',
                    'tags': ['users'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '204': {'description': 'Session deleted'}
                    }
                }
            }
        }
    
    def _build_course_paths(self) -> dict:
        """Build course-related paths."""
        return {
            '/courses/': {
                'get': {
                    'summary': 'List Courses',
                    'description': 'Get paginated list of courses',
                    'operationId': 'listCourses',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'search', 'in': 'query', 'schema': {'type': 'string'}},
                        {'name': 'category', 'in': 'query', 'schema': {'type': 'string'}},
                        {'name': 'instructor', 'in': 'query', 'schema': {'type': 'string', 'format': 'uuid'}},
                        {'name': 'is_published', 'in': 'query', 'schema': {'type': 'boolean'}},
                        {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
                        {'name': 'offset', 'in': 'query', 'schema': {'type': 'integer', 'default': 0}}
                    ],
                    'responses': {
                        '200': {'description': 'List of courses'}
                    }
                },
                'post': {
                    'summary': 'Create Course',
                    'description': 'Create a new course (instructor/admin only)',
                    'operationId': 'createCourse',
                    'tags': ['courses'],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/CourseCreateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '201': {'description': 'Course created'}
                    }
                }
            },
            '/courses/{id}/': {
                'get': {
                    'summary': 'Get Course',
                    'description': 'Get course details',
                    'operationId': 'getCourse',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Course details'}
                    }
                },
                'patch': {
                    'summary': 'Update Course',
                    'description': 'Update course details',
                    'operationId': 'updateCourse',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/CourseUpdateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Course updated'}
                    }
                },
                'delete': {
                    'summary': 'Delete Course',
                    'description': 'Delete a course',
                    'operationId': 'deleteCourse',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '204': {'description': 'Course deleted'}
                    }
                }
            },
            '/courses/{id}/catalog/': {
                'get': {
                    'summary': 'Get Course Catalog',
                    'description': 'Get course catalog with modules and lessons',
                    'operationId': 'getCourseCatalog',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Course catalog'}
                    }
                }
            },
            '/courses/{id}/enroll/': {
                'post': {
                    'summary': 'Enroll in Course',
                    'description': 'Enroll current user in a course',
                    'operationId': 'enrollInCourse',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '201': {'description': 'Enrolled successfully'}
                    }
                }
            },
            '/courses/{id}/modules/': {
                'get': {
                    'summary': 'List Course Modules',
                    'description': 'Get modules for a course',
                    'operationId': 'listCourseModules',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'List of modules'}
                    }
                },
                'post': {
                    'summary': 'Create Module',
                    'description': 'Create a module for a course',
                    'operationId': 'createModule',
                    'tags': ['courses'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ModuleCreateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '201': {'description': 'Module created'}
                    }
                }
            }
        }
    
    def _build_enrollment_paths(self) -> dict:
        """Build enrollment-related paths."""
        return {
            '/enrollments/': {
                'get': {
                    'summary': 'List Enrollments',
                    'description': 'Get user enrollments',
                    'operationId': 'listEnrollments',
                    'tags': ['enrollment'],
                    'responses': {
                        '200': {'description': 'List of enrollments'}
                    }
                }
            },
            '/enrollments/{id}/': {
                'get': {
                    'summary': 'Get Enrollment',
                    'description': 'Get enrollment details',
                    'operationId': 'getEnrollment',
                    'tags': ['enrollment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Enrollment details'}
                    }
                }
            },
            '/enrollments/{id}/progress/': {
                'get': {
                    'summary': 'Get Enrollment Progress',
                    'description': 'Get enrollment progress',
                    'operationId': 'getEnrollmentProgress',
                    'tags': ['enrollment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Enrollment progress'}
                    }
                },
                'post': {
                    'summary': 'Update Progress',
                    'description': 'Update enrollment progress',
                    'operationId': 'updateProgress',
                    'tags': ['enrollment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ProgressUpdateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Progress updated'}
                    }
                }
            },
            '/learning-paths/': {
                'get': {
                    'summary': 'List Learning Paths',
                    'description': 'Get available learning paths',
                    'operationId': 'listLearningPaths',
                    'tags': ['enrollment'],
                    'responses': {
                        '200': {'description': 'List of learning paths'}
                    }
                }
            },
            '/learning-paths/{id}/': {
                'get': {
                    'summary': 'Get Learning Path',
                    'description': 'Get learning path details',
                    'operationId': 'getLearningPath',
                    'tags': ['enrollment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Learning path details'}
                    }
                }
            }
        }
    
    def _build_assessment_paths(self) -> dict:
        """Build assessment-related paths."""
        return {
            '/quizzes/': {
                'get': {
                    'summary': 'List Quizzes',
                    'description': 'Get quizzes',
                    'operationId': 'listQuizzes',
                    'tags': ['assessment'],
                    'responses': {
                        '200': {'description': 'List of quizzes'}
                    }
                }
            },
            '/quizzes/{id}/': {
                'get': {
                    'summary': 'Get Quiz',
                    'description': 'Get quiz details',
                    'operationId': 'getQuiz',
                    'tags': ['assessment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Quiz details'}
                    }
                }
            },
            '/quizzes/{id}/attempt/': {
                'post': {
                    'summary': 'Start Quiz Attempt',
                    'description': 'Start a new quiz attempt',
                    'operationId': 'startQuizAttempt',
                    'tags': ['assessment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '201': {'description': 'Quiz attempt started'}
                    }
                }
            },
            '/quizzes/{id}/submit/': {
                'post': {
                    'summary': 'Submit Quiz',
                    'description': 'Submit quiz answers',
                    'operationId': 'submitQuiz',
                    'tags': ['assessment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/QuizSubmissionRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Quiz submitted'}
                    }
                }
            },
            '/assignments/': {
                'get': {
                    'summary': 'List Assignments',
                    'description': 'Get assignments',
                    'operationId': 'listAssignments',
                    'tags': ['assessment'],
                    'responses': {
                        '200': {'description': 'List of assignments'}
                    }
                }
            },
            '/assignments/{id}/': {
                'get': {
                    'summary': 'Get Assignment',
                    'description': 'Get assignment details',
                    'operationId': 'getAssignment',
                    'tags': ['assessment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Assignment details'}
                    }
                }
            },
            '/assignments/{id}/submit/': {
                'post': {
                    'summary': 'Submit Assignment',
                    'description': 'Submit assignment',
                    'operationId': 'submitAssignment',
                    'tags': ['assessment'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'multipart/form-data': {
                                'schema': {'$ref': '#/components/schemas/AssignmentSubmissionRequest'}
                            }
                        }
                    },
                    'responses': {
                        '201': {'description': 'Assignment submitted'}
                    }
                }
            }
        }
    
    def _build_certificate_paths(self) -> dict:
        """Build certificate-related paths."""
        return {
            '/certificates/': {
                'get': {
                    'summary': 'List Certificates',
                    'description': 'Get user certificates',
                    'operationId': 'listCertificates',
                    'tags': ['certificates'],
                    'responses': {
                        '200': {'description': 'List of certificates'}
                    }
                }
            },
            '/certificates/{id}/': {
                'get': {
                    'summary': 'Get Certificate',
                    'description': 'Get certificate details',
                    'operationId': 'getCertificate',
                    'tags': ['certificates'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Certificate details'}
                    }
                }
            },
            '/certificates/{id}/download/': {
                'get': {
                    'summary': 'Download Certificate',
                    'description': 'Download certificate PDF',
                    'operationId': 'downloadCertificate',
                    'tags': ['certificates'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Certificate PDF'}
                    }
                }
            },
            '/certificates/{id}/verify/': {
                'get': {
                    'summary': 'Verify Certificate',
                    'description': 'Verify certificate authenticity',
                    'operationId': 'verifyCertificate',
                    'tags': ['certificates'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Certificate verification result'}
                    }
                }
            }
        }
    
    def _build_scorm_paths(self) -> dict:
        """Build SCORM-related paths."""
        return {
            '/scorm/launch/{registration_id}/': {
                'get': {
                    'summary': 'Launch SCORM Content',
                    'description': 'Launch SCORM content for a registration',
                    'operationId': 'launchScorm',
                    'tags': ['scorm'],
                    'parameters': [
                        {'name': 'registration_id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'SCORM launch data'}
                    }
                }
            },
            '/scorm/api/': {
                'post': {
                    'summary': 'SCORM API',
                    'description': 'SCORM 1.2 API endpoint (LMSInitialize, LMSGetValue, LMSSetValue, LMSCommit, LMSFinish)',
                    'operationId': 'scormApi',
                    'tags': ['scorm'],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/SCORMAPIRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'SCORM API response'}
                    }
                }
            },
            '/scorm/sessions/{id}/suspend-data/': {
                'get': {
                    'summary': 'Get Suspend Data',
                    'description': 'Get SCORM suspend data for resume',
                    'operationId': 'getSuspendData',
                    'tags': ['scorm'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Suspend data'}
                    }
                }
            }
        }
    
    def _build_forum_paths(self) -> dict:
        """Build forum-related paths."""
        return {
            '/forums/{course_id}/threads/': {
                'get': {
                    'summary': 'List Forum Threads',
                    'description': 'Get threads for a course forum',
                    'operationId': 'listForumThreads',
                    'tags': ['forum'],
                    'parameters': [
                        {'name': 'course_id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'List of threads'}
                    }
                },
                'post': {
                    'summary': 'Create Thread',
                    'description': 'Create a new forum thread',
                    'operationId': 'createForumThread',
                    'tags': ['forum'],
                    'parameters': [
                        {'name': 'course_id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ForumThreadCreateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '201': {'description': 'Thread created'}
                    }
                }
            },
            '/threads/{id}/': {
                'get': {
                    'summary': 'Get Thread',
                    'description': 'Get thread with posts',
                    'operationId': 'getThread',
                    'tags': ['forum'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Thread details'}
                    }
                }
            },
            '/threads/{id}/posts/': {
                'post': {
                    'summary': 'Create Post',
                    'description': 'Create a post in a thread',
                    'operationId': 'createPost',
                    'tags': ['forum'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ForumPostCreateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '201': {'description': 'Post created'}
                    }
                }
            },
            '/posts/{id}/vote/': {
                'post': {
                    'summary': 'Vote on Post',
                    'description': 'Upvote or downvote a post',
                    'operationId': 'votePost',
                    'tags': ['forum'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/PostVoteRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Vote recorded'}
                    }
                }
            }
        }
    
    def _build_notification_paths(self) -> dict:
        """Build notification-related paths."""
        return {
            '/notifications/': {
                'get': {
                    'summary': 'List Notifications',
                    'description': 'Get user notifications',
                    'operationId': 'listNotifications',
                    'tags': ['notifications'],
                    'parameters': [
                        {'name': 'unread_only', 'in': 'query', 'schema': {'type': 'boolean'}},
                        {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}}
                    ],
                    'responses': {
                        '200': {'description': 'List of notifications'}
                    }
                }
            },
            '/notifications/{id}/': {
                'get': {
                    'summary': 'Get Notification',
                    'description': 'Get notification details',
                    'operationId': 'getNotification',
                    'tags': ['notifications'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Notification details'}
                    }
                },
                'patch': {
                    'summary': 'Update Notification',
                    'description': 'Mark notification as read',
                    'operationId': 'updateNotification',
                    'tags': ['notifications'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/NotificationUpdateRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Notification updated'}
                    }
                }
            },
            '/notifications/preferences/': {
                'get': {
                    'summary': 'Get Notification Preferences',
                    'description': 'Get user notification preferences',
                    'operationId': 'getNotificationPreferences',
                    'tags': ['notifications'],
                    'responses': {
                        '200': {'description': 'Notification preferences'}
                    }
                },
                'patch': {
                    'summary': 'Update Notification Preferences',
                    'description': 'Update notification preferences',
                    'operationId': 'updateNotificationPreferences',
                    'tags': ['notifications'],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/NotificationPreferencesRequest'}
                            }
                        }
                    },
                    'responses': {
                        '200': {'description': 'Preferences updated'}
                    }
                }
            }
        }
    
    def _build_analytics_paths(self) -> dict:
        """Build analytics-related paths."""
        return {
            '/analytics/dashboard/': {
                'get': {
                    'summary': 'Get Dashboard Analytics',
                    'description': 'Get dashboard analytics data',
                    'operationId': 'getDashboardAnalytics',
                    'tags': ['analytics'],
                    'responses': {
                        '200': {'description': 'Dashboard analytics'}
                    }
                }
            },
            '/analytics/courses/{id}/stats/': {
                'get': {
                    'summary': 'Get Course Statistics',
                    'description': 'Get statistics for a course',
                    'operationId': 'getCourseStats',
                    'tags': ['analytics'],
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}}
                    ],
                    'responses': {
                        '200': {'description': 'Course statistics'}
                    }
                }
            },
            '/analytics/audit-logs/': {
                'get': {
                    'summary': 'Get Audit Logs',
                    'description': 'Get audit logs (admin only)',
                    'operationId': 'getAuditLogs',
                    'tags': ['analytics'],
                    'parameters': [
                        {'name': 'user_id', 'in': 'query', 'schema': {'type': 'string', 'format': 'uuid'}},
                        {'name': 'action', 'in': 'query', 'schema': {'type': 'string'}},
                        {'name': 'start_date', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
                        {'name': 'end_date', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}}
                    ],
                    'responses': {
                        '200': {'description': 'Audit logs'}
                    }
                }
            }
        }
    
    def _build_components(self) -> dict:
        """Build the OpenAPI components section with schemas."""
        return {
            'securitySchemes': {
                'bearerAuth': {
                    'type': 'http',
                    'scheme': 'bearer',
                    'bearerFormat': 'JWT',
                    'description': 'JWT token for authentication'
                }
            },
            'schemas': self._build_schemas(),
            'responses': {
                'UnauthorizedError': {
                    'description': 'Authentication required',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'detail': {'type': 'string', 'example': 'Authentication credentials were not provided.'}
                                }
                            }
                        }
                    }
                },
                'ForbiddenError': {
                    'description': 'Permission denied',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'detail': {'type': 'string', 'example': 'You do not have permission to perform this action.'}
                                }
                            }
                        }
                    }
                },
                'NotFoundError': {
                    'description': 'Resource not found',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'detail': {'type': 'string', 'example': 'Not found.'}
                                }
                            }
                        }
                    }
                },
                'ValidationError': {
                    'description': 'Validation error',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'code': {'type': 'string', 'example': 'VALIDATION_ERROR'},
                                    'detail': {'type': 'string', 'example': 'Invalid input data.'},
                                    'field_errors': {'type': 'object'}
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _build_schemas(self) -> dict:
        """Build all schema definitions."""
        return {
            # Auth schemas
            'UserRegistrationRequest': {
                'type': 'object',
                'required': ['email', 'password', 'first_name', 'last_name'],
                'properties': {
                    'email': {'type': 'string', 'format': 'email'},
                    'password': {'type': 'string', 'minLength': 8},
                    'first_name': {'type': 'string'},
                    'last_name': {'type': 'string'},
                    'username': {'type': 'string'}
                }
            },
            'LoginRequest': {
                'type': 'object',
                'required': ['email', 'password'],
                'properties': {
                    'email': {'type': 'string', 'format': 'email'},
                    'password': {'type': 'string'}
                }
            },
            'TokenRefreshRequest': {
                'type': 'object',
                'required': ['refresh'],
                'properties': {
                    'refresh': {'type': 'string'}
                }
            },
            'PasswordResetRequest': {
                'type': 'object',
                'required': ['email'],
                'properties': {
                    'email': {'type': 'string', 'format': 'email'}
                }
            },
            'PasswordResetConfirmRequest': {
                'type': 'object',
                'required': ['token', 'new_password'],
                'properties': {
                    'token': {'type': 'string'},
                    'new_password': {'type': 'string', 'minLength': 8}
                }
            },
            # User schemas
            'UserUpdateRequest': {
                'type': 'object',
                'properties': {
                    'first_name': {'type': 'string'},
                    'last_name': {'type': 'string'},
                    'bio': {'type': 'string'},
                    'phone': {'type': 'string'},
                    'timezone': {'type': 'string'}
                }
            },
            'AvatarUploadRequest': {
                'type': 'object',
                'required': ['avatar'],
                'properties': {
                    'avatar': {'type': 'string', 'format': 'binary'}
                }
            },
            # Course schemas
            'CourseCreateRequest': {
                'type': 'object',
                'required': ['title', 'description'],
                'properties': {
                    'title': {'type': 'string', 'maxLength': 255},
                    'description': {'type': 'string'},
                    'syllabus': {'type': 'string'},
                    'price': {'type': 'number', 'minimum': 0},
                    'max_enrollments': {'type': 'integer', 'minimum': 1}
                }
            },
            'CourseUpdateRequest': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'maxLength': 255},
                    'description': {'type': 'string'},
                    'syllabus': {'type': 'string'},
                    'price': {'type': 'number', 'minimum': 0},
                    'is_published': {'type': 'boolean'},
                    'max_enrollments': {'type': 'integer', 'minimum': 1}
                }
            },
            'ModuleCreateRequest': {
                'type': 'object',
                'required': ['title'],
                'properties': {
                    'title': {'type': 'string', 'maxLength': 255},
                    'description': {'type': 'string'},
                    'sequence_order': {'type': 'integer'}
                }
            },
            # Enrollment schemas
            'ProgressUpdateRequest': {
                'type': 'object',
                'required': ['lesson_id', 'progress_percent'],
                'properties': {
                    'lesson_id': {'type': 'string', 'format': 'uuid'},
                    'progress_percent': {'type': 'number', 'minimum': 0, 'maximum': 100},
                    'is_completed': {'type': 'boolean'}
                }
            },
            # Assessment schemas
            'QuizSubmissionRequest': {
                'type': 'object',
                'required': ['answers'],
                'properties': {
                    'answers': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'question_id': {'type': 'string', 'format': 'uuid'},
                                'answer': {'type': 'string'}
                            }
                        }
                    }
                }
            },
            'AssignmentSubmissionRequest': {
                'type': 'object',
                'required': ['content'],
                'properties': {
                    'content': {'type': 'string'},
                    'attachments': {'type': 'array', 'items': {'type': 'string', 'format': 'binary'}}
                }
            },
            # Forum schemas
            'ForumThreadCreateRequest': {
                'type': 'object',
                'required': ['title', 'content'],
                'properties': {
                    'title': {'type': 'string', 'maxLength': 255},
                    'content': {'type': 'string'},
                    'is_pinned': {'type': 'boolean'}
                }
            },
            'ForumPostCreateRequest': {
                'type': 'object',
                'required': ['content'],
                'properties': {
                    'content': {'type': 'string'},
                    'parent_id': {'type': 'string', 'format': 'uuid'}
                }
            },
            'PostVoteRequest': {
                'type': 'object',
                'required': ['vote_type'],
                'properties': {
                    'vote_type': {'type': 'string', 'enum': ['up', 'down']}
                }
            },
            # Notification schemas
            'NotificationUpdateRequest': {
                'type': 'object',
                'properties': {
                    'is_read': {'type': 'boolean'}
                }
            },
            'NotificationPreferencesRequest': {
                'type': 'object',
                'properties': {
                    'email_enabled': {'type': 'boolean'},
                    'push_enabled': {'type': 'boolean'},
                    'in_app_enabled': {'type': 'boolean'}
                }
            },
            # SCORM schemas
            'SCORMAPIRequest': {
                'type': 'object',
                'required': ['method', 'element'],
                'properties': {
                    'method': {'type': 'string', 'enum': ['LMSInitialize', 'LMSGetValue', 'LMSSetValue', 'LMSCommit', 'LMSFinish']},
                    'element': {'type': 'string'},
                    'value': {'type': 'string'}
                }
            }
        }
    
    def _print_summary(self, contract: dict):
        """Print a summary of the generated contract."""
        path_count = len(contract.get('paths', {}))
        schema_count = len(contract.get('components', {}).get('schemas', {}))
        tag_count = len(contract.get('tags', {}))
        
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.NOTICE('API Contract Summary'))
        self.stdout.write('=' * 50)
        self.stdout.write(f'Title: {contract["info"]["title"]}')
        self.stdout.write(f'Version: {contract["info"]["version"]}')
        self.stdout.write(f'OpenAPI: {contract["openapi"]}')
        self.stdout.write(f'Endpoints: {path_count}')
        self.stdout.write(f'Schemas: {schema_count}')
        self.stdout.write(f'Tags: {tag_count}')
        self.stdout.write('=' * 50)
