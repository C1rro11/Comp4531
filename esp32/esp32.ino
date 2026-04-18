#include "config.h"
#include "nfc_module.h"
#include "mmwave_module.h"
#include "network_module.h"
#include "sdc40_module.h"


void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println("Starting ESP32 System...");
  //initMMWave();
  //mmwaveDebug();
  initSDC40();
  initWiFi();

  //initNFC();
}

void loop() {
  //mmwaveDebug();
  // delay(100);
  readSDC40();
  delay(5000); // Read every 5 seconds
  
  /***
  // 1. Check for a card
  String cardUID = readNFCCard();

  // 2. If a card was found, process it
  if (cardUID != "") {
    Serial.println("Found Card: " + cardUID);
    
    // Send it to the server
    sendUIDToServer(cardUID);
    
    // Wait so we don't spam the server
    delay(2000); 
  } else {
    // Keep ESP32 stable while waiting
    delay(50); 
  }
  ***/
}
