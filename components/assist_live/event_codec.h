// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace esphome {
namespace assist_live {

enum class Stage : uint8_t {
  WAKE_DETECTED,
  MIC_OPEN,
  PLAYBACK_START,
  PLAYBACK_END
};

struct Event {
  uint64_t boot;
  uint64_t seq;
  uint64_t device_ms;
  Stage stage;
  // Code generation supplies compact, sorted JSON. The queue owns this copy.
  char data[257];
};

using Hmac = bool (*)(const uint8_t *, size_t, const uint8_t *, size_t,
                      uint8_t *);

const char *stage_name(Stage stage);
std::string canonical_event(const std::string &device, const Event &event);
std::string encode_event(const std::string &device, const Event &event,
                         const uint8_t *key, size_t key_size, Hmac hmac);

} // namespace assist_live
} // namespace esphome
