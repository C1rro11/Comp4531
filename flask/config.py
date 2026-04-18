"""
Central configuration for the Smart Seat Monitoring System.
All timeouts and thresholds are overridable via environment variables
so the demo can run with shortened timers.
"""
import os

# ── Seat layout ──────────────────────────────────────────────────
SEAT_IDS = os.environ.get(
    "SEAT_IDS", "A-01,A-02,A-03,A-04"
).split(",")

# ── Timeouts (seconds) ──────────────────────────────────────────
# How long before an unoccupied (previously occupied) seat is flagged
HOARD_TIMEOUT_S = int(os.environ.get("HOARD_TIMEOUT_S", 1800))        # 30 min
# Window for student to tap RFID after suspected hoarding alert
HOARD_CONFIRM_WINDOW_S = int(os.environ.get("HOARD_CONFIRM_WINDOW_S", 300))  # 5 min
# How long before a ghost-occupied seat escalates to flagged
GHOST_TIMEOUT_S = int(os.environ.get("GHOST_TIMEOUT_S", 600))         # 10 min
# Maximum reservation duration
RESERVE_MAX_S = int(os.environ.get("RESERVE_MAX_S", 1800))            # 30 min

# ── Sensor thresholds ───────────────────────────────────────────
CO2_BASELINE_PPM = int(os.environ.get("CO2_BASELINE_PPM", 420))
CO2_OCCUPIED_DELTA = int(os.environ.get("CO2_OCCUPIED_DELTA", 50))     # ppm above baseline
MMWAVE_MOTION_THRESHOLD = float(os.environ.get("MMWAVE_MOTION_THRESHOLD", 10.0))
IMU_VIBRATION_THRESHOLD = float(os.environ.get("IMU_VIBRATION_THRESHOLD", 0.05))

# ── Server ───────────────────────────────────────────────────────
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
