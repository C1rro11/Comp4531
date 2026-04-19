#ifndef MMWAVE_MODULE_H
#define MMWAVE_MODULE_H
#include <Arduino.h>

struct mmwaveStruct {
  uint8_t detection;
  uint16_t distance;
  uint16_t gateEnergy[16];
};
void initMMWave();
void mmwaveDebug();
bool readMMWaveData(mmwaveStruct &mmwaveData);

#endif
