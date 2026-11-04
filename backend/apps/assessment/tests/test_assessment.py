"""
Assessment Tests for Enterprise LMS
Provides comprehensive test coverage for Quiz, Question, QuizAttempt, Assignment, Submission, and Grade models,
as well as the grading engine and API endpoints.
"""

import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.assessment.models import Quiz, Question, QuizAttempt, Assignment, Submission, Grade
from apps.assessment.services import GradingEngine, ManualGradingQueue, ScoreCalculator, AttemptService, SubmissionService
from apps.courses.models import Course, Module

User = get_user_model()


# =============================================================================
# Model Tests
# =============================================================================

class QuizModelTests(TestCase):
    """Tests for the Quiz model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            randomize_questions=False,
            show_correct_answers=True,
            is_published=True
        )
    
    def test_quiz_creation(self):
        """Test that a quiz can be created."""
        self.assertEqual(self.quiz.title, 'Test Quiz')
        self.assertEqual(self.quiz.course, self.course)
        self.assertEqual(self.quiz.time_limit_minutes, 30)
        self.assertEqual(self.quiz.passing_score, Decimal('70.00'))
        self.assertEqual(self.quiz.max_attempts, 3)
        self.assertTrue(self.quiz.is_published)
    
    def test_quiz_str_representation(self):
        """Test the string representation of a quiz."""
        self.assertEqual(str(self.quiz), f"{self.course.title} - {self.quiz.title}")
    
    def test_quiz_total_points_property(self):
        """Test the total_points property calculation."""
        # Create questions with points
        Question.objects.create(
            quiz=self.quiz,
            question_text='Q1',
            question_type='mcq',
            points=Decimal('10.00'),
            order_index=1
        )
        Question.objects.create(
            quiz=self.quiz,
            question_text='Q2',
            question_type='mcq',
            points=Decimal('15.00'),
            order_index=2
        )
        
        self.assertEqual(self.quiz.total_points, Decimal('25.00'))
    
    def test_quiz_question_count_property(self):
        """Test the question_count property."""
        self.assertEqual(self.quiz.question_count, 0)
        
        Question.objects.create(
            quiz=self.quiz,
            question_text='Q1',
            question_type='mcq',
            points=Decimal('10.00'),
            order_index=1
        )
        
        self.assertEqual(self.quiz.question_count, 1)


class QuestionModelTests(TestCase):
    """Tests for the Question model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
    
    def test_question_creation(self):
        """Test that a question can be created."""
        question = Question.objects.create(
            quiz=self.quiz,
            question_text='What is 2+2?',
            question_type='mcq',
            options={'A': '3', 'B': '4', 'C': '5', 'D': '6'},
            correct_answer='B',
            points=Decimal('10.00'),
            order_index=1
        )
        
        self.assertEqual(question.question_text, 'What is 2+2?')
        self.assertEqual(question.question_type, 'mcq')
        self.assertEqual(question.correct_answer, 'B')
        self.assertEqual(question.points, Decimal('10.00'))
    
    def test_question_is_auto_gradable(self):
        """Test the is_auto_gradable method."""
        mcq_question = Question.objects.create(
            quiz=self.quiz,
            question_text='MCQ Question',
            question_type='mcq',
            correct_answer='A',
            points=Decimal('10.00'),
            order_index=1
        )
        
        essay_question = Question.objects.create(
            quiz=self.quiz,
            question_text='Essay Question',
            question_type='essay',
            points=Decimal('20.00'),
            order_index=2
        )
        
        self.assertTrue(mcq_question.is_auto_gradable())
        self.assertFalse(essay_question.is_auto_gradable())
    
    def test_question_str_representation(self):
        """Test the string representation of a question."""
        question = Question.objects.create(
            quiz=self.quiz,
            question_text='Test Question',
            question_type='mcq',
            points=Decimal('10.00'),
            order_index=1
        )
        
        self.assertEqual(str(question), f"{self.quiz.title} - Question 1")


