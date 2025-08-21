#!/usr/bin/env node

/**
 * Update Claude statusline with token usage information
 * Uses ccusage to fetch current token counts and costs
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

// ANSI color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  dim: '\x1b[2m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  red: '\x1b[31m'
};

/**
 * Parse the ccusage output to extract token counts
 */
function parseCcusageOutput(output) {
  const lines = output.split('\n');
  const data = {
    today: {
      input: 0,
      output: 0,
      cacheCreate: 0,
      cacheRead: 0,
      total: 0,
      cost: 0
    },
    total: {
      input: 0,
      output: 0,
      cacheCreate: 0,
      cacheRead: 0,
      total: 0,
      cost: 0
    }
  };

  // Get today's date in YYYY-MM-DD format
  const today = new Date().toISOString().split('T')[0].replace(/-/g, ' ');
  
  let foundToday = false;
  let foundTotal = false;

  for (const line of lines) {
    // Skip separator lines and headers
    if (line.includes('─') || line.includes('Input') || line.includes('Output')) continue;
    
    // Clean up the line - remove ANSI codes and extra spaces
    const cleanLine = line.replace(/\x1b\[[0-9;]*m/g, '').trim();
    if (!cleanLine) continue;

    // Split by │ and clean up each cell
    const cells = cleanLine.split('│').map(cell => cell.trim());
    
    // Check for today's data
    if (cells[0] && cells[0].includes(today.substring(0, 7))) {
      foundToday = true;
      // Parse the numbers from the cells
      if (cells.length >= 8) {
        data.today.input = parseNumber(cells[2]);
        data.today.output = parseNumber(cells[3]);
        data.today.cacheCreate = parseNumber(cells[4]);
        data.today.cacheRead = parseNumber(cells[5]);
        data.today.total = parseNumber(cells[6]);
        data.today.cost = parseFloat(cells[7].replace('$', '').replace(',', '')) || 0;
      }
    }
    
    // Check for total line
    if (cells[0] && cells[0].toLowerCase() === 'total') {
      foundTotal = true;
      if (cells.length >= 8) {
        data.total.input = parseNumber(cells[2]);
        data.total.output = parseNumber(cells[3]);
        data.total.cacheCreate = parseNumber(cells[4]);
        data.total.cacheRead = parseNumber(cells[5]);
        data.total.total = parseNumber(cells[6]);
        data.total.cost = parseFloat(cells[7].replace('$', '').replace(',', '')) || 0;
      }
    }
  }

  return data;
}

/**
 * Parse numbers from string, handling abbreviations like "56,001,3…"
 */
function parseNumber(str) {
  if (!str) return 0;
  
  // Remove commas and spaces
  let cleaned = str.replace(/,/g, '').replace(/\s/g, '');
  
  // Handle truncated numbers (ending with …)
  if (cleaned.includes('…')) {
    // Just use the visible part * 1000 as an estimate
    cleaned = cleaned.replace('…', '000');
  }
  
  const num = parseInt(cleaned, 10);
  return isNaN(num) ? 0 : num;
}

/**
 * Format number for display with K/M suffixes
 */
function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

/**
 * Update Claude's statusline configuration
 */
async function updateStatusline(data) {
  // Path to Claude's settings file (adjust based on your system)
  const settingsPath = path.join(os.homedir(), '.claude', 'settings.json');
  
  try {
    // Read existing settings
    let settings = {};
    try {
      const content = await fs.readFile(settingsPath, 'utf8');
      settings = JSON.parse(content);
    } catch (err) {
      // Settings file doesn't exist yet, create new one
      console.log(`${colors.yellow}Settings file not found, creating new one...${colors.reset}`);
    }

    // Create the statusline text
    const statuslineText = [
      `📊 Tokens Today: ${formatNumber(data.today.total)}`,
      `💰 $${data.today.cost.toFixed(2)}`,
      `| Total: ${formatNumber(data.total.total)}`,
      `($${data.total.cost.toFixed(2)})`
    ].join(' ');

    // Update the settings
    settings.statusline = {
      enabled: true,
      text: statuslineText,
      position: 'bottom',
      style: {
        backgroundColor: '#1e293b',
        color: '#94a3b8',
        fontSize: '12px',
        padding: '4px 8px'
      }
    };

    // Ensure the .claude directory exists
    const claudeDir = path.dirname(settingsPath);
    await fs.mkdir(claudeDir, { recursive: true });

    // Write the updated settings
    await fs.writeFile(settingsPath, JSON.stringify(settings, null, 2));
    
    console.log(`${colors.green}✓${colors.reset} Statusline updated successfully!`);
    console.log(`${colors.cyan}${statuslineText}${colors.reset}`);
    
    return true;
  } catch (err) {
    console.error(`${colors.red}Error updating statusline:${colors.reset}`, err.message);
    return false;
  }
}

/**
 * Alternative: Output a format that can be used with Claude's CLI
 */
function outputForClaudeCLI(data) {
  // Format for potential use with claude-cli statusline command
  const format = {
    tokens_today: data.today.total,
    cost_today: data.today.cost,
    tokens_total: data.total.total,
    cost_total: data.total.cost,
    formatted: `📊 ${formatNumber(data.today.total)} ($${data.today.cost.toFixed(2)}) | Total: ${formatNumber(data.total.total)} ($${data.total.cost.toFixed(2)})`
  };
  
  console.log('\n' + colors.bright + 'Formatted for statusline:' + colors.reset);
  console.log(colors.cyan + format.formatted + colors.reset);
  
  console.log('\n' + colors.bright + 'JSON output:' + colors.reset);
  console.log(JSON.stringify(format, null, 2));
  
  return format;
}

/**
 * Main function
 */
async function main() {
  try {
    console.log(`${colors.bright}Fetching Claude usage data...${colors.reset}`);
    
    // Run ccusage command
    const { stdout, stderr } = await execAsync('npx ccusage@latest');
    
    if (stderr && !stderr.includes('ExperimentalWarning')) {
      console.error(`${colors.yellow}Warning:${colors.reset}`, stderr);
    }
    
    // Parse the output
    const data = parseCcusageOutput(stdout);
    
    console.log(`\n${colors.bright}Parsed Data:${colors.reset}`);
    console.log(`${colors.blue}Today:${colors.reset}`);
    console.log(`  Input: ${formatNumber(data.today.input)}`);
    console.log(`  Output: ${formatNumber(data.today.output)}`);
    console.log(`  Cache: ${formatNumber(data.today.cacheCreate + data.today.cacheRead)}`);
    console.log(`  Total: ${formatNumber(data.today.total)}`);
    console.log(`  Cost: $${data.today.cost.toFixed(2)}`);
    
    console.log(`\n${colors.blue}All Time:${colors.reset}`);
    console.log(`  Total Tokens: ${formatNumber(data.total.total)}`);
    console.log(`  Total Cost: $${data.total.cost.toFixed(2)}`);
    
    // Output formatted versions
    const formatted = outputForClaudeCLI(data);
    
    // Try to update the statusline (if settings file is accessible)
    await updateStatusline(data);
    
    // Also write to a file that can be sourced by other scripts
    const outputPath = path.join(process.cwd(), '.claude-usage.json');
    await fs.writeFile(outputPath, JSON.stringify(formatted, null, 2));
    console.log(`\n${colors.green}✓${colors.reset} Usage data saved to ${outputPath}`);
    
  } catch (err) {
    console.error(`${colors.red}Error:${colors.reset}`, err.message);
    if (err.message.includes('command not found')) {
      console.log(`\n${colors.yellow}Make sure ccusage is installed:${colors.reset}`);
      console.log('  npm install -g ccusage');
      console.log('  or use: npx ccusage@latest');
    }
    process.exit(1);
  }
}

// Run the script
main().catch(console.error);