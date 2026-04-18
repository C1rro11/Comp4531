"""
Per-seat finite state machine with rule-based transition logic.

States
------
VACANT              – seat empty and available
OCCUPIED            – student actively using the seat
RESERVED            – student away, reservation timer running
SUSPECTED_HOARDING  – no presence detected for HOARD_TIMEOUT_S
CONFIRMED_HOARDING  – no RFID tap within HOARD_CONFIRM_WINDOW_S after suspicion
GHOST_OCCUPIED      – belongings detected but student never tapped RFID
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from config import (
    CO2_BASELINE_PPM,
    CO2_OCCUPIED_DELTA,
    GHOST_TIMEOUT_S,
    HOARD_CONFIRM_WINDOW_S,
    HOARD_TIMEOUT_S,
    IMU_VIBRATION_THRESHOLD,
    MMWAVE_MOTION_THRESHOLD,
    RESERVE_MAX_S,
)


class SeatState(str, Enum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    SUSPECTED_HOARDING = "suspected_hoarding"
    CONFIRMED_HOARDING = "confirmed_hoarding"
    GHOST_OCCUPIED = "ghost_occupied"


# LED colour mapping (sent to ESP32 / shown on dashboard)
LED_COLORS = {
    SeatState.VACANT: "off",
    SeatState.OCCUPIED: "green",
    SeatState.RESERVED: "blue",
    SeatState.SUSPECTED_HOARDING: "amber",
    SeatState.CONFIRMED_HOARDING: "red_flash",
    SeatState.GHOST_OCCUPIED: "white_pulse",
}


class SeatStateMachine:
    """One instance per physical seat."""

    def __init__(self, seat_id: str) -> None:
        self.seat_id = seat_id
        self.state = SeatState.VACANT
        self.student_id: Optional[str] = None
        self.last_presence_time: float = 0.0
        self.state_changed_at: float = time.time()
        self.reservation_expiry: Optional[float] = None
        self.hoard_suspect_since: Optional[float] = None
        self.ghost_detected_since: Optional[float] = None

    # ── Public API ───────────────────────────────────────────────

    def update(self, payload: dict) -> dict:
        """Feed a sensor payload; returns a state-change dict (or current state if unchanged)."""
        now = time.time()
        presence = self._detect_presence(payload)
        rfid_tap = payload.get("rfid_tap")  # None or student_id string

        old_state = self.state

        if rfid_tap:
            self._handle_rfid_tap(rfid_tap, now)
        else:
            self._handle_sensor_reading(presence, now)

        # Check timed escalations regardless of sensor data
        self._check_escalations(now)

        changed = self.state != old_state
        return self.snapshot(changed=changed)

    def reserve(self, student_id: str, duration_s: int | None = None) -> dict:
        """Student reserves their seat via the app."""
        if self.state != SeatState.OCCUPIED or self.student_id != student_id:
            return self.snapshot(changed=False, error="Can only reserve your own occupied seat")
        duration = min(duration_s or RESERVE_MAX_S, RESERVE_MAX_S)
        self.reservation_expiry = time.time() + duration
        self._transition(SeatState.RESERVED)
        return self.snapshot(changed=True)

    def staff_reset(self) -> dict:
        """Staff force-resets seat to vacant."""
        self._transition(SeatState.VACANT)
        self.student_id = None
        self.reservation_expiry = None
        self.hoard_suspect_since = None
        self.ghost_detected_since = None
        return self.snapshot(changed=True)

    def snapshot(self, changed: bool = False, error: str | None = None) -> dict:
        out = {
            "seat_id": self.seat_id,
            "state": self.state.value,
            "led_color": LED_COLORS[self.state],
            "student_id": self.student_id,
            "changed": changed,
            "timestamp": time.time(),
        }
        if self.reservation_expiry and self.state == SeatState.RESERVED:
            out["reservation_remaining_s"] = max(0, self.reservation_expiry - time.time())
        if error:
            out["error"] = error
        return out

    # ── Internal helpers ─────────────────────────────────────────

    def _detect_presence(self, payload: dict) -> bool:
        """Rule-based presence detection from sensor readings."""
        mmwave = payload.get("mmwave_presence", False)
        motion = payload.get("mmwave_motion_energy", 0) >= MMWAVE_MOTION_THRESHOLD
        imu = payload.get("imu_vibration", 0) >= IMU_VIBRATION_THRESHOLD
        co2 = payload.get("co2_ppm", CO2_BASELINE_PPM) >= (CO2_BASELINE_PPM + CO2_OCCUPIED_DELTA)
        # Person present if mmWave says yes OR (motion + any supporting signal)
        return mmwave or (motion and (imu or co2))

    def _handle_rfid_tap(self, student_id: str, now: float) -> None:
        """Process an RFID tap event."""
        if self.state == SeatState.VACANT:
            # New student arrives
            self.student_id = student_id
            self.last_presence_time = now
            self._transition(SeatState.OCCUPIED)

        elif self.state == SeatState.OCCUPIED and self.student_id == student_id:
            # Student taps out — leave
            self._transition(SeatState.VACANT)
            self.student_id = None

        elif self.state in (SeatState.SUSPECTED_HOARDING, SeatState.CONFIRMED_HOARDING):
            # Student returns and taps — clear hoarding
            self.student_id = student_id
            self.last_presence_time = now
            self.hoard_suspect_since = None
            self._transition(SeatState.OCCUPIED)

        elif self.state == SeatState.RESERVED and self.student_id == student_id:
            # Student returns from reservation
            self.reservation_expiry = None
            self.last_presence_time = now
            self._transition(SeatState.OCCUPIED)

        elif self.state == SeatState.GHOST_OCCUPIED:
            # Someone finally taps — claim the seat
            self.student_id = student_id
            self.last_presence_time = now
            self.ghost_detected_since = None
            self._transition(SeatState.OCCUPIED)

    def _handle_sensor_reading(self, presence: bool, now: float) -> None:
        """Process a sensor tick (no RFID tap)."""
        if presence:
            self.last_presence_time = now

        if self.state == SeatState.VACANT:
            if presence:
                # Sensors detect someone but no RFID tap yet → ghost
                self.ghost_detected_since = now
                self._transition(SeatState.GHOST_OCCUPIED)

        elif self.state == SeatState.OCCUPIED:
            if not presence:
                elapsed = now - self.last_presence_time
                if elapsed >= HOARD_TIMEOUT_S:
                    self.hoard_suspect_since = now
                    self._transition(SeatState.SUSPECTED_HOARDING)

        elif self.state == SeatState.RESERVED:
            if presence:
                # Auto-resume: sensors confirm student returned
                self.reservation_expiry = None
                self.last_presence_time = now
                self._transition(SeatState.OCCUPIED)

    def _check_escalations(self, now: float) -> None:
        """Timer-based state escalations."""
        if self.state == SeatState.SUSPECTED_HOARDING and self.hoard_suspect_since:
            if now - self.hoard_suspect_since >= HOARD_CONFIRM_WINDOW_S:
                self._transition(SeatState.CONFIRMED_HOARDING)

        if self.state == SeatState.RESERVED and self.reservation_expiry:
            if now >= self.reservation_expiry:
                self.reservation_expiry = None
                self.hoard_suspect_since = now
                self._transition(SeatState.SUSPECTED_HOARDING)

        if self.state == SeatState.GHOST_OCCUPIED and self.ghost_detected_since:
            if now - self.ghost_detected_since >= GHOST_TIMEOUT_S:
                self._transition(SeatState.CONFIRMED_HOARDING)

    def _transition(self, new_state: SeatState) -> None:
        self.state = new_state
        self.state_changed_at = time.time()