class QuizAttemptModelTests(TestCase):
    """Tests for the QuizAttempt model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
    
    def test_attempt_creation(self):
        """Test that a quiz attempt can be created."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='in_progress',
            ip_address='127.0.0.1',
            user_agent='Test Agent'
        )
        
        self.assertEqual(attempt.user, self.learner)
        self.assertEqual(attempt.quiz, self.quiz)
        self.assertEqual(attempt.status, 'in_progress')
        self.assertIsNotNone(attempt.started_at)
    
    def test_attempt_is_passed_property(self):
        """Test the is_passed property."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='graded',
            score=Decimal('80.00'),
            score_percentage=Decimal('80.00'),
            ip_address='127.0.0.1'
        )
        
        self.assertTrue(attempt.is_passed)
        
        attempt.score_percentage = Decimal('60.00')
        attempt.save()
        
        self.assertFalse(attempt.is_passed)
    
    def test_attempt_number_property(self):
        """Test the attempt_number property."""
        # Create first attempt
        attempt1 = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='submitted',
            ip_address='127.0.0.1'
        )
        
        self.assertEqual(attempt1.attempt_number, 1)
        
        # Create second attempt
        attempt2 = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='in_progress',
            ip_address='127.0.0.1'
        )
        
        self.assertEqual(attempt2.attempt_number, 2)


class AssignmentModelTests(TestCase):
    """Tests for the Assignment model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Test Module',
            description='Test module description',
            order_index=1,
            status='published'
        )
    
    def test_assignment_creation(self):
        """Test that an assignment can be created."""
        assignment = Assignment.objects.create(
            course=self.course,
            module=self.module,
            title='Test Assignment',
            description='Test assignment description',
            instructions='Complete the following tasks...',
            due_date=timezone.now() + timedelta(days=7),
            max_points=Decimal('100.00'),
            late_submission_policy='penalty',
            late_penalty_percent=Decimal('10.00'),
            is_published=True
        )
        
        self.assertEqual(assignment.title, 'Test Assignment')
        self.assertEqual(assignment.course, self.course)
        self.assertEqual(assignment.module, self.module)
        self.assertEqual(assignment.max_points, Decimal('100.00'))
        self.assertTrue(assignment.is_published)
    
    def test_assignment_str_representation(self):
        """Test the string representation of an assignment."""
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        self.assertEqual(str(assignment), f"{self.course.title} - {assignment.title}")


class SubmissionModelTests(TestCase):
    """Tests for the Submission model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            due_date=timezone.now() + timedelta(days=7),
            max_points=Decimal('100.00'),
            is_published=True
        )
    
    def test_submission_creation(self):
        """Test that a submission can be created."""
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.learner,
            submitted_text='This is my submission text.',
            file_urls=['https://example.com/file1.pdf'],
            submitted_at=timezone.now(),
            status='submitted',
            version=1,
            ip_address='127.0.0.1'
        )
        
        self.assertEqual(submission.assignment, self.assignment)
        self.assertEqual(submission.user, self.learner)
        self.assertEqual(submission.status, 'submitted')
        self.assertEqual(submission.version, 1)
    
    def test_submission_str_representation(self):
        """Test the string representation of a submission."""
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.learner,
            submitted_text='Test submission',
            status='submitted',
            version=1
        )
        
        expected = f"{self.learner.email} - {self.assignment.title} (v1)"
        self.assertEqual(str(submission), expected)


class GradeModelTests(TestCase):
    """Tests for the Grade model."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
    
    def test_grade_creation(self):
        """Test that a grade can be created."""
        grade = Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=self.quiz.id,
            score=Decimal('85.00'),
            max_points=Decimal('100.00'),
            feedback='Great work!',
            graded_by=self.instructor,
            graded_at=timezone.now(),
            is_auto_graded=False
        )
        
        self.assertEqual(grade.user, self.learner)
        self.assertEqual(grade.gradable_type, 'quiz')
        self.assertEqual(grade.score, Decimal('85.00'))
        self.assertEqual(grade.percentage, Decimal('85.00'))
        self.assertEqual(grade.graded_by, self.instructor)
    
    def test_grade_percentage_calculation(self):
        """Test that percentage is calculated automatically."""
        grade = Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=self.quiz.id,
            score=Decimal('75.00'),
            max_points=Decimal('100.00')
        )
        
        self.assertEqual(grade.percentage, Decimal('75.00'))
    
    def test_grade_is_passed_property(self):
        """Test the is_passed property."""
        passing_grade = Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=self.quiz.id,
            score=Decimal('75.00'),
            max_points=Decimal('100.00')
        )
        
        failing_grade = Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=self.quiz.id,
            score=Decimal('50.00'),
            max_points=Decimal('100.00')
        )
        
        self.assertTrue(passing_grade.is_passed)
        self.assertFalse(failing_grade.is_passed)


