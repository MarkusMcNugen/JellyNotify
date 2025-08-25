import { useState, useEffect } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import ConnectionStatus from './ConnectionStatus';
import DarkModeToggle from './DarkModeToggle';
import AuthSetup from './AuthSetup';
import PasswordReset from './PasswordReset';
import { Icon, IconDuotone, IconLight } from './FontAwesomeIcon';
import logger from '../services/logger';

const Layout = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, logout, user, authRequired } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showAuthSetup, setShowAuthSetup] = useState(false);
  const [showPasswordReset, setShowPasswordReset] = useState(false);

  const navigation = [
    { name: 'Overview', href: '/', icon: 'home', style: 'duotone' },
    { name: 'Configuration', href: '/config', icon: 'cogs', style: 'duotone' },
    { name: 'Templates', href: '/templates', icon: 'file-code', style: 'duotone' },
    { name: 'Logs', href: '/logs', icon: 'search-plus', style: 'duotone' },
  ];

  // Log navigation changes
  useEffect(() => {
    logger.debug('Layout: Navigation changed', {
      path: location.pathname,
      isAuthenticated,
      user: user?.username
    });
  }, [location, isAuthenticated, user]);

  const handleLogout = () => {
    logger.info('Layout: User logging out');
    logout();
    navigate('/login');
  };

  const isActive = (path) => {
    return location.pathname === path;
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Mobile sidebar */}
      <div className={`fixed inset-0 z-50 lg:hidden ${sidebarOpen ? '' : 'hidden'}`}>
        <div className="fixed inset-0 bg-gray-600 bg-opacity-75" onClick={() => setSidebarOpen(false)} />
        <nav className="fixed top-0 left-0 bottom-0 flex flex-col w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <img className="h-8 w-auto" src="/logo.png" alt="Jellynouncer" />
              <span className="ml-2 text-xl font-semibold text-gray-900 dark:text-white">
                Jellynouncer
              </span>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="text-gray-500 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-300"
            >
              <IconLight icon="times" size="lg" />
            </button>
          </div>
          
          <div className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
            {navigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={`
                  flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors
                  ${isActive(item.href)
                    ? 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300'
                    : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                  }
                `}
                onClick={() => setSidebarOpen(false)}
              >
                <IconDuotone icon={item.icon} className="mr-3" />
                {item.name}
              </Link>
            ))}
          </div>

          {/* User info section - always visible */}
          <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {user?.username || (authRequired ? 'User' : 'Admin (No Auth)')}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {user?.email || (authRequired ? 'user@example.com' : 'Authentication Disabled')}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {!authRequired && (
                  <button
                    onClick={() => setShowAuthSetup(true)}
                    className="p-2 text-yellow-500 hover:text-yellow-600 dark:text-yellow-400 dark:hover:text-yellow-300"
                    title="Enable Authentication"
                  >
                    <IconDuotone icon="exclamation-triangle" size="sm" />
                  </button>
                )}
                {authRequired && (
                  <>
                    <button
                      onClick={() => setShowPasswordReset(true)}
                      className="p-2 text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300"
                      title="Change Password"
                    >
                      <IconDuotone icon="key" size="sm" />
                    </button>
                    <button
                      onClick={handleLogout}
                      className="p-2 text-gray-500 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-300"
                      title="Logout"
                    >
                      <IconDuotone icon="sign-out-alt" size="sm" />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </nav>
      </div>

      {/* Desktop sidebar */}
      <nav className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex flex-col flex-1 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
          <div className="flex items-center h-16 px-4 border-b border-gray-200 dark:border-gray-700">
            <img className="h-8 w-auto" src="/logo.png" alt="Jellynouncer" />
            <span className="ml-2 text-xl font-semibold text-gray-900 dark:text-white">
              Jellynouncer
            </span>
          </div>
          
          <div className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
            {navigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={`
                  flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors
                  ${isActive(item.href)
                    ? 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300'
                    : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                  }
                `}
              >
                <IconDuotone icon={item.icon} className="mr-3" />
                {item.name}
              </Link>
            ))}
          </div>

          {/* User info section - always visible */}
          <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {user?.username || (authRequired ? 'User' : 'Admin (No Auth)')}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {user?.email || (authRequired ? 'user@example.com' : 'Authentication Disabled')}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {!authRequired && (
                  <button
                    onClick={() => setShowAuthSetup(true)}
                    className="p-2 text-yellow-500 hover:text-yellow-600 dark:text-yellow-400 dark:hover:text-yellow-300"
                    title="Enable Authentication"
                  >
                    <IconDuotone icon="exclamation-triangle" size="sm" />
                  </button>
                )}
                {authRequired && (
                  <>
                    <button
                      onClick={() => setShowPasswordReset(true)}
                      className="p-2 text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300"
                      title="Change Password"
                    >
                      <IconDuotone icon="key" size="sm" />
                    </button>
                    <button
                      onClick={handleLogout}
                      className="p-2 text-gray-500 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-300"
                      title="Logout"
                    >
                      <IconDuotone icon="sign-out-alt" size="sm" />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <div className="lg:pl-64 flex flex-col flex-1">
        {/* Top header for mobile */}
        <header className="lg:hidden sticky top-0 z-40 flex items-center h-16 px-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-gray-500 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-300"
          >
            <IconLight icon="bars" size="lg" />
          </button>
          <span className="ml-4 text-xl font-semibold text-gray-900 dark:text-white">
            Jellynouncer
          </span>
        </header>

        {/* Page content */}
        <main className="flex-1">
          <div className="py-6">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
              <Outlet />
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex flex-col sm:flex-row justify-between items-center space-y-2 sm:space-y-0">
              <div className="flex items-center space-x-4">
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  © 2024 Jellynouncer - Made with ☕ by Mark Newton
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Version 2.0.0
                </p>
              </div>
              <div className="flex items-center space-x-4">
                <ConnectionStatus />
                <DarkModeToggle />
              </div>
            </div>
          </div>
        </footer>
      </div>
      
      {/* Auth Setup Modal */}
      {showAuthSetup && (
        <AuthSetup onClose={() => setShowAuthSetup(false)} />
      )}
      
      {/* Password Reset Modal */}
      {showPasswordReset && (
        <PasswordReset onClose={() => setShowPasswordReset(false)} />
      )}
    </div>
  );
};

export default Layout;