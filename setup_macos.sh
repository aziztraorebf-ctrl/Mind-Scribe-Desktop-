#!/bin/bash
# ============================================================================
# MindScribe Desktop - macOS Setup Script
# ============================================================================
# Usage:
#   chmod +x setup_macos.sh
#   ./setup_macos.sh
#
# This script prepares a macOS development environment for MindScribe Desktop.
# It performs the following steps:
#   1. Verifies we are running on macOS
#   2. Checks / installs Homebrew
#   3. Installs portaudio and ffmpeg via Homebrew
#   4. Verifies Python 3.11+ is available
#   5. Creates and activates a virtual environment (venv-mac)
#   6. Installs macOS-specific Python dependencies
#   7. Verifies critical imports
#   8. Copies .env.example to .env if .env doesn't exist
#   9. Prints success message with next steps
#
# Exit codes:
#   0 - Setup completed successfully
#   1 - Setup failed
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
VENV_DIR="${PROJECT_ROOT}/venv-mac"
VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"
REQUIREMENTS="${PROJECT_ROOT}/requirements.txt"

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
# Step 0a: Deactivate any active Python venv (so we find the real Python)
# --------------------------------------------------------------------------
if [ -n "${VIRTUAL_ENV:-}" ]; then
    write_warning "A Python venv is already active: ${VIRTUAL_ENV}"
    write_warning "Deactivating it so setup uses the system Python."
    deactivate 2>/dev/null || true
    # Remove the venv's bin from PATH as a fallback
    export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "${VENV_DIR}/bin" | tr '\n' ':' | sed 's/:$//')
    write_success "Previous venv deactivated."
    echo ""
fi

# --------------------------------------------------------------------------
# Step 0b: Deactivate conda if active (prevents venv isolation issues)
# --------------------------------------------------------------------------
if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
    write_warning "conda environment '${CONDA_DEFAULT_ENV}' is active."
    write_warning "conda can interfere with Python venvs and cause missing-package errors."
    echo ""
    echo -e "${YELLOW}Attempting to deactivate conda...${NC}"
    # conda deactivate may not be available as a function in subshells,
    # so we also unset the key environment variables as a fallback.
    if type conda &> /dev/null; then
        conda deactivate 2>/dev/null || true
    fi
    # If conda is still present after deactivate, strip it from PATH
    if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
        unset CONDA_DEFAULT_ENV
        unset CONDA_PREFIX
        # Remove conda paths from PATH
        export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v conda | tr '\n' ':' | sed 's/:$//')
        write_warning "Stripped conda from PATH for the duration of this script."
    fi
    write_success "conda deactivated."
    echo ""
fi

# --------------------------------------------------------------------------
# Step 1: Check that we are on macOS
# --------------------------------------------------------------------------
write_step "Checking platform"

if [ "$(uname)" != "Darwin" ]; then
    write_error "This script is intended for macOS only."
    write_error "Detected platform: $(uname)"
    exit 1
fi

write_success "Running on macOS ($(sw_vers -productVersion))"

# --------------------------------------------------------------------------
# Step 2: Check / install Homebrew
# --------------------------------------------------------------------------
write_step "Checking Homebrew"

if command -v brew &> /dev/null; then
    write_success "Homebrew is installed ($(brew --version | head -1))"
else
    write_warning "Homebrew is not installed."
    echo -e "${YELLOW}Homebrew is required to install system dependencies (portaudio, ffmpeg).${NC}"
    echo ""
    read -r -p "Would you like to install Homebrew now? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY])
            echo "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for Apple Silicon Macs
            if [ -f "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            fi
            write_success "Homebrew installed successfully."
            ;;
        *)
            write_error "Homebrew is required. Please install it manually:"
            write_error "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
            ;;
    esac
fi

# --------------------------------------------------------------------------
# Step 3: Install portaudio and ffmpeg
# --------------------------------------------------------------------------
write_step "Installing system dependencies via Homebrew"

for pkg in portaudio ffmpeg; do
    if brew list "${pkg}" &> /dev/null; then
        write_success "${pkg} is already installed."
    else
        echo "Installing ${pkg}..."
        brew install "${pkg}"
        write_success "${pkg} installed."
    fi
done

# --------------------------------------------------------------------------
# Step 4: Check Python 3.11+
# --------------------------------------------------------------------------
write_step "Checking Python version"

PYTHON_CMD=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "${candidate}" &> /dev/null; then
        # Resolve to the real binary path (not a symlink inside a venv)
        RESOLVED="$(command -v "${candidate}")"
        if [ -L "${RESOLVED}" ]; then
            RESOLVED="$(readlink -f "${RESOLVED}" 2>/dev/null || python3 -c "import os,sys; print(os.path.realpath(sys.executable))" 2>/dev/null)"
        fi
        # Skip if it lives inside the venv we are about to delete
        case "${RESOLVED}" in
            "${VENV_DIR}/"*) continue ;;
        esac
        PYTHON_CMD="${candidate}"
        break
    fi
