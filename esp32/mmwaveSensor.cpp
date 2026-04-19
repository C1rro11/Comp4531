#include "mmwaveSensor.h"
#include <cstdint>

mmWaveSensor::mmWaveSensor(Stream &dataStream, Stream &debugStream)
    : _dataPtr(&dataStream), _debugPtr(&debugStream) {}

bool mmWaveSensor::begin() { return _enableReportMode(); }

void mmWaveSensor::_writeLE(uint32_t value, size_t byteCount, uint8_t *buffer,
                            size_t &idx) {
  for (uint8_t i = 0; i < byteCount; i++) {
    buffer[idx++] = (value >> (i * 8)) & 0xFF;
  }
}

void mmWaveSensor::_writeBytes(const uint8_t *value, size_t valueLen,
                               uint8_t *buffer, size_t &idx) {
  for (size_t i = 0; i < valueLen; i++) {
    buffer[idx++] = value[i];
  }
}

bool mmWaveSensor::_enableReportMode() {
  RaderCommand command = RaderCommand::SET_MODE;
  RaderMode mode = RaderMode::REPORT;
  Arg arg = Arg::Distance;
  return _sendCommand(static_cast<uint16_t>(command),
                      static_cast<uint32_t>(arg), 2,
                      static_cast<uint32_t>(mode), 4);
}

bool mmWaveSensor::_sendCommand(uint16_t command, const uint32_t arg,
                                size_t argSize, const uint32_t payload,
                                size_t payloadSize) {
  if (!_dataPtr)
    return false;
  const uint8_t header[] = {0xFD, 0xFC, 0xFB, 0xFA};
  const uint8_t tail[] = {0x04, 0x03, 0x02, 0x01};

  uint16_t length = payloadSize + argSize + COMMANDSIZE;
  uint8_t buffer[64];
  size_t idx = 0;

  _writeBytes(header, sizeof(header), buffer, idx);
  _writeLE(length, 2, buffer, idx);
  _writeLE(command, COMMANDSIZE, buffer, idx);

  if (argSize > 0) {
    _writeLE(arg, argSize, buffer, idx);
  }

  if (payloadSize > 0) {
    _writeLE(payload, payloadSize, buffer, idx);
  }
  _writeBytes(tail, sizeof(tail), buffer, idx);
  _debugPtr->print("Sending: ");
  for (size_t i = 0; i < idx; i++) {
    _debugPtr->print(buffer[i], HEX);
    _debugPtr->print(' ');
  }
  return _dataPtr->write(buffer, idx) == idx;
}

bool mmWaveSensor::readFrame(uint8_t *outBuf) {
  while (_dataPtr->available() > 0) {
    // Maybe add timeout reset logic here if needed
    uint8_t byte = _dataPtr->read();
    if (!_frameIdx) {
      if (byte == static_cast<uint8_t>(RaderCommand::HEADER_BYTE)) {
        _frameBuffer[_frameIdx++] = byte;
      }
      continue;
    }
    _frameBuffer[_frameIdx++] = byte;
    if (_frameIdx == 45) {
      _frameIdx = 0;
      if (_frameBuffer[41] ==
              static_cast<uint8_t>(RaderCommand::TAIL_BYTE_01) &&
          _frameBuffer[42] ==
              static_cast<uint8_t>(RaderCommand::TAIL_BYTE_02) &&
          _frameBuffer[43] ==
              static_cast<uint8_t>(RaderCommand::TAIL_BYTE_03) &&
          _frameBuffer[44] ==
              static_cast<uint8_t>(RaderCommand::TAIL_BYTE_04)) {
        memcpy(outBuf, _frameBuffer, 45);
        return true;
      }
    }
  }
  return false;
}

void mmWaveSensor::debugPrintIncoming() {
  while (_dataPtr->available() > 0) {
    uint8_t buf[64];
    size_t n = _dataPtr->readBytes(buf, min(64, _dataPtr->available()));

    _debugPtr->print("RX ");
    _debugPtr->print(n);
    _debugPtr->print(" bytes: ");

    for (size_t i = 0; i < n; i++) {
      if (buf[i] < 0x10)
        _debugPtr->print('0');
      _debugPtr->print(buf[i], HEX);
      _debugPtr->print(' ');
    }
    _debugPtr->println();
  }
}