# =============================================================================
# Grading Engine Tests
# =============================================================================

class GradingEngineTests(TestCase):
    """Tests for the GradingEngine service."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
        
        # Create questions
        self.question1 = Question.objects.create(
            quiz=self.quiz,
            question_text='What is 2+2?',
            question_type='mcq',
            options={'A': '3', 'B': '4', 'C': '5', 'D': '6'},
            correct_answer='B',
            points=Decimal('10.00'),
            order_index=1
        )
        
        self.question2 = Question.objects.create(
            quiz=self.quiz,
            question_text='What is the capital of France?',
            question_type='mcq',
            options={'A': 'London', 'B': 'Berlin', 'C': 'Paris', 'D': 'Madrid'},
            correct_answer='C',
            points=Decimal('15.00'),
            order_index=2
        )
        
        self.question3 = Question.objects.create(
            quiz=self.quiz,
            question_text='Select prime numbers',
            question_type='multi_select',
            options={'A': '2', 'B': '3', 'C': '4', 'D': '5'},
            correct_answer=['A', 'B', 'D'],
            points=Decimal('20.00'),
            order_index=3
        )
        
        self.question4 = Question.objects.create(
            quiz=self.quiz,
            question_text='Describe your understanding',
            question_type='essay',
            points=Decimal('25.00'),
            order_index=4
        )
    
    def test_auto_grade_mcq_correct(self):
        """Test auto-grading with correct MCQ answer."""
        answers = {str(self.question1.id): 'B'}
        
        result = GradingEngine.auto_grade_mcq(self.question1, answers)
        
        self.assertTrue(result['is_correct'])
        self.assertEqual(result['points_earned'], Decimal('10.00'))
        self.assertEqual(result['max_points'], Decimal('10.00'))
    
    def test_auto_grade_mcq_incorrect(self):
        """Test auto-grading with incorrect MCQ answer."""
        answers = {str(self.question1.id): 'A'}
        
        result = GradingEngine.auto_grade_mcq(self.question1, answers)
        
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['points_earned'], Decimal('0.00'))
    
    def test_auto_grade_mcq_no_answer(self):
        """Test auto-grading when no answer is provided."""
        answers = {}
        
        result = GradingEngine.auto_grade_mcq(self.question1, answers)
        
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['points_earned'], Decimal('0.00'))
    
    def test_auto_grade_multi_select_correct(self):
        """Test auto-grading with correct multi-select answers."""
        answers = {str(self.question3.id): ['A', 'B', 'D']}
        
        result = GradingEngine.auto_grade_mcq(self.question3, answers)
        
        self.assertTrue(result['is_correct'])
        self.assertEqual(result['points_earned'], Decimal('20.00'))
    
    def test_auto_grade_multi_select_partial(self):
        """Test auto-grading with partial multi-select answers."""
        answers = {str(self.question3.id): ['A', 'B']}
        
        result = GradingEngine.auto_grade_mcq(self.question3, answers)
        
        # Should be partial credit (2 out of 3 correct)
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['points_earned'], Decimal('13.33'))
    
    def test_grade_quiz_attempt_full(self):
        """Test grading a complete quiz attempt."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='submitted',
            answers={
                str(self.question1.id): 'B',  # Correct
                str(self.question2.id): 'C',  # Correct
                str(self.question3.id): ['A', 'B', 'D'],  # Correct
                str(self.question4.id): 'Essay response here'  # Manual grading needed
            },
            ip_address='127.0.0.1'
        )
        
        result = GradingEngine.grade_quiz_attempt(attempt)
        
        self.assertIn('total_score', result)
        self.assertIn('max_points', result)
        self.assertIn('percentage', result)
        self.assertIn('question_results', result)
        self.assertIn('requires_manual_grading', result)
        
        # Essay question requires manual grading
        self.assertTrue(result['requires_manual_grading'])
        
        # Auto-graded questions should be correct
        self.assertEqual(len(result['question_results']), 4)
    
    def test_grade_quiz_attempt_all_auto(self):
        """Test grading a quiz with only auto-gradable questions."""
        # Remove essay question
        self.question4.delete()
        
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='submitted',
            answers={
                str(self.question1.id): 'B',  # Correct
                str(self.question2.id): 'C',  # Correct
                str(self.question3.id): ['A', 'B', 'D']  # Correct
            },
            ip_address='127.0.0.1'
        )
        
        result = GradingEngine.grade_quiz_attempt(attempt)
        
        self.assertFalse(result['requires_manual_grading'])
        self.assertEqual(result['total_score'], Decimal('45.00'))
        self.assertEqual(result['max_points'], Decimal('45.00'))
        self.assertEqual(result['percentage'], Decimal('100.00'))


