import { useEffect } from 'react';
import logger from '../services/logger';

/**
 * Higher-order component that adds lifecycle logging to any component
 * This helps debug component mounting/unmounting issues
 */
const withLifecycleLogging = (Component, componentName) => {
  return function LoggedComponent(props) {
    // Log when component is about to mount
    useEffect(() => {
      logger.info(`[LIFECYCLE] ${componentName}: Mounting component`, {
        props: Object.keys(props),
        timestamp: new Date().toISOString(),
        pathname: window.location.pathname
      });

      // Component mounted successfully
      logger.debug(`[LIFECYCLE] ${componentName}: Component mounted successfully`);

      // Cleanup function - runs on unmount
      return () => {
        logger.info(`[LIFECYCLE] ${componentName}: Unmounting component`, {
          timestamp: new Date().toISOString(),
          pathname: window.location.pathname
        });
      };
    }, []); // Empty dependency array - only run on mount/unmount

    // Log any prop changes
    useEffect(() => {
      logger.debug(`[LIFECYCLE] ${componentName}: Props updated`, {
        propKeys: Object.keys(props),
        timestamp: new Date().toISOString()
      });
    }, [props]);

    // Log that we're about to render
    logger.debug(`[LIFECYCLE] ${componentName}: Rendering component`, {
      timestamp: new Date().toISOString()
    });

    try {
      // Attempt to render the component
      return <Component {...props} />;
    } catch (error) {
      // Log any rendering errors
      logger.error(`[LIFECYCLE] ${componentName}: Render error`, {
        error: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString()
      });
      throw error; // Re-throw to let React handle it
    }
  };
};

export default withLifecycleLogging;