"""
main.py — Project Janus entry point.

1. Runs the Harvester against a list of target URLs to populate data/vault.db.
2. Launches the interactive Mistral/Ollama agent loop.
"""

import os
from src.harvester.engine import Harvester

# ---------------------------------------------------------------------------
# Target URLs to harvest (edit this list as needed)
# ---------------------------------------------------------------------------
TARGET_URLS = [
    # Add forum thread URLs here, e.g.:
    # "https://stolenhistory.net/threads/some-thread.1234/",
]

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vault.db")


def run_harvester():
    if not TARGET_URLS:
        print("[main] No target URLs configured — skipping harvest phase.")
        return

    print(f"[main] Starting harvest of {len(TARGET_URLS)} URL(s)...")
    harvester = Harvester(DB_PATH)
    for url in TARGET_URLS:
        harvester.ingest_thread(url)
    print("[main] Harvest complete.")


def run_agent():
    from run_agent import main as agent_main
    agent_main()


if __name__ == "__main__":
    run_harvester()
    run_agent()
