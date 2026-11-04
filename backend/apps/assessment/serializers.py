"""
Assessment Serializers for Enterprise LMS
Provides serializers for Quiz, Question, QuizAttempt, Assignment, Submission, and Grade models.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.assessment.models import (
    Quiz, Question, QuizAttempt, Assignment, Submission, Grade
)
from apps.courses.serializers import CourseListSerializer, ModuleListSerializer

User = get_user_model()


class QuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for Question model.
    Used for CRUD operations on questions.
    """
    is_auto_gradable = serializers.ReadOnlyField()
    
    class Meta:
        model = Question
        fields = [
            'id', 'quiz', 'question_text', 'question_type',
            'options', 'correct_answer', 'points', 'order_index',
            'is_auto_gradable', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class QuestionListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for Question list views.
    Excludes correct_answer for security in learner views.
    """
    class Meta:
        model = Question
        fields = [
            'id', 'question_text', 'question_type',
            'options', 'points', 'order_index'
        ]


class QuestionInstructorSerializer(serializers.ModelSerializer):
    """
    Full serializer for instructors - includes correct_answer.
    """
    is_auto_gradable = serializers.ReadOnlyField()
    
    class Meta:
        model = Question
        fields = [
            'id', 'quiz', 'question_text', 'question_type',
            'options', 'correct_answer', 'points', 'order_index',
            'is_auto_gradable', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class QuizSerializer(serializers.ModelSerializer):
    """
    Serializer for Quiz model.
    Includes nested questions and computed fields.
    """
    total_points = serializers.ReadOnlyField()
    question_count = serializers.ReadOnlyField()
    questions = QuestionListSerializer(many=True, read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            'id', 'course', 'course_title', 'title', 'description',
            'time_limit_minutes', 'passing_score', 'max_attempts',
            'randomize_questions', 'show_correct_answers', 'is_published',
            'total_points', 'question_count', 'questions',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class QuizListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for Quiz list views.
    """
    total_points = serializers.ReadOnlyField()
    question_count = serializers.ReadOnlyField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            'id', 'course', 'course_title', 'title',
            'time_limit_minutes', 'passing_score', 'max_attempts',
            'is_published', 'total_points', 'question_count',
            'created_at'
        ]


class QuizDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for Quiz with full question data.
    """
    total_points = serializers.ReadOnlyField()
    question_count = serializers.ReadOnlyField()
    questions = QuestionSerializer(many=True, read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            'id', 'course', 'course_title', 'title', 'description',
            'time_limit_minutes', 'passing_score', 'max_attempts',
            'randomize_questions', 'show_correct_answers', 'is_published',
            'total_points', 'question_count', 'questions',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class QuizAttemptSerializer(serializers.ModelSerializer):
    """
    Serializer for QuizAttempt model.
    """
    is_passed = serializers.ReadOnlyField()
    attempt_number = serializers.ReadOnlyField()
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = QuizAttempt
        fields = [
            'id', 'user', 'user_email', 'quiz', 'quiz_title',
            'started_at', 'submitted_at', 'score', 'score_percentage',
            'status', 'answers', 'ip_address', 'user_agent',
            'is_passed', 'attempt_number', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'started_at', 'score', 'score_percentage',
            'is_passed', 'attempt_number', 'created_at', 'updated_at'
        ]


class QuizAttemptCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new quiz attempt.
    """
    class Meta:
        model = QuizAttempt
        fields = ['quiz']


class QuizAttemptSubmitSerializer(serializers.Serializer):
    """
    Serializer for submitting quiz answers.
    """
    answers = serializers.JSONField(
        help_text="Dictionary of question_id: answer pairs"
    )
    
    def validate_answers(self, value):
        """Validate that answers is a dictionary."""
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Answers must be a dictionary of question_id: answer pairs"
            )
        return value


