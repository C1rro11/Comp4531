# COMP4531 — Smart Seat Monitoring System

## Problem Definition

During exam periods, students frequently remain in the library after class to revise, making available study spaces increasingly scarce. Finding a vacant seat often forces students to wander across multiple floors, wasting time and inadvertently disturbing those already studying.

A common aggravating factor is **seat hoarding** — students leave belongings at a seat to "reserve" it while they are away for extended periods. This effectively removes seats from availability without them being in use.

## Proposed Solution

We propose a **Smart Seat Monitoring System** that uses a combination of sensors at each seat to detect three states:

| State | Meaning |
|---|---|
| **Vacant** | Seat is empty and available |
| **Occupied** | A student is actively using the seat |
| **Hoarded** | Belongings are present but no student has been detected for an extended period |

Real-time seat states are surfaced through a **live web dashboard** accessible to students and library staff. An **RGB LED** at each seat serves as a physical hoarding alert, and a **button** allows students to confirm their presence.

## System Architecture

```
Per-seat sensor node (ESP32)
├── FSR / Load Cell (chair) → detects sitting
├── IMU - MPU6050 (desk) → detects activity/vibration
├── RGB LED → hoarding alert (off during normal use)
└── Tactile Button → "I'm back" confirmation
│
└── Wi-Fi → Flask Server
├── Seat state aggregation & timeout logic
├── Web Dashboard (Socket.IO real-time updates)
└── Staff alert system
```

### Data Flow

1. Each ESP32 reads its sensors periodically and sends seat state data to the Flask server over Wi-Fi
2. The server aggregates data from all seats, applies timeout/hoarding logic, and maintains the current state of every seat
3. The web dashboard receives real-time updates via Socket.IO and displays a floor map with seat statuses
4. When hoarding is suspected, the server instructs the ESP32 to light the LED; the student can press the button to clear the alert

## Hardware Components

### ESP32 DevKit V1 (WROOM-32) — The Controller (~$4–6)

The central microcontroller for each seat node. It reads all sensors, controls the LED and button, and communicates with the server over its **built-in Wi-Fi** — no extra networking hardware required. Cheap, widely supported, and runs Arduino or MicroPython. One per seat.

### IMU — MPU6050 (~$1–2) — Desk Vibration Sensor

Mounted to the underside of the desk with adhesive. Detects **activity on the desk surface**: writing, typing, page turning, placing or removing items. Answers the question: _"Is someone actively using this desk?"_

The IMU catches activity that the chair sensor alone would miss — for example, a student standing briefly, leaning forward, or reaching across the desk. It also helps detect the **transition from occupied to hoarding**: belongings sitting on a desk produce no vibration, so sustained silence combined with no chair pressure signals likely hoarding.

### FSR / Load Cell (~$2–5) — Chair Pressure Sensor

Placed under or on the chair seat. Detects **whether someone is physically sitting down**. This is the **primary occupancy signal** — the most reliable and most direct indicator.

A weight threshold (~15 kg) distinguishes a person from a bag left on the chair. The chair sensor is critical because a student sitting still and reading produces almost zero desk vibration — the IMU alone would miss them entirely.

### Why Both IMU and FSR?

They cover each other's blind spots:

| Scenario | Chair FSR | Desk IMU | Correct State |
|---|---|---|---|
| Student sitting and typing | ✓ Detected | ✓ Detected | Occupied |
| Student sitting still, reading | ✓ Detected | ✗ Missed | Occupied (FSR saves it) |
| Student standing at desk briefly | ✗ Missed | ✓ Detected | Occupied (IMU saves it) |
| Bag on chair, stuff on desk, nobody there | ✗ Below threshold | ✗ No vibration | Hoarded |
| Empty seat | ✗ Nothing | ✗ Nothing | Vacant |

Neither sensor alone handles all cases correctly. Together they provide robust three-state detection.

### RGB LED (~$0.30) — Hoarding Alert Light

A single WS2812B (NeoPixel) RGB LED at each seat. It is **off during normal operation** — it does not indicate vacant or occupied status (the dashboard handles that). It **only turns on when the system suspects hoarding**, serving two purposes:

1. **Returning student**: A clear physical signal that they need to press the button to confirm their presence
2. **Library staff**: A visual marker visible from across the room — staff can scan a floor and instantly spot lit-up seats without checking the dashboard

### Tactile Push Button (~$0.10) — Presence Confirmation

