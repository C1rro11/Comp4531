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
    pass
    return "success"


if __name__ == "__main__":
    # host='0.0.0.0' is crucial! It allows the ESP32 to connect over the local network
    # instead of restricting the server to localhost (127.0.0.1) only.
    print("Starting server... Make sure your ESP32 and PC are on the same Wi-Fi.")
    app.run(host="0.0.0.0", port=5000, debug=True)
