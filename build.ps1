# ============================================================================
# MindScribe Desktop - PyInstaller Build Script
# ============================================================================
# Usage:
#   .\build.ps1
#
# This script automates the PyInstaller build process for MindScribe Desktop.
# It performs the following steps:
#   1. Verifies that the Python virtual environment exists
#   2. Verifies that PyInstaller is installed in the venv
#   3. Kills any running MindScribe processes
#   4. Cleans the dist\MindScribe output folder
#   5. Runs PyInstaller with the MindScribe.spec file
#   6. Copies .env to the dist folder if present
#   7. Prints a build summary
#
# Exit codes:
#   0 - Build completed successfully
#   1 - Build failed
# ============================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$SpecFile = Join-Path $ProjectRoot "MindScribe.spec"
$DistFolder = Join-Path $ProjectRoot "dist\MindScribe"
$ExePath = Join-Path $DistFolder "MindScribe.exe"
$EnvSource = Join-Path $ProjectRoot ".env"
$EnvDest = Join-Path $DistFolder ".env"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "--- $Message ---" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error-Msg {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Warning-Msg {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

# --------------------------------------------------------------------------
# Step 1: Check that the virtual environment exists
# --------------------------------------------------------------------------
Write-Step "Checking virtual environment"

if (-not (Test-Path $VenvPython)) {
    Write-Error-Msg "Virtual environment not found at: $VenvPython"
    Write-Error-Msg "Please create the venv first: python -m venv venv"
    exit 1
}

Write-Success "Virtual environment found at: $VenvPython"

# --------------------------------------------------------------------------
# Step 2: Check that PyInstaller is installed
# --------------------------------------------------------------------------
Write-Step "Checking PyInstaller installation"

try {
    $pyinstallerCheck = & $VenvPython -m PyInstaller --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller check returned non-zero exit code"
    }
    Write-Success "PyInstaller is installed (version: $($pyinstallerCheck.Trim()))"
}
catch {
    Write-Error-Msg "PyInstaller is not installed in the virtual environment."
    Write-Error-Msg "Install it with: .\venv\Scripts\pip.exe install pyinstaller"
    exit 1
}

# --------------------------------------------------------------------------
# Step 3: Kill any running MindScribe processes
# --------------------------------------------------------------------------
Write-Step "Checking for running MindScribe processes"

$processes = Get-Process -Name "MindScribe" -ErrorAction SilentlyContinue
if ($processes) {
    Write-Warning-Msg "Found running MindScribe process(es). Stopping them..."
    $processes | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Success "MindScribe processes stopped."
}
else {
    Write-Success "No running MindScribe processes found."
}

# --------------------------------------------------------------------------
# Step 4: Clean the dist\MindScribe folder
# --------------------------------------------------------------------------
Write-Step "Cleaning output folder"

if (Test-Path $DistFolder) {
    Write-Warning-Msg "Removing existing dist\MindScribe folder..."
    try {
        Remove-Item -Path $DistFolder -Recurse -Force
        Write-Success "Cleaned dist\MindScribe folder."
    }
    catch {
        Write-Error-Msg "Failed to clean dist\MindScribe folder: $_"
        Write-Error-Msg "Make sure no files are locked by another process."
        exit 1
    }
}
else {
    Write-Success "dist\MindScribe folder does not exist. Nothing to clean."
}

# --------------------------------------------------------------------------
# Step 5: Run PyInstaller
# --------------------------------------------------------------------------
Write-Step "Running PyInstaller build"

Push-Location $ProjectRoot
try {
    & $VenvPython -m PyInstaller $SpecFile --clean -y 2>&1 | ForEach-Object {
        Write-Host $_
        if ($_ -match "Build complete!") {
            $script:buildSuccess = $true
        }
    }
    if (-not $script:buildSuccess) {
        throw "PyInstaller did not report 'Build complete!'"
    }
    Write-Success "PyInstaller build completed."
}
catch {
    Write-Error-Msg "PyInstaller build failed: $_"
    Pop-Location
    exit 1
}
finally {
    Pop-Location
}

# Verify the executable was created
if (-not (Test-Path $ExePath)) {
    Write-Error-Msg "Build appeared to succeed but MindScribe.exe was not found at: $ExePath"
    exit 1
}

# --------------------------------------------------------------------------
# Step 6: Copy .env file if it exists
# --------------------------------------------------------------------------
Write-Step "Checking for .env file"

$envCopied = $false
if (Test-Path $EnvSource) {
    try {
        Copy-Item -Path $EnvSource -Destination $EnvDest -Force
        $envCopied = $true
        Write-Success ".env copied to dist\MindScribe\"
    }
    catch {
        Write-Warning-Msg "Failed to copy .env file: $_"
    }
}
else {
    Write-Warning-Msg "No .env file found in project root. Skipping copy."
}

# --------------------------------------------------------------------------
# Step 7: Print build summary
# --------------------------------------------------------------------------
Write-Step "Build Summary"

$exeSize = (Get-Item $ExePath).Length
$exeSizeMB = [math]::Round($exeSize / 1MB, 2)

Write-Host ""
Write-Host "  Executable : $ExePath" -ForegroundColor White
Write-Host "  Size       : $exeSizeMB MB ($exeSize bytes)" -ForegroundColor White
if ($envCopied) {
    Write-Host "  .env       : Copied" -ForegroundColor Green
}
else {
    Write-Host "  .env       : Not copied (file not found in project root)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Build succeeded." -ForegroundColor Green

exit 0
