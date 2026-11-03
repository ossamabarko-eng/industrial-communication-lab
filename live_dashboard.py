import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

PROJECT = Path(r"C:\Users\amentag\Desktop\master's projects\Industrial-Predictive-Maintenance")
sys.path.insert(0, str(PROJECT))      # so `src` is found wherever this file is run from
from src.config import FEATURES, VIB_LIMIT

LIVE_DIR = PROJECT / "data" / "live"

SAFETY_MARGIN = 50     # readings subtracted from the predicted RUL when planning maintenance
REFRESH_SECONDS = 2    # how often the page updates
STALE_SECONDS = 10     # no new reading for this long = the data chain has stopped
LABELS = {
    "temperature_C": "Temperature (°C)",
    "vibration_mm_s": "Vibration (mm/s)",
    "current_A": "Current (A)",
    "rpm": "Speed (RPM)",
}

st.set_page_config(page_title="Live Motor Monitor", layout="wide")
st.title("Live Motor Monitor")
st.caption("Real-time condition monitoring: motor simulation → OPC UA → MQTT → health model. "
           "One reading = one second.")

auto = st.sidebar.checkbox("Auto-refresh", value=True)


def refresh_later():
    """Re-run the page every few seconds so it follows the live data."""
    if auto:
        time.sleep(REFRESH_SECONDS)
        st.rerun()


def recommendation(status, rul):
    """Turn the health status and predicted remaining life into a maintenance action."""
    known = not np.isnan(rul)
    if status == "Critical" or (known and rul <= SAFETY_MARGIN):
        return "error", "Immediate maintenance required. Stop the motor or repair it now."
    if status == "Degraded":
        return "error", "Plan maintenance now."
    if status == "Warning":
        return "warning", "Schedule an inspection for mechanical wear (bearings, alignment, lubrication)."
    return "success", "No action needed. Continue routine monitoring."


# ---------- Load what live_score.py writes ----------
state_path, result_path = LIVE_DIR / "live_state.json", LIVE_DIR / "live_motor.csv"
try:
    state = json.loads(state_path.read_text())
except (FileNotFoundError, ValueError):
    st.info("Waiting for the live scorer. In the lab folder, run `python live_score.py`.")
    refresh_later()
    st.stop()

# ---------- Freshness: is data still arriving? ----------
age = None
if state["last_reading_time"]:
    last = datetime.strptime(state["last_reading_time"], "%Y-%m-%d %H:%M:%S")
    age = (datetime.now() - last).total_seconds()
    st.sidebar.metric("Last reading", last.strftime("%H:%M:%S"), delta=f"{age:.0f} s ago",
                      delta_color="off", delta_arrow="off")
stale = age is None or age > STALE_SECONDS

if not state["ready"]:
    warmup, n_running = state.get("warmup", 0), state.get("n_running", state["n"])
    if n_running < warmup:
        st.subheader("Motor warming up")
        st.progress(min(n_running / warmup, 1.0),
                    text=f"{n_running} / {warmup} readings. These are not scored while the motor warms up.")
    else:
        st.subheader("Collecting the healthy baseline")
        st.progress(min(state["n"] / state["need"], 1.0),
                    text=f"{state['n']} / {state['need']} readings. Keep the motor healthy until this is full.")
    if stale:
        st.error("No new readings are arriving. Check the logger, bridge, OPC UA server and broker.")
    refresh_later()
    st.stop()

try:
    res = pd.read_csv(result_path)       # scores AND sensor values, for running readings only
except (FileNotFoundError, ValueError, pd.errors.EmptyDataError):
    refresh_later()
    st.stop()
sensors = res

if stale:
    st.error(f"No new readings for {age:.0f} s. The data chain may have stopped "
             "(logger, bridge, OPC UA server or broker). The values below are the last known ones.")

if not state["running"]:
    st.warning("Motor stopped: scoring is paused, so the numbers below are from the last running reading. "
               "A stopped motor is not a fault.")

# ---------- Current state ----------
now = len(res) - 1
detected, failure = state["detected"], state["failure"]
window, alarm_level = state["window"], state["alarm_level"]
cur = res.iloc[now]
score, status, index = cur["health_score"], cur["health_status"], cur["health_index"]

if failure is not None:
    rul_text, rul_note = "0", "Failure limit reached"
elif detected is None:
    rul_text, rul_note = "—", "No fault detected yet"
else:
    rul_text, rul_note = "—", "Live RUL estimate not available yet"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Health score", f"{score:.0f} / 100")
c2.metric("Status", status)
c3.metric("Health index", f"{index:.1f}", delta=f"alarm level {alarm_level}", delta_color="off", delta_arrow="off")
c4.metric("Remaining life (readings)", rul_text, delta=rul_note, delta_color="off", delta_arrow="off")
level, message = recommendation(status, float("nan") if failure is None else 0.0)
getattr(st, level)(f"**Maintenance recommendation:** {message}")

st.divider()

# ---------- Health score and health index ----------
left, right = st.columns(2)
xmax = max(now + 10, state["baseline"][1] + 60)

with left:
    st.subheader("Health score")
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.axhspan(70, 100, color="green", alpha=0.12)
    ax.axhspan(40, 70, color="gold", alpha=0.18)
    ax.axhspan(10, 40, color="orange", alpha=0.18)
    ax.axhspan(0, 10, color="red", alpha=0.15)
    ax.plot(res["time_step"], res["health_score"], color="black", linewidth=1.2)
    ax.set_xlim(state["baseline"][1], xmax)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Reading")
    ax.set_ylabel("Health score")