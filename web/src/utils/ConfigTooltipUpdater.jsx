// This file contains the updates needed for all remaining config fields
// It's a reference for updating the Config.jsx file with tooltips

// Server Tab Updates:
/*
Replace:
  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
    Host
  </label>
With:
  <LabelWithTooltip 
    label="Host" 
    tooltip={configDescriptions.server.host}
    className="block"
  />

Replace:
  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
    Port
  </label>
With:
  <LabelWithTooltip 
    label="Port" 
    tooltip={configDescriptions.server.port}
    className="block"
  />

Replace:
  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
    Log Level
  </label>
With:
  <LabelWithTooltip 
    label="Log Level" 
    tooltip={configDescriptions.server.log_level}
    className="block"
  />

Replace:
  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
    Run Mode
  </label>
With:
  <LabelWithTooltip 
    label="Run Mode" 
    tooltip={configDescriptions.server.run_mode}
    className="block"
  />
*/

// Database Tab:
/*
Replace all database labels with:
  <LabelWithTooltip 
    label="Database Path" 
    tooltip={configDescriptions.database.path}
    className="block"
  />
  
  <LabelWithTooltip 
    label="Vacuum Interval (hours)" 
    tooltip={configDescriptions.database.vacuum_interval_hours}
    className="block"
  />
  
For checkboxes:
  <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
    WAL Mode
  </span>
  <Tooltip text={configDescriptions.database.wal_mode} />
*/

// Sync Tab:
/*
Replace all sync labels and add tooltips for:
- Enabled checkbox
- Interval Minutes
- Batch Size
- Max Retries
- Libraries
*/

// Metadata Services:
/*
For each service (OMDb, TMDb, TVDb):
- Add tooltip to enabled checkbox
- Add tooltip to API Key field
- Add tooltip to Base URL field
*/

// SSL/TLS Tab:
/*
- Add tooltips for enabled checkbox
- Certificate path
- Key path
- PFX path
- PFX password
- Port
*/

export default null; // This is just a reference file