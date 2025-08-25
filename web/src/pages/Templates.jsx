import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiService } from '../services/api'
import Jinja2Editor from '../components/Jinja2Editor'
import { Icon, IconDuotone, IconLight } from '../components/FontAwesomeIcon'
import toast from 'react-hot-toast'
import logger from '../services/logger'

const Templates = () => {
  logger.info('[COMPONENT] Templates: Starting component initialization');
  
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [editorContent, setEditorContent] = useState('')
  
  logger.debug('[COMPONENT] Templates: State hooks initialized');
  const [showCheatsheet, setShowCheatsheet] = useState(false)
  const [isModified, setIsModified] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newTemplateName, setNewTemplateName] = useState('')
  const [activeTab, setActiveTab] = useState('basic')
  const [theme, setTheme] = useState(() => {
    // Check if dark mode is enabled
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  })
  
  const { data: templates, refetch } = useQuery({
    queryKey: ['templates'],
    queryFn: async () => {
      logger.debug('Templates: Fetching template list');
      try {
        const response = await apiService.getTemplates();
        const templates = response?.data || [];
        logger.info('Templates: List received', {
          count: templates.length,
          templates: templates.map(t => t.name)
        });
        return templates;
      } catch (err) {
        logger.error('Templates: Failed to fetch list', err);
        throw err;
      }
    }
  })

  const saveMutation = useMutation({
    mutationFn: ({ name, content }) => {
      logger.debug('Templates: Saving template', { name, contentLength: content.length });
      return apiService.updateTemplate(name, content);
    },
    onSuccess: () => {
      logger.info('Templates: Save successful');
      toast.success('Template saved successfully')
      setIsModified(false)
      void refetch()
    },
    onError: (err) => {
      logger.error('Templates: Save failed', err);
    }
  })

  const restoreMutation = useMutation({
    mutationFn: (name) => {
      logger.debug('Templates: Restoring template to default', { name });
      return apiService.restoreTemplate(name);
    },
    onSuccess: () => {
      logger.info('Templates: Restore successful');
      toast.success('Template restored to default')
      void loadTemplate(selectedTemplate)
      void refetch()
    },
    onError: (err) => {
      logger.error('Templates: Restore failed', err);
    }
  })

  const createMutation = useMutation({
    mutationFn: ({ name, content }) => {
      logger.debug('Templates: Creating new template', { name });
      return apiService.updateTemplate(name, content);
    },
    onSuccess: (_, { name }) => {
      logger.info('Templates: Create successful');
      toast.success('Template created successfully')
      setShowCreateModal(false)
      setNewTemplateName('')
      void refetch()
      void loadTemplate(name)
    },
    onError: (err) => {
      logger.error('Templates: Create failed', err);
      toast.error('Failed to create template')
    }
  })

  const loadTemplate = async (name) => {
    logger.debug('Templates: Loading template', { name });
    try {
      const response = await apiService.getTemplate(name)
      logger.info('Templates: Template loaded', { 
        name, 
        contentLength: response.data?.content?.length || 0 
      });
      setSelectedTemplate(name)
      setEditorContent(response.data.content)
      setIsModified(false)
    } catch (err) {
      logger.error('Templates: Failed to load template', { name, error: err });
    }
  }

  const handleEditorChange = (value) => {
    setEditorContent(value || '')
    setIsModified(true)
  }

  const handleSave = () => {
    if (isModified && selectedTemplate) {
      saveMutation.mutate({ name: selectedTemplate, content: editorContent })
    }
  }

  // Auto-select first template when templates are loaded
  useEffect(() => {
    if (templates && templates.length > 0 && !selectedTemplate) {
      const firstTemplate = templates[0].name;
      logger.debug('Templates: Auto-selecting first template', { name: firstTemplate });
      loadTemplate(firstTemplate);
    }
  }, [templates]); // Only depend on templates to avoid re-running

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-dark-border">
        <h2 className="text-2xl font-bold">Template Editor</h2>
        <div className="flex gap-2">
          <button 
            onClick={() => setShowCheatsheet(!showCheatsheet)}
            className="btn btn-secondary"
          >
            <IconDuotone icon="info-circle" className="mr-2" color="text-blue-500" />
            Jinja2 Guide
          </button>
        </div>
      </div>
      
      <div className="flex-1 flex">
        {/* Template List */}
        <div className="w-64 bg-dark-surface border-r border-dark-border">
          <div className="p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-dark-text-secondary">Templates</h3>
              <button 
                onClick={() => setShowCreateModal(true)}
                className="p-1 hover:bg-dark-elevated rounded group"
                title="Create new template"
              >
                <IconDuotone icon="plus-circle" size="lg" className="text-gray-400 group-hover:text-purple-500 transition-colors" />
              </button>
            </div>
            
            <div className="space-y-1">
              {templates?.map(template => (
                <div
                  key={template.name}
                  onClick={() => loadTemplate(template.name)}
                  className={`
                    p-3 rounded-lg cursor-pointer transition-all duration-200
                    hover:bg-dark-elevated
                    ${selectedTemplate === template.name 
                      ? 'bg-gradient-to-r from-jellyfin-purple/20 to-jellyfin-blue/20 border-l-4 border-jellyfin-purple' 
                      : ''
                    }
                  `}
                >
                  <div className="flex items-center gap-2">
                    <IconDuotone icon="file-code" className="text-dark-text-muted" size="sm" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{template.name}</p>
                      <p className="text-xs text-dark-text-muted">
                        {template['is_default'] ? 'Default' : 'Custom'}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        
        {/* Editor Area */}
        <div className="flex-1 flex flex-col">
          {selectedTemplate ? (
            <>
              {/* Editor Header */}
              <div className="flex items-center justify-between p-4 bg-dark-elevated border-b border-dark-border">
                <div className="flex items-center gap-4">
                  <h3 className="text-lg font-semibold">{selectedTemplate}.j2</h3>
                  {isModified && (
                    <span className="text-xs text-yellow-500 flex items-center gap-1">
                      <span className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></span>
                      Modified
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={() => { 
                      if (selectedTemplate) {
                        void restoreMutation.mutate(selectedTemplate);
                      }
                    }}
                    className="btn btn-secondary"
                    disabled={!templates?.find(t => t.name === selectedTemplate)?.['is_default']}
                  >
                    <IconDuotone icon="undo-alt" className="mr-2" color="text-yellow-500" />
                    Restore Default
                  </button>
                  <button 
                    onClick={() => { saveMutation.mutate({ name: selectedTemplate, content: editorContent }) }}
                    className="btn btn-primary"
                    disabled={!isModified}
                  >
                    <IconDuotone icon="save" className="mr-2" color="text-green-500" />
                    Save
                  </button>
                </div>
              </div>
              
              {/* CodeMirror 6 Jinja2 Editor */}
              <div className="flex-1 relative overflow-hidden">
                <Jinja2Editor
                  value={editorContent}
                  onChange={handleEditorChange}
                  onSave={handleSave}
                  theme={theme}
                  height="calc(100vh - 200px)"
                  readOnly={false}
                  placeholder="Enter your Jinja2 template here..."
                />
                
                {/* Jinja2 Cheatsheet Overlay */}
                {showCheatsheet && (
                  <div className="absolute top-4 right-4 w-[600px] max-h-[90vh] card overflow-auto z-50">
                    <div className="flex items-center justify-between mb-4">
                      <h4 className="font-semibold text-lg">Jinja2 Quick Reference</h4>
                      <button 
                        onClick={() => setShowCheatsheet(false)}
                        className="p-1 hover:bg-dark-elevated rounded"
                      >
                        <IconLight icon="times" size="lg" />
                      </button>
                    </div>
                    
                    <div className="space-y-4">
                      {/* Variables */}
                      <div>
                        <h5 className="text-sm font-semibold text-jellyfin-purple mb-2">Variables</h5>
                        <div className="space-y-1">
                          <CodeExample 
                            code="{{ item.name }}"
                            description="Output variable"
                          />
                          <CodeExample 
                            code="{{ item.name | default('Unknown') }}"
                            description="With default value"
                          />
                          <CodeExample 
                            code="{{ item.name | truncate(50) }}"
                            description="Apply filter"
                          />
                        </div>
                      </div>
                      
                      {/* Control Structures */}
                      <div>
                        <h5 className="text-sm font-semibold text-jellyfin-purple mb-2">Control Structures</h5>
                        <div className="space-y-1">
                          <CodeExample 
                            code="{% if item.video_height >= 1080 %}\n  HD Content\n{% endif %}"
                            description="Conditional"
                          />
                          <CodeExample 
                            code="{% for genre in item.genres %}\n  {{ genre }}\n{% endfor %}"
                            description="Loop"
                          />
                          <CodeExample 
                            code="{% set quality = 'HD' if item.video_height >= 1080 else 'SD' %}"
                            description="Variable assignment"
                          />
                        </div>
                      </div>
                      
                      {/* Filters */}
                      <div>
                        <h5 className="text-sm font-semibold text-jellyfin-purple mb-2">Common Filters</h5>
                        <div className="space-y-1">
                          <CodeExample 
                            code="{{ item.name | upper }}"
                            description="Uppercase"
                          />
                          <CodeExample 
                            code="{{ item.overview | truncate(200, True, '...') }}"
                            description="Truncate with ellipsis"
                          />
                          <CodeExample 
                            code="{{ item.genres | join(', ') }}"
                            description="Join list"
                          />
                          <CodeExample 
                            code="{{ item.name | tojson }}"
                            description="JSON escape (important!)"
                          />
                        </div>
                      </div>
                      
                      {/* Available Variables with Tabs */}
                      <div>
                        <h5 className="text-sm font-semibold text-jellyfin-purple mb-2">Available Variables</h5>
                        
                        {/* Tab Navigation */}
                        <div className="flex flex-wrap gap-1 mb-2 border-b border-dark-border">
                          {['basic', 'video', 'audio', 'tv', 'metadata', 'server'].map(tab => (
                            <button
                              key={tab}
                              onClick={() => setActiveTab(tab)}
                              className={`px-3 py-1 text-xs font-medium capitalize transition-colors ${
                                activeTab === tab 
                                  ? 'text-jellyfin-purple border-b-2 border-jellyfin-purple' 
                                  : 'text-dark-text-muted hover:text-dark-text-primary'
                              }`}
                            >
                              {tab}
                            </button>
                          ))}
                        </div>
                        
                        {/* Tab Content */}
                        <div className="text-xs space-y-1 text-dark-text-secondary max-h-[300px] overflow-y-auto">
                          {activeTab === 'basic' && (
                            <>
                              <div><span className="text-blue-400">item.item_id</span> - Unique Jellyfin ID</div>
                              <div><span className="text-blue-400">item.name</span> - Media title</div>
                              <div><span className="text-blue-400">item.item_type</span> - Movie/Episode/Series/Audio</div>
                              <div><span className="text-blue-400">item.year</span> - Release year</div>
                              <div><span className="text-blue-400">item.overview</span> - Description/plot</div>
                              <div><span className="text-blue-400">item.tagline</span> - Marketing tagline</div>
                              <div><span className="text-blue-400">item.official_rating</span> - MPAA/TV rating</div>
                              <div><span className="text-blue-400">item.genres</span> - List of genres</div>
                              <div><span className="text-blue-400">item.studios</span> - Production studios</div>
                              <div><span className="text-blue-400">item.tags</span> - User tags</div>
                              <div><span className="text-blue-400">item.runtime_formatted</span> - Duration (e.g., "2h 15m")</div>
                              <div><span className="text-blue-400">item.premiere_date</span> - Original release date</div>
                            </>
                          )}
                          
                          {activeTab === 'video' && (
                            <>
                              <div><span className="text-blue-400">item.video_height</span> - Height in pixels (1080, 2160)</div>
                              <div><span className="text-blue-400">item.video_width</span> - Width in pixels (1920, 3840)</div>
                              <div><span className="text-blue-400">item.video_codec</span> - Codec (h264, hevc, av1)</div>
                              <div><span className="text-blue-400">item.video_profile</span> - Profile (High, Main10)</div>
                              <div><span className="text-blue-400">item.video_range</span> - SDR/HDR10/DolbyVision</div>
                              <div><span className="text-blue-400">item.video_framerate</span> - FPS (24, 60)</div>
                              <div><span className="text-blue-400">item.aspect_ratio</span> - Aspect ratio (16:9)</div>
                              <div><span className="text-blue-400">item.video_bitrate</span> - Bitrate in bps</div>
                              <div><span className="text-blue-400">item.video_bitdepth</span> - Bit depth (8, 10)</div>
                              <div><span className="text-blue-400">item.video_colorspace</span> - Color space</div>
                              <div><span className="text-blue-400">item.video_interlaced</span> - True if interlaced</div>
                              <div><span className="text-blue-400">item.video_language</span> - Language code</div>
                            </>
                          )}
                          
                          {activeTab === 'audio' && (
                            <>
                              <div><span className="text-blue-400">item.audio_codec</span> - Codec (aac, ac3, dts)</div>
                              <div><span className="text-blue-400">item.audio_channels</span> - Channels (2, 6, 8)</div>
                              <div><span className="text-blue-400">item.audio_language</span> - Language code</div>
                              <div><span className="text-blue-400">item.audio_bitrate</span> - Bitrate in bps</div>
                              <div><span className="text-blue-400">item.audio_samplerate</span> - Sample rate (48000)</div>
                              <div><span className="text-blue-400">item.audio_title</span> - Track title</div>
                              <div><span className="text-blue-400">item.audio_default</span> - Default track</div>
                              <div><span className="text-blue-400">item.subtitle_language</span> - Subtitle language</div>
                              <div><span className="text-blue-400">item.subtitle_codec</span> - Subtitle format</div>
                              <div><span className="text-blue-400">item.subtitle_forced</span> - Forced subtitle</div>
                            </>
                          )}
                          
                          {activeTab === 'tv' && (
                            <>
                              <div><span className="text-blue-400">item.series_name</span> - TV series name</div>
                              <div><span className="text-blue-400">item.series_id</span> - Series ID</div>
                              <div><span className="text-blue-400">item.season_number</span> - Season number</div>
                              <div><span className="text-blue-400">item.season_id</span> - Season ID</div>
                              <div><span className="text-blue-400">item.episode_number</span> - Episode number</div>
                              <div><span className="text-blue-400">item.season_number_padded</span> - Padded (01, 02)</div>
                              <div><span className="text-blue-400">item.episode_number_padded</span> - Padded (01, 02)</div>
                              <div><span className="text-blue-400">item.air_time</span> - Air time</div>
                              <div><span className="text-blue-400">item.series_premiere_date</span> - Series premiere</div>
                            </>
                          )}
                          
                          {activeTab === 'metadata' && (
                            <>
                              <div><span className="text-blue-400">item.imdb_id</span> - IMDb ID (tt1234567)</div>
                              <div><span className="text-blue-400">item.tmdb_id</span> - TMDB ID</div>
                              <div><span className="text-blue-400">item.tvdb_id</span> - TVDB ID</div>
                              <div><span className="text-blue-400">item.tvdb_slug</span> - TVDB URL slug</div>
                              <div><span className="text-blue-400">item.file_path</span> - File system path</div>
                              <div><span className="text-blue-400">item.file_size</span> - File size in bytes</div>
                              <div><span className="text-blue-400">item.library_name</span> - Jellyfin library</div>
                              <div><span className="text-blue-400">item.date_created</span> - Added to Jellyfin</div>
                              <div><span className="text-blue-400">item.date_modified</span> - Last modified</div>
                            </>
                          )}
                          
                          {activeTab === 'server' && (
                            <>
                              <div><span className="text-blue-400">item.server_id</span> - Server ID</div>
                              <div><span className="text-blue-400">item.server_name</span> - Server name</div>
                              <div><span className="text-blue-400">item.server_version</span> - Server version</div>
                              <div><span className="text-blue-400">item.server_url</span> - Server URL</div>
                              <div><span className="text-blue-400">item.notification_type</span> - Event type</div>
                              <div><span className="text-blue-400">item.timestamp</span> - Local timestamp</div>
                              <div><span className="text-blue-400">item.utc_timestamp</span> - UTC timestamp</div>
                            </>
                          )}
                        </div>
                      </div>
                      
                      {/* Best Practices */}
                      <div>
                        <h5 className="text-sm font-semibold text-jellyfin-purple mb-2">Best Practices</h5>
                        <ul className="text-xs space-y-1 text-dark-text-secondary">
                          <li>• Always use <code className="text-green-400">| tojson</code> for JSON values</li>
                          <li>• Test with special characters in titles</li>
                          <li>• Use <code className="text-green-400">default()</code> for optional fields</li>
                          <li>• Keep messages under Discord limits</li>
                          <li>• Use <code className="text-green-400">truncate()</code> for long text</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <IconDuotone icon="file-code" size="3x" className="text-dark-text-muted mx-auto mb-4" />
                <p className="text-dark-text-secondary">Select a template to edit</p>
              </div>
            </div>
          )}
        </div>
      </div>
      {/* Create Template Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-bold text-white mb-4">
              Create New Template
            </h2>
            
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Template Name
              </label>
              <input
                type="text"
                value={newTemplateName}
                onChange={(e) => setNewTemplateName(e.target.value)}
                placeholder="e.g., custom_notification.j2"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                autoFocus
              />
              <p className="mt-1 text-xs text-gray-400">
                Use .j2 extension for Jinja2 templates
              </p>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={() => {
                  if (newTemplateName.trim()) {
                    const templateName = newTemplateName.endsWith('.j2') 
                      ? newTemplateName 
                      : `${newTemplateName}.j2`;
                    
                    createMutation.mutate({
                      name: templateName,
                      content: `{# Custom template: ${templateName} #}\n{# Created: ${new Date().toISOString()} #}\n\n{{ item.name }}`
                    });
                  }
                }}
                disabled={!newTemplateName.trim() || createMutation.isPending}
                className="flex-1 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white font-medium py-2 px-4 rounded transition-colors"
              >
                {createMutation.isPending ? 'Creating...' : 'Create'}
              </button>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setNewTemplateName('');
                }}
                className="flex-1 bg-gray-700 hover:bg-gray-600 text-gray-300 font-medium py-2 px-4 rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Helper component for code examples
const CodeExample = ({ code, description }) => (
  <div className="bg-dark-elevated p-2 rounded">
    <pre className="text-xs font-mono text-green-400 mb-1 whitespace-pre-wrap">{code}</pre>
    <p className="text-xs text-dark-text-muted">{description}</p>
  </div>
)

export default Templates