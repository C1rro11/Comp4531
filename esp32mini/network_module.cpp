#include "network_module.h"
#include "config.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <cstdint>

void initWiFi() {
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi connected! IP: ");
  Serial.println(WiFi.localIP());
}

void sendSeatStateToServer(String seatState) {
  HTTPClient http;
  http.begin(FSR_URL);
  http.addHeader("Content-Type", "application/json");
  JsonDocument doc;
  String jsonString;
  doc["seatState"] = seatState;
  serializeJson(doc, jsonString);
  serializeJson(doc, Serial);
  Serial.println();

  int httpResponseCode = http.POST(jsonString);
  if (httpResponseCode > 0) {
    Serial.println("Server replied: " + http.getString());
  } else {
    Serial.println("Error sending POST");
  }
  http.end();
}