done

if [ -z "${PYTHON_CMD}" ]; then
    write_error "Python 3 is not installed."
    write_error "Please install Python 3.11 or later: brew install python@3.12"
    exit 1
fi

PYTHON_VERSION=$("${PYTHON_CMD}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$("${PYTHON_CMD}" -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$("${PYTHON_CMD}" -c "import sys; print(sys.version_info.minor)")

if [ "${PYTHON_MAJOR}" -lt 3 ] || ([ "${PYTHON_MAJOR}" -eq 3 ] && [ "${PYTHON_MINOR}" -lt 11 ]); then
    write_error "Python 3.11+ is required. Found: Python ${PYTHON_VERSION}"
    write_error "Please install a newer version: brew install python@3.12"
    exit 1
fi

write_success "Python ${PYTHON_VERSION} found (${PYTHON_CMD})"

# --------------------------------------------------------------------------
# Step 5: Create virtual environment
# --------------------------------------------------------------------------
write_step "Setting up virtual environment"

if [ -d "${VENV_DIR}" ]; then
    write_warning "Virtual environment already exists at: ${VENV_DIR}"
    read -r -p "Recreate it? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY])
            rm -rf "${VENV_DIR}"
            echo "Removed old venv."
            ;;
        *)
            write_success "Keeping existing virtual environment."
            ;;
    esac
fi

if [ ! -d "${VENV_DIR}" ]; then
    "${PYTHON_CMD}" -m venv "${VENV_DIR}"
    write_success "Virtual environment created at: ${VENV_DIR}"
fi

# Activate (for the remainder of this script)
source "${VENV_DIR}/bin/activate"
write_success "Virtual environment activated."

# --------------------------------------------------------------------------
# Step 6: Install Python dependencies
# --------------------------------------------------------------------------
write_step "Installing Python dependencies"

if [ ! -f "${REQUIREMENTS}" ]; then
    write_error "Requirements file not found: ${REQUIREMENTS}"
    exit 1
fi

"${VENV_PIP}" install --upgrade pip setuptools wheel
"${VENV_PIP}" install -r "${REQUIREMENTS}"
write_success "All Python dependencies installed."

# --------------------------------------------------------------------------
# Step 7: Verify critical imports
# --------------------------------------------------------------------------
write_step "Verifying critical imports"

IMPORT_ERRORS=0

for module in PyQt6 sounddevice pynput pystray; do
    if "${VENV_PYTHON}" -c "import ${module}" 2>/dev/null; then
        write_success "${module} imports successfully."
    else
        write_error "${module} failed to import!"
        IMPORT_ERRORS=$((IMPORT_ERRORS + 1))
    fi
done

if [ "${IMPORT_ERRORS}" -gt 0 ]; then
    write_error "${IMPORT_ERRORS} critical import(s) failed. Please check the errors above."
    exit 1
fi

# --------------------------------------------------------------------------
# Step 8: Copy .env.example to .env if needed
# --------------------------------------------------------------------------
write_step "Checking .env file"

if [ -f "${PROJECT_ROOT}/.env" ]; then
    write_success ".env file already exists."
elif [ -f "${PROJECT_ROOT}/.env.example" ]; then
    cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    write_success "Copied .env.example to .env"
    write_warning "Please edit .env and add your API keys before running MindScribe."
else
    write_warning "No .env or .env.example found. You will need to create a .env file with your API keys."
fi

# --------------------------------------------------------------------------
# Step 9: Success!
# --------------------------------------------------------------------------
write_step "Setup Complete"

echo ""
echo -e "${GREEN}MindScribe Desktop macOS setup is complete!${NC}"
echo ""
echo -e "${WHITE}Next steps:${NC}"
echo ""
echo -e "  ${CYAN}1.${NC} Grant accessibility permissions:"
echo -e "     ${WHITE}System Settings > Privacy & Security > Accessibility${NC}"
echo -e "     Add your terminal app (Terminal, iTerm2, etc.)"
echo ""
echo -e "  ${CYAN}2.${NC} Grant microphone permissions:"
echo -e "     ${WHITE}System Settings > Privacy & Security > Microphone${NC}"
echo -e "     Allow your terminal app"
echo ""
echo -e "  ${CYAN}3.${NC} Edit your .env file with your API keys:"
echo -e "     ${WHITE}${PROJECT_ROOT}/.env${NC}"
echo ""
echo -e "  ${CYAN}4.${NC} Run MindScribe:"
echo -e "     ${WHITE}source ${VENV_DIR}/bin/activate${NC}"
echo -e "     ${WHITE}python run.py${NC}"
echo ""
echo -e "  ${CYAN}5.${NC} To build a standalone .app bundle:"
echo -e "     ${WHITE}./build.sh${NC}"
echo ""

exit 0
