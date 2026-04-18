"""
Flask + Socket.IO backend for the Smart Seat Monitoring System.

Endpoints
---------
POST /api/sensor-data    – accept a list of sensor payloads from ESP32 / simulator
GET  /api/seats          – return current state of all seats
POST /api/reserve        – student reserves their seat   {seat_id, student_id, duration_s}
POST /api/staff-reset    – staff force-resets a seat      {seat_id}
POST /nfc                – legacy endpoint for ESP32 NFC  {uid}

Socket.IO (namespace /seats)
    event: seat_update   – emitted on every state change
"""

from __future__ import annotations

import time

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

from config import HOST, PORT, SEAT_IDS
from seat_state import SeatStateMachine

# ── App init ─────────────────────────────────────────────────────

app = Flask(
    __name__,
    static_folder="../static",
    template_folder="../static",
)
app.config["SECRET_KEY"] = "dev-secret-change-in-prod"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# One state machine per seat
seats: dict[str, SeatStateMachine] = {
    sid: SeatStateMachine(sid) for sid in SEAT_IDS
}

# ── REST endpoints ───────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/seats", methods=["GET"])
def get_seats():
    return jsonify([s.snapshot() for s in seats.values()])


@app.route("/api/sensor-data", methods=["POST"])
def receive_sensor_data():
    """Accept a JSON list of sensor payloads."""
    payloads = request.get_json(force=True)
    if isinstance(payloads, dict):
        payloads = [payloads]

    results = []
    for p in payloads:
        seat_id = p.get("seat_id")
        if seat_id not in seats:
            results.append({"seat_id": seat_id, "error": "unknown seat"})
            continue
        result = seats[seat_id].update(p)
        results.append(result)
        if result.get("changed"):
            socketio.emit("seat_update", result, namespace="/seats")

    return jsonify(results)


@app.route("/api/reserve", methods=["POST"])
def reserve_seat():
    data = request.get_json(force=True)
    seat_id = data.get("seat_id")
    student_id = data.get("student_id")
    duration_s = data.get("duration_s")
    if seat_id not in seats:
        return jsonify({"error": "unknown seat"}), 404
    result = seats[seat_id].reserve(student_id, duration_s)
    if result.get("changed"):
        socketio.emit("seat_update", result, namespace="/seats")
    return jsonify(result)


@app.route("/api/staff-reset", methods=["POST"])
def staff_reset():
    data = request.get_json(force=True)
    seat_id = data.get("seat_id")
    if seat_id not in seats:
        return jsonify({"error": "unknown seat"}), 404
    result = seats[seat_id].staff_reset()
    if result.get("changed"):
        socketio.emit("seat_update", result, namespace="/seats")
    return jsonify(result)


# Legacy NFC endpoint (kept for ESP32 compatibility)
@app.route("/nfc", methods=["POST"])
def receive_nfc():
    data = request.get_json()
    if data and "uid" in data:
        uid = data["uid"]
        print(f"[NFC] Received UID: {uid}")
        return jsonify({"status": "success", "message": f"UID {uid} received"}), 200
    return jsonify({"status": "error", "message": "No UID provided"}), 400


# ── Socket.IO events ────────────────────────────────────────────

@socketio.on("connect", namespace="/seats")
def on_connect():
    """Send full seat state on new client connection."""
    for s in seats.values():
        socketio.emit("seat_update", s.snapshot(), namespace="/seats")


# ── Background task: periodic escalation check ──────────────────

def escalation_checker():
    """Run every second to catch timer-based state transitions."""
    while True:
        socketio.sleep(1)
        for s in seats.values():
            old_state = s.state
            # Feed an empty-ish payload just to trigger escalation checks
            result = s.update({
                "seat_id": s.seat_id,
                "mmwave_presence": False,
                "mmwave_motion_energy": 0,
                "imu_vibration": 0,
                "co2_ppm": 420,
                "rfid_tap": None,
                "timestamp": time.time(),
            })
            if result.get("changed"):
                socketio.emit("seat_update", result, namespace="/seats")


# ── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Starting Smart Seat server on {HOST}:{PORT}")
    print(f"Seats: {', '.join(SEAT_IDS)}")
    print(f"Dashboard: http://localhost:{PORT}")
    socketio.start_background_task(escalation_checker)
    socketio.run(app, host=HOST, port=PORT, debug=False)
