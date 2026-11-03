"""Settings shared by live_score.py and live_dashboard.py. No personal paths in this file.

Where is the companion project (the folder that contains src/health.py)?
  1. the environment variable IPM_PROJECT, if it is set;
  2. otherwise a local file lab_settings_local.py (ignored by git) that defines PROJECT;
  3. otherwise a folder called Industrial-Predictive-Maintenance next to this lab folder.
"""
import os
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
LIVE_CSV = LAB_DIR / "live_readings.csv"        # written by live_logger.py

PROJECT = LAB_DIR.parent / "Industrial-Predictive-Maintenance"
try:
    from lab_settings_local import PROJECT      # optional, never committed
except ImportError:
    pass
if os.environ.get("IPM_PROJECT"):
    PROJECT = os.environ["IPM_PROJECT"]
PROJECT = Path(PROJECT)