class ScoreCalculatorTests(TestCase):
    """Tests for the ScoreCalculator service."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
    
    def test_calculate_course_average(self):
        """Test calculating course average score."""
        quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
        
        # Create grades
        Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=quiz.id,
            score=Decimal('80.00'),
            max_points=Decimal('100.00')
        )
        
        Grade.objects.create(
            user=self.instructor,
            gradable_type='quiz',
            gradable_id=quiz.id,
            score=Decimal('90.00'),
            max_points=Decimal('100.00')
        )
        
        average = ScoreCalculator.calculate_course_average(self.course.id)
        
        self.assertEqual(average, Decimal('85.00'))
    
    def test_calculate_user_course_grade(self):
        """Test calculating a user's overall course grade."""
        quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
        
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        # Create grades
        Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=quiz.id,
            score=Decimal('80.00'),
            max_points=Decimal('100.00')
        )
        
        Grade.objects.create(
            user=self.learner,
            gradable_type='assignment',
            gradable_id=assignment.id,
            score=Decimal('90.00'),
            max_points=Decimal('100.00')
        )
        
        result = ScoreCalculator.calculate_user_course_grade(self.learner.id, self.course.id)
        
        self.assertEqual(result['average_percentage'], Decimal('85.00'))
        self.assertEqual(result['total_score'], Decimal('170.00'))
        self.assertEqual(result['total_max_points'], Decimal('200.00'))


class AttemptServiceTests(TestCase):
    """Tests for the AttemptService."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=2,
            is_published=True
        )
    
    def test_can_start_attempt_allowed(self):
        """Test that a user can start an attempt when under the limit."""
        result = AttemptService.can_start_attempt(self.learner, self.quiz)
        
        self.assertTrue(result['allowed'])
    
    def test_can_start_attempt_max_reached(self):
        """Test that a user cannot start an attempt when max is reached."""
        # Create max attempts
        for i in range(self.quiz.max_attempts):
            QuizAttempt.objects.create(
                user=self.learner,
                quiz=self.quiz,
                status='submitted',
                ip_address='127.0.0.1'
            )
        
        result = AttemptService.can_start_attempt(self.learner, self.quiz)
        
        self.assertFalse(result['allowed'])
        self.assertIn('error', result)
    
    def test_can_start_attempt_unlimited(self):
        """Test that a user can start unlimited attempts when max_attempts is 0."""
        self.quiz.max_attempts = 0
        self.quiz.save()
        
        # Create many attempts
        for i in range(10):
            QuizAttempt.objects.create(
                user=self.learner,
                quiz=self.quiz,
                status='submitted',
                ip_address='127.0.0.1'
            )
        
        result = AttemptService.can_start_attempt(self.learner, self.quiz)
        
        self.assertTrue(result['allowed'])
    
    def test_is_attempt_timed_out(self):
        """Test checking if an attempt has timed out."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='in_progress',
            started_at=timezone.now() - timedelta(minutes=45),  # 45 minutes ago
            ip_address='127.0.0.1'
        )
        
        is_timed_out = AttemptService.is_attempt_timed_out(attempt)
        
        self.assertTrue(is_timed_out)
    
    def test_is_attempt_timed_out_not_expired(self):
        """Test that an attempt is not timed out when within time limit."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='in_progress',
            started_at=timezone.now() - timedelta(minutes=15),  # 15 minutes ago
            ip_address='127.0.0.1'
        )
        
        is_timed_out = AttemptService.is_attempt_timed_out(attempt)
        
        self.assertFalse(is_timed_out)
    
    def test_is_attempt_timed_out_no_limit(self):
        """Test that an attempt never times out when there's no time limit."""
        self.quiz.time_limit_minutes = None
        self.quiz.save()
        
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='in_progress',
            started_at=timezone.now() - timedelta(hours=5),  # 5 hours ago
            ip_address='127.0.0.1'
        )
        
        is_timed_out = AttemptService.is_attempt_timed_out(attempt)
        
        self.assertFalse(is_timed_out)


