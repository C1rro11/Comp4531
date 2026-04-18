#include "sdc40_module.h"
#include "config.h"

SensirionI2cScd4x scd4x;

void initSDC40() {
  Serial.println("Starting SCD40 Sensor...");
  Wire.begin(I2C_SDA, I2C_SCL);
  scd4x.begin(Wire, 0x62);
  scd4x.startPeriodicMeasurement();
  Serial.println("SCD40 Sensor is ready!");
}

void readSDC40() {
  bool dataReady = false;
  scd4x.getDataReadyStatus(dataReady);

  if (!dataReady) {
    Serial.println("SCD40 data not ready");
    return;
  }

  uint16_t co2;
  float temperature, humidity;

  uint16_t error = scd4x.readMeasurement(co2, temperature, humidity);
  if (error) {
    Serial.println("SCD40 read error");
    return;
  }

  Serial.print("CO2: ");
  Serial.print(co2);
  Serial.println(" ppm");
  Serial.print("Temp: ");
  Serial.print(temperature);
  Serial.println(" °C");
  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");
}
