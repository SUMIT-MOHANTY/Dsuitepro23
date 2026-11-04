"""
Assessment Services for Enterprise LMS
Provides grading engine, attempt management, and submission services.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.assessment.models import (
    Quiz, Question, QuizAttempt, Assignment, Submission, Grade
)

User = get_user_model()
logger = logging.getLogger(__name__)


class GradingEngine:
    """
    Engine for auto-grading assessments.
    Supports MCQ, multi-select, and matching question types.
    """
    
    @staticmethod
    def auto_grade_mcq(question: Question, answer: Any) -> Tuple[Decimal, bool]:
        """
        Auto-grade a multiple choice question.
        
        Args:
            question: The Question instance
            answer: The user's answer (e.g., "A")
            
        Returns:
            Tuple of (points_earned, is_correct)
        """
        if not question.is_auto_gradable():
            return Decimal('0.00'), False
        
        correct_answer = question.correct_answer
        if correct_answer is None:
            return Decimal('0.00'), False
        
        # Normalize answer for comparison
        if isinstance(answer, str):
            answer = answer.strip().upper()
        
        if isinstance(correct_answer, str):
            correct_answer = correct_answer.strip().upper()
        
        is_correct = answer == correct_answer
        points = question.points if is_correct else Decimal('0.00')
        
        return points, is_correct
    
    @staticmethod
    def auto_grade_multi_select(question: Question, answer: Any) -> Tuple[Decimal, bool]:
        """
        Auto-grade a multiple select question.
        
        Args:
            question: The Question instance
            answer: The user's answers (e.g., ["A", "C"])
            
        Returns:
            Tuple of (points_earned, is_correct)
        """
        if not question.is_auto_gradable():
            return Decimal('0.00'), False
        
        correct_answer = question.correct_answer
        if correct_answer is None:
            return Decimal('0.00'), False
        
        # Normalize answers to sets
        if isinstance(answer, str):
            answer_set = set(answer.strip().upper().split(','))
        elif isinstance(answer, list):
            answer_set = set(str(a).strip().upper() for a in answer)
        else:
            return Decimal('0.00'), False
        
        if isinstance(correct_answer, str):
            correct_set = set(correct_answer.strip().upper().split(','))
        elif isinstance(correct_answer, list):
            correct_set = set(str(c).strip().upper() for c in correct_answer)
        else:
            return Decimal('0.00'), False
        
        # Full credit only if exact match
        is_correct = answer_set == correct_set
        points = question.points if is_correct else Decimal('0.00')
        
        return points, is_correct
    
    @staticmethod
    def auto_grade_match(question: Question, answer: Any) -> Tuple[Decimal, bool]:
        """
        Auto-grade a matching question.
        
        Args:
            question: The Question instance
            answer: The user's matches (e.g., {"Item 1": "Match 1", ...})
            
        Returns:
            Tuple of (points_earned, is_correct)
        """
        if not question.is_auto_gradable():
            return Decimal('0.00'), False
        
        correct_answer = question.correct_answer
        if correct_answer is None or not isinstance(answer, dict):
            return Decimal('0.00'), False
        
        # Normalize keys and values for comparison
        answer_normalized = {str(k).strip(): str(v).strip() 
                            for k, v in answer.items()}
        correct_normalized = {str(k).strip(): str(v).strip() 
                            for k, v in correct_answer.items()}
        
        # Full credit only if exact match
        is_correct = answer_normalized == correct_normalized
        points = question.points if is_correct else Decimal('0.00')
        
        return points, is_correct
    
    @classmethod
    def grade_question(cls, question: Question, answer: Any) -> Tuple[Decimal, bool]:
        """
        Grade a single question based on its type.
        
        Args:
            question: The Question instance
            answer: The user's answer
            
        Returns:
            Tuple of (points_earned, is_correct)
        """
        if question.question_type == 'mcq':
            return cls.auto_grade_mcq(question, answer)
        elif question.question_type == 'multi_select':
            return cls.auto_grade_multi_select(question, answer)
        elif question.question_type == 'match':
            return cls.auto_grade_match(question, answer)
        else:
            # Essay and short answer require manual grading
            return Decimal('0.00'), False
    
    @classmethod
    def grade_quiz_attempt(cls, attempt: QuizAttempt) -> Dict[str, Any]:
        """
        Auto-grade all auto-gradable questions in a quiz attempt.
        
        Args:
            attempt: The QuizAttempt instance
            
        Returns:
            Dict with grading results
        """
        answers = attempt.answers or {}
        questions = attempt.quiz.questions.all()
        
        total_score = Decimal('0.00')
        max_points = Decimal('0.00')
        graded_answers = {}
        
        for question in questions:
            max_points += question.points
            answer = answers.get(str(question.id))
            
            if answer is not None and question.is_auto_gradable():
                points, is_correct = cls.grade_question(question, answer)
                total_score += points
                graded_answers[str(question.id)] = {
                    'answer': answer,
                    'points_earned': float(points),
                    'max_points': float(question.points),
                    'is_correct': is_correct
                }
            else:
                # Manual grading required or no answer
                graded_answers[str(question.id)] = {
                    'answer': answer,
                    'points_earned': 0.0,
                    'max_points': float(question.points),
                    'is_correct': False,
                    'requires_manual_grading': not question.is_auto_gradable() and answer is not None
                }
        
        # Calculate percentage
        percentage = Decimal('0.00')
        if max_points > 0:
            percentage = (total_score / max_points) * 100
        
        return {
            'total_score': total_score,
            'max_points': max_points,
            'percentage': percentage,
            'graded_answers': graded_answers,
            'requires_manual_grading': any(
                a.get('requires_manual_grading', False) 
                for a in graded_answers.values()
            )
        }


class ManualGradingQueue:
    """
    Service for managing manual grading queue.
    """
    
    @staticmethod
    def queue_assignment_for_manual_grading(submission: Submission) -> None:
        """
        Queue an assignment submission for manual grading.
        
        Args:
            submission: The Submission instance
        """
        submission.status = 'submitted'
        submission.save(update_fields=['status'])
        
        logger.info(
            f"Assignment {submission.assignment.id} submission "
            f"{submission.id} queued for manual grading"
        )
    
    @staticmethod
    def get_pending_submissions(course_id: Optional[str] = None) -> List[Submission]:
        """
        Get all submissions pending manual grading.
        
        Args:
            course_id: Optional course filter
            
        Returns:
            List of Submission instances
        """
        queryset = Submission.objects.filter(status='submitted')
        
        if course_id:
            queryset = queryset.filter(assignment__course_id=course_id)
        
        return list(queryset.select_related('assignment', 'user'))
    
    @staticmethod
    def get_pending_quiz_attempts(course_id: Optional[str] = None) -> List[QuizAttempt]:
        """
        Get all quiz attempts with questions requiring manual grading.
        
        Args:
            course_id: Optional course filter
            
        Returns:
            List of QuizAttempt instances
        """
        # Get attempts that have been submitted but not fully graded
        queryset = QuizAttempt.objects.filter(
            status='submitted'
        ).select_related('quiz', 'user')
        
        if course_id:
            queryset = queryset.filter(quiz__course_id=course_id)
        
        # Filter for attempts with essay/short answer questions
        attempts_needing_grading = []
        for attempt in queryset:
            answers = attempt.answers or {}
            questions = attempt.quiz.questions.filter(
                question_type__in=['essay', 'short_answer']
            )
            
            for question in questions:
                if str(question.id) in answers:
                    attempts_needing_grading.append(attempt)
                    break
        
        return attempts_needing_grading


class ScoreCalculator:
    """
    Calculator for weighted scores and grade aggregation.
    """
    
    @staticmethod
    def calculate_weighted_score(
        scores: List[Tuple[Decimal, Decimal]]
    ) -> Decimal:
        """
        Calculate weighted average score.
        
        Args:
            scores: List of (score, weight) tuples
            
        Returns:
            Weighted average score
        """
        if not scores:
            return Decimal('0.00')
        
        total_weighted_score = Decimal('0.00')
        total_weight = Decimal('0.00')
        
        for score, weight in scores:
            total_weighted_score += score * weight
            total_weight += weight
        
        if total_weight == 0:
            return Decimal('0.00')
        
        return total_weighted_score / total_weight
    
    @staticmethod
    def calculate_course_grade(user_id: str, course_id: str) -> Dict[str, Any]:
        """
        Calculate overall grade for a user in a course.
        
        Args:
            user_id: The user's ID
            course_id: The course ID
            
        Returns:
            Dict with grade breakdown
        """
        # Get all grades for user in course
        quiz_grades = Grade.objects.filter(
            user_id=user_id,
            gradable_type='quiz',
            gradable_id__in=Quiz.objects.filter(course_id=course_id).values('id')
        )
        
        assignment_grades = Grade.objects.filter(
            user_id=user_id,
            gradable_type='assignment',
            gradable_id__in=Assignment.objects.filter(course_id=course_id).values('id')
        )
        
        quiz_scores = [(g.percentage, Decimal('1.00')) for g in quiz_grades]
        assignment_scores = [(g.percentage, Decimal('1.00')) for g in assignment_grades]
        
        quiz_avg = ScoreCalculator.calculate_weighted_score(quiz_scores) if quiz_scores else Decimal('0.00')
        assignment_avg = ScoreCalculator.calculate_weighted_score(assignment_scores) if assignment_scores else Decimal('0.00')
        
        # Overall grade (equal weighting between quizzes and assignments)
        if quiz_scores and assignment_scores:
            overall = (quiz_avg + assignment_avg) / 2
        elif quiz_scores:
            overall = quiz_avg
        elif assignment_scores:
            overall = assignment_avg
        else:
            overall = Decimal('0.00')
        
        return {
            'quiz_average': float(quiz_avg),
            'assignment_average': float(assignment_avg),
            'overall_grade': float(overall),
            'quiz_count': len(quiz_scores),
            'assignment_count': len(assignment_scores),
            'letter_grade': ScoreCalculator.percentage_to_letter(overall)
        }
    
    @staticmethod
    def percentage_to_letter(percentage: Decimal) -> str:
        """
        Convert percentage to letter grade.
        
        Args:
            percentage: Score percentage
            
        Returns:
            Letter grade
        """
        if percentage >= 97:
            return 'A+'
        elif percentage >= 93:
            return 'A'
        elif percentage >= 90:
            return 'A-'
        elif percentage >= 87:
            return 'B+'
        elif percentage >= 83:
            return 'B'
        elif percentage >= 80:
            return 'B-'
        elif percentage >= 77:
            return 'C+'
        elif percentage >= 73:
            return 'C'
        elif percentage >= 70:
            return 'C-'
        elif percentage >= 67:
            return 'D+'
        elif percentage >= 63:
            return 'D'
        elif percentage >= 60:
            return 'D-'
        else:
            return 'F'


class AttemptService:
    """
    Service for managing quiz attempts with time limits and attempt restrictions.
    """
    
    @staticmethod
    def can_start_attempt(user: User, quiz: Quiz) -> Tuple[bool, Optional[str]]:
        """
        Check if user can start a new attempt on this quiz.
        
        Args:
            user: The User instance
            quiz: The Quiz instance
            
        Returns:
            Tuple of (can_start, error_message)
        """
        if not quiz.is_published:
            return False, "Quiz is not published"
        
        # Check for existing in-progress attempt
        existing = QuizAttempt.objects.filter(
            user=user,
            quiz=quiz,
            status='in_progress'
        ).first()
        
        if existing:
            # Check if time limit exceeded
            if quiz.time_limit_minutes:
                time_limit = timedelta(minutes=quiz.time_limit_minutes)
                elapsed = timezone.now() - existing.started_at
                if elapsed > time_limit:
                    # Mark as expired
                    existing.status = 'expired'
                    existing.save(update_fields=['status'])
                else:
                    return False, "You have an in-progress attempt"
            else:
                return False, "You have an in-progress attempt"
        
        # Check max attempts
        if quiz.max_attempts > 0:
            attempt_count = QuizAttempt.objects.filter(
                user=user,
                quiz=quiz,
                status__in=['submitted', 'graded']
            ).count()
            if attempt_count >= quiz.max_attempts:
                return False, f"Maximum attempts ({quiz.max_attempts}) reached"
        
        return True, None
    
    @staticmethod
    def start_attempt(user: User, quiz: Quiz, ip_address: str = None, 
                     user_agent: str = '') -> QuizAttempt:
        """
        Start a new quiz attempt.
        
        Args:
            user: The User instance
            quiz: The Quiz instance
            ip_address: User's IP address
            user_agent: User agent string
            
        Returns:
            The new QuizAttempt instance
        """
        can_start, error = AttemptService.can_start_attempt(user, quiz)
        if not can_start:
            raise ValueError(error)
        
        attempt = QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            status='in_progress',
            ip_address=ip_address,
            user_agent=user_agent,
            answers={}
        )
        
        logger.info(f"Quiz attempt started: {attempt.id} for user {user.email}")
        return attempt
    
    @staticmethod
    def is_time_expired(attempt: QuizAttempt) -> bool:
        """
        Check if the attempt's time limit has expired.
        
        Args:
            attempt: The QuizAttempt instance
            
        Returns:
            True if time has expired
        """
        if not attempt.quiz.time_limit_minutes:
            return False
        
        time_limit = timedelta(minutes=attempt.quiz.time_limit_minutes)
        elapsed = timezone.now() - attempt.started_at
        return elapsed > time_limit
    
    @staticmethod
    def submit_attempt(attempt: QuizAttempt, answers: Dict[str, Any],
                      ip_address: str = None) -> Dict[str, Any]:
        """
        Submit a quiz attempt for grading.
        
        Args:
            attempt: The QuizAttempt instance
            answers: Dictionary of question_id: answer pairs
            ip_address: User's IP address
            
        Returns:
            Dict with submission results
        """
        if attempt.status != 'in_progress':
            raise ValueError("Attempt is not in progress")
        
        # Check time limit
        if AttemptService.is_time_expired(attempt):
            attempt.status = 'expired'
            attempt.save(update_fields=['status'])
            raise ValueError("Time limit exceeded")
        
        with transaction.atomic():
            attempt.answers = answers
            attempt.submitted_at = timezone.now()
            
            # Auto-grade the attempt
            grading_result = GradingEngine.grade_quiz_attempt(attempt)
            
            attempt.score = grading_result['total_score']
            attempt.score_percentage = grading_result['percentage']
            
            # Set status based on whether manual grading is needed
            if grading_result['requires_manual_grading']:
                attempt.status = 'submitted'
            else:
                attempt.status = 'graded'
            
            attempt.save()
            
            # Create or update grade record
            Grade.objects.update_or_create(
                user=attempt.user,
                gradable_type='quiz',
                gradable_id=attempt.quiz.id,
                attempt_id=attempt.id,
                defaults={
                    'score': grading_result['total_score'],
                    'max_points': grading_result['max_points'],
                    'percentage': grading_result['percentage'],
                    'is_auto_graded': not grading_result['requires_manual_grading'],
                    'graded_at': timezone.now() if not grading_result['requires_manual_grading'] else None
                }
            )
        
        logger.info(f"Quiz attempt submitted: {attempt.id}")
        
        return {
            'attempt_id': attempt.id,
            'score': float(grading_result['total_score']),
            'score_percentage': float(grading_result['percentage']),
            'is_passed': attempt.is_passed,
            'status': attempt.status,
            'requires_manual_grading': grading_result['requires_manual_grading']
        }


class SubmissionService:
    """
    Service for managing assignment submissions with late policy enforcement.
    """
    
    @staticmethod
    def can_submit(user: User, assignment: Assignment) -> Tuple[bool, Optional[str]]:
        """
        Check if user can submit to this assignment.
        
        Args:
            user: The User instance
            assignment: The Assignment instance
            
        Returns:
            Tuple of (can_submit, error_message)
        """
        if not assignment.is_published:
            return False, "Assignment is not published"
        
        # Check availability window
        now = timezone.now()
        if assignment.available_from and now < assignment.available_from:
            return False, "Assignment is not yet available"
        
        if assignment.available_until and now > assignment.available_until:
            return False, "Assignment is no longer available"
        
        # Check late submission policy
        if assignment.due_date and now > assignment.due_date:
            if assignment.late_submission_policy == 'no_late':
                return False, "Assignment deadline has passed"
        
        return True, None
    
    @staticmethod
    def is_late_submission(submission: Submission) -> bool:
        """
        Check if a submission is late.
        
        Args:
            submission: The Submission instance
            
        Returns:
            True if submission is late
        """
        if not submission.submitted_at or not submission.assignment.due_date:
            return False
        
        due_date = submission.assignment.due_date
        
        # Apply grace period if configured
        if submission.assignment.late_submission_policy == 'grace_period':
            grace_hours = submission.assignment.grace_period_hours or 0
            due_date = due_date + timedelta(hours=grace_hours)
        
        return submission.submitted_at > due_date
    
    @staticmethod
    def calculate_late_penalty(submission: Submission) -> Decimal:
        """
        Calculate late submission penalty.
        
        Args:
            submission: The Submission instance
            
        Returns:
            Penalty percentage (0-100)
        """
        if not SubmissionService.is_late_submission(submission):
            return Decimal('0.00')
        
        policy = submission.assignment.late_submission_policy
        
        if policy == 'no_late':
            return Decimal('100.00')  # No credit
        elif policy == 'accept':
            return Decimal('0.00')  # No penalty
        elif policy == 'penalty':
            return submission.assignment.late_penalty_percent or Decimal('10.00')
        elif policy == 'grace_period':
            # Check if within grace period
            due_date = submission.assignment.due_date
            grace_hours = submission.assignment.grace_period_hours or 0
            grace_end = due_date + timedelta(hours=grace_hours)
            
            if submission.submitted_at <= grace_end:
                return Decimal('0.00')
            else:
                return submission.assignment.late_penalty_percent or Decimal('10.00')
        
        return Decimal('0.00')
    
    @staticmethod
    def create_submission(user: User, assignment: Assignment,
                         submitted_text: str = '',
                         file_urls: List[str] = None,
                         ip_address: str = None) -> Submission:
        """
        Create a new assignment submission.
        
        Args:
            user: The User instance
            assignment: The Assignment instance
            submitted_text: Text content of submission
            file_urls: List of uploaded file URLs
            ip_address: User's IP address
            
        Returns:
            The new Submission instance
        """
        can_submit, error = SubmissionService.can_submit(user, assignment)
        if not can_submit:
            raise ValueError(error)
        
        # Check for existing draft and increment version
        previous = Submission.objects.filter(
            user=user,
            assignment=assignment
        ).order_by('-version').first()
        
        version = 1
        previous_id = None
        if previous:
            version = previous.version + 1
            previous_id = previous.id
        
        now = timezone.now()
        
        # Determine status based on lateness
        status = 'draft'
        if assignment.due_date and now > assignment.due_date:
            if assignment.late_submission_policy == 'no_late':
                raise ValueError("Assignment deadline has passed")
            status = 'late'
        
        submission = Submission.objects.create(
            user=user,
            assignment=assignment,
            submitted_text=submitted_text,
            file_urls=file_urls or [],
            submitted_at=now,
            status=status,
            version=version,
            previous_submission_id=previous_id,
            ip_address=ip_address
        )
        
        logger.info(f"Assignment submission created: {submission.id}")
        return submission
    
    @staticmethod
    def finalize_submission(submission: Submission) -> None:
        """
        Finalize a submission (change from draft to submitted).
        
        Args:
            submission: The Submission instance
        """
        if submission.status != 'draft':
            return
        
        submission.status = 'submitted'
        submission.submitted_at = timezone.now()
        submission.save(update_fields=['status', 'submitted_at'])
        
        # Queue for manual grading
        ManualGradingQueue.queue_assignment_for_manual_grading(submission)
    
    @staticmethod
    def grade_submission(submission: Submission, score: Decimal,
                        feedback: str = '', graded_by: User = None) -> Grade:
        """
        Grade an assignment submission.
        
        Args:
            submission: The Submission instance
            score: The score achieved
            feedback: Instructor feedback
            graded_by: The User who graded
            
        Returns:
            The Grade instance
        """
        # Apply late penalty
        penalty = SubmissionService.calculate_late_penalty(submission)
        adjusted_score = score * (1 - penalty / 100)
        
        with transaction.atomic():
            submission.status = 'graded'
            submission.save(update_fields=['status'])
            
            grade, created = Grade.objects.update_or_create(
                user=submission.user,
                gradable_type='assignment',
                gradable_id=submission.assignment.id,
                attempt_id=submission.id,
                defaults={
                    'score': adjusted_score,
                    'max_points': submission.assignment.max_points,
                    'feedback': feedback,
                    'graded_by': graded_by,
                    'graded_at': timezone.now(),
                    'is_auto_graded': False
                }
            )
        
        logger.info(f"Submission graded: {submission.id} with score {adjusted_score}")
        return grade
