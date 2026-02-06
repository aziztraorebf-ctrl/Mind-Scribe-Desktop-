#!/bin/bash
# ============================================================================
# MindScribe Desktop - PyInstaller Build Script (macOS)
# ============================================================================
# Usage:
#   chmod +x build-mac.sh
#   ./build-mac.sh
#
# This script automates the PyInstaller build process for MindScribe Desktop
# on macOS using the PyQt6-based spec file. It performs the following steps:
#   1. Verifies we are running on macOS
#   2. Verifies that the macOS virtual environment exists
#   3. Verifies that PyInstaller is installed in the venv
#   4. Kills any running MindScribe processes
#   5. Cleans the dist/MindScribe output folder
#   6. Runs PyInstaller with the MindScribe-mac.spec file
#   7. Verifies the .app bundle was created
#   8. Copies .env into the .app bundle's Resources directory
#   9. Prints a build summary
#
# Exit codes:
#   0 - Build completed successfully
#   1 - Build failed
# ============================================================================

set -e

# --- Color codes ---
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# --- Paths ---
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/venv-mac/bin/python"
VENV_PIP="${PROJECT_ROOT}/venv-mac/bin/pip"
SPEC_FILE="${PROJECT_ROOT}/MindScribe-mac.spec"
DIST_FOLDER="${PROJECT_ROOT}/dist/MindScribe"
APP_BUNDLE="${PROJECT_ROOT}/dist/MindScribe.app"
APP_RESOURCES="${APP_BUNDLE}/Contents/Resources"
APP_EXE="${APP_BUNDLE}/Contents/MacOS/MindScribe"
ENV_SOURCE="${PROJECT_ROOT}/.env"

# --- Helper functions ---
write_step() {
    echo ""
    echo -e "${CYAN}--- $1 ---${NC}"
}

write_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

write_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

write_warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# --------------------------------------------------------------------------
# Step 1: Check that we are on macOS
# --------------------------------------------------------------------------
write_step "Checking platform"

if [ "$(uname)" != "Darwin" ]; then
    write_error "This build script is intended for macOS only."
    write_error "Detected platform: $(uname)"
    exit 1
fi

write_success "Running on macOS ($(sw_vers -productVersion))"

# --------------------------------------------------------------------------
# Step 2: Check that the virtual environment exists
# --------------------------------------------------------------------------
write_step "Checking virtual environment"

if [ ! -f "${VENV_PYTHON}" ]; then
    write_error "Virtual environment not found at: ${VENV_PYTHON}"
    write_error "Please run setup_macos.sh first, or create the venv manually:"
    write_error "  python3 -m venv venv-mac && source venv-mac/bin/activate"
    write_error "  pip install -r requirements-mac.txt"
    exit 1
fi

write_success "Virtual environment found at: ${VENV_PYTHON}"

# --------------------------------------------------------------------------
# Step 3: Check that PyInstaller is installed
# --------------------------------------------------------------------------
write_step "Checking PyInstaller installation"

PYINSTALLER_VERSION=$("${VENV_PYTHON}" -m PyInstaller --version 2>&1) || {
    write_error "PyInstaller is not installed in the virtual environment."
    write_error "Install it with: ${VENV_PIP} install pyinstaller"
    exit 1
}

PYINSTALLER_VERSION=$(echo "${PYINSTALLER_VERSION}" | tr -d '[:space:]')
write_success "PyInstaller is installed (version: ${PYINSTALLER_VERSION})"

# --------------------------------------------------------------------------
# Step 4: Kill any running MindScribe processes
# --------------------------------------------------------------------------
write_step "Checking for running MindScribe processes"

if pgrep -x "MindScribe" > /dev/null 2>&1; then
    write_warning "Found running MindScribe process(es). Stopping them..."
    pkill -x "MindScribe" 2>/dev/null || true
    sleep 2
    write_success "MindScribe processes stopped."
else
    write_success "No running MindScribe processes found."
fi

# --------------------------------------------------------------------------
# Step 5: Clean the dist output folders
# --------------------------------------------------------------------------
write_step "Cleaning output folders"

