#ifndef NETWORK_MODULE_H
#define NETWORK_MODULE_H

#include <Arduino.h>
#include <cstdint>

void initWiFi();
void sendSeatStateToServer(String seatState);

#endif
