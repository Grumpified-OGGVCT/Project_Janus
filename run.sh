#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# Project Janus — Quick Launch (Unix/macOS)
# Activates venv, runs health check, launches demo page
# ══════════════════════════════════════════════════════════════

# ─── Check venv exists ────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo ""
    echo "  [!] Virtual environment not found."
    echo "  Please run install.sh first."
    echo ""
    exit 1
fi

# ─── Activate and launch ─────────────────────────────────────
source .venv/bin/activate
python scripts/setup_wizard.py --check
deactivate 2>/dev/null
