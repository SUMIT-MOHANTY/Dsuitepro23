import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Create axios instance with default config
const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// Request interceptor - add auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    
    // Log requests in development
    if (import.meta.env.VITE_APP_ENV === 'development') {
      console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.data)
    }
    
    return config
  },
  (error) => {
    console.error('[API Request Error]', error)
    return Promise.reject(error)
  }
)

// Response interceptor - handle errors and token refresh
apiClient.interceptors.response.use(
  (response) => {
    // Log responses in development
    if (import.meta.env.VITE_APP_ENV === 'development') {
      console.log(`[API Response] ${response.config.method?.toUpperCase()} ${response.config.url}`, response.data)
    }
    return response
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    
    // Log errors
    if (import.meta.env.VITE_APP_ENV === 'development') {
      console.error(`[API Error] ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url}`, error.response?.data)
    }
    
    // Handle 401 Unauthorized - token expired
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true
      
      try {
        const refreshToken = localStorage.getItem('refresh_token')
        if (refreshToken) {
          const response = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh/`, {
            refresh: refreshToken,
          })
          
          const { access } = response.data
          localStorage.setItem('access_token', access)
          
          // Retry original request with new token
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access}`
          }
          return apiClient(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed, logout user
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        // Use a custom event to notify the app about logout instead of direct window.location
        window.dispatchEvent(new CustomEvent('auth:logout', { detail: { reason: 'token_refresh_failed' } }))
        return Promise.reject(refreshError)
      }
    }
    
    // Handle other error statuses
    if (error.response) {
      const { status, data } = error.response
      
      switch (status) {
        case 403:
          console.error('Access forbidden:', data)
          break
        case 404:
          console.error('Resource not found:', data)
          break
        case 422:
          console.error('Validation error:', data)
          break
        case 500:
          console.error('Server error:', data)
          break
        default:
          console.error(`HTTP ${status} error:`, data)
      }
    } else if (error.request) {
      console.error('Network error - no response received:', error.request)
    } else {
      console.error('Error setting up request:', error.message)
    }
    
    return Promise.reject(error)
  }
)

export default apiClient
