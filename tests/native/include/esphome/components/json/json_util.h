// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <ArduinoJson.h>
namespace esphome {
namespace json {
inline JsonDocument parse_json(const uint8_t *data, size_t size) {
  JsonDocument document;
  if (deserializeJson(document, data, size))
    document.clear();
  return document;
}
} // namespace json
} // namespace esphome