class SubmissionServiceTests(TestCase):
    """Tests for the SubmissionService."""
    
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
    
    def test_is_late_submission(self):
        """Test checking if a submission is late."""
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            due_date=timezone.now() - timedelta(days=1),  # Due yesterday
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        submission = Submission.objects.create(
            assignment=assignment,
            user=self.learner,
            submitted_text='Late submission',
            submitted_at=timezone.now(),
            status='submitted'
        )
        
        is_late = SubmissionService.is_late_submission(submission)
        
        self.assertTrue(is_late)
    
    def test_is_late_submission_on_time(self):
        """Test that an on-time submission is not late."""
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            due_date=timezone.now() + timedelta(days=1),  # Due tomorrow
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        submission = Submission.objects.create(
            assignment=assignment,
            user=self.learner,
            submitted_text='On-time submission',
            submitted_at=timezone.now(),
            status='submitted'
        )
        
        is_late = SubmissionService.is_late_submission(submission)
        
        self.assertFalse(is_late)
    
    def test_calculate_late_penalty(self):
        """Test calculating late submission penalty."""
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            due_date=timezone.now() - timedelta(days=1),
            max_points=Decimal('100.00'),
            late_submission_policy='penalty',
            late_penalty_percent=Decimal('10.00'),
            is_published=True
        )
        
        submission = Submission.objects.create(
            assignment=assignment,
            user=self.learner,
            submitted_text='Late submission',
            submitted_at=timezone.now(),
            status='submitted'
        )
        
        adjusted_score = SubmissionService.calculate_late_penalty(submission, Decimal('90.00'))
        
        # 90 - (90 * 0.10) = 81
        self.assertEqual(adjusted_score, Decimal('81.00'))
    
    def test_calculate_late_penalty_no_penalty_policy(self):
        """Test that no penalty is applied when policy is 'accept'."""
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            due_date=timezone.now() - timedelta(days=1),
            max_points=Decimal('100.00'),
            late_submission_policy='accept',
            is_published=True
        )
        
        submission = Submission.objects.create(
            assignment=assignment,
            user=self.learner,
            submitted_text='Late submission',
            submitted_at=timezone.now(),
            status='submitted'
        )
        
        adjusted_score = SubmissionService.calculate_late_penalty(submission, Decimal('90.00'))
        
        self.assertEqual(adjusted_score, Decimal('90.00'))


# =============================================================================
# API Tests
# =============================================================================

