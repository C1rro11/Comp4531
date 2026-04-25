#ifndef LED_MODULE_H
#define LED_MODULE_H

#include "config.h"
#include <Arduino.h>

enum LEDState { OFF, ON, BLINK };
enum LEDColor { WHITE, RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA };

void initLEDs() {
  pinMode(RED_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BLUE_LED, OUTPUT);
  digitalWrite(RED_LED, LOW);
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(BLUE_LED, LOW);
}

// Helper: write a color to the pins
void applyColor(LEDColor color) {
  // Format: R, G, B  (HIGH = on for common cathode)
  switch (color) {
  case WHITE:
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(BLUE_LED, HIGH);
    break;
  case RED:
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(BLUE_LED, LOW);
    break;
  case GREEN:
    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(BLUE_LED, LOW);
    break;
  case BLUE:
    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(BLUE_LED, HIGH);
    break;
  case YELLOW:
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(BLUE_LED, LOW);
    break;
  case CYAN:
    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(BLUE_LED, HIGH);
    break;
  case MAGENTA:
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(BLUE_LED, HIGH);
    break;
  }
}

void setLEDState(LEDState state, LEDColor color = WHITE) {
  switch (state) {
  case OFF:
    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(BLUE_LED, LOW);
    break;

  case ON:
    applyColor(color);
    break;

  case BLINK: {
    static unsigned long lastToggle = 0;
    static bool isOn = false;
    unsigned long currentMillis = millis();

    if (currentMillis - lastToggle >= 500) {
      lastToggle = currentMillis;
      isOn = !isOn;
      if (isOn)
        applyColor(color);
      else {
        digitalWrite(RED_LED, LOW);
        digitalWrite(GREEN_LED, LOW);
        digitalWrite(BLUE_LED, LOW);
      }
    }
    break;
  }
  }
}
#endif
