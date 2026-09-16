#!/usr/bin/env bash
# ============================================================
#   AURAJOBS - AUTONOMOUS CAREER INTELLIGENCE ENGINE
#   Universal Zero-Install Launcher for macOS & Linux
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PYTHON_BIN=""

echo "============================================================"
echo "  AURAJOBS - AUTONOMOUS CAREER INTELLIGENCE ENGINE"
echo "============================================================"
echo ""

# ---------------------------------------------------------
# 1. Check for Local Portable Runtime in .runtime/
# ---------------------------------------------------------
if [ -x "$RUNTIME_DIR/bin/python3" ]; then
    if "$RUNTIME_DIR/bin/python3" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
        PYTHON_BIN="$RUNTIME_DIR/bin/python3"
        echo "[INFO] Using portable local Python runtime: .runtime/bin/python3"
    fi
fi

# ---------------------------------------------------------
# 2. Check System python3 or python (>= 3.10)
# ---------------------------------------------------------
if [ -z "$PYTHON_BIN" ]; then
    for candidate in python3 python python3.13 python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
                PYTHON_BIN="$(command -v "$candidate")"
                echo "[INFO] Using system Python: $PYTHON_BIN"
                break
            fi
        fi
    done
fi

# ---------------------------------------------------------
# 3. Auto-Provision Portable Python Runtime if Missing
# ---------------------------------------------------------
if [ -z "$PYTHON_BIN" ]; then
    echo "[!] No suitable Python 3.10+ installation detected."
    echo "[+] Auto-provisioning self-contained portable Python environment into .runtime/..."
    echo ""

    mkdir -p "$RUNTIME_DIR"
    OS_TYPE="$(uname -s)"
    ARCH_TYPE="$(uname -m)"
    DOWNLOAD_URL=""

    if [ "$OS_TYPE" = "Darwin" ]; then
        if [ "$ARCH_TYPE" = "arm64" ]; then
            DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-aarch64-apple-darwin-install_only.tar.gz"
        else
            DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-x86_64-apple-darwin-install_only.tar.gz"
        fi
    elif [ "$OS_TYPE" = "Linux" ]; then
        if [ "$ARCH_TYPE" = "aarch64" ] || [ "$ARCH_TYPE" = "arm64" ]; then
            DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-aarch64-unknown-linux-gnu-install_only.tar.gz"
        else
            DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-x86_64-unknown-linux-gnu-install_only.tar.gz"
        fi
    else
        echo "[ERROR] Unsupported operating system: $OS_TYPE"
        exit 1
    fi

    echo "[*] Downloading portable standalone Python build..."
    TEMP_ARCHIVE="/tmp/aurajobs_python.tar.gz"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$DOWNLOAD_URL" -o "$TEMP_ARCHIVE"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$DOWNLOAD_URL" -O "$TEMP_ARCHIVE"
    else
        echo "[ERROR] Neither curl nor wget was found. Please install curl or python3."
        exit 1
    fi

    echo "[*] Extracting portable runtime..."
    tar -xzf "$TEMP_ARCHIVE" -C "$RUNTIME_DIR" --strip-components=1
    rm -f "$TEMP_ARCHIVE"

    if [ -x "$RUNTIME_DIR/bin/python3" ]; then
        PYTHON_BIN="$RUNTIME_DIR/bin/python3"
        echo "[OK] Portable Python runtime provisioned successfully!"
    else
        echo "[ERROR] Failed to extract portable runtime."
        exit 1
    fi
fi

# ---------------------------------------------------------
# 4. Check & Install Dependencies
# ---------------------------------------------------------
echo ""
echo "[*] Verifying project dependencies..."
if ! "$PYTHON_BIN" -c "import pandas, yaml, jobspy, requests, tabulate, scrapling, patchright" 2>/dev/null; then
    echo "[!] Missing required dependencies. Installing from requirements.txt..."
    "$PYTHON_BIN" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt"
    echo "[OK] Dependencies successfully installed."
else
    echo "[OK] All dependencies verified."
fi

# ---------------------------------------------------------
# 5. Launch AuraJobs Engine
# ---------------------------------------------------------
echo ""
echo "============================================================"
echo "  LAUNCHING AURAJOBS ENGINE"
echo "============================================================"
echo ""

exec "$PYTHON_BIN" "$SCRIPT_DIR/main.py" "$@"
