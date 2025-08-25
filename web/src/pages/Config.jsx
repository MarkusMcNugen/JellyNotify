import { useState, useEffect } from 'react';
import {
  ServerIcon,
  ChatBubbleLeftRightIcon,
  BellIcon,
  KeyIcon,
  CheckIcon,
  XMarkIcon,
  ComputerDesktopIcon,
  CpuChipIcon,
  CircleStackIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
  ExclamationTriangleIcon,
  ArrowUpTrayIcon,
  DocumentArrowDownIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline';
import { apiService } from '../services/api';
import { apiClient } from '../utils/apiClient';
import WebhookTokenDisplay from '../components/WebhookTokenDisplay';
import Tooltip from '../components/Tooltip';
import LabelWithTooltip from '../components/LabelWithTooltip';
import { configDescriptions } from '../utils/configDescriptions';
import logger from '../services/logger';

const Config = () => {
  logger.info('[COMPONENT] Config: Starting component initialization');
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  logger.debug('[COMPONENT] Config: State hooks initialized');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeTab, setActiveTab] = useState('jellyfin');
  const [showAdvancedWarning, setShowAdvancedWarning] = useState(false);
  const [sslFile, setSslFile] = useState(null);
  const [sslKeyFile, setSslKeyFile] = useState(null);
  const [showWebhookToken, setShowWebhookToken] = useState(false);
  
  const [config, setConfig] = useState({
    jellyfin: {
      server_url: '',
      api_key: '',
      user_id: '',
      client_name: 'JellyNotify-Discord-Webhook',
      client_version: '1.0.0',
      device_name: 'jellynotify-webhook-service',
      device_id: 'jellynotify-discord-webhook-001',
    },
    discord: {
      webhooks: {
        default: { url: '', name: 'General', enabled: true, grouping: { mode: 'none', delay_minutes: 5, max_items: 25 } },
        movies: { url: '', name: 'Movies', enabled: false, grouping: { mode: 'none', delay_minutes: 5, max_items: 25 } },
        tv: { url: '', name: 'TV Shows', enabled: false, grouping: { mode: 'none', delay_minutes: 5, max_items: 25 } },
        music: { url: '', name: 'Music', enabled: false, grouping: { mode: 'none', delay_minutes: 5, max_items: 25 } },
      },
      routing: {
        enabled: false,
        movie_types: ['Movie'],
        tv_types: ['Episode', 'Season', 'Series'],
        music_types: ['Audio', 'MusicAlbum', 'MusicArtist'],
        fallback_webhook: 'default',
      },
      rate_limit: {
        requests_per_period: 5,
        period_seconds: 2,
        channel_limit_per_minute: 30,
      },
    },
    notifications: {
      watch_changes: {
        resolution: true,
        codec: true,
        audio_codec: true,
        audio_channels: true,
        hdr_status: true,
        file_size: true,
      },
      colors: {
        new_item: 65280,
        resolution_upgrade: 16766720,
        codec_upgrade: 16747520,
        audio_upgrade: 9662683,
        hdr_upgrade: 16716947,
      },
      filter_renames: true,
      filter_deletes: true,
    },
    metadata_services: {
      enabled: true,
      omdb: { enabled: false, api_key: '', base_url: 'https://www.omdbapi.com/' },
      tmdb: { enabled: false, api_key: '', base_url: 'https://api.themoviedb.org/3/' },
      tvdb: { enabled: false, api_key: '', base_url: 'https://api4.thetvdb.com/v4/', subscriber_pin: null },
      cache_duration_hours: 168,
      tvdb_cache_ttl_hours: 24,
      request_timeout_seconds: 10,
      retry_attempts: 3,
    },
    server: {
      host: '0.0.0.0',
      port: 1984,
      log_level: 'INFO',
      run_mode: 'all',
      data_dir: '/app/data',
      log_dir: '/app/logs',
      environment: 'production',
      development_mode: false,
      show_docker_interfaces: false,
      allowed_hosts: [],
      force_color_output: false,
      disable_color_output: false,
    },
    web_interface: {
      enabled: true,
      port: 1985,
      host: '0.0.0.0',
      jwt_secret: null,
      auth_enabled: false,
      username: null,
      password: null,
      ssl_enabled: false,
      ssl_cert_path: null,
      ssl_key_path: null,
      ssl_port: 9000,
    },
    database: {
      path: '/app/data/jellyfin_items.db',
      wal_mode: true,
      vacuum_interval_hours: 24,
    },
    templates: {
      directory: '/app/templates',
      new_item_template: 'new_item.j2',
      upgraded_item_template: 'upgraded_item.j2',
      deleted_item_template: 'deleted_item.j2',
      new_items_by_event_template: 'new_items_by_event.j2',
      upgraded_items_by_event_template: 'upgraded_items_by_event.j2',
      new_items_by_type_template: 'new_items_by_type.j2',
      upgraded_items_by_type_template: 'upgraded_items_by_type.j2',
      new_items_grouped_template: 'new_items_grouped.j2',
      upgraded_items_grouped_template: 'upgraded_items_grouped.j2',
    },
  });

  const tabs = [
    { id: 'jellyfin', name: 'Jellyfin', icon: ServerIcon },
    { id: 'discord', name: 'Discord', icon: ChatBubbleLeftRightIcon },
    { id: 'notifications', name: 'Notifications', icon: BellIcon },
    { id: 'metadata_services', name: 'External APIs', icon: KeyIcon },
    { id: 'server', name: 'Server', icon: ComputerDesktopIcon, advanced: true },
    { id: 'web_interface', name: 'Web Interface', icon: CpuChipIcon, advanced: true },
    { id: 'database', name: 'Database', icon: CircleStackIcon, advanced: true },
    { id: 'templates', name: 'Templates', icon: DocumentTextIcon, advanced: true },
    { id: 'ssl', name: 'SSL/Security', icon: ShieldCheckIcon, advanced: true },
  ];

  useEffect(() => {
    void fetchConfig();
  }, []);

  const fetchConfig = async () => {
    logger.debug('Config: Starting fetchConfig');
    try {
      setLoading(true);
      logger.debug('Config: Fetching from /api/config');
      const response = await apiService.getConfig();
      logger.info('Config: Data received', {
        hasData: !!response.data,
        keys: response.data ? Object.keys(response.data) : []
      });
      setConfig(response.data || response);
      setError(null);
      logger.debug('Config: Successfully loaded configuration');
    } catch (err) {
      logger.error('Config: Failed to load', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status
      });
      setError('Failed to load configuration');
    } finally {
      setLoading(false);
      logger.debug('Config: Fetch complete');
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      
      // Handle auth settings separately if they've changed
      if (config.web_interface) {
        const authEnabled = config.web_interface.auth_enabled || false;
        const requireWebhookAuth = config.web_interface.require_webhook_auth || false;
        
        logger.debug('Config: Updating auth settings', { authEnabled, requireWebhookAuth });
        
        // Update auth settings through the proper endpoint
        await apiClient.put('/api/auth/settings', null, {
          params: {
            auth_enabled: authEnabled,
            require_webhook_auth: requireWebhookAuth
          }
        });
      }
      
      // Save the rest of the config
      await apiClient.put('/api/config', config);
      setSuccess('Configuration saved successfully');
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to save configuration');
      console.error('Save error:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleInputChange = (section, key, value, subkey = null) => {
    setConfig(prev => {
      const newConfig = { ...prev };
      if (subkey) {
        newConfig[section][key][subkey] = value;
      } else {
        newConfig[section][key] = value;
      }
      return newConfig;
    });
  };

  const handleArrayChange = (section, key, value) => {
    setConfig(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: value.split(',').map(v => v.trim()).filter(v => v),
      },
    }));
  };

  const handleWebhookChange = (webhookType, field, value, subfield = null) => {
    setConfig(prev => {
      const newConfig = { ...prev };
      if (subfield) {
        newConfig.discord.webhooks[webhookType][field][subfield] = value;
      } else {
        newConfig.discord.webhooks[webhookType][field] = value;
      }
      return newConfig;
    });
  };

  const handleSSLFileUpload = async (type) => {
    const file = type === 'cert' ? sslFile : sslKeyFile;
    if (!file) return;

    const formData = new FormData();
    if (file instanceof File) {
      formData.append('file', file);
    }
    formData.append('type', type);

    try {
      const response = await apiClient.post('/api/ssl/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      
      // Update config with the uploaded file path
      if (type === 'cert') {
        handleInputChange('web_interface', 'ssl_cert_path', response.data.path);
      } else {
        handleInputChange('web_interface', 'ssl_key_path', response.data.path);
      }
      
      setSuccess(`SSL ${type} uploaded successfully`);
    } catch (err) {
      console.error('SSL upload error:', err);
      setError(`Failed to upload SSL ${type}`);
    }
  };

  const generateCSR = async () => {
    try {
      const response = await apiClient.post('/api/ssl/generate-csr', {
        commonName: window.location.hostname,
        country: 'US',
        state: 'State',
        locality: 'City',
        organization: 'Organization',
        organizationalUnit: 'IT',
      });
      
      // Download the Certificate Signing Request
      const responseData = response.data || {};
      const csrContent = responseData['csr'] || '';
      const blob = new Blob([csrContent], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'certificate.csr';
      a.click();
      
      setSuccess('CSR generated and downloaded');
    } catch (err) {
      console.error('CSR generation error:', err);
      setError('Failed to generate CSR');
    }
  };

  const testConnection = async (type) => {
    try {
      const endpoint = type === 'jellyfin' ? '/api/test/jellyfin' : `/api/test/discord/${type}`;
      await apiClient.post(endpoint, config[type] || config.discord.webhooks[type]);
      setSuccess(`${type} connection test successful`);
    } catch (err) {
      console.error('Connection test error:', err);
      setError(`${type} connection test failed`);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Configuration
            </h2>
            <button
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {saving ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Saving...
                </>
              ) : (
                <>
                  <CheckIcon className="h-4 w-4 mr-2" />
                  Save Changes
                </>
              )}
            </button>
          </div>
        </div>

        {/* Notifications */}
        {error && (
          <div className="mx-6 mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
            <div className="flex">
              <XMarkIcon className="h-5 w-5 text-red-400" />
              <div className="ml-3">
                <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
              </div>
            </div>
          </div>
        )}

        {success && (
          <div className="mx-6 mt-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
            <div className="flex">
              <CheckIcon className="h-5 w-5 text-green-400" />
              <div className="ml-3">
                <p className="text-sm text-green-800 dark:text-green-300">{success}</p>
              </div>
            </div>
          </div>
        )}

        {/* Advanced Warning */}
        {showAdvancedWarning && (
          <div className="mx-6 mt-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md">
            <div className="flex">
              <ExclamationTriangleIcon className="h-5 w-5 text-yellow-400" />
              <div className="ml-3">
                <p className="text-sm text-yellow-800 dark:text-yellow-300">
                  Advanced settings can affect system stability. Proceed with caution.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="-mb-px flex space-x-8 px-6 overflow-x-auto" aria-label="Tabs">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTab(tab.id);
                    if (tab.advanced && !showAdvancedWarning) {
                      setShowAdvancedWarning(true);
                    }
                  }}
                  className={`
                    whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm inline-flex items-center
                    ${activeTab === tab.id
                      ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                    }
                  `}
                >
                  <Icon className="h-5 w-5 mr-2" />
                  {tab.name}
                  {tab.advanced && (
                    <span className="ml-2 text-xs text-yellow-600 dark:text-yellow-400">Advanced</span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Jellyfin Tab */}
          {activeTab === 'jellyfin' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <LabelWithTooltip 
                    label="Server URL" 
                    tooltip={configDescriptions.jellyfin.server_url}
                    className="block"
                  />
                  <input
                    type="text"
                    value={config.jellyfin.server_url || ''}
                    onChange={(e) => handleInputChange('jellyfin', 'server_url', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    placeholder="http://jellyfin.local:8096"
                  />
                </div>
                <div>
                  <LabelWithTooltip 
                    label="API Key" 
                    tooltip={configDescriptions.jellyfin.api_key}
                    className="block"
                  />
                  <input
                    type="password"
                    value={config.jellyfin.api_key || ''}
                    onChange={(e) => handleInputChange('jellyfin', 'api_key', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <LabelWithTooltip 
                    label="User ID" 
                    tooltip={configDescriptions.jellyfin.user_id}
                    className="block"
                  />
                  <input
                    type="text"
                    value={config.jellyfin.user_id || ''}
                    onChange={(e) => handleInputChange('jellyfin', 'user_id', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    onClick={() => testConnection('jellyfin')}
                    className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600"
                  >
                    Test Connection
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Discord Tab */}
          {activeTab === 'discord' && (
            <div className="space-y-6">
              {Object.entries(config.discord.webhooks).map(([key, webhook]) => (
                <div key={key} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                    {webhook.name} Webhook
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <LabelWithTooltip 
                        label="Webhook URL" 
                        tooltip={configDescriptions.discord.webhooks[key]?.url || configDescriptions.discord.webhooks.default.url}
                        className="block"
                      />
                      <input
                        type="text"
                        value={webhook.url || ''}
                        onChange={(e) => handleWebhookChange(key, 'url', e.target.value)}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                        placeholder="https://discord.com/api/webhooks/..."
                      />
                    </div>
                    <div className="flex items-end space-x-4">
                      <label className="inline-flex items-center">
                        <input
                          type="checkbox"
                          checked={webhook.enabled}
                          onChange={(e) => handleWebhookChange(key, 'enabled', e.target.checked)}
                          className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                        />
                        <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Enabled</span>
                        <Tooltip text={configDescriptions.discord.webhooks[key]?.enabled || configDescriptions.discord.webhooks.default.enabled} />
                      </label>
                      <button
                        onClick={() => testConnection(key)}
                        className="px-3 py-1 border border-gray-300 rounded-md shadow-sm text-xs font-medium text-gray-700 bg-white hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600"
                      >
                        Test
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Grouping Mode
                      </label>
                      <select
                        value={webhook.grouping.mode}
                        onChange={(e) => handleWebhookChange(key, 'grouping', e.target.value, 'mode')}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                      >
                        <option value="none">None</option>
                        <option value="type">By Type</option>
                        <option value="event">By Event</option>
                        <option value="all">All</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Delay (minutes)
                      </label>
                      <input
                        type="number"
                        value={webhook.grouping.delay_minutes}
                        onChange={(e) => handleWebhookChange(key, 'grouping', parseInt(e.target.value), 'delay_minutes')}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                        min="1"
                        max="60"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Max Items
                      </label>
                      <input
                        type="number"
                        value={webhook.grouping.max_items}
                        onChange={(e) => handleWebhookChange(key, 'grouping', parseInt(e.target.value), 'max_items')}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                        min="1"
                        max="100"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Notifications Tab */}
          {activeTab === 'notifications' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                  Watch for Changes
                </h3>
                <div className="space-y-2">
                  {Object.entries(config.notifications.watch_changes).map(([key, value]) => (
                    <label key={key} className="inline-flex items-center">
                      <input
                        type="checkbox"
                        checked={value}
                        onChange={(e) => handleInputChange('notifications', 'watch_changes', e.target.checked, key)}
                        className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </span>
                      <Tooltip text={configDescriptions.notifications.watch_changes[key]} />
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                  Notification Colors (Decimal)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(config.notifications.colors).map(([key, value]) => (
                    <div key={key}>
                      <LabelWithTooltip 
                        label={key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        tooltip={configDescriptions.notifications.colors[key]}
                        className="block"
                      />
                      <input
                        type="number"
                        value={value}
                        onChange={(e) => handleInputChange('notifications', 'colors', parseInt(e.target.value), key)}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                  Filters
                </h3>
                <div className="space-y-2">
                  <label className="inline-flex items-center">
                    <input
                      type="checkbox"
                      checked={config.notifications.filter_renames}
                      onChange={(e) => handleInputChange('notifications', 'filter_renames', e.target.checked)}
                      className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                    />
                    <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Filter Renames</span>
                    <Tooltip text={configDescriptions.notifications.filter_renames} />
                  </label>
                  <label className="inline-flex items-center">
                    <input
                      type="checkbox"
                      checked={config.notifications.filter_deletes}
                      onChange={(e) => handleInputChange('notifications', 'filter_deletes', e.target.checked)}
                      className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                    />
                    <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Filter Deletes</span>
                    <Tooltip text={configDescriptions.notifications.filter_deletes} />
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* External APIs Tab */}
          {activeTab === 'metadata_services' && (
            <div className="space-y-6">
              <div>
                <label className="inline-flex items-center mb-4">
                  <input
                    type="checkbox"
                    checked={config.metadata_services.enabled}
                    onChange={(e) => handleInputChange('metadata_services', 'enabled', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    Enable Metadata Services
                  </span>
                  <Tooltip text={configDescriptions.metadata_services.enabled} />
                </label>
              </div>

              {/* OMDB */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">OMDB API</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="inline-flex items-center">
                      <input
                        type="checkbox"
                        checked={config.metadata_services.omdb.enabled}
                        onChange={(e) => handleInputChange('metadata_services', 'omdb', e.target.checked, 'enabled')}
                        className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Enabled</span>
                      <Tooltip text={configDescriptions.metadata_services.omdb.enabled} />
                    </label>
                  </div>
                  <div>
                    <LabelWithTooltip 
                      label="API Key" 
                      tooltip={configDescriptions.metadata_services.omdb.api_key}
                      className="block"
                    />
                    <input
                      type="password"
                      value={config.metadata_services.omdb.api_key || ''}
                      onChange={(e) => handleInputChange('metadata_services', 'omdb', e.target.value, 'api_key')}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    />
                  </div>
                </div>
              </div>

              {/* TMDB */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">TMDB API</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="inline-flex items-center">
                      <input
                        type="checkbox"
                        checked={config.metadata_services.tmdb.enabled}
                        onChange={(e) => handleInputChange('metadata_services', 'tmdb', e.target.checked, 'enabled')}
                        className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Enabled</span>
                    </label>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      API Key
                    </label>
                    <input
                      type="password"
                      value={config.metadata_services.tmdb.api_key || ''}
                      onChange={(e) => handleInputChange('metadata_services', 'tmdb', e.target.value, 'api_key')}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    />
                  </div>
                </div>
              </div>

              {/* TVDB */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">TVDB API</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="inline-flex items-center">
                      <input
                        type="checkbox"
                        checked={config.metadata_services.tvdb.enabled}
                        onChange={(e) => handleInputChange('metadata_services', 'tvdb', e.target.checked, 'enabled')}
                        className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Enabled</span>
                    </label>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      API Key
                    </label>
                    <input
                      type="password"
                      value={config.metadata_services.tvdb.api_key || ''}
                      onChange={(e) => handleInputChange('metadata_services', 'tvdb', e.target.value, 'api_key')}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Server Tab */}
          {activeTab === 'server' && (
            <div className="space-y-6">
              <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md p-4">
                <div className="flex">
                  <ExclamationTriangleIcon className="h-5 w-5 text-yellow-400" />
                  <div className="ml-3">
                    <p className="text-sm text-yellow-800 dark:text-yellow-300">
                      These settings affect core server operation. Changes may require restart.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <LabelWithTooltip 
                    label="Host" 
                    tooltip={configDescriptions.server.host}
                    className="block"
                  />
                  <input
                    type="text"
                    value={config.server.host}
                    onChange={(e) => handleInputChange('server', 'host', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <LabelWithTooltip 
                    label="Port" 
                    tooltip={configDescriptions.server.port}
                    className="block"
                  />
                  <input
                    type="number"
                    value={config.server.port}
                    onChange={(e) => handleInputChange('server', 'port', parseInt(e.target.value))}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <LabelWithTooltip 
                    label="Log Level" 
                    tooltip={configDescriptions.server.log_level}
                    className="block"
                  />
                  <select
                    value={config.server.log_level}
                    onChange={(e) => handleInputChange('server', 'log_level', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  >
                    <option value="DEBUG">DEBUG</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                    <option value="CRITICAL">CRITICAL</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Run Mode
                  </label>
                  <select
                    value={config.server.run_mode}
                    onChange={(e) => handleInputChange('server', 'run_mode', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  >
                    <option value="all">All Services</option>
                    <option value="webhook">Webhook Only</option>
                    <option value="web">Web Only</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Data Directory
                  </label>
                  <input
                    type="text"
                    value={config.server.data_dir}
                    onChange={(e) => handleInputChange('server', 'data_dir', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Log Directory
                  </label>
                  <input
                    type="text"
                    value={config.server.log_dir}
                    onChange={(e) => handleInputChange('server', 'log_dir', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Environment
                  </label>
                  <select
                    value={config.server.environment}
                    onChange={(e) => handleInputChange('server', 'environment', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  >
                    <option value="production">Production</option>
                    <option value="development">Development</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Allowed Hosts (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={config.server.allowed_hosts?.join(', ') || ''}
                    onChange={(e) => handleArrayChange('server', 'allowed_hosts', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    placeholder="Leave empty to allow all"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="inline-flex items-center">
                  <input
                    type="checkbox"
                    checked={config.server.development_mode}
                    onChange={(e) => handleInputChange('server', 'development_mode', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Development Mode</span>
                </label>
                <label className="inline-flex items-center">
                  <input
                    type="checkbox"
                    checked={config.server.show_docker_interfaces}
                    onChange={(e) => handleInputChange('server', 'show_docker_interfaces', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Show Docker Interfaces</span>
                </label>
                <label className="inline-flex items-center">
                  <input
                    type="checkbox"
                    checked={config.server.force_color_output}
                    onChange={(e) => handleInputChange('server', 'force_color_output', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Force Color Output</span>
                </label>
                <label className="inline-flex items-center">
                  <input
                    type="checkbox"
                    checked={config.server.disable_color_output}
                    onChange={(e) => handleInputChange('server', 'disable_color_output', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">Disable Color Output</span>
                </label>
              </div>
            </div>
          )}

          {/* Web Interface Tab */}
          {activeTab === 'web_interface' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="inline-flex items-center">
                    <input
                      type="checkbox"
                      checked={config.web_interface.enabled}
                      onChange={(e) => handleInputChange('web_interface', 'enabled', e.target.checked)}
                      className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                    />
                    <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                      Enable Web Interface
                    </span>
                    <Tooltip text={configDescriptions.web_interface.enabled} />
                  </label>
                </div>
                <div>
                  <label className="inline-flex items-center">
                    <input
                      type="checkbox"
                      checked={config.web_interface.auth_enabled}
                      onChange={(e) => handleInputChange('web_interface', 'auth_enabled', e.target.checked)}
                      className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                    />
                    <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                      Require Web Interface Authentication
                    </span>
                    <Tooltip text={configDescriptions.web_interface.auth_enabled} />
                  </label>
                </div>
                <div>
                  <label className="inline-flex items-center">
                    <input
                      type="checkbox"
                      checked={config.web_interface.require_webhook_auth || false}
                      onChange={(e) => handleInputChange('web_interface', 'require_webhook_auth', e.target.checked)}
                      className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                      disabled={!config.web_interface.auth_enabled}
                    />
                    <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                      Require Webhook Authentication
                    </span>
                    <Tooltip text={configDescriptions.web_interface.require_webhook_auth} />
                  </label>
                  {config.web_interface.require_webhook_auth && (
                    <div className="mt-2 space-y-2">
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Jellyfin webhooks must include a Bearer token with the same credentials
                      </p>
                      <button
                        type="button"
                        onClick={() => setShowWebhookToken(true)}
                        className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
                      >
                        <KeyIcon className="h-3 w-3 mr-1.5" />
                        View Webhook Token
                      </button>
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Host
                  </label>
                  <input
                    type="text"
                    value={config.web_interface.host}
                    onChange={(e) => handleInputChange('web_interface', 'host', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Port
                  </label>
                  <input
                    type="number"
                    value={config.web_interface.port}
                    onChange={(e) => handleInputChange('web_interface', 'port', parseInt(e.target.value))}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                {config.web_interface.auth_enabled && (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Username
                      </label>
                      <input
                        type="text"
                        value={config.web_interface.username || ''}
                        onChange={(e) => handleInputChange('web_interface', 'username', e.target.value)}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Password
                      </label>
                      <input
                        type="password"
                        value={config.web_interface.password || ''}
                        onChange={(e) => handleInputChange('web_interface', 'password', e.target.value)}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                      />
                    </div>
                  </>
                )}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    JWT Secret
                  </label>
                  <input
                    type="password"
                    value={config.web_interface.jwt_secret || ''}
                    onChange={(e) => handleInputChange('web_interface', 'jwt_secret', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    placeholder="Auto-generated if empty"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Database Tab */}
          {activeTab === 'database' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <LabelWithTooltip 
                    label="Database Path" 
                    tooltip={configDescriptions.database.path}
                    className="block"
                  />
                  <input
                    type="text"
                    value={config.database.path}
                    onChange={(e) => handleInputChange('database', 'path', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
                <div>
                  <LabelWithTooltip 
                    label="Vacuum Interval (hours)" 
                    tooltip={configDescriptions.database.vacuum_interval_hours}
                    className="block"
                  />
                  <input
                    type="number"
                    value={config.database.vacuum_interval_hours}
                    onChange={(e) => handleInputChange('database', 'vacuum_interval_hours', parseInt(e.target.value))}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    min="1"
                    max="168"
                  />
                </div>
              </div>
              <div>
                <label className="inline-flex items-center">
                  <input
                    type="checkbox"
                    checked={config.database.wal_mode}
                    onChange={(e) => handleInputChange('database', 'wal_mode', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                    Enable WAL Mode (Write-Ahead Logging)
                  </span>
                  <Tooltip text={configDescriptions.database.wal_mode} />
                </label>
              </div>
            </div>
          )}

          {/* Templates Tab */}
          {activeTab === 'templates' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Template Directory
                  </label>
                  <input
                    type="text"
                    value={config.templates.directory}
                    onChange={(e) => handleInputChange('templates', 'directory', e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                  />
                </div>
              </div>
              
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                  Template Files
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(config.templates).filter(([key]) => key !== 'directory').map(([key, value]) => (
                    <div key={key}>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </label>
                      <input
                        type="text"
                        value={value}
                        onChange={(e) => handleInputChange('templates', key, e.target.value)}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* SSL/Security Tab */}
          {activeTab === 'ssl' && (
            <div className="space-y-6">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                <div className="flex">
                  <LockClosedIcon className="h-5 w-5 text-blue-400" />
                  <div className="ml-3">
                    <p className="text-sm text-blue-800 dark:text-blue-300">
                      SSL/TLS configuration for secure connections
                    </p>
                  </div>
                </div>
              </div>

              <div>
                <label className="inline-flex items-center mb-4">
                  <input
                    type="checkbox"
                    checked={config.web_interface.ssl_enabled}
                    onChange={(e) => handleInputChange('web_interface', 'ssl_enabled', e.target.checked)}
                    className="rounded border-gray-300 text-purple-600 shadow-sm focus:border-purple-500 focus:ring-purple-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    Enable SSL/HTTPS
                  </span>
                  <Tooltip text={configDescriptions.ssl.enabled} />
                </label>
              </div>

              {config.web_interface.ssl_enabled && (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <LabelWithTooltip 
                        label="SSL Port" 
                        tooltip={configDescriptions.ssl.port}
                        className="block"
                      />
                      <input
                        type="number"
                        value={config.web_interface.ssl_port}
                        onChange={(e) => handleInputChange('web_interface', 'ssl_port', parseInt(e.target.value))}
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <LabelWithTooltip 
                        label="SSL Certificate" 
                        tooltip={configDescriptions.ssl.cert_path}
                        className="block mb-2"
                      />
                      <div className="flex items-center space-x-4">
                        <input
                          type="file"
                          accept=".crt,.pem,.cer"
                          onChange={(e) => setSslFile(e.target.files?.[0] || null)}
                          className="block w-full text-sm text-gray-500 dark:text-gray-400
                            file:mr-4 file:py-2 file:px-4
                            file:rounded-md file:border-0
                            file:text-sm file:font-semibold
                            file:bg-purple-50 file:text-purple-700
                            hover:file:bg-purple-100
                            dark:file:bg-purple-900 dark:file:text-purple-300"
                        />
                        <button
                          onClick={() => handleSSLFileUpload('cert')}
                          disabled={!sslFile}
                          className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600 disabled:opacity-50"
                        >
                          <ArrowUpTrayIcon className="h-4 w-4" />
                        </button>
                      </div>
                      {config.web_interface.ssl_cert_path && (
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          Current: {config.web_interface.ssl_cert_path}
                        </p>
                      )}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        SSL Private Key
                      </label>
                      <div className="flex items-center space-x-4">
                        <input
                          type="file"
                          accept=".key,.pem"
                          onChange={(e) => setSslKeyFile(e.target.files?.[0] || null)}
                          className="block w-full text-sm text-gray-500 dark:text-gray-400
                            file:mr-4 file:py-2 file:px-4
                            file:rounded-md file:border-0
                            file:text-sm file:font-semibold
                            file:bg-purple-50 file:text-purple-700
                            hover:file:bg-purple-100
                            dark:file:bg-purple-900 dark:file:text-purple-300"
                        />
                        <button
                          onClick={() => handleSSLFileUpload('key')}
                          disabled={!sslKeyFile}
                          className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600 disabled:opacity-50"
                        >
                          <ArrowUpTrayIcon className="h-4 w-4" />
                        </button>
                      </div>
                      {config.web_interface.ssl_key_path && (
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          Current: {config.web_interface.ssl_key_path}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                      Certificate Tools
                    </h3>
                    <div className="space-x-4">
                      <button
                        onClick={generateCSR}
                        className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600"
                      >
                        <DocumentArrowDownIcon className="h-4 w-4 mr-2" />
                        Generate CSR
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
      
      {/* Webhook Token Modal */}
      {showWebhookToken && (
        <WebhookTokenDisplay onClose={() => setShowWebhookToken(false)} />
      )}
    </div>
  );
};

export default Config;