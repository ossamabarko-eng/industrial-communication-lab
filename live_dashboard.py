import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from lab_settings import PROJECT          # edit lab_settings_local.py, not this file

sys.path.insert(0, str(PROJECT))          # so `src` is found wherever this file is run from
from src.config import FEATURES, VIB_LIMIT

LIVE_DIR = PROJECT / "data" / "live"

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


def recommendation(status, rul, safety_margin):
    """Turn the health status and predicted remaining life into a maintenance action."""
    known = not np.isnan(rul)
    if status == "Critical" or (known and rul <= safety_margin):
        return "error", "Immediate maintenance required. Stop the motor or repair it now."
    if status == "Degraded":
        if known:
            window = max(rul - safety_margin, 0)
            return "error", f"Plan maintenance now and complete it within about {window:.0f} readings."
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
    res = pd.read_csv(result_path)       # scores, remaining life AND sensor values, running readings only
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
min_after, safety_margin = state.get("min_after", 100), state.get("safety_margin", 50)
cur = res.iloc[now]
score, status, index = cur["health_score"], cur["health_status"], cur["health_index"]
rul = cur["conservative"]

if failure is not None:
    rul, rul_text, rul_note = 0.0, "0", "Failure limit reached"
elif detected is None:
    rul_text, rul_note = "—", "No fault detected yet"
elif np.isnan(rul):
    rul_text, rul_note = "—", "Collecting trend"
else:
    rul_text, rul_note = f"{rul:.0f}", "Conservative estimate"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Health score", f"{score:.0f} / 100")
c2.metric("Status", status)
c3.metric("Health index", f"{index:.1f}", delta=f"alarm level {alarm_level}", delta_color="off", delta_arrow="off")
c4.metric("Remaining life (readings)", rul_text, delta=rul_note, delta_color="off", delta_arrow="off")
level, message = recommendation(status, rul, safety_margin)
getattr(st, level)(f"**Maintenance recommendation:** {message}")

st.divider()

# ---------- Health score, health index and remaining life ----------
left, middle, right = st.columns(3)
xmax = max(now + 10, state["baseline"][1] + 60)

with left:
    st.subheader("Health score")
    fig, ax = plt.subplots(figsize=(5, 3.4))
    ax.axhspan(70, 100, color="green", alpha=0.12)
    ax.axhspan(40, 70, color="gold", alpha=0.18)
    ax.axhspan(10, 40, color="orange", alpha=0.18)
    ax.axhspan(0, 10, color="red", alpha=0.15)
    ax.plot(res["time_step"], res["health_score"], color="black", linewidth=1.2)
    ax.set_xlim(state["baseline"][1], xmax)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Reading")
    ax.set_ylabel("Health score")
    ax.grid(alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

with middle:
    st.subheader("Anomaly (health index)")
    fig, ax = plt.subplots(figsize=(5, 3.4))
    ax.plot(res["time_step"], res["health_index"], linewidth=1.2)
    ax.axhline(alarm_level, color="red", linestyle="--", label="Alarm level")
    ax.set_xlim(state["baseline"][0], xmax)           # readings before the baseline are just start-up
    ax.set_yscale("symlog", linthresh=alarm_level)    # healthy values (about 2) and fault values (hundreds) both visible
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Reading")
    ax.set_ylabel("Distance from healthy baseline")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left")
    st.pyplot(fig)
    plt.close(fig)

with right:
    st.subheader("Remaining useful life")
    est = res.dropna(subset=["conservative"])
    if est.empty:
        st.info(f"Estimates start {min_after} readings after a fault is detected.")
    else:
        fig, ax = plt.subplots(figsize=(5, 3.4))
        ax.plot(est["time_step"], est["conservative"], label="Predicted (conservative)", linewidth=1.5)
        if failure is not None:
            ax.axvline(failure, color="black", linestyle="--", linewidth=1, label="Failure limit reached")
        ax.set_xlim(est["time_step"].min() - 5, xmax)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Reading")
        ax.set_ylabel("Readings left")
        ax.grid(alpha=0.3)
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)

# ---------- Sensor trends ----------
st.subheader("Sensor trends")
fig, axes = plt.subplots(2, 2, figsize=(12, 5), sharex=True)
for ax, col in zip(axes.flat, FEATURES):
    ax.plot(sensors["time_step"], sensors[col], linewidth=0.5, alpha=0.5)
    ax.plot(sensors["time_step"], sensors[col].rolling(window, min_periods=1).mean(),
            linewidth=1.8, label=f"{window}-reading average")
    if detected is not None:
        ax.axvline(detected, color="red", linestyle="--", linewidth=1, label="Fault detected")
    ax.set_title(LABELS[col], fontsize=10)
    ax.set_xlim(0, xmax)
    ax.grid(alpha=0.3)
axes[0, 0].legend(loc="upper left", fontsize=8)
plt.tight_layout()
st.pyplot(fig)
plt.close(fig)

# ---------- Alert history ----------
st.subheader("Alert history")
events = []
if detected is not None:
    events.append({"reading": detected, "event": "Fault detected",
                   "health score": round(float(res.loc[detected, "health_score"]))})
for label in ["Warning", "Degraded", "Critical"]:
    reached = res.loc[(res["health_status"] == label) & (res["time_step"] >= state["baseline"][1]), "time_step"]
    if len(reached):
        first = int(reached.min())
        events.append({"reading": first, "event": f"Status first reached {label}",
                       "health score": round(float(res.loc[first, "health_score"]))})
if failure is not None:
    events.append({"reading": failure, "event": f"Failure limit reached (vibration {VIB_LIMIT} mm/s)",
                   "health score": round(float(res.loc[failure, "health_score"]))})
if events:
    st.dataframe(pd.DataFrame(events).sort_values("reading"), hide_index=True)
else:
    st.info("No alerts so far. The motor is operating normally.")

st.caption(f"Mode: {state['mode']} (window {window}, baseline readings "
           f"{state['baseline'][0]}-{state['baseline'][1]}). Failure is defined as smoothed vibration "
           f"reaching {VIB_LIMIT} mm/s, a placeholder for a real engineering limit. "
           "Reading numbers count running readings only. Remaining life is a conservative trend "
           "extrapolation, not a guarantee.")

refresh_later()