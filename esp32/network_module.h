#ifndef NETWORK_MODULE_H
#define NETWORK_MODULE_H

#include <Arduino.h>
#include <cstdint>

void initWiFi();
void sendNFCUIDToServer(String uid);
void sendSDC40DataToServer(uint16_t &co2, float &temperature, float &humidity);

#endif
