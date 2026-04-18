#ifndef mmwaveSensor_h
#define mmwaveSensor_h

#include <Arduino.h>
#include <cstdint>

class mmWaveSensor {
public:
  mmWaveSensor(Stream &dataStream, Stream &debugStream);

  bool begin();
  bool readFirmwareVersion();
  bool readSerialNumber();
  void debugPrintIncoming();

private:
  enum class RaderCommand : uint8_t {
    READ_FIRMWARE_VERSION = 0x00,
    READ_SERIAL_NUMBER = 0x11,
    SET_MODE = 0x12,

    // Add more commands as needed
  };

  enum class Arg : uint8_t {
    Distance = 0x00,
  };

  enum class RaderMode : uint8_t {
    REPORT = 0x04,
  };
  const int COMMANDSIZE = 2;

  Stream *_dataPtr = nullptr;
  Stream *_debugPtr = nullptr;

  bool _enableReportMode();
  bool _sendCommand(uint16_t command, const uint32_t arg, size_t argSize,
                    const uint32_t payload, size_t payloadSize);

  void _writeLE(uint32_t value, size_t byteCount, uint8_t *buffer, size_t &idx);
  void _writeBytes(const uint8_t *value, size_t valueLen, uint8_t *buffer,
                   size_t &idx);
  void _readFrame();
};

#endif
