import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import Layout from './components/Layout'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Config from './pages/Config'
import Templates from './pages/Templates'
import Logs from './pages/Logs'
import { useEffect, useState } from 'react'
import logger from './services/logger'
import RouteLogger from './components/RouteLogger'
import withLifecycleLogging from './utils/withLifecycleLogging'

// Wrap page components with lifecycle logging
const LoggedOverview = withLifecycleLogging(Overview, 'Overview');
const LoggedConfig = withLifecycleLogging(Config, 'Config');
const LoggedTemplates = withLifecycleLogging(Templates, 'Templates');
const LoggedLogs = withLifecycleLogging(Logs, 'Logs');
const LoggedLayout = withLifecycleLogging(Layout, 'Layout');

function App() {
  const { isAuthenticated, authRequired, checkAuth } = useAuthStore()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Log app initialization
    logger.info('Jellynouncer Web Interface initializing', {
      version: '1.0.0',
      environment: import.meta.env.MODE
    })
    
    // Check if user is authenticated on app load
    const initAuth = async () => {
      try {
        logger.debug('Checking authentication status')
        await checkAuth()
        logger.debug('Authentication check completed', {
          authRequired,
          isAuthenticated
        })
      } catch (error) {
        logger.error('Authentication check failed', {
          error: error.message,
          stack: error.stack
        })
      } finally {
        setLoading(false)
      }
    }
    initAuth()
  }, [checkAuth])

  // Log successful app load
  useEffect(() => {
    if (!loading) {
      logger.info('App loaded successfully', {
        authRequired,
        isAuthenticated
      })
    }
  }, [loading, authRequired, isAuthenticated])

  // Show loading spinner while checking auth
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-900">
        <div className="text-white">Loading...</div>
      </div>
    )
  }

  // Only show login if auth is required and user is not authenticated
  if (authRequired && !isAuthenticated) {
    logger.debug('Showing login page - authentication required')
    return <Login />
  }

  return (
    <>
      <RouteLogger />
      <Routes>
        <Route path="/" element={<LoggedLayout />}>
          <Route index element={<LoggedOverview />} />
          <Route path="config" element={<LoggedConfig />} />
          <Route path="templates" element={<LoggedTemplates />} />
          <Route path="logs" element={<LoggedLogs />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default App