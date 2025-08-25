import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const AuthEnableModal = ({ isOpen, onClose, onProceedToSetup }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <h2 className="text-xl font-bold text-white mb-4">
          Setup Required
        </h2>
        
        <div className="mb-6">
          <p className="text-gray-300 mb-4">
            No admin account has been configured yet. You must create an admin account before enabling authentication, otherwise you&apos;ll be locked out of the web interface.
          </p>
          
          <div className="bg-yellow-900 border border-yellow-600 rounded-lg p-3 mb-4">
            <div className="flex items-start">
              <svg className="w-5 h-5 text-yellow-500 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div className="text-sm text-yellow-300">
                <p className="font-semibold">Important:</p>
                <p>Enabling authentication without an admin account will lock you out!</p>
              </div>
            </div>
          </div>
          
          <p className="text-gray-400 text-sm">
            Would you like to set up an admin account now?
          </p>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onProceedToSetup}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded transition-colors"
          >
            Yes, Setup Admin Account
          </button>
          <button
            onClick={onClose}
            className="flex-1 bg-gray-700 hover:bg-gray-600 text-gray-300 font-medium py-2 px-4 rounded transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default AuthEnableModal;