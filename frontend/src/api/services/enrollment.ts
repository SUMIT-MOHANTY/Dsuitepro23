import apiClient from '../client'

// Types
export interface Enrollment {
  id: string
  user_id: string
  course_id: string
  course_title: string
  course_cover?: string
  status: 'pending' | 'active' | 'completed' | 'dropped' | 'suspended'
  progress_percent: number
  completed_lessons: number
  total_lessons: number
  enrolled_at: string
  started_at?: string
  completed_at?: string
  last_accessed_at?: string
  certificate_issued: boolean
  certificate_id?: string
}

export interface LessonProgress {
  id: string
  enrollment_id: string
  lesson_id: string
  lesson_title: string
  status: 'not_started' | 'in_progress' | 'completed'
  progress_percent: number
  time_spent_seconds: number
  started_at?: string
  completed_at?: string
  last_accessed_at?: string
}

export interface ProgressUpdate {
  lesson_id: string
  status?: LessonProgress['status']
  progress_percent?: number
  time_spent_seconds?: number
}

export interface LearningPath {
  id: string
  title: string
  description?: string
  is_published: boolean
  estimated_duration_hours: number
  course_count: number
  courses: Array<{
    course_id: string
    order_index: number
    is_required: boolean
  }>
}

export interface LearningPathEnrollment {
  id: string
  learning_path_id: string
  learning_path_title: string
  status: 'active' | 'completed' | 'dropped'
  progress_percent: number
  enrolled_at: string
  completed_at?: string
}

export interface EnrollmentNote {
  id: string
  enrollment_id: string
  note: string
  created_by: string
  created_at: string
}

// Enrollment Service
export const enrollmentService = {
  // Enrollments
  getEnrollments: async (params?: { status?: string; course?: string }): Promise<{ results: Enrollment[]; count: number }> => {
    const response = await apiClient.get('/enrollments/', { params })
    return response.data
  },
  
  getEnrollment: async (id: string): Promise<Enrollment> => {
    const response = await apiClient.get(`/enrollments/${id}/`)
    return response.data
  },
  
  createEnrollment: async (courseId: string): Promise<Enrollment> => {
    const response = await apiClient.post('/enrollments/', { course_id: courseId })
    return response.data
  },
  
  updateEnrollment: async (id: string, data: Partial<Enrollment>): Promise<Enrollment> => {
    const response = await apiClient.patch(`/enrollments/${id}/`, data)
    return response.data
  },
  
  dropEnrollment: async (id: string): Promise<void> => {
    await apiClient.post(`/enrollments/${id}/drop/`)
  },

  completeEnrollment: async (id: string): Promise<Enrollment> => {
    const response = await apiClient.post(`/enrollments/${id}/complete/`)
    return response.data
  },
  
  // Progress
  getProgress: async (enrollmentId: string): Promise<{ enrollment: Enrollment; lesson_progress: LessonProgress[] }> => {
    const response = await apiClient.get(`/enrollments/${enrollmentId}/progress/`)
    return response.data
  },
  
  updateProgress: async (enrollmentId: string, data: ProgressUpdate): Promise<LessonProgress> => {
    const response = await apiClient.post(`/enrollments/${enrollmentId}/progress/`, data)
    return response.data
  },
  
  getLessonProgress: async (enrollmentId: string, lessonId: string): Promise<LessonProgress> => {
    const response = await apiClient.get(`/enrollments/${enrollmentId}/progress/${lessonId}/`)
    return response.data
  },
  
  // Learning Paths
  getLearningPaths: async (): Promise<{ results: LearningPath[]; count: number }> => {
    const response = await apiClient.get('/learning-paths/')
    return response.data
  },
  
  getLearningPath: async (id: string): Promise<LearningPath> => {
    const response = await apiClient.get(`/learning-paths/${id}/`)
    return response.data
  },
  
  enrollInLearningPath: async (learningPathId: string): Promise<LearningPathEnrollment> => {
    const response = await apiClient.post(`/learning-paths/${learningPathId}/enroll/`)
    return response.data
  },
  
  getLearningPathEnrollments: async (): Promise<{ results: LearningPathEnrollment[]; count: number }> => {
    const response = await apiClient.get('/learning-paths/enrollments/')
    return response.data
  },
  
  // Enrollment Notes (for instructors/admins)
  getEnrollmentNotes: async (enrollmentId: string): Promise<EnrollmentNote[]> => {
    const response = await apiClient.get(`/enrollments/${enrollmentId}/notes/`)
    return response.data.results || response.data
  },
  
  addEnrollmentNote: async (enrollmentId: string, note: string): Promise<EnrollmentNote> => {
    const response = await apiClient.post(`/enrollments/${enrollmentId}/notes/`, { note })
    return response.data
  },
  
  // Stats
  getEnrollmentStats: async (): Promise<{
    total_enrollments: number
    active_enrollments: number
    completed_enrollments: number
    average_progress: number
    certificates_earned: number
  }> => {
    const response = await apiClient.get('/enrollments/stats/')
    return response.data
  },
}

// Re-export types for convenience
export type { Enrollment, LessonProgress, ProgressUpdate, LearningPath, LearningPathEnrollment, EnrollmentNote }
