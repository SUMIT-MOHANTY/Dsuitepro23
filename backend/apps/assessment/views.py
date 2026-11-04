"""
Assessment Views for Enterprise LMS
Provides ViewSets for Quiz, Question, QuizAttempt, Assignment, Submission, and Grade.
"""

import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend

from apps.assessment.models import (
    Quiz, Question, QuizAttempt, Assignment, Submission, Grade
)
from apps.assessment.serializers import (
    QuizSerializer, QuizListSerializer, QuizDetailSerializer,
    QuestionSerializer, QuestionListSerializer, QuestionInstructorSerializer,
    QuizAttemptSerializer, QuizAttemptCreateSerializer, QuizAttemptSubmitSerializer,
    QuizAttemptResultSerializer, QuizStartResponseSerializer, QuizSubmitResponseSerializer,
    AssignmentSerializer, AssignmentListSerializer,
    SubmissionSerializer, SubmissionCreateSerializer, SubmissionGradeSerializer,
    GradeSerializer, GradeListSerializer, GradeUpdateSerializer,
    AssessmentStatsSerializer
)
from apps.assessment.services import (
    GradingEngine, AttemptService, SubmissionService
)
from apps.core.pagination import StandardResultsSetPagination


class QuizViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Quiz CRUD operations.
    Provides endpoints for quiz management and learner interactions.
    """
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['course', 'is_published', 'max_attempts']
    ordering_fields = ['created_at', 'title', 'passing_score']
    ordering = ['-created_at']
    search_fields = ['title', 'description']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return QuizListSerializer
        elif self.action == 'retrieve':
            return QuizDetailSerializer
        return QuizSerializer
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def start(self, request, pk=None):
        """
        Start a new quiz attempt.
        POST /api/v1/assessments/quizzes/{id}/start/
        """
        quiz = self.get_object()
        user = request.user
        
        # Check if quiz is published
        if not quiz.is_published:
            return Response(
                {"detail": "This quiz is not available."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check max attempts
        if quiz.max_attempts > 0:
            attempt_count = QuizAttempt.objects.filter(
                user=user,
                quiz=quiz,
                status__in=['submitted', 'graded']
            ).count()
            if attempt_count >= quiz.max_attempts:
                return Response(
                    {"detail": "Maximum attempts reached for this quiz."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Check for existing in-progress attempt
        existing_attempt = QuizAttempt.objects.filter(
            user=user,
            quiz=quiz,
            status='in_progress'
        ).first()
        
        if existing_attempt:
            # Check if attempt has expired
            if AttemptService.is_attempt_expired(existing_attempt):
                existing_attempt.status = 'expired'
                existing_attempt.save()
            else:
                # Resume existing attempt
                serializer = QuizStartResponseSerializer({
                    'attempt_id': existing_attempt.id,
                    'started_at': existing_attempt.started_at,
                    'time_limit_minutes': quiz.time_limit_minutes,
                    'question_count': quiz.question_count
                })
                return Response(serializer.data)
        
        # Create new attempt
        attempt = QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            status='in_progress',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        serializer = QuizStartResponseSerializer({
            'attempt_id': attempt.id,
            'started_at': attempt.started_at,
            'time_limit_minutes': quiz.time_limit_minutes,
            'question_count': quiz.question_count
        })
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def questions(self, request, pk=None):
        """
        Get questions for a quiz (learner view - excludes correct answers).
        GET /api/v1/assessments/quizzes/{id}/questions/
        """
        quiz = self.get_object()
        
        # Check if user has an active attempt
        attempt = QuizAttempt.objects.filter(
            user=request.user,
            quiz=quiz,
            status='in_progress'
        ).first()
        
        if not attempt:
            return Response(
                {"detail": "No active attempt found. Start a quiz attempt first."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if attempt has expired
        if AttemptService.is_attempt_expired(attempt):
            attempt.status = 'expired'
            attempt.save()
            return Response(
                {"detail": "Quiz attempt has expired."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        questions = quiz.questions.all()
        if quiz.randomize_questions:
            questions = questions.order_by('?')
        else:
            questions = questions.order_by('order_index')
        
        serializer = QuestionListSerializer(questions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def stats(self, request, pk=None):
        """
        Get quiz statistics.
        GET /api/v1/assessments/quizzes/{id}/stats/
        """
        quiz = self.get_object()
        attempts = QuizAttempt.objects.filter(quiz=quiz, status__in=['submitted', 'graded'])
        
        total_attempts = attempts.count()
        passed_attempts = attempts.filter(score_percentage__gte=quiz.passing_score).count()
        
        avg_score = 0
        if total_attempts > 0:
            avg_score = sum(a.score_percentage or 0 for a in attempts) / total_attempts
        
        return Response({
            'total_attempts': total_attempts,
            'passed_attempts': passed_attempts,
            'failed_attempts': total_attempts - passed_attempts,
            'pass_rate': (passed_attempts / total_attempts * 100) if total_attempts > 0 else 0,
            'average_score': round(avg_score, 2),
            'highest_score': attempts.order_by('-score_percentage').first().score_percentage if attempts.exists() else None,
            'lowest_score': attempts.order_by('score_percentage').first().score_percentage if attempts.exists() else None,
        })


class QuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Question CRUD operations.
    """
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['quiz', 'question_type']
    ordering_fields = ['order_index', 'created_at', 'points']
    ordering = ['order_index', 'created_at']
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on user role."""
        if self.request.user.is_staff or self.request.user.is_superuser:
            return QuestionInstructorSerializer
        return QuestionSerializer
    
    def get_queryset(self):
        """Filter questions based on query params."""
        queryset = super().get_queryset()
        quiz_id = self.request.query_params.get('quiz')
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        return queryset


class QuizAttemptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for QuizAttempt operations.
    """
    queryset = QuizAttempt.objects.all()
    serializer_class = QuizAttemptSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'quiz', 'status']
    ordering_fields = ['started_at', 'submitted_at', 'score']
    ordering = ['-started_at']
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['update', 'partial_update', 'destroy', 'grade']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        """Filter attempts based on user permissions."""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return self.queryset
        return self.queryset.filter(user=user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return QuizAttemptCreateSerializer
        return QuizAttemptSerializer
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        """
        Submit a quiz attempt with answers.
        POST /api/v1/assessments/attempts/{id}/submit/
        """
        attempt = self.get_object()
        user = request.user
        
        # Verify ownership
        if attempt.user != user and not (user.is_staff or user.is_superuser):
            return Response(
                {"detail": "You can only submit your own attempts."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check status
        if attempt.status != 'in_progress':
            return Response(
                {"detail": f"Attempt is already {attempt.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if expired
        if AttemptService.is_attempt_expired(attempt):
            attempt.status = 'expired'
            attempt.save()
            return Response(
                {"detail": "Quiz attempt has expired."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate answers
        serializer = QuizAttemptSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data['answers']
        
        # Update attempt with answers
        attempt.answers = answers
        attempt.submitted_at = timezone.now()
        attempt.status = 'submitted'
        attempt.save()
        
        # Auto-grade the attempt
        grading_result = GradingEngine.auto_grade_attempt(attempt)
        
        response_serializer = QuizSubmitResponseSerializer({
            'attempt_id': attempt.id,
            'score': attempt.score,
            'score_percentage': attempt.score_percentage,
            'is_passed': attempt.is_passed,
            'status': attempt.status
        })
        
        return Response(response_serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def result(self, request, pk=None):
        """
        Get quiz attempt result.
        GET /api/v1/assessments/attempts/{id}/result/
        """
        attempt = self.get_object()
        
        # Verify ownership or instructor access
        if attempt.user != request.user and not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "You can only view your own results."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if attempt.status not in ['submitted', 'graded']:
            return Response(
                {"detail": "Attempt has not been submitted yet."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = QuizAttemptResultSerializer(attempt)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def grade(self, request, pk=None):
        """
        Manually grade a quiz attempt (for essay/short answer questions).
        POST /api/v1/assessments/attempts/{id}/grade/
        """
        attempt = self.get_object()
        
        if attempt.status not in ['submitted', 'graded']:
            return Response(
                {"detail": "Attempt must be submitted before grading."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get manual scores from request
        manual_scores = request.data.get('manual_scores', {})
        feedback = request.data.get('feedback', '')
        
        # Apply manual grading
        result = GradingEngine.apply_manual_grading(
            attempt=attempt,
            manual_scores=manual_scores,
            feedback=feedback,
            graded_by=request.user
        )
        
        return Response({
            'attempt_id': attempt.id,
            'score': attempt.score,
            'score_percentage': attempt.score_percentage,
            'is_passed': attempt.is_passed,
            'status': attempt.status,
            'graded': result
        })


class AssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Assignment CRUD operations.
    """
    queryset = Assignment.objects.all()
    serializer_class = AssignmentSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['course', 'module', 'is_published', 'due_date']
    ordering_fields = ['created_at', 'due_date', 'title']
    ordering = ['-created_at']
    search_fields = ['title', 'description']
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return AssignmentListSerializer
        return AssignmentSerializer
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def submissions(self, request, pk=None):
        """
        Get submissions for an assignment.
        GET /api/v1/assessments/assignments/{id}/submissions/
        """
        assignment = self.get_object()
        user = request.user
        
        if user.is_staff or user.is_superuser:
            # Instructors see all submissions
            submissions = Submission.objects.filter(assignment=assignment)
        else:
            # Learners see only their own submissions
            submissions = Submission.objects.filter(assignment=assignment, user=user)
        
        page = self.paginate_queryset(submissions)
        if page is not None:
            serializer = SubmissionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = SubmissionSerializer(submissions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        """
        Submit an assignment.
        POST /api/v1/assessments/assignments/{id}/submit/
        """
        assignment = self.get_object()
        user = request.user
        
        # Check if assignment is available
        if not assignment.is_published:
            return Response(
                {"detail": "This assignment is not available."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check availability dates
        now = timezone.now()
        if assignment.available_from and now < assignment.available_from:
            return Response(
                {"detail": "This assignment is not yet available."},
                status=status.HTTP_403_FORBIDDEN
            )
        if assignment.available_until and now > assignment.available_until:
            return Response(
                {"detail": "This assignment is no longer available."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check late submission policy
        is_late = False
        if assignment.due_date and now > assignment.due_date:
            if assignment.late_submission_policy == 'no_late':
                return Response(
                    {"detail": "Late submissions are not accepted for this assignment."},
                    status=status.HTTP_403_FORBIDDEN
                )
            is_late = True
        
        # Validate submission data
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create submission
        submission = Submission.objects.create(
            assignment=assignment,
            user=user,
            submitted_text=serializer.validated_data.get('submitted_text', ''),
            file_urls=serializer.validated_data.get('file_urls', []),
            submitted_at=now,
            status='late' if is_late else 'submitted',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Queue for manual grading
        SubmissionService.queue_for_grading(submission)
        
        response_serializer = SubmissionSerializer(submission)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Submission operations.
    """
    queryset = Submission.objects.all()
    serializer_class = SubmissionSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['assignment', 'user', 'status']
    ordering_fields = ['submitted_at', 'version']
    ordering = ['-submitted_at']
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['update', 'partial_update', 'destroy', 'grade']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        """Filter submissions based on user permissions."""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return self.queryset
        return self.queryset.filter(user=user)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def grade(self, request, pk=None):
        """
        Grade a submission.
        POST /api/v1/assessments/submissions/{id}/grade/
        """
        submission = self.get_object()
        
        if submission.status not in ['submitted', 'late', 'graded']:
            return Response(
                {"detail": "Submission cannot be graded."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = SubmissionGradeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create or update grade
        grade, created = Grade.objects.update_or_create(
            user=submission.user,
            gradable_type='assignment',
            gradable_id=submission.assignment.id,
            attempt_id=submission.id,
            defaults={
                'score': serializer.validated_data['score'],
                'max_points': submission.assignment.max_points,
                'feedback': serializer.validated_data.get('feedback', ''),
                'graded_by': request.user,
                'graded_at': timezone.now(),
                'is_auto_graded': False
            }
        )
        
        # Update submission status
        submission.status = 'graded'
        submission.save()
        
        return Response({
            'submission_id': submission.id,
            'grade_id': grade.id,
            'score': grade.score,
            'max_points': grade.max_points,
            'percentage': grade.percentage,
            'is_passed': grade.is_passed,
            'graded_by': request.user.email
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def resubmit(self, request, pk=None):
        """
        Resubmit a submission (create new version).
        POST /api/v1/assessments/submissions/{id}/resubmit/
        """
        submission = self.get_object()
        user = request.user
        
        # Verify ownership
        if submission.user != user:
            return Response(
                {"detail": "You can only resubmit your own submissions."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Only allow resubmission if returned for revision
        if submission.status != 'returned':
            return Response(
                {"detail": "Submission can only be resubmitted when returned for revision."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate submission data
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create new submission version
        new_submission = Submission.objects.create(
            assignment=submission.assignment,
            user=user,
            submitted_text=serializer.validated_data.get('submitted_text', ''),
            file_urls=serializer.validated_data.get('file_urls', []),
            submitted_at=timezone.now(),
            status='submitted',
            version=submission.version + 1,
            previous_submission=submission,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        response_serializer = SubmissionSerializer(new_submission)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class GradeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Grade operations.
    """
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'gradable_type', 'is_auto_graded']
    ordering_fields = ['graded_at', 'score', 'percentage']
    ordering = ['-graded_at']
    
    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        """Filter grades based on user permissions."""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return self.queryset
        return self.queryset.filter(user=user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return GradeListSerializer
        elif self.action in ['update', 'partial_update']:
            return GradeUpdateSerializer
        return GradeSerializer
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_grades(self, request):
        """
        Get current user's grades.
        GET /api/v1/assessments/grades/my_grades/
        """
        grades = self.get_queryset().filter(user=request.user)
        page = self.paginate_queryset(grades)
        if page is not None:
            serializer = GradeListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = GradeListSerializer(grades, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def stats(self, request):
        """
        Get assessment statistics.
        GET /api/v1/assessments/grades/stats/
        """
        total_quizzes = Quiz.objects.count()
        total_assignments = Assignment.objects.count()
        total_attempts = QuizAttempt.objects.count()
        total_submissions = Submission.objects.count()
        
        # Calculate average quiz score
        graded_attempts = QuizAttempt.objects.filter(
            status__in=['submitted', 'graded'],
            score_percentage__isnull=False
        )
        avg_score = 0
        if graded_attempts.exists():
            avg_score = sum(a.score_percentage for a in graded_attempts) / graded_attempts.count()
        
        # Count pending grading
        pending_grading = Submission.objects.filter(
            status__in=['submitted', 'late']
        ).count()
        
        serializer = AssessmentStatsSerializer({
            'total_quizzes': total_quizzes,
            'total_assignments': total_assignments,
            'total_attempts': total_attempts,
            'total_submissions': total_submissions,
            'average_quiz_score': round(avg_score, 2),
            'pending_grading_count': pending_grading
        })
        
        return Response(serializer.data)


class AssessmentDashboardView(viewsets.ViewSet):
    """
    ViewSet for assessment dashboard data.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        Get assessment dashboard overview.
        GET /api/v1/assessments/dashboard/
        """
        user = request.user
        
        if user.is_staff or user.is_superuser:
            # Instructor/Admin dashboard
            return self._get_instructor_dashboard(user)
        else:
            # Learner dashboard
            return self._get_learner_dashboard(user)
    
    def _get_instructor_dashboard(self, user):
        """Get instructor dashboard data."""
        # Pending grading
        pending_submissions = Submission.objects.filter(
            status__in=['submitted', 'late']
        ).count()
        
        # Recent attempts
        recent_attempts = QuizAttempt.objects.filter(
            status__in=['submitted', 'graded']
        ).order_by('-submitted_at')[:10]
        
        # Quiz stats
        quiz_stats = []
        for quiz in Quiz.objects.filter(is_published=True)[:5]:
            attempts = QuizAttempt.objects.filter(quiz=quiz, status__in=['submitted', 'graded'])
            quiz_stats.append({
                'quiz_id': str(quiz.id),
                'quiz_title': quiz.title,
                'total_attempts': attempts.count(),
                'average_score': sum(a.score_percentage or 0 for a in attempts) / attempts.count() if attempts.exists() else 0
            })
        
        return Response({
            'role': 'instructor',
            'pending_grading': pending_submissions,
            'recent_attempts': QuizAttemptSerializer(recent_attempts, many=True).data,
            'quiz_stats': quiz_stats
        })
    
    def _get_learner_dashboard(self, user):
        """Get learner dashboard data."""
        # My attempts
        my_attempts = QuizAttempt.objects.filter(user=user).order_by('-started_at')[:10]
        
        # My submissions
        my_submissions = Submission.objects.filter(user=user).order_by('-submitted_at')[:10]
        
        # My grades
        my_grades = Grade.objects.filter(user=user).order_by('-graded_at')[:10]
        
        # Average score
        avg_score = 0
        if my_grades.exists():
            avg_score = sum(g.percentage for g in my_grades) / my_grades.count()
        
        return Response({
            'role': 'learner',
            'average_score': round(avg_score, 2),
            'recent_attempts': QuizAttemptSerializer(my_attempts, many=True).data,
            'recent_submissions': SubmissionSerializer(my_submissions, many=True).data,
            'recent_grades': GradeListSerializer(my_grades, many=True).data
        })
