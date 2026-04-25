#ifndef CONFIG_H
#define CONFIG_H

// WiFi
#define WIFI_SSID "NekoCat"
#define WIFI_PASS "waishun2006"

#define SERVER_IP "192.168.31.193"
#define SERVER_PORT "5000"
#define SERVER_URL "http://" SERVER_IP ":" SERVER_PORT
// Flask server ( NFC )
#define NFC_SERVER_URL SERVER_URL "/nfc"
#define SDC_SERVER_URL SERVER_URL "/sdc40"
#define MMWAVE_SERVER_URL SERVER_URL "/mmwave"

// NFC Pins (N16R8)
#define I2C_SDA 5
#define I2C_SCL 4

#define I2C_SDA_2 7
#define I2C_SCL_2 6

// LED Pins
#define RED_LED 19
#define GREEN_LED 20
#define BLUE_LED 21

// mmWave Pins
#define mmwave_Tx 9
#define mmwave_Rx 10

// Weight sensor pins

// threshold
#define THRESHOLD 75
#endif
