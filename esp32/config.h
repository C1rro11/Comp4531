#ifndef CONFIG_H
#define CONFIG_H

// WiFi
#define WIFI_SSID "Fatboy"
#define WIFI_PASS "92511265"

// Flask server ( NFC )
#define SERVER_URL "http://192.168.31.193:5000/nfc"

// NFC Pins (N16R8)
#define I2C_SDA 5
#define I2C_SCL 4

// mmWave Pins
#define mmWave_Tx 9
#define mmWave_Rx 10
// threshold
#define THRESHOLD 75
#endif
