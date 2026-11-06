<#
.SYNOPSIS
    CareerOrbit AI — Autonomous Local Application Launcher for Windows PowerShell
.DESCRIPTION
    Autonomously verifies environment, virtualenv, dependencies, database, and configuration,
    safely checks for already-running instances to prevent collisions, starts the FastAPI/Uvicorn
    application, waits for health confirmation, and opens the dashboard in the default browser.
.PARAMETER Port
    Port to bind dashboard server (default: 8000 or CAREERORBIT_PORT from .env).
.PARAMETER HostAddress
    Host interface to bind (default: 127.0.0.1).
.PARAMETER NoBrowser
    Do not launch the default web browser upon successful startup.
.PARAMETER Status
    Check status of CareerOrbit AI backend and exit.
.PARAMETER Stop
    Stop any existing CareerOrbit AI backend process running on the configured port.
#>

[CmdletBinding()]
param (
    [Parameter(Mandatory = $false)]
    [int]$Port = 0,

    [Parameter(Mandatory = $false)]
    [string]$HostAddress = "",

    [Parameter(Mandatory = $false)]
    [switch]$NoBrowser,

    [Parameter(Mandatory = $false)]
    [switch]$Background,

    [Parameter(Mandatory = $false)]
    [switch]$Status,

    [Parameter(Mandatory = $false)]
    [switch]$Stop
)

# 1. Establish project root
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "   CareerOrbit AI -- Autonomous Local Launcher (Windows)" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"

# 2. Parse .env for default host/port if not supplied
$EnvFile = Join-Path $ProjectRoot ".env"
$DefaultHost = "127.0.0.1"
$DefaultPort = 8000

if (Test-Path -LiteralPath $EnvFile) {
    Get-Content -LiteralPath $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            if ($line -match '^CAREERORBIT_PORT\s*=\s*(\d+)') {
                $DefaultPort = [int]$matches[1]
            }
            if ($line -match '^CAREERORBIT_HOST\s*=\s*(.+)$') {
                $DefaultHost = $matches[1].Trim()
            }
        }
    }
} else {
    Write-Warning "Local .env file not found. Defaulting to Host=$DefaultHost, Port=$DefaultPort."
}

if ($Port -le 0) { $Port = $DefaultPort }
if ([string]::IsNullOrWhiteSpace($HostAddress)) { $HostAddress = $DefaultHost }

$BaseUrl = "http://" + $HostAddress + ":" + $Port

# Helper: Find process listening on specified port
function Get-CareerOrbitProcessOnPort {
    param([int]$TargetPort)
    $conn = Get-NetTCPConnection -LocalPort $TargetPort -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
    if ($conn) {
        $procId = $conn[0].OwningProcess
        return Get-Process -Id $procId -ErrorAction SilentlyContinue
    }
    return $null
}

# 3. Handle -Stop switch
if ($Stop) {
    Write-Host "[*] Checking for running instances on port $Port..." -ForegroundColor Yellow
    $existingProc = Get-CareerOrbitProcessOnPort -TargetPort $Port
    if ($existingProc) {
        Write-Host "[*] Terminating process $($existingProc.Id) ($($existingProc.ProcessName)) on port $Port..." -ForegroundColor Yellow
        Stop-Process -Id $existingProc.Id -Force
        Start-Sleep -Seconds 1
        Write-Host "[+] Successfully stopped CareerOrbit instance." -ForegroundColor Green
    } else {
        Write-Host "[INFO] No process listening on port $Port." -ForegroundColor Gray
    }
    exit 0
}

# 4. Handle -Status switch
if ($Status) {
    Write-Host "[*] Checking CareerOrbit AI liveness at $BaseUrl/api/health/liveness..." -ForegroundColor Yellow
    try {
        $resp = Invoke-RestMethod -Uri "$BaseUrl/api/health/liveness" -Method Get -TimeoutSec 3 -ErrorAction Stop
        Write-Host "[PASS] CareerOrbit AI is ALIVE." -ForegroundColor Green
        Write-Host "       App Version: $($resp.version)"
        Write-Host "       Dashboard:   $BaseUrl"
    } catch {
        Write-Host "[INFO] CareerOrbit AI is not currently responding at $BaseUrl." -ForegroundColor Yellow
    }
    exit 0
}

