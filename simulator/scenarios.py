"""
Predefined seat-lifecycle scenario generators.

Each scenario is a Python generator that yields one sensor-payload dict per tick.
The simulator calls next(scenario) every --interval seconds and POSTs the result.

Sensor payload schema (mirrors what a real ESP32 would send):
{
    "seat_id":              str,
    "mmwave_presence":      bool,
    "mmwave_motion_energy": float (0-100),
    "imu_vibration":        float (g-force RMS),
    "co2_ppm":              int,
    "rfid_tap":             str | None,    # student_id or null
    "timestamp":            str (ISO 8601)
}
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Generator

# ── Helpers ──────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _baseline(seat_id: str, **overrides) -> dict:
    """Empty / baseline sensor reading."""
    d = {
        "seat_id": seat_id,
        "mmwave_presence": False,
        "mmwave_motion_energy": random.uniform(0, 3),
        "imu_vibration": random.uniform(0, 0.02),
        "co2_ppm": random.randint(400, 430),
        "rfid_tap": None,
        "timestamp": _ts(),
    }
    d.update(overrides)
    return d


def _occupied(seat_id: str, **overrides) -> dict:
    """Reading when a student is actively studying."""
    d = {
        "seat_id": seat_id,
        "mmwave_presence": True,
        "mmwave_motion_energy": random.uniform(30, 80),
        "imu_vibration": random.uniform(0.08, 0.5),
        "co2_ppm": random.randint(550, 750),
        "rfid_tap": None,
        "timestamp": _ts(),
    }
    d.update(overrides)
    return d


# ── Scenario generators ─────────────────────────────────────────

def vacant(seat_id: str) -> Generator[dict, None, None]:
    """Seat stays empty forever."""
    while True:
        yield _baseline(seat_id)


def arrive_and_study(seat_id: str, student_id: str = "STU-001",
                     study_ticks: int = 60) -> Generator[dict, None, None]:
    """
    Student arrives, taps RFID, studies for study_ticks ticks, then taps out.
    After that the seat returns to vacant baseline forever.
    """
    # Tick 0 – RFID tap in
    yield _occupied(seat_id, rfid_tap=student_id)

    # Studying phase – CO2 ramps up
    co2 = 450
    for i in range(study_ticks):
        co2 = min(750, co2 + random.randint(1, 5))
        yield _occupied(seat_id, co2_ppm=co2)

    # Tap out
    yield _baseline(seat_id, rfid_tap=student_id)

    # Vacant forever after
    while True:
        yield _baseline(seat_id)


def hoard(seat_id: str, student_id: str = "STU-002",
          occupy_ticks: int = 10) -> Generator[dict, None, None]:
    """
    Student arrives, studies briefly, then leaves WITHOUT tapping out.
    Sensors decay to baseline (belongings still on desk → low readings).
    The backend should eventually flag suspected → confirmed hoarding.
    """
    # Arrive + tap
    yield _occupied(seat_id, rfid_tap=student_id)

    # Study briefly
    for _ in range(occupy_ticks):
        yield _occupied(seat_id)

    # Leave without tapping — CO2 slowly drops, mmWave off, IMU off
    co2 = 600
    for _ in range(5):
        co2 = max(420, co2 - random.randint(20, 40))
        yield {
            "seat_id": seat_id,
            "mmwave_presence": False,
            "mmwave_motion_energy": random.uniform(0, 5),
            "imu_vibration": random.uniform(0, 0.03),
            "co2_ppm": co2,
            "rfid_tap": None,
            "timestamp": _ts(),
        }

    # Flat baseline — nobody home
    while True:
        yield _baseline(seat_id)


def ghost_occupied(seat_id: str, initial_ticks: int = 3) -> Generator[dict, None, None]:
    """
    Belongings placed on seat but student never tapped RFID.
    Sensors briefly detect some presence (placing bag triggers mmWave momentarily),
    then settle to near-baseline.
    """
    # Brief mmWave blip as items are placed
    for _ in range(initial_ticks):
        yield {
            "seat_id": seat_id,
            "mmwave_presence": True,
            "mmwave_motion_energy": random.uniform(15, 30),
            "imu_vibration": random.uniform(0.06, 0.12),
            "co2_ppm": random.randint(420, 450),
            "rfid_tap": None,
            "timestamp": _ts(),
        }
    # Settle — no person, slight noise
    while True:
        yield _baseline(seat_id)


def reserve_and_return(seat_id: str, student_id: str = "STU-003",
                       occupy_ticks: int = 10,
                       away_ticks: int = 15) -> Generator[dict, None, None]:
    """
    Student arrives, studies, reserves via the app (handled by stub.py posting
    to /api/reserve), leaves, returns after away_ticks.

    NOTE: The reservation API call is made by stub.py, not yielded here.
    This generator only produces sensor data. The stub detects the "away" phase
    and calls the reserve endpoint separately.

    Phase markers returned via a '_phase' key (not sent to server, used by stub):
        'study'   – student studying
        'leaving' – about to leave (stub should call /api/reserve here)
        'away'    – seat empty, student away
        'return'  – student returning (RFID tap)
        'resumed' – studying again
    """
    # Arrive + tap
    d = _occupied(seat_id, rfid_tap=student_id)
    d["_phase"] = "study"
    yield d

    # Study
    for _ in range(occupy_ticks):
        d = _occupied(seat_id)
        d["_phase"] = "study"
        yield d

    # Signal that student is about to leave — stub should POST /api/reserve
    d = _occupied(seat_id)
    d["_phase"] = "leaving"
    yield d

    # Away — baseline
    for _ in range(away_ticks):
        d = _baseline(seat_id)
        d["_phase"] = "away"
        yield d

    # Return — tap RFID
    d = _occupied(seat_id, rfid_tap=student_id)
    d["_phase"] = "return"
    yield d

    # Resume studying
    while True:
        d = _occupied(seat_id)
        d["_phase"] = "resumed"
        yield d


# ── Registry ─────────────────────────────────────────────────────

SCENARIOS = {
    "vacant": vacant,
    "study": arrive_and_study,
    "hoard": hoard,
    "ghost": ghost_occupied,
    "reserve": reserve_and_return,
}
