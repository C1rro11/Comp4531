#!/usr/bin/env python3
"""
Sensor data simulator — replaces physical ESP32 nodes during development.

Usage:
    python stub.py                          # 4 seats, mixed scenarios, 2s interval
    python stub.py --seats 2 --interval 1   # 2 seats, 1s interval
    python stub.py --scenario hoard         # all seats run the 'hoard' scenario

While running, type commands in the terminal:
    rfid <seat_id> <student_id>   – simulate an RFID tap
    reserve <seat_id> <student_id> [duration_s]
    reset <seat_id>               – staff reset
    quit / q                      – stop

Ctrl-C also stops gracefully.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

import requests

from scenarios import SCENARIOS, arrive_and_study, ghost_occupied, hoard, reserve_and_return, vacant

# ── Defaults ─────────────────────────────────────────────────────
DEFAULT_SEATS = ["A-01", "A-02", "A-03", "A-04"]
DEFAULT_INTERVAL = 2.0
DEFAULT_SERVER = "http://localhost:5000"

# Mixed scenario assignment for demo
DEFAULT_ASSIGNMENT = {
    "A-01": ("study", {"student_id": "STU-001", "study_ticks": 40}),
    "A-02": ("hoard", {"student_id": "STU-002", "occupy_ticks": 8}),
    "A-03": ("ghost", {}),
    "A-04": ("vacant", {}),
}


def build_generators(seats: list[str], scenario_name: str | None) -> dict:
    """Create a generator per seat."""
    gens = {}
    for seat_id in seats:
        if scenario_name:
            fn = SCENARIOS[scenario_name]
            gens[seat_id] = fn(seat_id)
        elif seat_id in DEFAULT_ASSIGNMENT:
            name, kwargs = DEFAULT_ASSIGNMENT[seat_id]
            gens[seat_id] = SCENARIOS[name](seat_id, **kwargs)
        else:
            gens[seat_id] = vacant(seat_id)
    return gens


def post_sensor_data(server: str, payloads: list[dict]) -> None:
    try:
        r = requests.post(
            f"{server}/api/sensor-data",
            json=payloads,
            timeout=5,
        )
        if r.status_code != 200:
            print(f"  [WARN] server responded {r.status_code}: {r.text[:120]}")
    except requests.ConnectionError:
        print("  [ERR] cannot reach server — is Flask running?")


def post_reserve(server: str, seat_id: str, student_id: str, duration: int = 1800) -> None:
    try:
        r = requests.post(
            f"{server}/api/reserve",
            json={"seat_id": seat_id, "student_id": student_id, "duration_s": duration},
            timeout=5,
        )
        print(f"  [RESERVE] {seat_id}: {r.json()}")
    except Exception as e:
        print(f"  [ERR] reserve failed: {e}")


def post_rfid_tap(server: str, seat_id: str, student_id: str) -> None:
    """Send a single RFID tap as a sensor payload."""
    payload = {
        "seat_id": seat_id,
        "mmwave_presence": False,
        "mmwave_motion_energy": 0,
        "imu_vibration": 0,
        "co2_ppm": 420,
        "rfid_tap": student_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    post_sensor_data(server, [payload])
    print(f"  [RFID] tapped {student_id} at {seat_id}")


def post_staff_reset(server: str, seat_id: str) -> None:
    try:
        r = requests.post(
            f"{server}/api/staff-reset",
            json={"seat_id": seat_id},
            timeout=5,
        )
        print(f"  [RESET] {seat_id}: {r.json()}")
    except Exception as e:
        print(f"  [ERR] reset failed: {e}")


# ── Interactive command reader (runs in a background thread) ─────

stop_event = threading.Event()
command_queue: list[tuple] = []
cmd_lock = threading.Lock()


def input_thread(server: str):
    """Read user commands from stdin."""
    while not stop_event.is_set():
        try:
            line = input()
        except EOFError:
            break
        parts = line.strip().split()
        if not parts:
            continue
        cmd = parts[0].lower()

        if cmd in ("quit", "q"):
            stop_event.set()
            break
        elif cmd == "rfid" and len(parts) >= 3:
            post_rfid_tap(server, parts[1], parts[2])
        elif cmd == "reserve" and len(parts) >= 3:
            dur = int(parts[3]) if len(parts) >= 4 else 1800
            post_reserve(server, parts[1], parts[2], dur)
        elif cmd == "reset" and len(parts) >= 2:
            post_staff_reset(server, parts[1])
        else:
            print("Commands: rfid <seat> <id> | reserve <seat> <id> [dur] | reset <seat> | quit")


# ── Main loop ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sensor data simulator")
    parser.add_argument("--seats", nargs="*", default=DEFAULT_SEATS)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), default=None,
                        help="Force all seats to run a single scenario")
    parser.add_argument("--ticks", type=int, default=0,
                        help="Stop after N ticks (0 = run forever)")
    args = parser.parse_args()

    gens = build_generators(args.seats, args.scenario)
    print(f"Simulator started — {len(gens)} seats, interval={args.interval}s, server={args.server}")
    print("Type 'rfid <seat> <id>' to simulate a tap, 'quit' to stop.\n")

    # Start keyboard listener (only if stdin is a TTY)
    if sys.stdin.isatty():
        t = threading.Thread(target=input_thread, args=(args.server,), daemon=True)
        t.start()

    tick = 0
    try:
        while not stop_event.is_set():
            if args.ticks and tick >= args.ticks:
                break
            payloads = []
            for seat_id, gen in gens.items():
                payload = next(gen)

                # Handle the _phase hint for reserve scenario
                phase = payload.pop("_phase", None)
                if phase == "leaving":
                    student_id = payload.get("rfid_tap") or "STU-003"
                    post_reserve(args.server, seat_id, student_id)

                payloads.append(payload)

            # POST batch
            post_sensor_data(args.server, payloads)

            tick += 1
            if tick % 5 == 0:
                print(f"  [tick {tick}] sent {len(payloads)} readings")

            stop_event.wait(timeout=args.interval)
    except KeyboardInterrupt:
        pass

    print("\nSimulator stopped.")


if __name__ == "__main__":
    main()
