import { useState } from 'react';
import { Icon, IconDuotone } from './FontAwesomeIcon';
import { useAuthStore } from '../stores/authStore';
import toast from 'react-hot-toast';
import logger from '../services/logger';

const AuthSetup = ({ onClose, onComplete }) => {
  const [step, setStep] = useState(1); // 1: intro, 2: create account, 3: confirm, 4: complete
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    email: ''
  });
  const [loading, setLoading] = useState(false);
  const { setupAuth, updateAuthSettings } = useAuthStore();

  const handleCreateAccount = async (e) => {
    e.preventDefault();
    
    // Validate form
    if (formData.password !== formData.confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    
    if (formData.password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    
    setLoading(true);
    logger.info('AuthSetup: Creating admin account', { username: formData.username });
    
    try {
      // Create the admin account (auth is still disabled at this point)
      const success = await setupAuth(
        formData.username,
        formData.password,
        formData.email
      );
      
      if (success) {
        logger.info('AuthSetup: Account created successfully');
        setStep(3); // Move to confirmation step
      } else {
        toast.error('Failed to create account');
        logger.error('AuthSetup: Account creation failed');
      }
    } catch (error) {
      logger.error('AuthSetup: Error creating account', error);
      toast.error('Error creating account');
    } finally {
      setLoading(false);
    }
  };

  const handleEnableAuth = async () => {
    setLoading(true);
    logger.info('AuthSetup: Enabling authentication');
    
    try {
      // Enable authentication (both web UI and optionally webhooks)
      const success = await updateAuthSettings(true, false); // Start with webhook auth disabled
      
      if (success) {
        logger.info('AuthSetup: Authentication enabled successfully');
        toast.success('Authentication enabled! Please log in with your new credentials.');
        setStep(4);
        
        // If we have an onComplete callback, use it instead of redirecting
        if (onComplete) {
          setTimeout(() => {
            onComplete();
          }, 2000);
        } else {
          // Default behavior: Force logout and redirect to login after a short delay
          setTimeout(() => {
            window.location.href = '/login';
          }, 2000);
        }
      } else {
        toast.error('Failed to enable authentication');
        logger.error('AuthSetup: Failed to enable authentication');
      }
    } catch (error) {
      logger.error('AuthSetup: Error enabling authentication', error);
      toast.error('Error enabling authentication');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {step === 1 && 'Enable Authentication'}
            {step === 2 && 'Create Admin Account'}
            {step === 3 && 'Confirm Account Creation'}
            {step === 4 && 'Setup Complete'}
          </h2>
          {step < 4 && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
            >
              <Icon icon="times" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Introduction */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="flex items-center justify-center w-16 h-16 mx-auto bg-yellow-100 dark:bg-yellow-900 rounded-full">
                <IconDuotone icon="shield-alt" size="2x" className="text-yellow-600 dark:text-yellow-400" />
              </div>
              
              <div className="text-center">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  Secure Your Jellynouncer Instance
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Authentication is currently disabled. Follow these steps to secure your instance:
                </p>
              </div>
              
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                <div className="flex">
                  <IconDuotone icon="info-circle" className="text-blue-600 dark:text-blue-400 mt-0.5" />
                  <div className="ml-3 text-sm text-gray-700 dark:text-gray-300">
                    <p className="font-semibold mb-1">What will happen:</p>
                    <ol className="list-decimal list-inside space-y-1">
                      <li>Create your admin account</li>
                      <li>Verify account details</li>
                      <li>Enable authentication</li>
                      <li>You&apos;ll be logged out and must sign in</li>
                    </ol>
                  </div>
                </div>
              </div>
              
              <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
                <div className="flex">
                  <IconDuotone icon="exclamation-triangle" className="text-amber-600 dark:text-amber-400 mt-0.5" />
                  <div className="ml-3 text-sm text-gray-700 dark:text-gray-300">
                    <p className="font-semibold">Important:</p>
                    <p>Make sure to remember your credentials. You&apos;ll need them to access the interface once authentication is enabled.</p>
                  </div>
                </div>
              </div>
              
              <button
                onClick={() => setStep(2)}
                className="w-full btn btn-primary"
              >
                Continue to Account Setup
                <Icon icon="arrow-right" className="ml-2" />
              </button>
            </div>
          )}

          {/* Step 2: Create Account */}
          {step === 2 && (
            <form onSubmit={handleCreateAccount} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Username
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="input w-full"
                  placeholder="admin"
                  autoFocus
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Email (optional)
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="input w-full"
                  placeholder="admin@example.com"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Password
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="input w-full"
                  placeholder="••••••••"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Must be at least 8 characters
                </p>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Confirm Password
                </label>
                <input
                  type="password"
                  required
                  value={formData.confirmPassword}
                  onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                  className="input w-full"
                  placeholder="••••••••"
                />
              </div>
              
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="flex-1 btn btn-secondary"
                  disabled={loading}
                >
                  <Icon icon="arrow-left" className="mr-2" />
                  Back
                </button>
                <button
                  type="submit"
                  className="flex-1 btn btn-primary"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <Icon icon="spinner" className="mr-2 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      Create Account
                      <Icon icon="arrow-right" className="ml-2" />
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* Step 3: Confirm */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="flex items-center justify-center w-16 h-16 mx-auto bg-green-100 dark:bg-green-900 rounded-full">
                <IconDuotone icon="check-circle" size="2x" className="text-green-600 dark:text-green-400" />
              </div>
              
              <div className="text-center">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  Account Created Successfully!
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Your admin account has been created with the following details:
                </p>
              </div>
              
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Username:</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{formData.username}</span>
                </div>
                {formData.email && (
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Email:</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">{formData.email}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Password:</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-white">••••••••</span>
                </div>
              </div>
              
              <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
                <div className="flex">
                  <IconDuotone icon="exclamation-triangle" className="text-amber-600 dark:text-amber-400 mt-0.5" />
                  <div className="ml-3 text-sm text-gray-700 dark:text-gray-300">
                    <p className="font-semibold">Next Step:</p>
                    <p>When you click &quot;Enable Authentication&quot;, you will be immediately logged out and must sign in with your new credentials.</p>
                  </div>
                </div>
              </div>
              
              <div className="flex gap-3">
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 btn btn-secondary"
                  disabled={loading}
                >
                  <Icon icon="arrow-left" className="mr-2" />
                  Back
                </button>
                <button
                  onClick={handleEnableAuth}
                  className="flex-1 btn btn-primary"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <Icon icon="spinner" className="mr-2 animate-spin" />
                      Enabling...
                    </>
                  ) : (
                    <>
                      Enable Authentication
                      <IconDuotone icon="lock" className="ml-2" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Complete */}
          {step === 4 && (
            <div className="space-y-4 text-center">
              <div className="flex items-center justify-center w-16 h-16 mx-auto bg-green-100 dark:bg-green-900 rounded-full">
                <IconDuotone icon="shield-check" size="2x" className="text-green-600 dark:text-green-400" />
              </div>
              
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  Authentication Enabled!
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Your Jellynouncer instance is now secured. Redirecting to login...
                </p>
              </div>
              
              <div className="flex items-center justify-center">
                <Icon icon="spinner" className="animate-spin text-gray-400" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AuthSetup;