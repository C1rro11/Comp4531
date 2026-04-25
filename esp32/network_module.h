#ifndef NETWORK_MODULE_H
#define NETWORK_MODULE_H

#include <Arduino.h>
#include <cstdint>
#include <mmwave_module.h>

void initWiFi();
void sendNFCUIDToServer(String uid);
void sendSDC40DataToServer(uint16_t &co2, float &temperature, float &humidity);
void sendMmwaveDataToServer(mmwaveStruct &mmwaveData);

#endif
