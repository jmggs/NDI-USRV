# NDI Signal Generator — Windows Installer (PowerShell)
# Run as Administrator: powershell -ExecutionPolicy Bypass -File install.ps1

param(
    [string]$InstallDir = "C:\ndi-generator",
    [int]$Port = 8080,
    [string]$ServiceName = "NDIGenerator"
)

$ErrorActionPreference = "Stop"

function Write-Ok   { Write-Host "✔ $args" -ForegroundColor Green }
function Write-Warn { Write-Host "⚠ $args" -ForegroundColor Yellow }
function Write-Die  { Write-Host "✘ $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗"
Write-Host "║        NDI Signal Generator  —  Windows Installer    ║"
Write-Host "╚══════════════════════════════════════════════════════╝"
Write-Host ""

# ── Check Python ─────────────────────────────────────────────────────────────
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Die "Python 3.10+ required. Install from python.org" }
$pyVer = & python -c "import sys; print(sys.version)"
Write-Ok "Python: $pyVer"

# ── NDI SDK check ─────────────────────────────────────────────────────────────
$ndiPath = "C:\Program Files\NDI\NDI 6 SDK\Bin\x64"
$ndiFound = Test-Path "$ndiPath\Processing.NDI.Lib.x64.dll"
if ($ndiFound) {
    Write-Ok "NDI SDK found at $ndiPath"
} else {
    Write-Warn "NDI SDK not found. Download from: https://ndi.video/for-developers/ndi-sdk/download/"
    Write-Warn "Running in MOCK mode until SDK is installed."
}

# ── Copy files ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installing to: $InstallDir"
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir | Out-Null }
Copy-Item -Path ".\*" -Destination $InstallDir -Recurse -Force
Write-Ok "Files copied"

# ── Virtual environment ───────────────────────────────────────────────────────
$venv = "$InstallDir\venv"
python -m venv $venv
& "$venv\Scripts\pip" install --upgrade pip -q
& "$venv\Scripts\pip" install -r "$InstallDir\requirements.txt" -q
Write-Ok "Python venv created"

if ($ndiFound) {
    & "$venv\Scripts\pip" install ndi-python -q
    Write-Ok "ndi-python installed"
} else {
    Write-Warn "Skipping ndi-python (NDI SDK not found)"
}

New-Item -ItemType Directory -Force "$InstallDir\uploads" | Out-Null

# ── Windows Service via NSSM ──────────────────────────────────────────────────
$nssm = Get-Command nssm -ErrorAction SilentlyContinue

if ($nssm) {
    Write-Host "Installing Windows service via NSSM…"
    $pyExe = "$venv\Scripts\python.exe"

    & nssm install $ServiceName $pyExe "main.py --host 0.0.0.0 --port $Port"
    & nssm set $ServiceName AppDirectory $InstallDir
    & nssm set $ServiceName DisplayName "NDI Signal Generator"
    & nssm set $ServiceName Description "Professional NDI test signal generator with web management"
    & nssm set $ServiceName Start SERVICE_AUTO_START
    & nssm set $ServiceName AppStdout "$InstallDir\ndi-generator.log"
    & nssm set $ServiceName AppStderr "$InstallDir\ndi-generator.log"
    & nssm start $ServiceName

    Write-Ok "Windows service '$ServiceName' installed and started"
    Write-Host "  Manage: services.msc or nssm {start|stop|restart} $ServiceName"
} else {
    Write-Warn "NSSM not found — install from nssm.cc for service support"
    Write-Host ""
    Write-Host "  To run manually:"
    Write-Host "  cd $InstallDir"
    Write-Host "  .\venv\Scripts\python main.py --port $Port"
    Write-Host ""
    Write-Host "  Or create a scheduled task to run on startup."
    Write-Host ""

    # Create a simple .bat launcher
    @"
@echo off
cd /d $InstallDir
.\venv\Scripts\python main.py --host 0.0.0.0 --port $Port
pause
"@ | Out-File -FilePath "$InstallDir\start.bat" -Encoding ASCII
    Write-Ok "Created $InstallDir\start.bat"
}

# ── Firewall rule ─────────────────────────────────────────────────────────────
try {
    New-NetFirewallRule -DisplayName "NDI Generator Web ($Port)" `
        -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port `
        -ErrorAction SilentlyContinue | Out-Null
    Write-Ok "Firewall rule added for port $Port"
} catch {
    Write-Warn "Could not add firewall rule — open port $Port manually"
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗"
Write-Host "║  Installation complete!                              ║"
Write-Host "║                                                      ║"
Write-Host "║  Web UI:  http://localhost:$Port                    ║"
if (-not $ndiFound) {
Write-Host "║                                                      ║"
Write-Host "║  ⚠ NDI SDK not installed — mock mode active          ║"
}
Write-Host "╚══════════════════════════════════════════════════════╝"
Write-Host ""
