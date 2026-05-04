#ifndef CONFIG_H
#define CONFIG_H

// WiFi
#define WIFI_SSID "COMP4531 demo"
#define WIFI_PASS "comp4531demo"

#define SERVER_IP "172.22.190.112"
#define SERVER_PORT "5000"
#define SERVER_URL "http://" SERVER_IP ":" SERVER_PORT
// Weight sensor pins
#define FSR_PIN 4

#define FSR_URL SERVER_URL "/seat_state"
#endif
