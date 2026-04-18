#include "mmwave_module.h"
#include "config.h"
#include "mmwaveSensor.h"

mmWaveSensor mmwave(Serial2, Serial);
void initMMWave() {
  Serial.println("Initializing mmWave Sensor...");
  Serial2.begin(115200, SERIAL_8N1, mmWave_Rx, mmWave_Tx);
  mmwave.begin() ? Serial.println("mmWave Sensor initialized successfully!")
                 : Serial.println("Failed to initialize mmWave Sensor.");
}

void mmwaveDebug() { mmwave.debugPrintIncoming(); }
