#ifndef SDC40_MODULE_H
#define SDC40_MODULE_H

#include <Arduino.h>
#include <SensirionI2cScd4x.h>
#include <Wire.h>
#include <cstdint>

void initSDC40();
void readSDC40(uint16_t &co2, float &temperature, float &humidity);
#endif
