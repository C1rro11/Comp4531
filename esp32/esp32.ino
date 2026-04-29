#include "config.h"
#include "nfc_module.h"
#include "mmwave_module.h"
#include "network_module.h"
#include "sdc40_module.h"
#include "LED_module.h"

String lastCardUid = "";
bool cardRegistered = false;
void nfcTask(void* param) {
  for (;;) {
    String cardUID = readNFCCard();

    if (cardUID == "") {
      vTaskDelay(pdMS_TO_TICKS(50));
      continue;
    }

    Serial.println("Read Card UID: " + cardUID);

    // New card, nobody logged in → register
    if (cardUID != lastCardUid && !cardRegistered) {
      Serial.println("Found Card: " + cardUID);
      sendNFCUIDToServer(cardUID);
      lastCardUid = cardUID;
      cardRegistered = true;
      setLEDState(ON, GREEN);
      vTaskDelay(pdMS_TO_TICKS(1000)); // debounce: ignore reads for 1s
    }

    // Same card again → logout
    else if (cardUID == lastCardUid && cardRegistered) {
      Serial.println("Logged out: " + lastCardUid);
      lastCardUid = "";
      cardRegistered = false;
      setLEDState(ON, WHITE);
      vTaskDelay(pdMS_TO_TICKS(1000)); // debounce
    }

    // Different card, someone already logged in → reject
    else if (cardUID != lastCardUid && cardRegistered) {
      Serial.println("Wrong person: " + cardUID);
      setLEDState(ON, RED);
      vTaskDelay(pdMS_TO_TICKS(1000));
      setLEDState(ON, GREEN);       // restore logged-in state
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println("Starting ESP32v2 System...");
  initLEDs();
  setLEDState(BLINK, YELLOW);
  initMMWave();
  delay(100);
  initSDC40();
  initWiFi();
  initNFC();
  // Core 0, stack 4096, priority 1
  xTaskCreatePinnedToCore(nfcTask, "NFCTask", 4096, NULL, 1, NULL, 0);
  setLEDState(ON, WHITE);

}

bool firstLoop = true;
unsigned long lastMMWave = 0;
unsigned long lastSDC40  = 0;

void loop() {
  unsigned long now = millis();

  if (now - lastMMWave >= 1000) {
    lastMMWave = now;
    mmwaveStruct mmwaveData;
    if (readMMWaveData(mmwaveData)) {
      sendMmwaveDataToServer(mmwaveData);
    }
  }

  if (now - lastSDC40 >= 5000) {
    if (firstLoop) {
      firstLoop = false;
      lastSDC40 = now;
    }
    else {
      lastSDC40 = now;
      uint16_t co2; float temperature, humidity;
      readSDC40(co2, temperature, humidity);
      sendSDC40DataToServer(co2, temperature, humidity);
    }
  }
}
