#include "nfc_module.h"
#include "config.h"
#include <Wire.h>
#include <Adafruit_PN532.h>

// Create the NFC object only inside this file
Adafruit_PN532 nfc(I2C_SDA, I2C_SCL);

void initNFC() {
  Serial.println("Starting NFC Reader...");
  Wire.begin(I2C_SDA, I2C_SCL);
  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("Didn't find PN53x board");
    while (1) { delay(10); } 
  }
  nfc.SAMConfig();
  Serial.println("NFC Sensor is ready!");
}

String readNFCCard() {
  uint8_t success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };
  uint8_t uidLength;

  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength);

  if (success) {
    String uidString = "";
    for (uint8_t i = 0; i < uidLength; i++) {
      if (uid[i] < 0x10) uidString += "0";
      uidString += String(uid[i], HEX);
    }
    uidString.toUpperCase();
    return uidString; // Return the formatted UID
  }
  
  return ""; // Return empty string if no card found
}