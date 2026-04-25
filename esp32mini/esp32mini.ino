#include "network_module.h"
#include "config.h"

bool isSeatOccupied = false;

bool getSeatState() {
  return digitalRead(FSR_PIN) == LOW; // LOW means occupied
}

void sendSeatState(){
  isSeatOccupied = getSeatState();
  sendSeatStateToServer(isSeatOccupied ? "seatOccupied" : "empty");
}

void setup() {
  Serial.begin(115200);
  delay(1000); // Wait for serial to initialize
  initWiFi();
  pinMode(FSR_PIN, INPUT_PULLUP); 
  sendSeatState();
}


void loop() {
  bool currentState = getSeatState();
  if (currentState != isSeatOccupied) {
    sendSeatState();
  }
  Serial.println(digitalRead(FSR_PIN));
  delay(1000);
  
}