class QuizAttemptResultSerializer(serializers.ModelSerializer):
    """
    Serializer for quiz attempt results.
    Includes detailed scoring information.
    """
    is_passed = serializers.ReadOnlyField()
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    passing_score = serializers.DecimalField(
        source='quiz.passing_score',
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
    total_points = serializers.SerializerMethodField()
    
    class Meta:
        model = QuizAttempt
        fields = [
            'id', 'quiz', 'quiz_title', 'started_at', 'submitted_at',
            'score', 'score_percentage', 'passing_score', 'total_points',
            'is_passed', 'status', 'answers', 'created_at'
        ]
    
    def get_total_points(self, obj):
        return obj.quiz.total_points


class AssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for Assignment model.
    """
    course_title = serializers.CharField(source='course.title', read_only=True)
    module_title = serializers.CharField(
        source='module.title',
        read_only=True,
        allow_null=True
    )
    is_late_submission_allowed = serializers.SerializerMethodField()
    
    class Meta:
        model = Assignment
        fields = [
            'id', 'course', 'course_title', 'module', 'module_title',
            'title', 'description', 'instructions', 'due_date',
            'available_from', 'available_until', 'max_points',
            'late_submission_policy', 'late_penalty_percent',
            'grace_period_hours', 'allow_file_upload', 'max_file_size_mb',
            'allowed_file_types', 'is_published', 'is_late_submission_allowed',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_is_late_submission_allowed(self, obj):
        """Check if late submissions are allowed."""
        return obj.late_submission_policy != 'no_late'


class AssignmentListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for Assignment list views.
    """
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = Assignment
        fields = [
            'id', 'course', 'course_title', 'title',
            'due_date', 'max_points', 'is_published', 'created_at'
        ]


class SubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for Submission model.
    """
    assignment_title = serializers.CharField(
        source='assignment.title',
        read_only=True
    )
    user_email = serializers.CharField(source='user.email', read_only=True)
    is_late = serializers.SerializerMethodField()
    
    class Meta:
        model = Submission
        fields = [
            'id', 'assignment', 'assignment_title', 'user', 'user_email',
            'submitted_text', 'file_urls', 'submitted_at', 'status',
            'version', 'previous_submission', 'ip_address', 'is_late',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'submitted_at', 'version', 'ip_address',
            'created_at', 'updated_at'
        ]
    
    def get_is_late(self, obj):
        """Check if submission is late."""
        if obj.submitted_at and obj.assignment.due_date:
            return obj.submitted_at > obj.assignment.due_date
        return False


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new submission.
    """
    class Meta:
        model = Submission
        fields = ['assignment', 'submitted_text', 'file_urls']


class SubmissionGradeSerializer(serializers.Serializer):
    """
    Serializer for grading a submission.
    """
    score = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        help_text="Score achieved"
    )
    feedback = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Instructor feedback"
    )


class GradeSerializer(serializers.ModelSerializer):
    """
    Serializer for Grade model.
    """
    is_passed = serializers.ReadOnlyField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    graded_by_email = serializers.CharField(
        source='graded_by.email',
        read_only=True,
        allow_null=True
    )
    gradable_title = serializers.SerializerMethodField()
    
    class Meta:
        model = Grade
        fields = [
            'id', 'user', 'user_email', 'gradable_type', 'gradable_id',
            'gradable_title', 'score', 'max_points', 'percentage',
            'feedback', 'graded_by', 'graded_by_email', 'graded_at',
            'is_auto_graded', 'attempt_id', 'is_passed',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'percentage', 'graded_at', 'is_auto_graded',
            'created_at', 'updated_at'
        ]
    
    def get_gradable_title(self, obj):
        """Get the title of the gradable item."""
        try:
            if obj.gradable_type == 'quiz':
                from apps.assessment.models import Quiz
                quiz = Quiz.objects.filter(id=obj.gradable_id).first()
                return quiz.title if quiz else "Unknown Quiz"
            elif obj.gradable_type == 'assignment':
                from apps.assessment.models import Assignment
                assignment = Assignment.objects.filter(id=obj.gradable_id).first()
                return assignment.title if assignment else "Unknown Assignment"
        except Exception:
            pass
        return "Unknown"


class GradeListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for Grade list views.
    """
    is_passed = serializers.ReadOnlyField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Grade
        fields = [
            'id', 'user', 'user_email', 'gradable_type', 'gradable_id',
            'score', 'max_points', 'percentage', 'is_passed',
            'graded_at', 'is_auto_graded'
        ]


class GradeUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating a grade (manual grading).
    """
    class Meta:
        model = Grade
        fields = ['score', 'feedback', 'graded_by']


class QuizStartResponseSerializer(serializers.Serializer):
    """
    Response serializer for quiz start action.
    """
    attempt_id = serializers.UUIDField()
    started_at = serializers.DateTimeField()
    time_limit_minutes = serializers.IntegerField(allow_null=True)
    question_count = serializers.IntegerField()


class QuizSubmitResponseSerializer(serializers.Serializer):
    """
    Response serializer for quiz submission.
    """
    attempt_id = serializers.UUIDField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2)
    score_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_passed = serializers.BooleanField()
    status = serializers.CharField()


class AssessmentStatsSerializer(serializers.Serializer):
    """
    Serializer for assessment statistics.
    """
    total_quizzes = serializers.IntegerField()
    total_assignments = serializers.IntegerField()
    total_attempts = serializers.IntegerField()
    total_submissions = serializers.IntegerField()
    average_quiz_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    pending_grading_count = serializers.IntegerField()
