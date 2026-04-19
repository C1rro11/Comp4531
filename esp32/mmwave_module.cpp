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

bool readMMWaveData(mmwaveStruct &mmwaveData) {
  uint8_t buf[64];
  if (!mmwave.readFrame(buf)) {
    Serial.println("No valid mmWave frame received.");
    return false;
  }

  mmwaveData.detection = buf[6];
  mmwaveData.distance = buf[7] | (buf[8] << 8);
  for (int i = 0; i < 16; i++) {
    mmwaveData.gateEnergy[i] = (buf[9 + i * 2]) | (buf[10 + i * 2] << 8);
  }
  return true;
}