class QuizAPITests(APITestCase):
    """Tests for Quiz API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
    
    def test_create_quiz(self):
        """Test creating a quiz via API."""
        self.client.force_authenticate(user=self.instructor)
        
        data = {
            'course': str(self.course.id),
            'title': 'New Quiz',
            'description': 'New quiz description',
            'time_limit_minutes': 45,
            'passing_score': '75.00',
            'max_attempts': 2,
            'is_published': False
        }
        
        response = self.client.post('/api/v1/assessments/quizzes/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Quiz')
        self.assertEqual(response.data['time_limit_minutes'], 45)
    
    def test_list_quizzes(self):
        """Test listing quizzes via API."""
        Quiz.objects.create(
            course=self.course,
            title='Quiz 1',
            description='Description 1',
            time_limit_minutes=30,
            is_published=True
        )
        Quiz.objects.create(
            course=self.course,
            title='Quiz 2',
            description='Description 2',
            time_limit_minutes=45,
            is_published=True
        )
        
        self.client.force_authenticate(user=self.learner)
        
        response = self.client.get('/api/v1/assessments/quizzes/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_get_quiz_detail(self):
        """Test getting quiz details via API."""
        quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test description',
            time_limit_minutes=30,
            is_published=True
        )
        
        self.client.force_authenticate(user=self.learner)
        
        response = self.client.get(f'/api/v1/assessments/quizzes/{quiz.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Quiz')


class QuizAttemptAPITests(APITestCase):
    """Tests for QuizAttempt API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
        self.question = Question.objects.create(
            quiz=self.quiz,
            question_text='What is 2+2?',
            question_type='mcq',
            options={'A': '3', 'B': '4', 'C': '5', 'D': '6'},
            correct_answer='B',
            points=Decimal('10.00'),
            order_index=1
        )
    
    def test_start_quiz_attempt(self):
        """Test starting a quiz attempt via API."""
        self.client.force_authenticate(user=self.learner)
        
        response = self.client.post(f'/api/v1/assessments/quizzes/{self.quiz.id}/start/')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('attempt_id', response.data)
        self.assertIn('started_at', response.data)
        self.assertEqual(response.data['time_limit_minutes'], 30)
    
    def test_start_quiz_attempt_max_reached(self):
        """Test that starting an attempt fails when max attempts reached."""
        # Create max attempts
        for i in range(self.quiz.max_attempts):
            QuizAttempt.objects.create(
                user=self.learner,
                quiz=self.quiz,
                status='submitted',
                ip_address='127.0.0.1'
            )
        
        self.client.force_authenticate(user=self.learner)
        
        response = self.client.post(f'/api/v1/assessments/quizzes/{self.quiz.id}/start/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_submit_quiz_attempt(self):
        """Test submitting a quiz attempt via API."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='in_progress',
            ip_address='127.0.0.1'
        )
        
        self.client.force_authenticate(user=self.learner)
        
        data = {
            'answers': {
                str(self.question.id): 'B'  # Correct answer
            }
        }
        
        response = self.client.post(
            f'/api/v1/assessments/attempts/{attempt.id}/submit/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('score', response.data)
        self.assertIn('score_percentage', response.data)
        self.assertTrue(response.data['is_passed'])


class AssignmentAPITests(APITestCase):
    """Tests for Assignment API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
    
    def test_create_assignment(self):
        """Test creating an assignment via API."""
        self.client.force_authenticate(user=self.instructor)
        
        data = {
            'course': str(self.course.id),
            'title': 'New Assignment',
            'description': 'New assignment description',
            'instructions': 'Complete the following tasks...',
            'due_date': (timezone.now() + timedelta(days=7)).isoformat(),
            'max_points': '100.00',
            'is_published': True
        }
        
        response = self.client.post('/api/v1/assessments/assignments/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Assignment')
    
    def test_list_assignments(self):
        """Test listing assignments via API."""
        Assignment.objects.create(
            course=self.course,
            title='Assignment 1',
            description='Description 1',
            max_points=Decimal('100.00'),
            is_published=True
        )
        Assignment.objects.create(
            course=self.course,
            title='Assignment 2',
            description='Description 2',
            max_points=Decimal('50.00'),
            is_published=True
        )
        
        self.client.force_authenticate(user=self.learner)
        
        response = self.client.get('/api/v1/assessments/assignments/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)


class SubmissionAPITests(APITestCase):
    """Tests for Submission API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            due_date=timezone.now() + timedelta(days=7),
            max_points=Decimal('100.00'),
            is_published=True
        )
    
    def test_create_submission(self):
        """Test creating a submission via API."""
        self.client.force_authenticate(user=self.learner)
        
        data = {
            'assignment': str(self.assignment.id),
            'submitted_text': 'This is my submission.',
            'file_urls': ['https://example.com/file1.pdf']
        }
        
        response = self.client.post('/api/v1/assessments/submissions/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['submitted_text'], 'This is my submission.')
    
    def test_submit_assignment_action(self):
        """Test the submit assignment action via API."""
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.learner,
            submitted_text='Draft submission',
            status='draft',
            version=1
        )
        
        self.client.force_authenticate(user=self.learner)
        
        data = {
            'submitted_text': 'Final submission',
            'file_urls': ['https://example.com/file1.pdf']
        }
        
        response = self.client.post(
            f'/api/v1/assessments/assignments/{self.assignment.id}/submit/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'submitted')


class GradeAPITests(APITestCase):
    """Tests for Grade API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
    
    def test_list_grades(self):
        """Test listing grades via API."""
        Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=self.quiz.id,
            score=Decimal('85.00'),
            max_points=Decimal('100.00'),
            graded_by=self.instructor,
            graded_at=timezone.now()
        )
        
        self.client.force_authenticate(user=self.learner)
        
        response = self.client.get('/api/v1/assessments/grades/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_get_user_grades(self):
        """Test getting grades for a specific user via API."""
        Grade.objects.create(
            user=self.learner,
            gradable_type='quiz',
            gradable_id=self.quiz.id,
            score=Decimal('85.00'),
            max_points=Decimal('100.00'),
            graded_by=self.instructor,
            graded_at=timezone.now()
        )
        
        self.client.force_authenticate(user=self.instructor)
        
        response = self.client.get(f'/api/v1/assessments/grades/user/{self.learner.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
    
    def test_grade_submission(self):
        """Test grading a submission via API."""
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        submission = Submission.objects.create(
            assignment=assignment,
            user=self.learner,
            submitted_text='Submission text',
            status='submitted',
            version=1
        )
        
        self.client.force_authenticate(user=self.instructor)
        
        data = {
            'score': '85.00',
            'feedback': 'Great work!'
        }
        
        response = self.client.post(
            f'/api/v1/assessments/submissions/{submission.id}/grade/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], '85.00')
        self.assertEqual(response.data['feedback'], 'Great work!')


class ManualGradingTests(APITestCase):
    """Tests for manual grading workflow."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title='Test Quiz',
            description='Test quiz description',
            time_limit_minutes=30,
            passing_score=70.00,
            max_attempts=3,
            is_published=True
        )
        self.question = Question.objects.create(
            quiz=self.quiz,
            question_text='Essay question',
            question_type='essay',
            points=Decimal('25.00'),
            order_index=1
        )
    
    def test_manual_grade_quiz_attempt(self):
        """Test manually grading a quiz attempt via API."""
        attempt = QuizAttempt.objects.create(
            user=self.learner,
            quiz=self.quiz,
            status='submitted',
            answers={str(self.question.id): 'Essay response'},
            ip_address='127.0.0.1'
        )
        
        self.client.force_authenticate(user=self.instructor)
        
        data = {
            'score': '20.00',
            'feedback': 'Good essay, but could use more detail.'
        }
        
        response = self.client.post(
            f'/api/v1/assessments/attempts/{attempt.id}/grade/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], '20.00')
        self.assertEqual(response.data['feedback'], 'Good essay, but could use more detail.')
    
    def test_get_pending_grading_list(self):
        """Test getting list of items pending manual grading."""
        # Create a submission that needs grading
        assignment = Assignment.objects.create(
            course=self.course,
            title='Test Assignment',
            description='Test assignment description',
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        Submission.objects.create(
            assignment=assignment,
            user=self.learner,
            submitted_text='Submission text',
            status='submitted',
            version=1
        )
        
        self.client.force_authenticate(user=self.instructor)
        
        response = self.client.get('/api/v1/assessments/grades/pending/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AssessmentDashboardAPITests(APITestCase):
    """Tests for Assessment Dashboard API."""
    
    def setUp(self):
        self.client = APIClient()
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            username='instructor',
            password='testpass123'
        )
        self.learner = User.objects.create_user(
            email='learner@example.com',
            username='learner',
            password='testpass123'
        )
        self.course = Course.objects.create(
            title='Test Course',
            slug='test-course',
            description='Test course description',
            instructor=self.instructor,
            status='published'
        )
    
    def test_get_assessment_dashboard(self):
        """Test getting assessment dashboard statistics."""
        # Create some assessment data
        Quiz.objects.create(
            course=self.course,
            title='Quiz 1',
            description='Description',
            time_limit_minutes=30,
            is_published=True
        )
        
        Assignment.objects.create(
            course=self.course,
            title='Assignment 1',
            description='Description',
            max_points=Decimal('100.00'),
            is_published=True
        )
        
        self.client.force_authenticate(user=self.instructor)
        
        response = self.client.get('/api/v1/assessments/dashboard/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_quizzes', response.data)
        self.assertIn('total_assignments', response.data)
        self.assertEqual(response.data['total_quizzes'], 1)
        self.assertEqual(response.data['total_assignments'], 1)
