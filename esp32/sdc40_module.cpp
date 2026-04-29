#include "sdc40_module.h"
#include "config.h"
#include <cstddef>
#include <cstdint>
#include <sys/types.h>

TwoWire scd40Wire = TwoWire(1);
SensirionI2cScd4x scd4x;

void initSDC40() {
  Serial.println("Starting SCD40 Sensor...");
  scd40Wire.begin(I2C_SDA_2, I2C_SCL_2);
  scd4x.begin(scd40Wire, 0x62);
  scd4x.stopPeriodicMeasurement();
  delay(500);
  scd4x.startPeriodicMeasurement();
  uint16_t x;
  float y, z;
  scd4x.readMeasurement(x, y, z); // discard first reading
  Serial.println("SCD40 Sensor is ready!");
}

void readSDC40(uint16_t &co2, float &temperature, float &humidity) {
  bool dataReady = false;
  scd4x.getDataReadyStatus(dataReady);

  if (!dataReady) {
    Serial.println("SCD40 data not ready");
    return;
  }

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
