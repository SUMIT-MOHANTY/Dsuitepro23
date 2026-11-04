import apiClient from '../client'

// Types
export interface Quiz {
  id: string
  title: string
  description?: string
  course_id?: string
  lesson_id?: string
  time_limit_minutes?: number
  passing_score: number
  max_attempts?: number
  shuffle_questions: boolean
  show_correct_answers: boolean
  is_published: boolean
  question_count: number
  total_points: number
  created_at: string
}

export interface Question {
  id: string
  quiz_id: string
  question_type: 'multiple_choice' | 'multiple_select' | 'short_answer' | 'essay' | 'true_false'
  question_text: string
  explanation?: string
  points: number
  order_index: number
  options?: QuestionOption[]
  correct_answer?: string | string[]
}

export interface QuestionOption {
  id: string
  text: string
  is_correct: boolean
  order_index: number
}

export interface QuizAttempt {
  id: string
  quiz_id: string
  user_id: string
  started_at: string
  submitted_at?: string
  status: 'in_progress' | 'submitted' | 'graded'
  score?: number
  max_score: number
  percentage?: number
  passed?: boolean
  time_spent_seconds: number
  answers: Answer[]
  ip_address: string
}

export interface Answer {
  id: string
  question_id: string
  question_text: string
  selected_options?: string[]
  text_answer?: string
  is_correct?: boolean
  points_earned: number
  feedback?: string
}

export interface Assignment {
  id: string
  title: string
  description?: string
  course_id?: string
  lesson_id?: string
  due_date?: string
  max_points: number
  allowed_file_types?: string[]
  max_file_size_mb: number
  is_published: boolean
  submission_count: number
  created_at: string
}

export interface Submission {
  id: string
  assignment_id: string
  user_id: string
  submitted_at: string
  status: 'submitted' | 'graded' | 'returned'
  file_url?: string
  text_submission?: string
  score?: number
  feedback?: string
  graded_at?: string
  graded_by?: string
}

export interface Grade {
  id: string
  user_id: string
  course_id?: string
  enrollment_id?: string
  assessment_type: 'quiz' | 'assignment'
  assessment_id: string
  assessment_title: string
  score: number
  max_score: number
  percentage: number
  letter_grade?: string
  feedback?: string
  graded_at: string
}

// Assessment Service
export const assessmentService = {
  // Quizzes
  getQuizzes: async (params?: { course?: string; lesson?: string }): Promise<{ results: Quiz[]; count: number }> => {
    const response = await apiClient.get('/quizzes/', { params })
    return response.data
  },
  
  getQuiz: async (id: string): Promise<Quiz> => {
    const response = await apiClient.get(`/quizzes/${id}/`)
    return response.data
  },
  
  getQuizWithQuestions: async (id: string): Promise<Quiz & { questions: Question[] }> => {
    const response = await apiClient.get(`/quizzes/${id}/detail/`)
    return response.data
  },
  
  // Quiz Attempts
  startAttempt: async (quizId: string): Promise<QuizAttempt> => {
    const response = await apiClient.post(`/quizzes/${quizId}/attempt/`)
    return response.data
  },
  
  getAttempt: async (quizId: string, attemptId: string): Promise<QuizAttempt> => {
    const response = await apiClient.get(`/quizzes/${quizId}/attempts/${attemptId}/`)
    return response.data
  },
  
  getMyAttempts: async (quizId: string): Promise<QuizAttempt[]> => {
    const response = await apiClient.get(`/quizzes/${quizId}/my-attempts/`)
    return response.data.results || response.data
  },
  
  submitAnswer: async (quizId: string, attemptId: string, questionId: string, answer: { selected_options?: string[]; text_answer?: string }): Promise<Answer> => {
    const response = await apiClient.post(`/quizzes/${quizId}/attempts/${attemptId}/answers/`, {
      question_id: questionId,
      ...answer,
    })
    return response.data
  },
  
  submitQuiz: async (quizId: string, attemptId: string): Promise<QuizAttempt> => {
    const response = await apiClient.post(`/quizzes/${quizId}/attempts/${attemptId}/submit/`)
    return response.data
  },
  
  // Assignments
  getAssignments: async (params?: { course?: string; lesson?: string }): Promise<{ results: Assignment[]; count: number }> => {
    const response = await apiClient.get('/assignments/', { params })
    return response.data
  },
  
  getAssignment: async (id: string): Promise<Assignment> => {
    const response = await apiClient.get(`/assignments/${id}/`)
    return response.data
  },
  
  // Submissions
  getMySubmissions: async (assignmentId: string): Promise<Submission[]> => {
    const response = await apiClient.get(`/assignments/${assignmentId}/my-submissions/`)
    return response.data.results || response.data
  },
  
  submitAssignment: async (assignmentId: string, data: { text_submission?: string; file?: File }): Promise<Submission> => {
    const formData = new FormData()
    if (data.text_submission) {
      formData.append('text_submission', data.text_submission)
    }
    if (data.file) {
      formData.append('file', data.file)
    }
    
    const response = await apiClient.post(`/assignments/${assignmentId}/submit/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },
  
  // Grades
  getMyGrades: async (): Promise<{ results: Grade[]; count: number }> => {
    const response = await apiClient.get('/grades/my-grades/')
    return response.data
  },
  
  getGrade: async (gradeId: string): Promise<Grade> => {
    const response = await apiClient.get(`/grades/${gradeId}/`)
    return response.data
  },
  
  // Dashboard
  getAssessmentDashboard: async (): Promise<{
    total_quizzes_taken: number
    average_quiz_score: number
    total_assignments_submitted: number
    pending_assignments: number
    overall_grade_average: number
  }> => {
    const response = await apiClient.get('/assessments/dashboard/')
    return response.data
  },
}

// Re-export types for convenience
export type { Quiz, Question, QuestionOption, QuizAttempt, Answer, Assignment, Submission, Grade }
