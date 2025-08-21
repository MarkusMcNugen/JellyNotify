import axios from 'axios'
import toast from 'react-hot-toast'
import logger from './logger'

// Create axios instance with default config
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Track request timing
const requestTimings = new Map()

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Generate unique request ID
    const requestId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    config.requestId = requestId
    
    // Start timing
    requestTimings.set(requestId, performance.now())
    
    // Log the request
    logger.debug(`API Request: ${config.method?.toUpperCase()} ${config.url}`, {
      method: config.method,
      url: config.url,
      params: config.params,
      data: config.data,
      headers: config.headers,
      requestId
    })
    
    // Add timestamp to prevent caching
    if (config.method === 'get') {
      config.params = {
        ...config.params,
        _t: Date.now(),
      }
    }
    return config
  },
  (error) => {
    logger.error('API Request Error', {
      message: error.message,
      stack: error.stack
    })
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => {
    // Calculate request duration
    const requestId = response.config.requestId
    let duration = 0
    if (requestId && requestTimings.has(requestId)) {
      duration = performance.now() - requestTimings.get(requestId)
      requestTimings.delete(requestId)
    }
    
    // Log successful response
    logger.debug(`API Response: ${response.config.method?.toUpperCase()} ${response.config.url}`, {
      status: response.status,
      statusText: response.statusText,
      duration: `${duration.toFixed(2)}ms`,
      requestId,
      dataSize: JSON.stringify(response.data).length
    })
    
    return response
  },
  async (error) => {
    const originalRequest = error.config
    
    // Calculate request duration even for errors
    const requestId = originalRequest?.requestId
    let duration = 0
    if (requestId && requestTimings.has(requestId)) {
      duration = performance.now() - requestTimings.get(requestId)
      requestTimings.delete(requestId)
    }
    
    // Log the error
    const errorDetails = {
      method: originalRequest?.method,
      url: originalRequest?.url,
      status: error.response?.status,
      statusText: error.response?.statusText,
      duration: `${duration.toFixed(2)}ms`,
      requestId,
      message: error.message,
      responseData: error.response?.data
    }
    
    // Handle 401 errors (unauthorized)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      
      logger.info('Token expired, attempting refresh', { url: originalRequest.url })
      
      // Try to refresh the token
      const authStore = (await import('../stores/authStore')).useAuthStore.getState()
      const success = await authStore.refreshAccessToken()
      
      if (success) {
        logger.info('Token refreshed successfully, retrying request')
        // Retry the original request with new token
        originalRequest.headers['Authorization'] = `Bearer ${authStore.accessToken}`
        return api(originalRequest)
      } else {
        logger.warn('Token refresh failed, logging out user')
        // Refresh failed, logout user
        authStore.logout()
        window.location.href = '/login'
      }
    }
    
    // Log different error types with appropriate levels
    if (error.response) {
      // Server responded with error
      const message = error.response.data?.detail || error.response.data?.message || 'An error occurred'
      
      if (error.response.status >= 500) {
        logger.error(`API Server Error: ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url}`, errorDetails)
      } else if (error.response.status >= 400) {
        logger.warn(`API Client Error: ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url}`, errorDetails)
      }
      
      // Don't show toast for auth status checks
      if (!error.config.url?.includes('/auth/status')) {
        toast.error(message)
      }
    } else if (error.request) {
      // Request was made but no response
      logger.error('API Network Error - No response received', errorDetails)
      toast.error('No response from server. Please check your connection.')
    } else {
      // Something else happened
      logger.error('API Unexpected Error', {
        ...errorDetails,
        stack: error.stack
      })
      toast.error('An unexpected error occurred')
    }
    
    return Promise.reject(error)
  }
)

export default api

// Convenience methods for common API calls
export const apiService = {
  // Auth
  checkAuthStatus: () => api.get('/api/auth/status'),
  login: (username, password) => api.post('/api/auth/login', { username, password }),
  setupAuth: (username, password, email) => api.post('/api/auth/setup', { username, password, email }),
  updateAuthSettings: (authEnabled, requireWebhookAuth) => 
    api.put('/api/auth/settings', null, { params: { auth_enabled: authEnabled, require_webhook_auth: requireWebhookAuth } }),
  
  // Overview
  getOverview: () => api.get('/api/overview'),
  
  // Config
  getConfig: () => api.get('/api/config'),
  updateConfig: (section, key, value) => api.put('/api/config', { section, key, value }),
  
  // Templates
  getTemplates: () => api.get('/api/templates'),
  getTemplate: (name) => api.get(`/api/templates/${name}`),
  updateTemplate: (name, content) => api.put(`/api/templates/${name}`, { name, content }),
  restoreTemplate: (name) => api.post(`/api/templates/${name}/restore`),
  
  // Logs
  getLogs: (params) => api.post('/api/logs', params),
  
  // Health
  healthCheck: () => api.get('/api/health'),
}