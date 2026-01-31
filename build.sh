#!/bin/bash
# ============================================================================
# MindScribe Desktop - PyInstaller Build Script (macOS/Linux)
# ============================================================================
# Usage:
#   chmod +x build.sh
#   ./build.sh
#
# This script automates the PyInstaller build process for MindScribe Desktop.
# It performs the following steps:
#   1. Verifies that the Python virtual environment exists
#   2. Verifies that PyInstaller is installed in the venv
#   3. Kills any running MindScribe processes
#   4. Cleans the dist/MindScribe output folder
#   5. Runs PyInstaller with the MindScribe.spec file
#   6. Copies .env to the dist folder if present
#   7. Prints a build summary
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
VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"
SPEC_FILE="${PROJECT_ROOT}/MindScribe.spec"
DIST_FOLDER="${PROJECT_ROOT}/dist/MindScribe"
EXE_PATH="${DIST_FOLDER}/MindScribe"
ENV_SOURCE="${PROJECT_ROOT}/.env"
ENV_DEST="${DIST_FOLDER}/.env"

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
# Step 1: Check that the virtual environment exists
# --------------------------------------------------------------------------
write_step "Checking virtual environment"

if [ ! -f "${VENV_PYTHON}" ]; then
    write_error "Virtual environment not found at: ${VENV_PYTHON}"
    write_error "Please create the venv first: python3 -m venv venv"
    exit 1
fi

write_success "Virtual environment found at: ${VENV_PYTHON}"

# --------------------------------------------------------------------------
# Step 2: Check that PyInstaller is installed
# --------------------------------------------------------------------------
write_step "Checking PyInstaller installation"

PYINSTALLER_VERSION=$("${VENV_PYTHON}" -m PyInstaller --version 2>&1) || {
    write_error "PyInstaller is not installed in the virtual environment."
    write_error "Install it with: ./venv/bin/pip install pyinstaller"
    exit 1
}

PYINSTALLER_VERSION=$(echo "${PYINSTALLER_VERSION}" | tr -d '[:space:]')
write_success "PyInstaller is installed (version: ${PYINSTALLER_VERSION})"

# --------------------------------------------------------------------------
# Step 3: Kill any running MindScribe processes
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
# Step 4: Clean the dist/MindScribe folder
# --------------------------------------------------------------------------
write_step "Cleaning output folder"

if [ -d "${DIST_FOLDER}" ]; then
    write_warning "Removing existing dist/MindScribe folder..."
    if rm -rf "${DIST_FOLDER}"; then
        write_success "Cleaned dist/MindScribe folder."
    else
        write_error "Failed to clean dist/MindScribe folder."
        write_error "Make sure no files are locked by another process."
        exit 1
    fi
else
    write_success "dist/MindScribe folder does not exist. Nothing to clean."
fi

# --------------------------------------------------------------------------
# Step 5: Run PyInstaller
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

# Verify the executable was created
# On macOS, PyInstaller may produce a .app bundle or a bare executable
if [ -f "${EXE_PATH}" ]; then
    FINAL_EXE_PATH="${EXE_PATH}"
elif [ -d "${EXE_PATH}.app" ]; then
    FINAL_EXE_PATH="${EXE_PATH}.app/Contents/MacOS/MindScribe"
    if [ ! -f "${FINAL_EXE_PATH}" ]; then
        write_error "Build appeared to succeed but MindScribe executable was not found inside: ${EXE_PATH}.app"
        exit 1
    fi
else
    write_error "Build appeared to succeed but MindScribe was not found at: ${EXE_PATH}"
    exit 1
fi

# --------------------------------------------------------------------------
# Step 6: Copy .env file if it exists
# --------------------------------------------------------------------------
write_step "Checking for .env file"

ENV_COPIED=false
if [ -f "${ENV_SOURCE}" ]; then
    if cp "${ENV_SOURCE}" "${ENV_DEST}" 2>/dev/null; then
        ENV_COPIED=true
        write_success ".env copied to dist/MindScribe/"
    else
        write_warning "Failed to copy .env file."
    fi
else
    write_warning "No .env file found in project root. Skipping copy."
fi

# --------------------------------------------------------------------------
# Step 7: Print build summary
# --------------------------------------------------------------------------
write_step "Build Summary"

if [ "$(uname)" = "Darwin" ]; then
    # macOS: stat -f for file size
    EXE_SIZE=$(stat -f%z "${FINAL_EXE_PATH}" 2>/dev/null || echo "0")
else
    # Linux: stat -c for file size
    EXE_SIZE=$(stat -c%s "${FINAL_EXE_PATH}" 2>/dev/null || echo "0")
fi

if command -v awk > /dev/null 2>&1; then
    EXE_SIZE_MB=$(awk "BEGIN {printf \"%.2f\", ${EXE_SIZE} / 1048576}")
else
    EXE_SIZE_MB=$(echo "scale=2; ${EXE_SIZE} / 1048576" | bc 2>/dev/null || echo "N/A")
fi

echo ""
echo -e "${WHITE}  Executable : ${FINAL_EXE_PATH}${NC}"
echo -e "${WHITE}  Size       : ${EXE_SIZE_MB} MB (${EXE_SIZE} bytes)${NC}"
if [ "${ENV_COPIED}" = "true" ]; then
    echo -e "${GREEN}  .env       : Copied${NC}"
else
    echo -e "${YELLOW}  .env       : Not copied (file not found in project root)${NC}"
fi
echo ""
echo -e "${GREEN}Build succeeded.${NC}"

exit 0
