"""Windows Task Scheduler script generator and inspection utilities for CareerOrbit AI."""
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from careerorbit.config.settings import SETTINGS
from careerorbit.scheduler.timezone_helper import (
    compute_local_trigger_time,
    get_machine_timezone_info,
    validate_timezone_compatibility,
)

CANONICAL_TASK_NAME = SETTINGS.WINDOWS_TASK_NAME


def generate_windows_task_script(output_path: Path) -> Path:
    """Generate robust, parameter-supported PowerShell registration script for Windows Task Scheduler."""
    python_exe = str(SETTINGS.BASE_DIR / ".venv" / "Scripts" / "python.exe")
    run_script = str(SETTINGS.BASE_DIR / "run.py")
    project_root = str(SETTINGS.BASE_DIR)

    ps1_content = f"""<#
.SYNOPSIS
    CareerOrbit AI — Windows Scheduled Task Installer & Manager
.DESCRIPTION
    Registers, verifies, or unregisters the canonical daily job discovery task
    scheduled to execute at 08:00 AM Asia/Kolkata (India Standard Time).
.PARAMETER DryRun
    Simulate the registration without making changes.
.PARAMETER Force
    Overwrite an existing scheduled task if present.
.PARAMETER Uninstall
    Remove the scheduled task and any legacy task names.
.PARAMETER EnforceIST
    Require the host operating system to be in India Standard Time.
.PARAMETER TaskName
    Override the canonical task name (defaults to '{CANONICAL_TASK_NAME}').
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force,
    [switch]$Uninstall,
    [switch]$EnforceIST,
    [string]$TaskName = '{CANONICAL_TASK_NAME}',
    [string]$PythonExe = '{python_exe}',
    [string]$RunScript = '{run_script}',
    [string]$ProjectRoot = '{project_root}'
)

$ErrorActionPreference = 'Stop'

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "CAREERORBIT AI — WINDOWS TASK SCHEDULER MANAGEMENT" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# 1. Environment & Path Verification
if (-not $IsWindows -and ($env:OS -notlike "*Windows*")) {{
    Write-Error "Windows Task Scheduler registration requires a Windows host operating system."
    exit 1
}}

if (-not (Test-Path -LiteralPath $PythonExe)) {{
    Write-Error "Python virtual environment not found at: $PythonExe"
    exit 1
}}

if (-not (Test-Path -LiteralPath $RunScript)) {{
    Write-Error "CareerOrbit launcher entry point not found at: $RunScript"
    exit 1
}}

if (-not (Test-Path -LiteralPath $ProjectRoot)) {{
    Write-Error "Project root directory not found at: $ProjectRoot"
    exit 1
}}

# Ensure logs directory exists
$LogsDir = Join-Path $ProjectRoot "data\\logs"
if (-not (Test-Path -LiteralPath $LogsDir)) {{
    New-Item -Path $LogsDir -ItemType Directory -Force | Out-Null
}}

# 2. Timezone Diagnostics & Trigger Calculation
$tz = Get-TimeZone
$isIst = ($tz.Id -eq 'India Standard Time' -or $tz.BaseUtcOffset.TotalMinutes -eq 330)
$targetUtc = [DateTime]::UtcNow.Date.AddHours(2).AddMinutes(30)
$localTarget = [TimeZoneInfo]::ConvertTimeFromUtc($targetUtc, $tz)
$TriggerTime = $localTarget.ToString("hh:mm tt")

Write-Host "Timezone Diagnostics:" -ForegroundColor Yellow
Write-Host "  -> Machine Timezone:  $($tz.DisplayName) (Id: $($tz.Id), UTC $($tz.BaseUtcOffset))"
Write-Host "  -> Intended Schedule: 08:00 AM Asia/Kolkata (IST)"
Write-Host "  -> Local Trigger:     $TriggerTime"

if (-not $isIst) {{
    if ($EnforceIST) {{
        Write-Error "Strict IST enforcement active (-EnforceIST): Machine timezone $($tz.Id) is not India Standard Time."
        exit 1
    }}
    Write-Warning "Machine timezone differs from Asia/Kolkata. Local trigger $TriggerTime is configured to match 08:00 AM IST."
}} else {{
    Write-Host "  -> Machine is in native India Standard Time. Direct schedule alignment confirmed." -ForegroundColor Green
}}

# 3. Handle Uninstall Mode
if ($Uninstall) {{
    Write-Host "`nUninstalling CareerOrbit scheduled tasks..." -ForegroundColor Yellow
    $targets = @($TaskName, "CareerOrbitJobDiscovery", "CareerOrbit_Daily_Study_Plan")
    foreach ($t in $targets) {{
        $existing = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
        if ($existing) {{
            Unregister-ScheduledTask -TaskName $t -Confirm:$false
            Write-Host "  -> Unregistered: $t" -ForegroundColor Green
        }} else {{
            Write-Host "  -> Not registered: $t" -ForegroundColor Gray
        }}
    }}
    Write-Host "Uninstall completed successfully." -ForegroundColor Green
    exit 0
}}

# 4. Handle Existing Task
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {{
    Write-Host "`nExisting task '$TaskName' detected." -ForegroundColor Yellow
    if (-not $Force -and -not $DryRun) {{
        Write-Host "Task is already registered. Use -Force to update configuration, or query with Get-ScheduledTask." -ForegroundColor Yellow
        $info = $existingTask | Get-ScheduledTaskInfo
        [PSCustomObject]@{{
            TaskName       = $existingTask.TaskName
            State          = $existingTask.State
            LastRunTime    = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
            NextRunTime    = $info.NextRunTime
        }} | Format-List
        exit 0
    }}
}}

# 5. Define Task Components
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument ('"{{0}}" --job-discovery' -f $RunScript) -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15)

if ($DryRun) {{
    Write-Host "`n[DRY RUN] Planned Scheduled Task Definition:" -ForegroundColor Cyan
    Write-Host "  Task Name:         $TaskName"
    Write-Host "  Action Executable: $PythonExe"
    Write-Host "  Action Arguments:  `"$RunScript`" --job-discovery"
    Write-Host "  Working Directory: $ProjectRoot"
    Write-Host "  Trigger Time:      $TriggerTime Daily"
    Write-Host "  Principal:         $env:USERDOMAIN\\$env:USERNAME (Interactive, Limited)"
    Write-Host "  Settings:          AllowStartIfOnBatteries, StartWhenAvailable, MultipleInstances=IgnoreNew"
    Write-Host "  Validation:        All prerequisites passed. Ready for registration." -ForegroundColor Green
    exit 0
}}

# 6. Unregister Legacy/Conflicting Tasks
$legacyStudy = Get-ScheduledTask -TaskName "CareerOrbit_Daily_Study_Plan" -ErrorAction SilentlyContinue
if ($legacyStudy) {{
    Unregister-ScheduledTask -TaskName "CareerOrbit_Daily_Study_Plan" -Confirm:$false
    Write-Host "  -> Removed legacy background study plan task (decoupled to on-demand)." -ForegroundColor Yellow
}}

$legacyDiscovery = Get-ScheduledTask -TaskName "CareerOrbitJobDiscovery" -ErrorAction SilentlyContinue
if ($legacyDiscovery -and ($TaskName -ne "CareerOrbitJobDiscovery")) {{
    Unregister-ScheduledTask -TaskName "CareerOrbitJobDiscovery" -Confirm:$false
    Write-Host "  -> Removed legacy task name 'CareerOrbitJobDiscovery' in favor of canonical '$TaskName'." -ForegroundColor Yellow
}}

# 7. Register Task
Write-Host "`nRegistering task '$TaskName' in Windows Task Scheduler..." -ForegroundColor Cyan
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "CareerOrbit AI daily automated job discovery at 08:00 AM Asia/Kolkata" `
    -Force | Out-Null

# 8. Post-Registration Verification
$registeredTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $registeredTask) {{
    Write-Error "Failed to verify registered task '$TaskName'. Task was not found after registration."
    exit 1
}}

$taskInfo = $registeredTask | Get-ScheduledTaskInfo
Write-Host "`n[SUCCESS] Windows Scheduled Task Registered & Verified:" -ForegroundColor Green
Write-Host "  Task Name:      $($registeredTask.TaskName)"
Write-Host "  State:          $($registeredTask.State)"
Write-Host "  Next Run Time:  $($taskInfo.NextRunTime)"
Write-Host "  Last Run Time:  $($taskInfo.LastRunTime)"
Write-Host "  Last Result:    $($taskInfo.LastTaskResult)"

Write-Host "`nExecution logs will be recorded in $LogsDir\\scheduler.log and workflow_runs.jsonl." -ForegroundColor Gray
exit 0
"""
    output_path.write_text(ps1_content, encoding="utf-8")
    return output_path


def inspect_windows_task(task_name: str = CANONICAL_TASK_NAME) -> Dict[str, Any]:
    """Inspect the real Windows Task Scheduler state using schtasks."""
    if os.name != "nt":
        return {"installed": False, "mode": "NON_WINDOWS_OS", "task_name": task_name}

    try:
        res = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/fo", "LIST", "/v"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            info = {}
            for line in res.stdout.splitlines():
                if ":" in line:
                    parts = line.split(":", 1)
                    info[parts[0].strip()] = parts[1].strip()
            return {
                "installed": True,
                "task_name": task_name,
                "state": info.get("Status", "Unknown"),
                "next_run_time": info.get("Next Run Time", "N/A"),
                "last_run_time": info.get("Last Run Time", "N/A"),
                "last_result": info.get("Last Result", "N/A"),
                "author": info.get("Author", "N/A"),
                "raw": res.stdout[:500],
            }
    except Exception as e:
        return {"installed": False, "error": str(e), "task_name": task_name}

    return {"installed": False, "task_name": task_name}
