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
├── MMwave sensor → detects sitting
├── SDC40 Co2 Sensor -> detect if sitting
├── IMU - MPU6050 (desk) → detects activity/vibration
├── RGB LED → turns green when seat is occupied (When you tap your student ID card)
└── RFID Sensor → Telling the system you have occupied the seat (can be replaced by BLE)
│
└── Wi-Fi → Flask Server
├── Using XGBoost to determine the state of the seat (vacant, occupied, hoarded)
├── Seat state aggregation & timeout logic
├── Web Dashboard (Socket.IO real-time updates)
└── Staff alert system
```

### Data Flow

1. Each ESP32 reads its sensors periodically and sends seat state data to the Flask server over Wi-Fi
2. The server combine all incoming data, applies the XGBoost model to classify each seat's state, and runs timeout logic to detect hoarding
3. The web dashboard receives real-time updates via Socket.IO and displays a floor map with seat statuses
4. When hoarding is suspected, the server instructs the ESP32 to light the LED; the student can press the button to clear the alert

## Hardware Components

### ESP32 DevKit V1 (WROOM-32) — The Controller (~$4–6)

The central microcontroller for each seat node. It reads all sensors, controls the RGB LED and RFID reader, and communicates with the server over its **built-in Wi-Fi** — no extra networking hardware required. Cheap, widely supported, and runs Arduino or MicroPython. One per seat.

### IMU — MPU6050 (~$1–2) — Desk Vibration Sensor

Mounted to the underside of the desk with adhesive. Detects **activity on the desk surface**: writing, typing, page turning, placing or removing items. Answers the question: _"Is someone actively using this desk?"_

The IMU catches activity that mmWave alone would miss — for example, a student standing briefly, leaning forward, or reaching across the desk. It also helps detect the **transition from occupied to hoarding**: belongings sitting on a desk produce no vibration, so sustained silence combined with no mmWave presence signals likely hoarding.

### mmWave Radar Sensor — Presence Detection (~$3–6)

Mounted facing the seat area. Detects **micro-motion and breathing patterns** to confirm whether a living person is present — distinguishing a seated student from an abandoned bag of belongings. Unlike PIR sensors, mmWave can detect a completely still person.

Combined with the IMU, it covers the full detection surface:

| Scenario | mmWave | Desk IMU | Correct State |
|---|---|---|---|
| Student sitting and typing | ✓ Detected | ✓ Detected | Occupied |
| Student sitting still, reading | ✓ Detected | ✗ Missed | Occupied (mmWave saves it) |
| Student standing at desk briefly | ✓ Detected | ✓ Detected | Occupied |
| Bag on chair, stuff on desk, nobody there | ✗ No micro-motion | ✗ No vibration | Hoarded |
| Empty seat | ✗ Nothing | ✗ Nothing | Vacant |

### SCD40 — CO₂ Sensor (~$10–15)

Detects **CO₂ concentration** in the immediate vicinity of the seat. A person breathing raises local CO₂ levels above the ambient baseline (~400 ppm); an abandoned bag does not. This is the strongest differentiator between a **hoarded** seat (flat CO₂, baseline) and a truly **occupied** seat (rising CO₂).

The **CO₂ delta** (rate of change over 30 seconds) is used as a key feature in the XGBoost classifier — a flat or falling delta alongside no mmWave micro-motion is a high-confidence hoarding signal.

### RFID Reader — Identity & Presence Confirmation (~$1–3)

When a student arrives at their seat, they tap their student ID card on the RFID reader to confirm their presence. The seat is then marked **Occupied** and bound to that specific student's ID.

If a student needs to leave temporarily, they must **reserve the seat via the app**. If they exceed the reservation window (30 minutes), the seat is flagged and library staff are notified. Staff can return the student's belongings once the student presents their ID card.

If a student leaves belongings without ever tapping their ID — a **Ghost Occupied** state — the system prompts for an ID tap. Without a tap within 10 minutes, the seat escalates directly to Flagged.

### RGB LED (~$0.30) — Ambient Status Light

A single RGB LED at each seat. It is **off during normal operation** — it does not indicate vacant or occupied status (the dashboard handles that). It **only activates when the system requires student or staff attention**, serving two purposes:

1. **Returning student**: A clear physical signal at the seat that action is needed (tap ID or the seat will be flagged)
2. **Library staff**: A visual marker visible from across the room — staff can scan a floor and instantly spot lit-up seats without checking the dashboard

| Color | Meaning |
|---|---|
| Green        | Occupied (normal) |
|  White pulse | Awaiting RFID tap (Ghost Occupied) |
|  Blue steady | Reserved — student away, timer running |
|  Amber steady | Suspected Hoarding — student should tap ID |
|  Red flashing | Confirmed Hoarding — staff notified |

## Seat State Logic & Workflow

### Normal Operation (LED off)

1. **Student arrives** at an empty seat and sits down
2. mmWave detects presence → server marks seat as **Occupied**
3. Student taps their ID on the RFID reader → session is bound to their student ID
4. Student studies — mmWave, IMU, and SCD40 continuously confirm presence
5. **Student leaves** - tap card again and takes all belongings → sensors clear → seat returns to **Vacant**

### Leaving Temporarily — Reservation Mode

1. Student reserve seat on phone/pc (similar to writing a note now) → seat enters **Reserved**, 30-minute countdown starts
2. Student receives a push notification at **T−5 minutes** as a warning
3. Student may **extend once (+15 min)** via the app
4. If student returns and taps ID → timer cancels, seat returns to **Occupied**
5. If mmWave + CO₂ confirm the student has returned (person detected, CO₂ rising) → seat auto-resumes

### Hoarding Detection & Escalation

1. mmWave detects no micro-motion, IMU detects no vibration, and CO₂ remains at baseline for **30 minutes** while the seat was previously Occupied and no reservation was made
2. Server flags seat as **Suspected Hoarding** → LED turns amber
3. **Student returns and taps ID** → LED off, seat returns to Occupied, timer resets
4. **No tap within 5 minutes** → escalates to **Confirmed Hoarding** → LED flashes red, staff app receives alert with seat location and timestamp
5. Staff collects belongings; student reclaims by tapping their ID at any RFID terminal

### Ghost Occupied Handling

1. Sensors detect possible belongings (no mmWave micro-motion, no IMU activity, flat CO₂) but student did not reserve seat in app
2. LED pulses white — seat prompts: _"Tap your ID to claim this seat"_
3. Send notification to student app: _"We detected belongings at a seat. Please tap your ID at the seat to confirm your reservation or the seat will be flagged in 10 minutes."_
3. No tap within **10 minutes** → escalates directly to Flagged

### State Summary

| State | LED | Dashboard | How to Resolve |
|---|---|---|---|
| Vacant | Off | 🟢 Available | Student sits down |
| Occupied | 🟢 Green | 🔴 Occupied | -- |
| Reserved | 🔵 Blue steady | 🔵 Away (timer shown) | Student returns & taps ID |
| Suspected Hoarding | 🟡 Amber steady | 🟡 Verify | Student taps ID within 5 min |
| Confirmed Hoarding | 🔴 Red flashing | 🔴 Flagged — staff alerted | Staff resets remotely or on-site |
| Ghost Occupied | ⚪ White pulse | ⚠️ Unregistered | Student taps ID within 10 min |

## Software Stack

| Layer | Technology | Purpose |
|---|---|---|
| Firmware | Arduino / MicroPython on ESP32 | Read sensors, control LED/RFID, POST events to server |
| Backend | Python Flask + APScheduler | Seat state machine, reservation timers, XGBoost inference |
| ML Model | XGBoost | Sensor fusion classifier (mmWave + IMU + CO₂) |
| Real-time updates | Socket.IO | Push seat state changes to dashboard and app instantly |
| Notifications | Firebase Cloud Messaging (FCM) | Push alerts to student and staff mobile apps |
| Frontend | HTML / CSS / JS | Live floor map dashboard; student reservation app |

## Estimated Per-Seat Bill of Materials

| Component | Estimated Cost |
|---|---|
| ESP32 DevKit V1 (WROOM-32) | $4–6 |
| MPU6050 IMU | $1–2 |
| mmWave Radar Sensor | $3–6 |
| SCD40 CO₂ Sensor | $10–15 |
| RFID Reader (RC522) | $1–3 |
| WS2812B RGB LED | $0.30 |
| Wiring & Enclosure | $2–3 |
| **Total per seat** | **~$21–35** |

## Physical Setup

The sensor node (ESP32 + RFID reader + RGB LED) sits in a small enclosure on the desk surface, accessible to the student. The MPU6050 is adhered to the **underside of the desk**. The mmWave radar and SCD40 are mounted in the enclosure facing the seat area. All wiring runs along the desk leg into the enclosure.

## Innovation & Design Rationale

### Study time tracking

Student can check how many hours they spent studying at the library. This feature may also be added to some study tracking app for UST students in the future.
The school may also use the data to analyze studying time for different majors.

### Privacy-First by Design

No cameras. No images. No video. No visual data is captured, stored, or transmitted at any point — a significant advantage over YOLOv8 or thermal camera systems in a library setting where students expect privacy.

### No Vision-Based Training Data Required

The mmWave + IMU + CO₂ sensor fusion operates on **measurable physical signals** — micro-motion, vibration, and gas concentration — rather than visual patterns. The XGBoost classifier is trained on simple labeled sensor readings, not hours of annotated video footage.

### Why Not Single-Sensor Alternatives?

| Sensor | Limitation |
|---|---|
| mmWave alone | Detects presence but cannot distinguish a still bag from a still person without CO₂ confirmation |
| CO₂ alone | Slow response time; affected by room ventilation and neighbouring seats |
| IMU alone | Misses a completely still, seated student |
| Camera + CV | Privacy concerns; requires GPU inference; needs large labeled dataset |

The **mmWave + IMU + SCD40 fusion** addresses all of these limitations while remaining low-cost, privacy-safe, and deployable on standard library furniture.

