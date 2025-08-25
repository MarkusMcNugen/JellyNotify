import { useState } from 'react';
import { Icon, IconDuotone } from './FontAwesomeIcon';
import toast from 'react-hot-toast';
import { useAuthStore } from '../stores/authStore';

const WebhookTokenDisplay = ({ onClose }) => {
  const { accessToken } = useAuthStore();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (accessToken) {
      navigator.clipboard.writeText(`Bearer ${accessToken}`);
      setCopied(true);
      toast.success('Token copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const webhookUrl = `${window.location.protocol}//${window.location.hostname}:1984/webhook`;
  const curlExample = `curl -X POST "${webhookUrl}" \\
  -H "Authorization: Bearer ${accessToken || 'YOUR_TOKEN'}" \\
  -H "Content-Type: application/json" \\
  -d '{"Event": "ItemAdded", "Item": {...}}'`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Webhook Authentication Token
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
          >
            <Icon icon="times" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Info */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
            <div className="flex">
              <IconDuotone icon="info-circle" className="text-blue-600 dark:text-blue-400 mt-0.5" />
              <div className="ml-3 text-sm text-gray-700 dark:text-gray-300">
                <p className="font-semibold mb-1">How to use webhook authentication:</p>
                <ol className="list-decimal list-inside space-y-1">
                  <li>Copy the Bearer token below</li>
                  <li>Configure Jellyfin webhook plugin to include Authorization header</li>
                  <li>Use the token in the format: Bearer YOUR_TOKEN</li>
                  <li>The token is the same as your web interface login token</li>
                </ol>
              </div>
            </div>
          </div>

          {/* Token Display */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Bearer Token
            </label>
            <div className="flex items-center gap-2">
              <div className="flex-1 p-3 bg-gray-100 dark:bg-gray-700 rounded-lg font-mono text-xs break-all">
                {accessToken ? `Bearer ${accessToken}` : 'No token available - please log in'}
              </div>
              <button
                onClick={handleCopy}
                className="btn btn-secondary"
                disabled={!accessToken}
              >
                {copied ? (
                  <>
                    <IconDuotone icon="check" className="mr-2 text-green-500" />
                    Copied!
                  </>
                ) : (
                  <>
                    <IconDuotone icon="copy" className="mr-2" />
                    Copy
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Webhook URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Webhook Endpoint
            </label>
            <div className="p-3 bg-gray-100 dark:bg-gray-700 rounded-lg font-mono text-sm">
              {webhookUrl}
            </div>
          </div>

          {/* Example */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Example cURL Command
            </label>
            <pre className="p-3 bg-gray-900 text-gray-100 rounded-lg text-xs overflow-x-auto">
              {curlExample}
            </pre>
          </div>

          {/* Warning */}
          <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
            <div className="flex">
              <IconDuotone icon="exclamation-triangle" className="text-amber-600 dark:text-amber-400 mt-0.5" />
              <div className="ml-3 text-sm text-gray-700 dark:text-gray-300">
                <p className="font-semibold">Security Notice:</p>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>Keep your token secure and never share it publicly</li>
                  <li>The token expires after 30 minutes and will need to be refreshed</li>
                  <li>If you log out, you&apos;ll need to generate a new token</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Close Button */}
          <div className="flex justify-end">
            <button
              onClick={onClose}
              className="btn btn-primary"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default WebhookTokenDisplay;