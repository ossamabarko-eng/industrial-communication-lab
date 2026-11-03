import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(r"C:\Users\amentag\Desktop\master's projects\Industrial-Predictive-Maintenance")
LIVE_CSV = Path(r"C:\Users\amentag\Desktop\Industrial communication lab\live_readings.csv")
LIVE_DIR = PROJECT / "data" / "live"
OUT_FILE = LIVE_DIR / "live_motor.csv"
STATE_FILE = LIVE_DIR / "live_state.json"

MODE = "demo"      # "full" = your exact config (8+ minutes), "demo" = shorter windows
POLL = 2.0         # seconds between scoring passes
RUNNING_FRACTION = 0.9   # a reading counts as "running" above this fraction of the normal speed
WARMUP = 90              # running readings ignored while the motor warms up

os.chdir(PROJECT)                    # your config uses relative paths such as data/runs
sys.path.insert(0, str(PROJECT))
from src.config import RUNS_DIR
import src.health as H


def reference_failure_level():
    """Median health index around failure over the reference runs (same recipe as run_pipeline.py)."""
    levels = []
    for path in sorted(RUNS_DIR.glob("run_*.csv")):
        df = pd.read_csv(path)
        idx = H.health_index(df)
        t_fail = H.failure_time(df)
        if t_fail is not None:
            levels.append(idx[t_fail - 10: t_fail + 11].mean())
    return float(np.median(levels)), len(levels)


if MODE == "demo":
    # shorter windows so the whole story fits in a few minutes
    H.WINDOW, H.BASELINE, H.ALARM_FROM, H.PERSIST = 10, (60, 180), 180, 5

# The failure level must be measured with the SAME window and baseline as the live scoring,
# because the health index grows with the window length.
D_FAIL, N_REF = reference_failure_level()
print(f"Failure level from {N_REF} reference runs: {D_FAIL:.2f}")
print(f"Mode: {MODE} | window {H.WINDOW} | baseline readings {H.BASELINE[0]}-{H.BASELINE[1]} "
      f"| detection from reading {H.ALARM_FROM} | alarm level {H.ALARM_LEVEL} | warm-up {WARMUP}")


def running_rows(df):
    """Keep only the readings taken while the motor ran at normal speed.

    A stopped motor looks like a disaster to a model trained on running motors,
    so its readings must not be scored.
    """
    typical = df.loc[df["rpm"] > 500, "rpm"].median()
    if np.isnan(typical):
        return df.iloc[0:0], False
    mask = df["rpm"] > RUNNING_FRACTION * typical
    running = df[mask]
    return running, bool(mask.iloc[-1])


def score(df):
    """Run your own functions on the live readings."""
    df = df.copy()
    df["time_step"] = np.arange(len(df))          # your code assumes time_step = row number
    idx = H.health_index(df)
    t = df["time_step"].to_numpy()
    sc = H.health_score(idx, D_FAIL)
    out = pd.DataFrame({
        "time_step": t,
        "health_index": idx,
        "health_score": sc,
        "health_status": H.health_status(sc),
        "degradation_level": np.nan,              # unknown for a live motor
    })
    for col in ["linear", "quadratic", "conservative", "true_rul"]:
        out[col] = np.nan                         # RUL comes in a later step
    out["timestamp"] = df["timestamp"].to_numpy()
    for col in H.FEATURES:
        out[col] = df[col].to_numpy()             # sensor values, for the dashboard charts
    return out, H.detect_fault(idx, t), H.failure_time(df)


def save_atomic(path, writer):
    """Write to a temporary file first, so the dashboard never reads a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    writer(tmp)
    os.replace(tmp, path)


def main(once=False):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    need = H.BASELINE[1]
    while True:
        try:
            df = pd.read_csv(LIVE_CSV, on_bad_lines="skip").dropna()
        except (FileNotFoundError, pd.errors.EmptyDataError):
            df = pd.DataFrame()
        n_total = len(df)
        last_time = str(df["timestamp"].iloc[-1]) if n_total else None
        df, running_now = running_rows(df) if n_total else (df, False)
        n_running = len(df)
        df = df.iloc[WARMUP:].reset_index(drop=True)      # warm-up readings are never scored
        n = len(df)
        state = {
            "mode": MODE, "ready": n >= need, "n": n, "need": need,
            "n_total": n_total, "n_running": n_running, "warmup": WARMUP, "running": running_now,
            "window": int(H.WINDOW), "baseline": [int(b) for b in H.BASELINE],
            "alarm_level": float(H.ALARM_LEVEL), "d_fail": D_FAIL,
            "detected": None, "failure": None,
            "last_reading_time": last_time,
        }
        if n_running < WARMUP:
            print(f"motor warming up: {n_running}/{WARMUP} readings (not scored)")
        elif n < need:
            print(f"collecting healthy baseline: {n}/{need} readings (keep the motor healthy)")
        else:
            try:
                out, t_det, t_fail = score(df)
                state["detected"] = t_det
                state["failure"] = t_fail
                save_atomic(OUT_FILE, lambda p: out.to_csv(p, index=False))
                last = out.iloc[-1]
                msg = ("" if running_now else "MOTOR STOPPED, scoring paused | ")
                msg += (f"reading {n:4d} | index {last.health_index:8.1f} | "
                       f"score {last.health_score:5.1f} | {last.health_status}")
                if t_det is not None:
                    msg += f" | FAULT DETECTED at reading {t_det}"
                print(msg)
            except np.linalg.LinAlgError:
                print("baseline is unusable (a sensor never varies): check the sensor noise edits")
            except PermissionError:
                print("(file busy, will retry)")
        try:
            save_atomic(STATE_FILE, lambda p: p.write_text(json.dumps(state)))
        except PermissionError:
            pass
        if once:
            break
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main(once=len(sys.argv) > 1 and sys.argv[1] == "once")
    except KeyboardInterrupt:
        print("\nScoring stopped.")