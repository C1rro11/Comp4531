# Simulator Guide — Smart Seat Monitoring System

This guide walks you through running and using the simulated data stub so you can develop and demo the full system **without any physical hardware**.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start (one command)](#quick-start-one-command)
4. [Manual Start (two terminals)](#manual-start-two-terminals)
5. [CLI Arguments](#cli-arguments)
6. [Interactive Commands](#interactive-commands)
7. [Scenarios Explained](#scenarios-explained)
8. [Understanding Seat States](#understanding-seat-states)
9. [Dashboard](#dashboard)
10. [REST API Reference](#rest-api-reference)
11. [Sensor Payload Schema](#sensor-payload-schema)
12. [Configuration & Environment Variables](#configuration--environment-variables)
13. [Walkthrough: Full Demo Script](#walkthrough-full-demo-script)
14. [Transitioning to Real Hardware](#transitioning-to-real-hardware)
15. [Troubleshooting](#troubleshooting)

---

## Overview

The simulator replaces physical ESP32 sensor nodes during development. It generates fake sensor readings (mmWave, IMU, CO₂, RFID) and sends them to the Flask backend over HTTP — the exact same endpoint that real hardware will use.

```
┌────────────────────┐         POST /api/sensor-data         ┌──────────────────┐
│   simulator/       │  ──────────────────────────────────▶   │   flask/         │
│   stub.py          │                                        │   app.py         │
│                    │         Socket.IO (seat_update)        │                  │
│   Generates fake   │                                        │   State machine  │
│   sensor payloads  │                                        │   + REST API     │
└────────────────────┘                                        └───────┬──────────┘
                                                                      │
                                                               Socket.IO push
                                                                      │
                                                                      ▼
                                                              ┌──────────────────┐
                                                              │   static/        │
                                                              │   Web Dashboard  │
                                                              │   (browser)      │
                                                              └──────────────────┘
```

---

## Prerequisites

- **Python 3.10+**
- **pip** (comes with Python)

Install dependencies:

```bash
pip install -r flask/requirements.txt
pip install -r simulator/requirements.txt
```

This installs Flask, Flask-SocketIO, eventlet, and requests.

---

## Quick Start (one command)

The demo launcher starts the server with **shortened timeouts** (hoarding triggers in 30 seconds instead of 30 minutes) and the simulator with a mixed set of scenarios:

```bash
chmod +x run_demo.sh
./run_demo.sh
```

Then open **http://localhost:5000** in your browser to see the live dashboard.

### What happens automatically

| Seat | Scenario | What you'll see |
|------|----------|-----------------|
| A-01 | `study` | Student arrives (RFID tap), studies for ~80 seconds, then leaves normally |
| A-02 | `hoard` | Student arrives, studies briefly (~16 sec), leaves without tapping out → triggers hoarding |
| A-03 | `ghost` | Belongings placed without any RFID tap → ghost occupied → escalates to flagged |
| A-04 | `vacant` | Seat stays empty |

---

## Manual Start (two terminals)

If you want more control, start the server and simulator separately.

### Terminal 1 — Flask server

```bash
cd flask

# Production timeouts (30 min hoarding, 5 min confirm):
python app.py

# OR demo timeouts (30 sec hoarding, 10 sec confirm):
HOARD_TIMEOUT_S=30 HOARD_CONFIRM_WINDOW_S=10 GHOST_TIMEOUT_S=15 python app.py
```

You should see:
```
Starting Smart Seat server on 0.0.0.0:5000
Seats: A-01, A-02, A-03, A-04
Dashboard: http://localhost:5000
```

### Terminal 2 — Simulator

```bash
cd simulator
python stub.py
```

You should see:
```
Simulator started — 4 seats, interval=2.0s, server=http://localhost:5000
Type 'rfid <seat> <id>' to simulate a tap, 'quit' to stop.
```

Every 5 ticks, it prints a progress line:
```
  [tick 5] sent 4 readings
  [tick 10] sent 4 readings
```

---

## CLI Arguments

```
python stub.py [OPTIONS]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--seats` | `A-01 A-02 A-03 A-04` | Space-separated seat IDs to simulate |
| `--interval` | `2.0` | Seconds between each tick (sensor reading batch) |
| `--server` | `http://localhost:5000` | Flask server URL |
| `--scenario` | *(mixed)* | Force ALL seats to run one scenario: `vacant`, `study`, `hoard`, `ghost`, or `reserve` |
| `--ticks` | `0` (infinite) | Stop after N ticks (useful for testing) |

### Examples

```bash
# Simulate 2 seats, both hoarding, 1-second interval
python stub.py --seats A-01 A-02 --scenario hoard --interval 1

# Run only 10 ticks then stop
python stub.py --ticks 10

# Point at a remote server
python stub.py --server http://192.168.1.50:5000
```

If `--scenario` is **not** specified, the simulator uses the default mixed assignment:
- A-01 → `study` (student studies for 40 ticks)
- A-02 → `hoard` (student leaves after 8 ticks without tapping out)
- A-03 → `ghost` (belongings placed, no RFID ever)
- A-04 → `vacant` (empty seat)

---

## Interactive Commands

While the simulator is running, you can type commands directly in the terminal:

| Command | Example | What it does |
|---------|---------|--------------|
| `rfid <seat_id> <student_id>` | `rfid A-04 STU-099` | Simulates a student tapping their RFID card at the specified seat |
| `reserve <seat_id> <student_id> [duration_s]` | `reserve A-01 STU-001 60` | Reserves a seat (student going away temporarily). Duration defaults to 1800s |
| `reset <seat_id>` | `reset A-02` | Staff force-resets a seat to Vacant |
| `quit` or `q` | `quit` | Stops the simulator gracefully |

**Note:** You can also press `Ctrl-C` at any time to stop.

### Example interactive session

```
Simulator started — 4 seats, interval=2.0s, server=http://localhost:5000
Type 'rfid <seat> <id>' to simulate a tap, 'quit' to stop.

  [tick 5] sent 4 readings
rfid A-04 STU-050
  [RFID] tapped STU-050 at A-04
  [tick 10] sent 4 readings
reserve A-04 STU-050 60
  [RESERVE] A-04: {'seat_id': 'A-04', 'state': 'reserved', 'changed': true, ...}
  [tick 15] sent 4 readings
reset A-02
  [RESET] A-02: {'seat_id': 'A-02', 'state': 'vacant', 'changed': true, ...}
quit

Simulator stopped.
```

---

## Scenarios Explained

Each scenario is a Python generator that produces one sensor payload per tick. The simulator calls `next(generator)` every `--interval` seconds.

### 1. `vacant`

The simplest scenario — seat stays empty forever.

- mmWave: off
- IMU: near-zero noise
- CO₂: baseline (~400–430 ppm)
- RFID: no tap

**State on dashboard:** 🟢 Vacant (grey card)

---

### 2. `study` (arrive_and_study)

Full normal lifecycle:

1. **Tick 0** — student taps RFID (payload includes `rfid_tap: "STU-001"`)
2. **Ticks 1–N** — mmWave: on, IMU: active, CO₂: gradually rises from ~450 to ~750 ppm
3. **Tick N+1** — student taps RFID again (tap-out)
4. **After** — baseline readings forever

**Parameters:**
- `student_id` (default: `"STU-001"`)
- `study_ticks` (default: `60`) — how many ticks the student studies

**State transitions:** Vacant → **Occupied** → Vacant

---

### 3. `hoard`

Student arrives but **leaves without tapping out** — the hoarding scenario:

1. **Tick 0** — RFID tap in
2. **Ticks 1–N** — studying (mmWave on, IMU active, CO₂ high)
3. **Ticks N+1 to N+5** — student leaves; CO₂ gradually drops, mmWave off, IMU off
4. **After** — flat baseline forever (bag on seat, nobody home)

The backend's timer starts counting when presence signals drop. After `HOARD_TIMEOUT_S` seconds of no presence (30 min real / 30 sec demo), the seat escalates.

**Parameters:**
- `student_id` (default: `"STU-002"`)
- `occupy_ticks` (default: `10`)

**State transitions:** Vacant → **Occupied** → *(timeout)* → **Suspected Hoarding** → *(no tap for 5 min/10 sec)* → **Confirmed Hoarding**

---

### 4. `ghost` (ghost_occupied)

Belongings placed without any RFID tap — the "ghost" scenario:

1. **Ticks 0–2** — brief mmWave blip as someone places items (motion energy 15–30, no RFID)
2. **After** — flat baseline (items on desk, no person)

**Parameters:**
- `initial_ticks` (default: `3`)

**State transitions:** Vacant → **Ghost Occupied** → *(no RFID tap for `GHOST_TIMEOUT_S`)* → **Confirmed Hoarding**

---

### 5. `reserve` (reserve_and_return)

Student reserves their seat before leaving:

1. **Tick 0** — RFID tap in
2. **Ticks 1–N** — studying
3. **Tick N+1** — leaving (simulator auto-calls `POST /api/reserve`)
4. **Ticks N+2 to N+2+M** — seat empty (reserved, timer counting)
5. **Tick N+3+M** — student returns (RFID tap)
6. **After** — studying again

**Parameters:**
- `student_id` (default: `"STU-003"`)
- `occupy_ticks` (default: `10`)
- `away_ticks` (default: `15`)

**State transitions:** Vacant → **Occupied** → **Reserved** → *(student returns)* → **Occupied**

If the student doesn't return before the timer expires: Reserved → **Suspected Hoarding** → **Confirmed Hoarding**

---

## Understanding Seat States

| State | LED Color | Dashboard | Server Trigger |
|-------|-----------|-----------|----------------|
| **Vacant** | Off | Grey card | All sensors at baseline |
| **Occupied** | 🟢 Green | Green card | mmWave presence OR (motion + CO₂/IMU) + RFID tap |
| **Reserved** | 🔵 Blue | Blue card (timer shown) | Student calls `/api/reserve` before leaving |
| **Suspected Hoarding** | 🟡 Amber | Amber card | No presence for `HOARD_TIMEOUT_S` after being occupied |
| **Confirmed Hoarding** | 🔴 Red (flashing) | Red card (pulsing) | No RFID tap within `HOARD_CONFIRM_WINDOW_S` after suspicion |
| **Ghost Occupied** | ⚪ White (pulsing) | Dark grey card (pulsing) | Sensors detect activity but no RFID tap ever registered |

### State transition diagram

```
                    ┌─────────┐
                    │  VACANT │ ◄──────────────────────────── staff reset
                    └────┬────┘                                   ▲
                         │                                        │
          RFID tap       │     sensors detect presence            │
          ───────────────┤     (no RFID tap)                      │
                         │     ─────────────────┐                 │
                         ▼                      ▼                 │
                   ┌──────────┐          ┌──────────────┐         │
                   │ OCCUPIED │          │    GHOST     │         │
                   └────┬─────┘          │  OCCUPIED    │         │
                        │                └──────┬───────┘         │
             ┌──────────┼──────────┐            │                 │
             │          │          │     no tap for                │
        RFID tap   no presence   /api/   GHOST_TIMEOUT_S          │
        (tap out)  for HOARD_    reserve       │                  │
             │     TIMEOUT_S       │           │                  │
             ▼          │          ▼           │                  │
          VACANT        │    ┌──────────┐      │                  │
                        │    │ RESERVED │      │                  │
                        │    └────┬─────┘      │                  │
                        │         │            │                  │
                        │    timer expires     │                  │
                        │         │            │                  │
                        ▼         ▼            ▼                  │
                   ┌────────────────────┐                         │
                   │     SUSPECTED      │                         │
                   │     HOARDING       │──── RFID tap ──► OCCUPIED
                   └─────────┬──────────┘
                             │
                     no tap for
                     HOARD_CONFIRM_WINDOW_S
                             │
                             ▼
                   ┌────────────────────┐
                   │     CONFIRMED      │──── staff reset ────────┘
                   │     HOARDING       │
                   └────────────────────┘
```

---

## Dashboard

Open **http://localhost:5000** in your browser.

### What you see
- A **grid of seat cards**, one per seat, colour-coded by state
- A **stats bar** at the top showing total / vacant / occupied / reserved / hoarded counts
- Each card shows:
  - Seat ID (e.g., `A-01`)
  - State label (e.g., `Occupied`, `Suspected Hoarding`)
  - Student ID (if assigned)
  - Last update timestamp
  - A **Staff Reset** button (only visible on hoarded/suspected seats)

### Real-time updates
The dashboard connects via **Socket.IO** and updates instantly when the server processes new sensor data — no page refresh needed.

---

## REST API Reference

All endpoints accept and return JSON.

### `GET /api/seats`

Returns the current state of all seats.

```bash
curl http://localhost:5000/api/seats
```

Response:
```json
[
  {
    "seat_id": "A-01",
    "state": "occupied",
    "led_color": "green",
    "student_id": "STU-001",
    "changed": false,
    "timestamp": 1776495123.79
  },
  ...
]
```

---

### `POST /api/sensor-data`

Send sensor readings (single payload or array). This is what the ESP32 / simulator calls every tick.

```bash
curl -X POST http://localhost:5000/api/sensor-data \
  -H "Content-Type: application/json" \
  -d '[{
    "seat_id": "A-01",
    "mmwave_presence": true,
    "mmwave_motion_energy": 50,
    "imu_vibration": 0.15,
    "co2_ppm": 620,
    "rfid_tap": "STU-001",
    "timestamp": "2026-04-18T15:00:00Z"
  }]'
```

---

### `POST /api/reserve`

Reserve a seat for a student who is leaving temporarily.

```bash
curl -X POST http://localhost:5000/api/reserve \
  -H "Content-Type: application/json" \
  -d '{"seat_id": "A-01", "student_id": "STU-001", "duration_s": 60}'
```

Only works if the seat is currently `occupied` and belongs to that student.

---

### `POST /api/staff-reset`

Force-reset any seat back to Vacant. Used by library staff.

```bash
curl -X POST http://localhost:5000/api/staff-reset \
  -H "Content-Type: application/json" \
  -d '{"seat_id": "A-02"}'
```

---

## Sensor Payload Schema

This is the JSON payload that both the simulator and real ESP32 send to `POST /api/sensor-data`:

```json
{
  "seat_id":              "A-01",
  "mmwave_presence":      true,
  "mmwave_motion_energy": 42.5,
  "imu_vibration":        0.12,
  "co2_ppm":              620,
  "rfid_tap":             "STU-001",
  "timestamp":            "2026-04-18T14:30:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `seat_id` | string | Unique seat identifier (e.g., `"A-01"`) |
| `mmwave_presence` | boolean | Whether the mmWave radar detects a person |
| `mmwave_motion_energy` | float (0–100) | Motion energy level; higher = more movement |
| `imu_vibration` | float (g-force RMS) | Desk vibration level from IMU |
| `co2_ppm` | int | CO₂ concentration in ppm from SCD40 |
| `rfid_tap` | string or null | Student ID if RFID was tapped this tick; `null` otherwise |
| `timestamp` | string (ISO 8601) | Time of reading |

### Thresholds used by the state machine

| Parameter | Default | Env Variable |
|-----------|---------|--------------|
| mmWave motion threshold | `10.0` | `MMWAVE_MOTION_THRESHOLD` |
| IMU vibration threshold | `0.05` g | `IMU_VIBRATION_THRESHOLD` |
| CO₂ baseline | `420` ppm | `CO2_BASELINE_PPM` |
| CO₂ occupied delta | `50` ppm above baseline | `CO2_OCCUPIED_DELTA` |

A person is considered **present** if:
- `mmwave_presence` is `true`, **OR**
- `mmwave_motion_energy` ≥ threshold **AND** (`imu_vibration` ≥ threshold **OR** `co2_ppm` ≥ baseline + delta)

---

## Configuration & Environment Variables

All settings in `flask/config.py` are overridable via environment variables:

| Variable | Default | Demo Value | Description |
|----------|---------|------------|-------------|
| `SEAT_IDS` | `A-01,A-02,A-03,A-04` | — | Comma-separated seat IDs |
| `HOARD_TIMEOUT_S` | `1800` (30 min) | `30` | Time without presence before suspected hoarding |
| `HOARD_CONFIRM_WINDOW_S` | `300` (5 min) | `10` | Time to tap RFID before confirming hoarding |
| `GHOST_TIMEOUT_S` | `600` (10 min) | `15` | Time before ghost seat escalates |
| `RESERVE_MAX_S` | `1800` (30 min) | `60` | Max reservation duration |
| `HOST` | `0.0.0.0` | — | Server bind address |
| `PORT` | `5000` | — | Server port |

### How to override

```bash
# Inline (for one run)
HOARD_TIMEOUT_S=30 GHOST_TIMEOUT_S=15 python app.py

# Or export
export HOARD_TIMEOUT_S=30
export GHOST_TIMEOUT_S=15
python app.py
```

The `run_demo.sh` script already sets all demo values for you.

---

## Walkthrough: Full Demo Script

Here's a step-by-step demo you can perform for a presentation. Uses demo timeouts so everything happens quickly.

### Setup

```bash
# Terminal 1 — start server with demo timeouts
cd flask
HOARD_TIMEOUT_S=30 HOARD_CONFIRM_WINDOW_S=10 GHOST_TIMEOUT_S=15 RESERVE_MAX_S=60 python app.py
```

```bash
# Terminal 2 — start simulator
cd simulator
python stub.py --interval 2
```

Open **http://localhost:5000** in your browser.

### Demo flow

| Time | What happens | What you see on dashboard |
|------|-------------|--------------------------|
| 0s | Simulator starts | A-01: Occupied (green), A-02: Occupied (green), A-03: Ghost (white pulse), A-04: Vacant (grey) |
| ~6s | A-03 ghost detection kicks in | A-03 turns to Ghost Occupied |
| ~16s | A-02's student leaves (sensors drop to baseline) | A-02 stays Occupied briefly (timer counting) |
| ~21s | A-03 ghost timeout expires (15s) | A-03 escalates to Confirmed Hoarding (red flash) |
| ~46s | A-02 hoard timeout expires (30s after sensors dropped) | A-02 → Suspected Hoarding (amber) |
| ~56s | A-02 confirm window expires (10s) | A-02 → Confirmed Hoarding (red flash) |

### Interactive demo actions

While the simulator is running in Terminal 2:

```
# 1. Simulate a student arriving at the vacant seat
rfid A-04 STU-NEW
# → Dashboard: A-04 turns green (Occupied)

# 2. Student reserves their seat and leaves
reserve A-04 STU-NEW 60
# → Dashboard: A-04 turns blue (Reserved, 60s timer)

# 3. Student returns
rfid A-04 STU-NEW
# → Dashboard: A-04 turns green again (Occupied)

# 4. Staff resets a hoarded seat
reset A-02
# → Dashboard: A-02 turns grey (Vacant)

# 5. Stop the simulator
quit
```

---

## Transitioning to Real Hardware

The simulator and real ESP32 use **the exact same API**. To switch:

1. Program the ESP32 to read sensors and format the JSON payload (same schema as above)
2. `POST` to `http://<server-ip>:5000/api/sensor-data` every 2 seconds
3. Remove or stop the simulator — the server doesn't care who sends data

The existing ESP32 NFC code already sends to this server. You just need to:
- Add mmWave / SCD40 / IMU readings to the payload
- Change the endpoint from `/nfc` to `/api/sensor-data`
- Include all sensor fields in the JSON

The `/nfc` legacy endpoint still works for backward compatibility.

---

## Troubleshooting

### "cannot reach server — is Flask running?"

The simulator can't connect to the Flask server. Check:
- Is the server running in another terminal?
- Is it on port 5000? (`--server http://localhost:5000`)
- Is another process using port 5000? (`lsof -i :5000`)

### Seats not changing state

- Are you using demo timeouts? With default timeouts, hoarding takes 30 **minutes**
- Check server logs for incoming POST data
- Try a manual curl: `curl http://localhost:5000/api/seats`

### Dashboard not updating

- Open browser dev tools → Console tab. Check for Socket.IO connection errors
- Make sure you're on `http://localhost:5000`, not a file:// URL
- Try hard refresh (Cmd+Shift+R)

### "unknown seat" error

The seat ID in the simulator doesn't match `SEAT_IDS` in `config.py`. Make sure both use the same IDs (default: `A-01` through `A-04`).

### Escalation checker keeps resetting state

The server runs a background task every second that checks timer-based escalations. If you manually set a seat to Occupied via curl but don't keep sending presence data, it will eventually escalate. This is by design — in production, the ESP32 sends continuous readings.
