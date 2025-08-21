#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Check Claude API token usage and display formatted output
.DESCRIPTION
    Fetches token usage from ccusage and displays it in a formatted way
    Can also update the Claude statusline configuration
.EXAMPLE
    .\check_claude_usage.ps1
    .\check_claude_usage.ps1 -UpdateStatusline
#>

param(
    [switch]$UpdateStatusline,
    [switch]$JsonOutput,
    [switch]$Verbose
)

# Colors for terminal output
$colors = @{
    Reset = "`e[0m"
    Bright = "`e[1m"
    Green = "`e[32m"
    Yellow = "`e[33m"
    Blue = "`e[34m"
    Cyan = "`e[36m"
    Magenta = "`e[35m"
    Red = "`e[31m"
}

function Format-TokenCount {
    param([int64]$count)
    
    if ($count -ge 1000000000) {
        return "{0:F1}B" -f ($count / 1000000000)
    }
    elseif ($count -ge 1000000) {
        return "{0:F1}M" -f ($count / 1000000)
    }
    elseif ($count -ge 1000) {
        return "{0:F1}K" -f ($count / 1000)
    }
    else {
        return $count.ToString()
    }
}

function Get-ClaudeUsage {
    try {
        # Run ccusage command
        $output = & npx ccusage@latest 2>$null | Out-String
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to run ccusage"
        }
        
        # Parse the output
        $lines = $output -split "`n"
        $todayData = @{}
        $totalData = @{}
        
        # Get today's date
        $today = Get-Date -Format "yyyy MM-dd"
        $todayPattern = ($today -split " ")[0..1] -join "\s+"
        
        foreach ($line in $lines) {
            # Clean ANSI codes
            $cleanLine = $line -replace '\x1b\[[0-9;]*m', ''
            
            # Look for today's data
            if ($cleanLine -match $todayPattern) {
                $parts = $cleanLine -split '\|' | ForEach-Object { $_.Trim() }
                if ($parts.Count -ge 8) {
                    $todayData = @{
                        Input = [int]($parts[2] -replace '[^\d]', '')
                        Output = [int]($parts[3] -replace '[^\d]', '')
                        CacheCreate = [int]($parts[4] -replace '[^\d]', '')
                        CacheRead = [int]($parts[5] -replace '[^\d]', '')
                        Total = [int]($parts[6] -replace '[^\d]', '')
                        Cost = [decimal]($parts[7] -replace '[^\$,]', '')
                    }
                }
            }
            
            # Look for total line
            if ($cleanLine -match '^\s*Total\s*\|') {
                $parts = $cleanLine -split '\|' | ForEach-Object { $_.Trim() }
                if ($parts.Count -ge 8) {
                    # Handle truncated numbers
                    $totalTokens = $parts[6] -replace '[^\d]', ''
                    if ($parts[6] -match '…') {
                        $totalTokens += "000"  # Estimate for truncated
                    }
                    
                    $totalData = @{
                        Input = [int64]($parts[2] -replace '[^\d]', '')
                        Output = [int64]($parts[3] -replace '[^\d]', '')
                        Total = [int64]$totalTokens
                        Cost = [decimal]($parts[7] -replace '[^\$,]', '')
                    }
                }
            }
        }
        
        return @{
            Today = $todayData
            Total = $totalData
        }
    }
    catch {
        Write-Error "Failed to get Claude usage: $_"
        return $null
    }
}

