// SPDX-License-Identifier: GPL-3.0-or-later
#include "event_codec.h"
#include <cassert>
#include <cstring>
#include <iostream>

using namespace esphome::assist_live;
static std::string expected_key, expected_body, expected_digest;

static std::string unhex(const std::string &text) {
  std::string result;
  for (size_t i = 0; i < text.size(); i += 2)
    result += static_cast<char>(std::stoul(text.substr(i, 2), nullptr, 16));
  return result;
}

static bool hmac_oracle(const uint8_t *key, size_t key_size,
                        const uint8_t *body, size_t body_size,
                        uint8_t *digest) {
  assert(std::string(reinterpret_cast<const char *>(key), key_size) ==
         expected_key);
  assert(std::string(reinterpret_cast<const char *>(body), body_size) ==
         expected_body);
  std::memcpy(digest, expected_digest.data(), 32);
  return true;
}

int main(int argc, char **argv) {
  assert(argc == 11);
  expected_key = unhex(argv[1]);
  expected_body = unhex(argv[2]);
  expected_digest = unhex(argv[3]);
  Event event{};
  event.boot = std::stoull(argv[5]);
  event.seq = std::stoull(argv[6]);
  event.device_ms = std::stoull(argv[7]);
  bool found = false;
  for (int i = 0; i < 4; ++i) {
    if (std::string(stage_name(static_cast<Stage>(i))) == argv[8]) {
      event.stage = static_cast<Stage>(i);
      found = true;
    }
  }
  assert(found);
  const auto data = unhex(argv[9]);
  assert(data.size() <= 256);
  std::strcpy(event.data, data.c_str());
  assert(canonical_event(argv[4], event) == expected_body);
  auto wire = encode_event(
      argv[4], event, reinterpret_cast<const uint8_t *>(expected_key.data()),
      expected_key.size(), hmac_oracle);
  assert(wire == unhex(argv[10]));
  std::cout << wire << '\n';
}
