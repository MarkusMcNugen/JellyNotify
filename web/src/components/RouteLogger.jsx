import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import logger from '../services/logger';

/**
 * Component that logs all route changes
 * Place this at the top level of your app to track navigation
 */
const RouteLogger = () => {
  const location = useLocation();

  useEffect(() => {
    logger.info('[ROUTER] Navigation occurred', {
      pathname: location.pathname,
      search: location.search,
      hash: location.hash,
      state: location.state,
      timestamp: new Date().toISOString()
    });

    // Log which component should be rendered for this route
    const routeMap = {
      '/': 'Overview',
      '/config': 'Config',
      '/templates': 'Templates',
      '/logs': 'Logs',
      '/login': 'Login'
    };

    const expectedComponent = routeMap[location.pathname] || 'Unknown';
    logger.debug(`[ROUTER] Expected component for route: ${expectedComponent}`, {
      pathname: location.pathname
    });
  }, [location]);

  return null; // This component doesn't render anything
};

export default RouteLogger;