for target in "${DIST_FOLDER}" "${APP_BUNDLE}"; do
    if [ -e "${target}" ]; then
        write_warning "Removing existing: ${target}"
        if rm -rf "${target}"; then
            write_success "Cleaned: ${target}"
        else
            write_error "Failed to clean: ${target}"
            write_error "Make sure no files are locked by another process."
            exit 1
        fi
    fi
done

write_success "Output folders are clean."

# --------------------------------------------------------------------------
# Step 6: Run PyInstaller
# --------------------------------------------------------------------------
write_step "Running PyInstaller build"

# Temporarily disable set -e so we can capture the build result
set +e

BUILD_SUCCESS=false
cd "${PROJECT_ROOT}"

"${VENV_PYTHON}" -m PyInstaller "${SPEC_FILE}" --clean -y 2>&1 | while IFS= read -r line; do
    echo "${line}"
    if echo "${line}" | grep -q "Build complete!"; then
        touch "${PROJECT_ROOT}/.build_success_marker"
    fi
done

PYINSTALLER_EXIT_CODE=${PIPESTATUS[0]}

set -e

if [ -f "${PROJECT_ROOT}/.build_success_marker" ]; then
    rm -f "${PROJECT_ROOT}/.build_success_marker"
    BUILD_SUCCESS=true
fi

if [ "${PYINSTALLER_EXIT_CODE}" -ne 0 ]; then
    write_error "PyInstaller build failed with exit code ${PYINSTALLER_EXIT_CODE}."
    exit 1
fi

if [ "${BUILD_SUCCESS}" != "true" ]; then
    write_error "PyInstaller did not report 'Build complete!'"
    exit 1
fi

write_success "PyInstaller build completed."

# --------------------------------------------------------------------------
# Step 7: Verify .app bundle was created
# --------------------------------------------------------------------------
write_step "Verifying .app bundle"

if [ ! -d "${APP_BUNDLE}" ]; then
    write_error ".app bundle was not created at: ${APP_BUNDLE}"
    exit 1
fi

if [ ! -f "${APP_EXE}" ]; then
    write_error "Executable not found inside .app bundle at: ${APP_EXE}"
    exit 1
fi

write_success ".app bundle created at: ${APP_BUNDLE}"

# --------------------------------------------------------------------------
# Step 8: Copy .env into .app bundle's Resources directory
# --------------------------------------------------------------------------
write_step "Copying .env into .app bundle"

ENV_COPIED=false
if [ -f "${ENV_SOURCE}" ]; then
    if [ -d "${APP_RESOURCES}" ]; then
        if cp "${ENV_SOURCE}" "${APP_RESOURCES}/.env" 2>/dev/null; then
            ENV_COPIED=true
            write_success ".env copied to ${APP_RESOURCES}/.env"
        else
            write_warning "Failed to copy .env into .app bundle."
        fi
    else
        write_warning "Resources directory not found: ${APP_RESOURCES}"
    fi
else
    write_warning "No .env file found in project root. Skipping copy."
fi

# --------------------------------------------------------------------------
# Step 9: Print build summary
# --------------------------------------------------------------------------
write_step "Build Summary"

# Get the size of the .app bundle
APP_SIZE=$(du -sh "${APP_BUNDLE}" 2>/dev/null | cut -f1)

echo ""
echo -e "${WHITE}  App Bundle : ${APP_BUNDLE}${NC}"
echo -e "${WHITE}  Executable : ${APP_EXE}${NC}"
echo -e "${WHITE}  Bundle Size: ${APP_SIZE}${NC}"
if [ "${ENV_COPIED}" = "true" ]; then
    echo -e "${GREEN}  .env       : Copied into Resources${NC}"
else
    echo -e "${YELLOW}  .env       : Not copied (file not found in project root)${NC}"
fi
echo ""
echo -e "${GREEN}Build succeeded.${NC}"
echo ""
echo -e "${WHITE}To run the app:${NC}"
echo -e "  ${CYAN}open ${APP_BUNDLE}${NC}"
echo ""
echo -e "${WHITE}Or from the command line:${NC}"
echo -e "  ${CYAN}${APP_EXE}${NC}"
echo ""

exit 0