When the LED lights up (hoarding suspected), the student presses the button to say **"I'm back."** This solves the hardest problem in hoarding detection: distinguishing a 5-minute bathroom break from a 2-hour absence.

Without the button, the system would need either a long timeout (missing real hoarding) or a short timeout (generating false alerts on quick breaks). The button lets honest students self-resolve quickly.

The button is the lowest-friction confirmation method — no app, no card, no account, just press.

## Seat State Logic & Workflow

### Normal Operation (LED off)

1. **Student arrives** at an empty seat and sits down
2. Chair FSR detects weight → server marks seat as **Occupied**
3. Student studies — IMU and FSR continuously confirm presence
4. **Student leaves** and takes belongings → sensors detect no presence → server marks seat as **Vacant**
5. Other students check the **web dashboard** on their phone to find vacant seats before walking over

### Hoarding Detection (LED turns on)

1. Chair FSR reads no weight and IMU reads no vibration for **30 minutes**, but the seat was previously Occupied
2. Server flags seat as **Suspected Hoarding**
3. ESP32 turns on the **RGB LED** (amber)
4. **If the student returns and presses the button** → LED turns off, seat returns to Occupied, 30-minute timer resets
5. **If no button press within 5 minutes** → seat escalates to **Confirmed Hoarding** (LED flashes red), staff dashboard is flagged
6. Staff can investigate or remotely release the seat from the dashboard

### State Summary

| State | LED | Dashboard | Button Action |
|---|---|---|---|
| Vacant | Off | Available (green) | No effect |
| Occupied | Off | Occupied (red) | No effect |
| Suspected Hoarding | Amber (on) | Verify (amber) | Press → returns to Occupied |
| Confirmed Hoarding | Red (flashing) | Hoarded — staff flagged | Staff resets remotely |

## Software Stack

| Layer | Technology | Purpose |
|---|---|---|
| Firmware | Arduino / MicroPython on ESP32 | Read sensors, control LED/button, send data over Wi-Fi |
| Backend | Python Flask | Receive sensor data, run seat-state logic & timeouts, serve dashboard |
| Real-time updates | Socket.IO | Push seat state changes to the web dashboard instantly |
| Frontend | HTML/CSS/JS | Live dashboard with floor map showing seat statuses |

## Estimated Per-Seat Bill of Materials

| Component | Estimated Cost |
|---|---|
| ESP32 DevKit V1 | $4–6 |
| MPU6050 (IMU) | $1–2 |
| FSR / Load Cell | $2–5 |
| WS2812B RGB LED | $0.30 |
| Tactile Push Button | $0.10 |
| Wiring & Enclosure | $2–3 |
| **Total per seat** | **~$10–16** |

## Physical Setup

The sensor node (ESP32 + IMU + LED + button) is mounted in a small enclosure attached to the desk. The IMU is adhered to the underside of the desk surface. The FSR or load cell is placed under or on the chair seat. The LED and button are visible and accessible to the student on the desk surface or enclosure.

## Demo Plan

1. Set up one seat with the full sensor node and chair sensor
2. Open the web dashboard on a screen
3. **Vacant**: Seat is empty — dashboard shows green, LED is off
4. **Occupied**: Sit down — dashboard updates to red in real time, LED remains off
5. **Hoarding trigger**: Leave the seat (simulate a 30-min timeout with a shortened timer for demo) — LED turns amber, dashboard shows amber
6. **Confirmation**: Return and press the button — LED turns off, dashboard returns to red
7. **Hoarding escalation**: Leave again, do not press button — LED flashes red, staff dashboard flags the seat

## Innovation and Novelty

Unlike camera-based solutions (e.g., YOLOv8 vision models), this system:

- **Preserves privacy** — no images are captured, no visual data is stored or transmitted
- **Requires no training data** — sensor thresholds and logic replace ML model training, eliminating the difficulty of collecting labeled library footage
- **Runs on-device** — no GPU server needed for inference; the ESP32 handles all sensor processing locally
- **Achieves three-state detection** without vision by combining complementary sensor modalities (pressure + vibration + manual confirmation)

Compared to single-sensor approaches (mmWave, thermal, ultrasonic):

- **mmWave** suffers from interference and reduced accuracy when seats are closely spaced
- **Thermal sensors** produce false readings from laptops, chargers, and other heat sources
- **Ultrasonic** detects presence but cannot distinguish a person from belongings

Our multi-sensor fusion approach provides reliable, fine-grained seat-state classification while remaining low-cost, privacy-safe, and easy to deploy.