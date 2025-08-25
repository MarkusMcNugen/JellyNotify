import { useState, useRef, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiService } from '../services/api'
import { Icon, IconDuotone, IconLight } from '../components/FontAwesomeIcon'
import { parseLogText, filterLogs, getLogStatistics, formatLogForDisplay, exportLogs, LOG_LEVEL_COLORS } from '../utils/logParser'
import { FixedSizeList as VirtualList } from 'react-window'
import logger from '../services/logger'
// Removed unused lucide-react import - using FontAwesome icons instead

const Logs = () => {
  logger.info('[COMPONENT] Logs: Starting component initialization');
  
  const [logFile, setLogFile] = useState('jellynouncer.log')
  const [lines, setLines] = useState(500)
  
  logger.debug('[COMPONENT] Logs: State hooks initialized');
  const [level, setLevel] = useState('')
  const [component, setComponent] = useState('')
  const [search, setSearch] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [showStats] = useState(true) // Could be toggled in future
  
  const listRef = useRef(null)
  
  // Fetch logs
  const { data: logsResponse, refetch, isLoading } = useQuery({
    queryKey: ['logs', logFile, lines, level, component, search],
    queryFn: async () => {
      logger.debug('Logs: Fetching logs', {
        file: logFile,
        lines,
        level,
        component,
        search
      });
      try {
        const result = await apiService.getLogs({
          file: logFile,
          lines,
          level: level || undefined,
          component: component || undefined,
          search: search || undefined
        });
        logger.info('Logs: Data received', {
          logCount: result?.data?.logs?.length || 0,
          hasData: !!result?.data
        });
        return result;
      } catch (err) {
        logger.error('Logs: Failed to fetch', err);
        throw err;
      }
    },
    refetchInterval: autoRefresh ? 5000 : false
  })
  
  // Parse and filter logs
  const { parsedLogs, stats } = useMemo(() => {
    if (!logsResponse?.data?.logs) {
      return { parsedLogs: [], stats: {} }
    }
    
    // Convert API response to raw log text
    const logText = logsResponse.data.logs.map(log => 
      `[${log.timestamp}][${log.level}][${log.component}] ${log.message}`
    ).join('\n')
    
    const parsed = parseLogText(logText)
    const filtered = filterLogs(parsed, { level, component, search })
    const statistics = getLogStatistics(filtered)
    
    return { parsedLogs: filtered, stats: statistics }
  }, [logsResponse, level, component, search])
  
  // Get log level icon
  const getLevelIcon = (level) => {
    switch(level) {
      case 'ERROR':
      case 'CRITICAL':
      case 'FATAL':
        return <IconDuotone icon="exclamation-circle" size="xs" className="text-red-500" />
      case 'WARNING':
      case 'WARN':
        return <IconDuotone icon="exclamation-triangle" size="xs" className="text-yellow-500" />
      case 'INFO':
        return <IconDuotone icon="info-circle" size="xs" className="text-blue-500" />
      case 'DEBUG':
        return <IconDuotone icon="bug" size="xs" className="text-gray-500" />
      default:
        return null
    }
  }
  
  // Row renderer for virtual list
  const LogRow = ({ index, style }) => {
    const log = parsedLogs[index]
    
    if (!log) return null
    
    if (log.type !== 'log') {
      return (
        <div style={style} className="flex items-center px-4 py-1 font-mono text-xs text-dark-text-muted">
          {log.text}
        </div>
      )
    }
    
    const formatted = formatLogForDisplay(log, { 
      showTimestamp: true, 
      showComponent: true,
      highlightSearch: search 
    })
    
    return (
      <div 
        style={style} 
        className={`flex items-center gap-2 px-4 py-1 hover:bg-dark-elevated/50 transition-colors ${formatted.rowClassName}`}
      >
        {/* Timestamp */}
        <span className="text-xs text-dark-text-muted font-mono min-w-[180px]">
          {log.timestamp}
        </span>
        
        {/* Level */}
        <span 
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold min-w-[80px] justify-center"
          style={{ 
            color: formatted.level.color,
            backgroundColor: formatted.level.bgColor 
          }}
        >
          {getLevelIcon(log.level)}
          {log.level}
        </span>
        
        {/* Component */}
        <span className="text-xs text-jellyfin-purple font-mono min-w-[200px]">
          [{log.component}]
        </span>
        
        {/* Message */}
        <span 
          className="flex-1 text-sm font-mono text-dark-text-primary"
          dangerouslySetInnerHTML={{ 
            __html: search ? log.message.replace(
              new RegExp(`(${search})`, 'gi'), 
              '<mark class="bg-yellow-400/30 text-yellow-200">$1</mark>'
            ) : log.message 
          }}
        />
      </div>
    )
  }
  
  // Export logs handler
  const handleExport = (format) => {
    const exported = exportLogs(parsedLogs, format)
    const blob = new Blob([exported], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `jellynouncer-logs-${new Date().toISOString()}.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }
  
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-dark-border">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">Log Viewer</h2>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input 
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded"
              />
              Auto-refresh
            </label>
            <button 
              onClick={() => refetch()}
              className="btn btn-secondary"
              disabled={isLoading}
            >
              <IconDuotone icon="sync-alt" spin={isLoading} />
            </button>
          </div>
        </div>
        
        {/* Filters */}
        <div className="flex gap-3">
          <select 
            className="input"
            value={logFile}
            onChange={(e) => setLogFile(e.target.value)}
          >
            <option value="jellynouncer.log">Main Log</option>
            <option value="error.log">Error Log</option>
            <option value="debug.log">Debug Log</option>
          </select>
          
          <select 
            className="input"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            <option value="">All Levels</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          
          <input 
            type="text"
            className="input"
            placeholder="Filter by component..."
            value={component}
            onChange={(e) => setComponent(e.target.value)}
          />
          
          <div className="flex-1 relative">
            <IconLight icon="search" className="absolute left-3 top-1/2 transform -translate-y-1/2 text-dark-text-muted" size="lg" />
            <input 
              type="text"
              className="input pl-10 w-full"
              placeholder="Search logs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          
          <select 
            className="input"
            value={lines}
            onChange={(e) => setLines(Number(e.target.value))}
          >
            <option value={100}>Last 100</option>
            <option value={500}>Last 500</option>
            <option value={1000}>Last 1000</option>
            <option value={5000}>Last 5000</option>
          </select>
          
          <div className="relative">
            <button className="btn btn-secondary flex items-center gap-2">
              <IconDuotone icon="download" size="sm" />
              Export
              <IconLight icon="chevron-down" size="xs" />
            </button>
            <div className="absolute right-0 mt-1 w-32 bg-dark-elevated rounded-lg shadow-lg hidden group-hover:block">
              <button 
                onClick={() => handleExport('txt')}
                className="w-full px-4 py-2 text-left hover:bg-dark-border text-sm"
              >
                Text (.txt)
              </button>
              <button 
                onClick={() => handleExport('json')}
                className="w-full px-4 py-2 text-left hover:bg-dark-border text-sm"
              >
                JSON (.json)
              </button>
              <button 
                onClick={() => handleExport('csv')}
                className="w-full px-4 py-2 text-left hover:bg-dark-border text-sm"
              >
                CSV (.csv)
              </button>
            </div>
          </div>
        </div>
      </div>
      
      {/* Statistics Bar */}
      {showStats && stats.total > 0 && (
        <div className="px-4 py-2 bg-dark-elevated border-b border-dark-border">
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-dark-text-muted">Total:</span>
              <span className="font-semibold">{stats.total}</span>
            </div>
            
            {Object.entries(LOG_LEVEL_COLORS).map(([levelName, levelStyle]) => {
              const count = stats.byLevel[levelName] || 0
              if (count === 0) return null
              
              return (
                <div key={levelName} className="flex items-center gap-2">
                  <span 
                    className="px-2 py-0.5 rounded text-xs font-bold"
                    style={{ 
                      color: levelStyle.color,
                      backgroundColor: levelStyle.bgColor 
                    }}
                  >
                    {levelName}
                  </span>
                  <span className="font-semibold">{count}</span>
                </div>
              )
            })}
            
            {stats.errorCount > 0 && (
              <div className="flex items-center gap-2 text-red-500">
                <Icon icon="exclamation-circle" size="sm" />
                <span>{stats.errorCount} errors</span>
              </div>
            )}
            
            {stats.warningCount > 0 && (
              <div className="flex items-center gap-2 text-yellow-500">
                <Icon icon="exclamation-triangle" size="sm" />
                <span>{stats.warningCount} warnings</span>
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* Log Viewer */}
      <div className="flex-1 bg-dark-bg">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="spinner"></div>
          </div>
        ) : parsedLogs.length > 0 ? (
          <VirtualList
            ref={listRef}
            height={window.innerHeight - 200} // Adjust based on header height
            itemCount={parsedLogs.length}
            itemSize={28} // Height of each log row
            width="100%"
            className="scrollbar-thin scrollbar-thumb-dark-border scrollbar-track-dark-surface"
          >
            {LogRow}
          </VirtualList>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Info size={48} className="text-dark-text-muted mx-auto mb-4" />
              <p className="text-dark-text-secondary">No logs found</p>
              <p className="text-sm text-dark-text-muted mt-2">
                Try adjusting your filters or refreshing
              </p>
            </div>
          </div>
        )}
      </div>
      
      {/* Recent Errors Panel (if any) */}
      {stats.recentErrors && stats.recentErrors.length > 0 && (
        <div className="p-4 bg-red-900/20 border-t border-red-500/30">
          <h3 className="text-sm font-semibold text-red-400 mb-2">Recent Errors</h3>
          <div className="space-y-1">
            {stats.recentErrors.slice(0, 3).map((error, index) => (
              <div key={index} className="text-xs">
                <span className="text-dark-text-muted">{error.timestamp}</span>
                <span className="text-red-400 ml-2">[{error.component}]</span>
                <span className="text-dark-text-primary ml-2">{error.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default Logs