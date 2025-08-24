import { useState, useEffect } from 'react';
import { Line, Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
  ArrowPathIcon,
  ServerIcon,
  FilmIcon,
  TvIcon,
  MusicalNoteIcon,
} from '@heroicons/react/24/outline';
import { apiService } from '../services/api';
import JellyfinStats from '../components/JellyfinStats';
import logger from '../services/logger';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const Overview = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [recentNotifications, setRecentNotifications] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    logger.debug('Overview: Starting fetchData', { 
      currentState: { loading, hasStats: !!stats, hasHealth: !!health, hasError: !!error }
    });
    
    try {
      setRefreshing(true);
      logger.debug('Overview: Making API calls to /api/overview and /api/health');
      
      const [overviewData, healthData] = await Promise.all([
        apiService.getOverview(),
        apiService.healthCheck(),
      ]);

      logger.info('Overview: API responses received', {
        overviewStatus: overviewData.status,
        healthStatus: healthData.status,
        hasOverviewData: !!overviewData.data,
        hasHealthData: !!healthData.data,
        overviewKeys: overviewData.data ? Object.keys(overviewData.data) : [],
        healthKeys: healthData.data ? Object.keys(healthData.data) : []
      });

      // Extract data from axios response
      const overview = overviewData.data;
      logger.debug('Overview: Processing overview data', {
        hasData: !!overview,
        keys: overview ? Object.keys(overview) : [],
        totalItems: overview?.total_items,
        itemsToday: overview?.items_today
      });
      setStats(overview);
      
      logger.debug('Overview: Processing health data', {
        status: healthData.data?.status,
        components: healthData.data?.components ? Object.keys(healthData.data.components) : []
      });
      setHealth(healthData.data);
      
      const notifications = overview && overview['recent_notifications'] ? overview['recent_notifications'] : [];
      logger.debug('Overview: Processing notifications', {
        count: notifications.length,
        hasNotifications: notifications.length > 0
      });
      setRecentNotifications(notifications);
      
      setError(null);
      logger.info('Overview: Data fetch successful');
    } catch (err) {
      logger.error('Overview: API Error', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        statusText: err.response?.statusText,
        url: err.config?.url
      });
      setError('Failed to fetch dashboard data');
    } finally {
      setLoading(false);
      setRefreshing(false);
      logger.debug('Overview: Fetch complete, loading set to false');
    }
  };

  useEffect(() => {
    void fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const getHealthColor = (status) => {
    switch (status) {
      case 'healthy':
        return 'text-green-600 bg-green-100';
      case 'degraded':
        return 'text-yellow-600 bg-yellow-100';
      case 'unhealthy':
        return 'text-red-600 bg-red-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const getHealthIcon = (status) => {
    switch (status) {
      case 'healthy':
        return <CheckCircleIcon className="h-5 w-5" />;
      case 'degraded':
        return <ExclamationTriangleIcon className="h-5 w-5" />;
      case 'unhealthy':
        return <XCircleIcon className="h-5 w-5" />;
      default:
        return <ServerIcon className="h-5 w-5" />;
    }
  };

  const getContentIcon = (type) => {
    switch (type?.toLowerCase()) {
      case 'movie':
        return <FilmIcon className="h-5 w-5" />;
      case 'series':
      case 'episode':
        return <TvIcon className="h-5 w-5" />;
      case 'music':
      case 'audio':
        return <MusicalNoteIcon className="h-5 w-5" />;
      default:
        return <ServerIcon className="h-5 w-5" />;
    }
  };

  // Chart data
  const queueStats = stats?.['queue_stats'] || {};
  const lineDataset = {
    label: 'Notifications',
    data: Object.values(queueStats).map(v => typeof v === 'number' ? v : Number(v) || 0),
    tension: 0.3,
    fill: true,
  };
  // Add color properties using bracket notation to avoid type warnings
  lineDataset['borderColor'] = 'rgb(147, 51, 234)';
  lineDataset['backgroundColor'] = 'rgba(147, 51, 234, 0.1)';
  
  const notificationChartData = {
    labels: Object.keys(queueStats),
    datasets: [lineDataset],
  };

  const contentTypeChartData = {
    labels: ['Movies', 'TV Shows', 'Music'],
    datasets: [
      {
        data: [
          Number((stats && stats['discord_webhooks'] && stats['discord_webhooks']['movies'] && stats['discord_webhooks']['movies']['count']) || 0),
          Number((stats && stats['discord_webhooks'] && stats['discord_webhooks']['tv'] && stats['discord_webhooks']['tv']['count']) || 0),
          Number((stats && stats['discord_webhooks'] && stats['discord_webhooks']['music'] && stats['discord_webhooks']['music']['count']) || 0),
        ],
        backgroundColor: [
          'rgba(147, 51, 234, 0.8)',
          'rgba(59, 130, 246, 0.8)',
          'rgba(16, 185, 129, 0.8)',
        ],
        borderWidth: 0,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        mode: 'index',
        intersect: false,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          display: true,
          color: 'rgba(156, 163, 175, 0.1)',
        },
      },
      x: {
        grid: {
          display: false,
        },
      },
    },
  };

  // Log render conditions
  logger.debug('Overview: Render check', {
    loading,
    hasStats: !!stats,
    hasHealth: !!health,
    hasError: !!error,
    statsKeys: stats ? Object.keys(stats) : null,
    willShowLoading: loading && !stats,
    willShowContent: !loading || stats
  });

  if (loading && !stats) {
    logger.debug('Overview: Showing loading spinner');
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  logger.info('Overview: Rendering main content', {
    statsAvailable: !!stats,
    healthAvailable: !!health,
    notificationsCount: recentNotifications.length
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard Overview</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Monitor your Jellynouncer service health and statistics
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={refreshing}
          className={`
            inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md
            text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 
            focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50 disabled:cursor-not-allowed
          `}
        >
          <ArrowPathIcon className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {/* Health Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {health && health['components'] && Object.entries(health['components']).map(([name, status]) => (
          <div key={name} className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400 capitalize">
                  {name.replace('_', ' ')}
                </p>
                <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white capitalize">
                  {status}
                </p>
              </div>
              <div className={`p-2 rounded-full ${getHealthColor(status)}`}>
                {getHealthIcon(status)}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Total Notifications
          </p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
            {(stats && stats['total_items']) || 0}
          </p>
          <p className="mt-1 text-sm text-green-600 dark:text-green-400">
            +{(stats && stats['items_today']) || 0} today
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Queue Size
          </p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
            {(stats && stats['queue_stats'] && stats['queue_stats']['pending']) || 0}
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {(stats && stats['queue_stats'] && stats['queue_stats']['processing_rate']) || 0}/min
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Database Items
          </p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
            {(stats && stats['total_items']) || 0}
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {(stats && stats['system_health'] && stats['system_health']['database_size_mb']) || 0} MB
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Uptime
          </p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
            {(stats && stats['system_health'] && stats['system_health']['uptime_hours']) || 0}h
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {(stats && stats['system_health'] && stats['system_health']['uptime_percentage']) || 100}% available
          </p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Notifications Over Time
          </h2>
          <div className="h-64">
            <Line data={notificationChartData} options={chartOptions} />
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Content Distribution
          </h2>
          <div className="h-64">
            <Doughnut data={contentTypeChartData} options={{ ...chartOptions, aspectRatio: 1 }} />
          </div>
        </div>
      </div>

      {/* Jellyfin Server Statistics */}
      {stats && stats['jellyfin_stats'] && (
        <JellyfinStats stats={stats['jellyfin_stats']} />
      )}

      {/* Recent Notifications */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent Notifications
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Time
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Title
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Event
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {recentNotifications.length > 0 ? (
                recentNotifications.map((notification, index) => (
                  <tr key={index} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                      {new Date(notification.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-gray-900 dark:text-gray-300">
                        {getContentIcon(notification.type)}
                        <span className="ml-2">{notification.type}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                      {notification.title}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                      <span className={`
                        inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
                        ${notification.event === 'new' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 
                          notification.event === 'upgraded' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' :
                          'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}
                      `}>
                        {notification.event}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                      <span className={`
                        inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
                        ${notification.status === 'sent' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 
                          notification.status === 'failed' ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' :
                          'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'}
                      `}>
                        {notification.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="5" className="px-6 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
                    No recent notifications
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Overview;