function Show-UsageReport {
    param($usage)
    
    if (-not $usage) {
        Write-Host "No usage data available" -ForegroundColor Red
        return
    }
    
    Write-Host "`n$($colors.Bright)═══ Claude Token Usage Report ═══$($colors.Reset)" -ForegroundColor Cyan
    
    # Today's usage
    Write-Host "`n$($colors.Blue)📅 Today's Usage ($(Get-Date -Format 'yyyy-MM-dd')):$($colors.Reset)"
    Write-Host "  ↑ Input:  $(Format-TokenCount $usage.Today.Input)" -ForegroundColor Green
    Write-Host "  ↓ Output: $(Format-TokenCount $usage.Today.Output)" -ForegroundColor Yellow
    Write-Host "  ⧗ Total:  $(Format-TokenCount $usage.Today.Total)" -ForegroundColor Magenta
    Write-Host "  💰 Cost:   `$$($usage.Today.Cost)" -ForegroundColor Cyan
    
    # Total usage
    Write-Host "`n$($colors.Blue)📊 All-Time Usage:$($colors.Reset)"
    Write-Host "  ↑ Input:  $(Format-TokenCount $usage.Total.Input)" -ForegroundColor Green
    Write-Host "  ↓ Output: $(Format-TokenCount $usage.Total.Output)" -ForegroundColor Yellow
    Write-Host "  ∑ Total:  $(Format-TokenCount $usage.Total.Total)" -ForegroundColor Magenta
    Write-Host "  💰 Cost:   `$$($usage.Total.Cost)" -ForegroundColor Cyan
    
    # Statusline preview
    $branch = git branch --show-current 2>$null
    if (-not $branch) { $branch = "main" }
    $statusline = "Jellynouncer | Branch: $branch | Claude | In:$(Format-TokenCount $usage.Today.Input) Out:$(Format-TokenCount $usage.Today.Output) Total:$(Format-TokenCount $usage.Total.Total) | $(Get-Date -Format 'HH:mm:ss')"
    
    Write-Host "`n$($colors.Bright)Statusline Preview:$($colors.Reset)"
    Write-Host $statusline -ForegroundColor DarkGray
}

function Update-ClaudeStatusline {
    param($usage)
    
    $settingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"
    
    try {
        # Create statusline text
        $branch = git branch --show-current 2>$null
        if (-not $branch) { $branch = "main" }
        
        $statusText = "Jellynouncer | Branch: $branch | Claude | In:$(Format-TokenCount $usage.Today.Input) Out:$(Format-TokenCount $usage.Today.Output) Total:$(Format-TokenCount $usage.Total.Total) | {time}"
        
        # Read existing settings
        if (Test-Path $settingsPath) {
            $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
        }
        else {
            $settings = @{}
        }
        
        # Update statusline
        $settings.statusline = @{
            enabled = $true
            text = $statusText
            position = "bottom"
            style = @{
                backgroundColor = "#1e293b"
                color = "#94a3b8"
                fontSize = "12px"
                padding = "4px 8px"
            }
        }
        
        # Ensure directory exists
        $dir = Split-Path $settingsPath -Parent
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        
        # Save settings
        $settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath
        
        Write-Host "`n✅ Statusline updated successfully!" -ForegroundColor Green
        Write-Host "Location: $settingsPath" -ForegroundColor DarkGray
        
        return $true
    }
    catch {
        Write-Error "Failed to update statusline: $_"
        return $false
    }
}

# Main execution
$usage = Get-ClaudeUsage

if ($usage) {
    if ($JsonOutput) {
        # Output as JSON
        $output = @{
            timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            today = $usage.Today
            total = $usage.Total
            formatted = @{
                today_input = Format-TokenCount $usage.Today.Input
                today_output = Format-TokenCount $usage.Today.Output
                today_total = Format-TokenCount $usage.Today.Total
                total_all = Format-TokenCount $usage.Total.Total
            }
        }
        $output | ConvertTo-Json -Depth 10
    }
    else {
        # Show formatted report
        Show-UsageReport -usage $usage
        
        if ($UpdateStatusline) {
            Update-ClaudeStatusline -usage $usage
        }
    }
    
    # Save to file for other scripts
    $outputFile = Join-Path $PSScriptRoot "..\data\claude-usage.json"
    $usage | ConvertTo-Json -Depth 10 | Set-Content $outputFile
    
    if ($Verbose) {
        Write-Host "`nUsage data saved to: $outputFile" -ForegroundColor DarkGray
    }
}
else {
    Write-Host "Failed to retrieve usage data" -ForegroundColor Red
    exit 1
}