# 5. Verify Python Virtual Environment
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Error "Virtual environment Python executable not found at '$VenvPython'. Please run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# 6. Verify Database exists
$DbPath = Join-Path $ProjectRoot "data\careerorbit.db"
if (-not (Test-Path -LiteralPath $DbPath)) {
    Write-Host "[*] Database not detected at $DbPath; will be automatically initialized by launcher." -ForegroundColor Yellow
}

# 7. Check if application is ALREADY running and healthy
try {
    $healthCheck = Invoke-RestMethod -Uri "$BaseUrl/api/health/liveness" -Method Get -TimeoutSec 2 -ErrorAction Stop
    if ($healthCheck.status -eq "alive") {
        Write-Host "[PASS] CareerOrbit AI is ALREADY RUNNING and verified healthy at $BaseUrl." -ForegroundColor Green
        Write-Host "[+] Dashboard: $BaseUrl" -ForegroundColor Cyan
        Write-Host "[+] API Docs:  $BaseUrl/docs" -ForegroundColor Cyan
        if (-not $NoBrowser) {
            Write-Host "[*] Opening browser to $BaseUrl..." -ForegroundColor Cyan
            Start-Process $BaseUrl
        }
        exit 0
    }
} catch {
    # Not responding on this port; safe to proceed with startup
}

# 8. Start Backend in Background
Write-Host "[*] Starting CareerOrbit AI on $BaseUrl..." -ForegroundColor Cyan

$LogDir = Join-Path $ProjectRoot "data\logs"
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$StdOutLog = Join-Path $LogDir "careerorbit_stdout.log"
$StdErrLog = Join-Path $LogDir "careerorbit_stderr.log"

$StartArgs = @("run.py", "--host", $HostAddress, "--port", $Port)

$StartProc = Start-Process -FilePath $VenvPython -ArgumentList $StartArgs -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $StdOutLog -RedirectStandardError $StdErrLog

Write-Host "[*] Process launched (PID: $($StartProc.Id)). Waiting for health check..." -ForegroundColor Yellow

# 9. Wait for health check confirmation (polling up to 15 seconds)
$MaxRetries = 15
$IsHealthy = $false

for ($i = 1; $i -le $MaxRetries; $i++) {
    Start-Sleep -Seconds 1
    if ($StartProc.HasExited) {
        Write-Error "CareerOrbit process exited unexpectedly with code $($StartProc.ExitCode). Check stderr at: $StdErrLog"
        if (Test-Path -LiteralPath $StdErrLog) {
            Get-Content -LiteralPath $StdErrLog -Tail 20 | Write-Host -ForegroundColor Red
        }
        exit 1
    }

    try {
        $health = Invoke-RestMethod -Uri "$BaseUrl/api/health/liveness" -Method Get -TimeoutSec 1 -ErrorAction Stop
        if ($health.status -eq "alive") {
            $IsHealthy = $true
            break
        }
    } catch {
        # Waiting for server to bind
    }
}

if ($IsHealthy) {
    Write-Host "========================================================================" -ForegroundColor Green
    Write-Host "[SUCCESS] CareerOrbit AI is RUNNING and verified healthy!" -ForegroundColor Green
    Write-Host "          PID:       $($StartProc.Id)" -ForegroundColor Green
    Write-Host "          Dashboard: $BaseUrl" -ForegroundColor Cyan
    Write-Host "          API Docs:  $BaseUrl/docs" -ForegroundColor Cyan
    Write-Host "          Stdout:    $StdOutLog" -ForegroundColor Gray
    Write-Host "          Stderr:    $StdErrLog" -ForegroundColor Gray
    Write-Host "========================================================================" -ForegroundColor Green

    if (-not $NoBrowser) {
        Write-Host "[*] Opening browser..." -ForegroundColor Cyan
        Start-Process $BaseUrl
    }

    if (-not $Background) {
        Write-Host "[*] CareerOrbit server is active (PID: $($StartProc.Id)). Press CTRL+C to stop." -ForegroundColor Yellow
        try {
            Wait-Process -Id $StartProc.Id
        } finally {
            if (-not $StartProc.HasExited) {
                Write-Host "`n[*] Stopping CareerOrbit server..." -ForegroundColor Yellow
                Stop-Process -Id $StartProc.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
} else {
    Write-Error "Application failed to become healthy within $MaxRetries seconds. Check stderr at: $StdErrLog"
    exit 1
}
