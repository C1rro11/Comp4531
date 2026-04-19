#include "config.h"
#include "nfc_module.h"
#include "mmwave_module.h"
#include "network_module.h"
#include "sdc40_module.h"


void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println("Starting ESP32 System...");
  initMMWave();
  delay(100);
  initSDC40();
  initWiFi();

  //initNFC();
}

void loop() {
  mmwaveStruct mmwaveData;
  if(readMMWaveData(mmwaveData)) {
    Serial.print("Detection: "); Serial.print(mmwaveData.detection);
    Serial.print(", Distance: "); Serial.print(mmwaveData.distance);
    Serial.print(", Gate Energy: ");
    for (int i = 0; i < 16; i++) {
      Serial.print(mmwaveData.gateEnergy[i]);
      if (i < 15) Serial.print(" ");
    }
    Serial.println();
  }
  delay(1000);
  
  //mmwaveDebug();
  // delay(100);
  //uint16_t co2; float temperature, humidity;
  //readSDC40(co2, temperature, humidity);
  //sendSDC40DataToServer(co2, temperature, humidity);
  //delay(5000); // Read every 5 seconds
  
  /***
  // 1. Check for a card
  String cardUID = readNFCCard();

  // 2. If a card was found, process it
  if (cardUID != "") {
    Serial.println("Found Card: " + cardUID);
    
    // Send it to the server
    sendNFCUIDToServer(cardUID);
    
    // Wait so we don't spam the server
    delay(2000); 
  } else {
    // Keep ESP32 stable while waiting
    delay(50); 
  }
  ***/
}
