// SPDX-License-Identifier: GPL-3.0-or-later
#include "event_codec.h"

#include "mbedtls/platform_util.h"
#include <cstring>

namespace esphome {
namespace assist_live {

const char *stage_name(Stage stage) {
  switch (stage) {
  case Stage::WAKE_DETECTED:
    return "wake_detected";
  case Stage::MIC_OPEN:
    return "mic_open";
  case Stage::PLAYBACK_START:
    return "playback_start";
  case Stage::PLAYBACK_END:
    return "playback_end";
  default:
    return "";
  }
}

static void integer(std::string &output, uint64_t value, size_t size) {
  for (size_t i = size; i > 0; --i)
    output.push_back(static_cast<char>(value >> ((i - 1) * 8)));
}

static void field(std::string &output, const std::string &value) {
  integer(output, value.size(), 4);
  output += value;
}

std::string canonical_event(const std::string &device, const Event &event) {
  if (device.empty() || device.size() > 128 ||
      std::strlen(stage_name(event.stage)) == 0 ||
      std::memchr(event.data, '\0', sizeof(event.data)) == nullptr)
    return {};
  for (char c : device)
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '-' || c == '_'))
      return {};
  std::string output(1, '\x01');
  field(output, device);
  integer(output, event.boot, 8);
  integer(output, event.seq, 8);
  integer(output, event.device_ms, 8);
  field(output, stage_name(event.stage));
  field(output, event.data);
  return output;
}

std::string encode_event(const std::string &device, const Event &event,
                         const uint8_t *key, size_t key_size, Hmac hmac) {
  const auto canonical = canonical_event(device, event);
  if (canonical.empty() || key_size == 0)
    return {};
  uint8_t digest[32]{};
  if (!hmac(key, key_size, reinterpret_cast<const uint8_t *>(canonical.data()),
            canonical.size(), digest)) {
    mbedtls_platform_zeroize(digest, sizeof(digest));
    return {};
  }
  static const char HEX[] = "0123456789abcdef";
  std::string tag;
  tag.reserve(64);
  for (auto byte : digest) {
    tag += HEX[byte >> 4];
    tag += HEX[byte & 15];
  }
  mbedtls_platform_zeroize(digest, sizeof(digest));
  return "{\"version\":1,\"device\":\"" + device +
         "\",\"boot\":" + std::to_string(event.boot) +
         ",\"seq\":" + std::to_string(event.seq) +
         ",\"device_ms\":" + std::to_string(event.device_ms) + ",\"stage\":\"" +
         stage_name(event.stage) + "\",\"data\":" + event.data + ",\"tag\":\"" +
         tag + "\"}";
}

} // namespace assist_live
} // namespace esphome
