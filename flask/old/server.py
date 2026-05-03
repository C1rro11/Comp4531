from flask import Flask, request, jsonify

app = Flask(__name__)


# Check if esp32 can connect to the server
@app.route("/", methods=["GET"])
def index():
    return "ESP32 NFC Flask Server is running!"


# Create a route that listens for POST requests at /nfc
@app.route("/nfc", methods=["POST"])
def receive_nfc():
    try:
        # Get the JSON data sent by the ESP32
        data = request.get_json()

        if data and "uid" in data:
            uid = data["uid"]
            print(f"\n[SUCCESS] Received NFC Card UID: {uid}")

            # You can trigger other PC scripts or database entries here based on the UID

            return jsonify({"status": "success", "message": f"UID {uid} received"}), 200
        else:
            print("Received request, but no 'uid' found in JSON.")
            return jsonify({"status": "error", "message": "No UID provided"}), 400

    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/mmwave", methods=["POST"])
def receive_mmwave():
    try:
        data = request.get_json()
        if data:
            detection = data["detection"]
            distance = data["distance"]
            energyArray = data["energyArray"]
            print(
                f"\n[SUCCESS] Received mmWave Data - Detection: {detection}, Distance: {distance} cm, Energy Array: {energyArray}"
            )
            return jsonify(
                {
                    "status": "success",
                    "message": f"mmWave data received, Distance: {distance} cm",
                }
            ), 200

    except Exception as e:
        print(f"Error processing mmWave request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return "success"


@app.route("/seat_state", methods=["POST"])
def receive_seat_state():
    try:
        data = request.get_json()

        if data:
            seat_state = data["seatState"]
            print(f"\n[SUCCESS] Received Seat State Data - Seat State: {seat_state}")
        return jsonify(
            {"status": "success", "message": f"Seat state {seat_state} received"}
        ), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/sdc40", methods=["POST"])
def receive_sdc():
    try:
        data = request.get_json()

        if data:
            co2 = data["co2"]
            temperature = data["temperature"]
            humidity = data["humidity"]
            print(
                f"\n[SUCCESS] Received SDC Data - CO2: {co2} ppm, Temperature: {temperature} °C, Humidity: {humidity} %"
            )

            return jsonify({"status": "success", "message": "SDC data received"}), 200
        else:
            print(
                "Received SDC request, but missing 'co2', 'temperature', or 'humidity' in JSON."
            )
            return jsonify(
                {
                    "status": "error",
                    "message": "Missing CO2, temperature, or humidity data",
                }
            ), 400
    except Exception as e:
        print(f"Error processing SDC request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # host='0.0.0.0' is crucial! It allows the ESP32 to connect over the local network
    # instead of restricting the server to localhost (127.0.0.1) only.
    print("Starting server... Make sure your ESP32 and PC are on the same Wi-Fi.")
    app.run(host="0.0.0.0", port=5000, debug=True)
