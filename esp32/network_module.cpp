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

void sendNFCUIDToServer(String uid) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(NFC_SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    JsonDocument doc;
    String jsonString;
    doc["uid"] = uid;
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
}

void sendSDC40DataToServer(uint16_t &co2, float &temperature, float &humidity) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SDC_SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    JsonDocument doc;
    String jsonString;
    doc["co2"] = co2;
    doc["temperature"] = temperature;
    doc["humidity"] = humidity;
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
}

void sendMmwaveDataToServer(mmwaveStruct &mmwaveData) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected");
    return;
  }

  WiFiClient client;
  client.setTimeout(2000);

  HTTPClient http;
  http.setConnectTimeout(2000);
  http.setTimeout(2000);

  if (!http.begin(client, MMWAVE_SERVER_URL)) {
    Serial.println("http.begin failed");
    return;
  }

  http.addHeader("Content-Type", "application/json");

  JsonDocument doc;
  String jsonString;

  doc["detection"] = mmwaveData.detection;
  doc["distance"] = mmwaveData.distance;
  JsonArray energyArray = doc["energyArray"].to<JsonArray>();
  for (int i = 0; i < 16; i++) {
    energyArray.add(mmwaveData.gateEnergy[i]);
  }

  serializeJson(doc, jsonString);

  Serial.print("POST body: ");
  Serial.println(jsonString);
  Serial.println("before POST");

  int httpResponseCode = http.POST(jsonString);

  Serial.print("after POST, code = ");
  Serial.println(httpResponseCode);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.print("Server replied: ");
    Serial.println(response);
  } else {
    Serial.print("POST failed: ");
    Serial.println(http.errorToString(httpResponseCode));
  }

  http.end();
}
