/**
 * Authentication API Module
 * 
 * Handles all authentication-related API calls including login, register,
 * password reset, token refresh, and user profile management.
 */

import apiClient from './client';

// ============================================
// Types
// ============================================

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role?: 'learner' | 'instructor' | 'admin';
}

export interface Tokens {
  access: string;
  refresh: string;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'admin' | 'instructor' | 'learner';
  is_active: boolean;
  avatar?: string;
}

export interface LoginResponse {
  tokens: Tokens;
  user: User;
}

export interface RegisterResponse {
  tokens: Tokens;
  user: User;
  message: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  password: string;
}

export interface PasswordChangeData {
  current_password: string;
  new_password: string;
}

export interface UpdateProfileData {
  first_name?: string;
  last_name?: string;
  bio?: string;
  phone_number?: string;
}

export interface Notification {
  id: string;
  user: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  is_read: boolean;
  action_url?: string;
  created_at: string;
}

export interface Enrollment {
  id: string;
  course: string;
  status: 'active' | 'completed' | 'dropped' | 'suspended';
  progress: number;
  started_at: string;
  completed_at?: string;
  last_accessed_at: string;
}

export interface ProgressRecord {
  id: string;
  enrollment: string;
  lesson: string;
  is_completed: boolean;
  completed_at?: string;
  time_spent: number;
  last_position?: number;
}

export interface Certificate {
  id: string;
  enrollment: string;
  certificate_number: string;
  issued_at: string;
  pdf_url?: string;
  is_verified: boolean;
}

// ============================================
// Auth API Functions
// ============================================

/**
 * Login with email and password
 */
export const login = async (credentials: LoginCredentials): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/auth/login/', credentials);
  return response.data;
};

/**
 * Register a new user
 */
export const register = async (data: RegisterData): Promise<RegisterResponse> => {
  const response = await apiClient.post<RegisterResponse>('/auth/register/', data);
  return response.data;
};

/**
 * Logout the current user
 */
export const logout = async (): Promise<void> => {
  try {
    await apiClient.post('/auth/logout/');
  } finally {
    // Clear tokens regardless of API response
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }
};

/**
 * Refresh the access token
 */
export const refreshToken = async (): Promise<Tokens> => {
  const refresh = localStorage.getItem('refresh_token');
  if (!refresh) {
    throw new Error('No refresh token available');
  }
  
  const response = await apiClient.post<Tokens>('/auth/refresh/', { refresh });
  
  // Update stored tokens
  if (response.data.access) {
    localStorage.setItem('access_token', response.data.access);
  }
  if (response.data.refresh) {
    localStorage.setItem('refresh_token', response.data.refresh);
  }
  
  return response.data;
};

/**
 * Request password reset
 */
export const requestPasswordReset = async (data: PasswordResetRequest): Promise<{ message: string }> => {
  const response = await apiClient.post<{ message: string }>('/auth/password-reset-request/', data);
  return response.data;
};

/**
 * Confirm password reset with token
 */
export const confirmPasswordReset = async (data: PasswordResetConfirm): Promise<{ message: string }> => {
  const response = await apiClient.post<{ message: string }>('/auth/password-reset-confirm/', data);
  return response.data;
};

/**
 * Verify email address
 */
export const verifyEmail = async (token: string): Promise<{ message: string }> => {
  const response = await apiClient.post<{ message: string }>('/auth/verify-email/', { token });
  return response.data;
};

/**
 * Resend verification email
 */
export const resendVerification = async (): Promise<{ message: string }> => {
  const response = await apiClient.post<{ message: string }>('/auth/resend-verification/');
  return response.data;
};

// ============================================
// User API Functions
// ============================================

/**
 * Get current user profile
 */
export const getCurrentUser = async (): Promise<User> => {
  const response = await apiClient.get<User>('/users/me/');
  return response.data;
};

/**
 * Update current user profile
 */
export const updateProfile = async (data: UpdateProfileData): Promise<User> => {
  const response = await apiClient.patch<User>('/users/me/', data);
  return response.data;
};

/**
 * Upload user avatar
 */
export const uploadAvatar = async (file: File): Promise<{ avatar_url: string }> => {
  const formData = new FormData();
  formData.append('avatar', file);
  
  const response = await apiClient.post<{ avatar_url: string }>('/users/me/avatar/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

/**
 * Change password
 */
export const changePassword = async (data: PasswordChangeData): Promise<{ message: string }> => {
  const response = await apiClient.post<{ message: string }>('/users/me/password/', data);
  return response.data;
};

// ============================================
// User Data API Functions
// ============================================

/**
 * Get user enrollments
 */
export const getUserEnrollments = async (): Promise<Enrollment[]> => {
  const response = await apiClient.get<Enrollment[]>('/users/me/enrollments/');
  return response.data;
};

/**
 * Get user progress
 */
export const getUserProgress = async (): Promise<ProgressRecord[]> => {
  const response = await apiClient.get<ProgressRecord[]>('/users/me/progress/');
  return response.data;
};

/**
 * Get user certificates
 */
export const getUserCertificates = async (): Promise<Certificate[]> => {
  const response = await apiClient.get<Certificate[]>('/users/me/certificates/');
  return response.data;
};

/**
 * Get user notifications
 */
export const getUserNotifications = async (): Promise<Notification[]> => {
  const response = await apiClient.get<Notification[]>('/users/me/notifications/');
  return response.data;
};

/**
 * Mark notification as read
 */
export const markNotificationRead = async (notificationId: string): Promise<void> => {
  await apiClient.patch(`/users/me/notifications/${notificationId}/read/`, {});
};

/**
 * Mark all notifications as read
 */
export const markAllNotificationsRead = async (): Promise<void> => {
  await apiClient.post('/users/me/notifications/read-all/', {});
};

// ============================================
// OAuth API Functions
// ============================================

/**
 * Get available OAuth providers
 */
export const getOAuthProviders = async (): Promise<{ providers: string[] }> => {
  const response = await apiClient.get<{ providers: string[] }>('/auth/oauth/providers/');
  return response.data;
};

/**
 * Handle OAuth callback
 */
export const handleOAuthCallback = async (provider: string, code: string): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/auth/oauth/callback/', { provider, code });
  return response.data;
};

// ============================================
// Session Management
// ============================================

/**
 * Get active user sessions
 */
export const getUserSessions = async (): Promise<Array<{
  id: string;
  device: string;
  browser: string;
  ip_address: string;
  created_at: string;
  last_active: string;
  is_current: boolean;
}>> => {
  const response = await apiClient.get<Array<{
    id: string;
    device: string;
    browser: string;
    ip_address: string;
    created_at: string;
    last_active: string;
    is_current: boolean;
  }>>('/users/me/sessions/');
  return response.data;
};

/**
 * Revoke a session
 */
export const revokeSession = async (sessionId: string): Promise<void> => {
  await apiClient.delete(`/users/me/sessions/${sessionId}/`);
};

// ============================================
// Auth Service Object
// ============================================

export const authApi = {
  // Auth
  login,
  register,
  logout,
  refreshToken,
  requestPasswordReset,
  confirmPasswordReset,
  verifyEmail,
  resendVerification,
  
  // User
  getCurrentUser,
  updateProfile,
  uploadAvatar,
  changePassword,
  
  // User Data
  getUserEnrollments,
  getUserProgress,
  getUserCertificates,
  getUserNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  
  // OAuth
  getOAuthProviders,
  handleOAuthCallback,
  
  // Sessions
  getUserSessions,
  revokeSession,
};

export default authApi;
