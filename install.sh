#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# Project Janus — Unix/macOS Installation Script
# Sovereign Archival Intelligence
# ══════════════════════════════════════════════════════════════
set -e

echo ""
echo "================================================================"
echo "  Project Janus — Sovereign Archival Intelligence"
echo "  Unix/macOS Installation Script"
echo "================================================================"
echo ""

# ─── Check Python ─────────────────────────────────────────────
echo "[*] Checking Python installation..."

PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3 is not installed."
    echo "  macOS:    brew install python3"
    echo "  Ubuntu:   sudo apt install python3 python3-venv"
    echo "  Fedora:   sudo dnf install python3"
    exit 1
fi

PYTHON_VER=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "[+] $PYTHON_CMD $PYTHON_VER found."

# ─── Version check (3.10+) ────────────────────────────────────
PY_MINOR=$(echo "${PYTHON_VER}" | cut -d. -f2)
if [ "${PY_MINOR}" -lt 10 ]; then
    echo "[ERROR] Python 3.10+ required. Found: ${PYTHON_VER}"
    exit 1
fi

# ─── Create venv ──────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo ""
    echo "[*] Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
    echo "[+] Virtual environment created in .venv/"
else
    echo "[+] Virtual environment already exists."
fi

# ─── Activate ─────────────────────────────────────────────────
echo "[*] Activating virtual environment..."
source .venv/bin/activate

# ─── Upgrade pip ──────────────────────────────────────────────
echo "[*] Upgrading pip..."
pip install --upgrade pip --quiet 2>/dev/null

# ─── Install dependencies ────────────────────────────────────
echo "[*] Installing dependencies from requirements.txt..."
echo "    This may take a few minutes on first install."
echo ""
pip install -r requirements.txt

# ─── Launch Setup Wizard ─────────────────────────────────────
echo ""
echo "================================================================"
echo "[*] Launching Interactive Setup Wizard..."
echo "================================================================"
echo ""
python scripts/setup_wizard.py

# ─── Done ─────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo "[+] Installation complete!"
echo ""
echo "  Quick launch:    ./run.sh"
echo "  Reconfigure:     python scripts/setup_wizard.py --config"
echo "  Health check:    python scripts/setup_wizard.py --check"
echo "================================================================"
echo ""
