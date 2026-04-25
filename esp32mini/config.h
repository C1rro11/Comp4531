#ifndef CONFIG_H
#define CONFIG_H

// WiFi
#define WIFI_SSID "NekoCat"
#define WIFI_PASS "waishun2006"

#define SERVER_IP "192.168.31.193"
#define SERVER_PORT "5000"
#define SERVER_URL "http://" SERVER_IP ":" SERVER_PORT
// Weight sensor pins
#define FSR_PIN 4

#define FSR_URL SERVER_URL "/seat_state"
#endif
