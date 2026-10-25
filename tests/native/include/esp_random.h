// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
#include <cstdint>
#include <cstring>
inline uint64_t random_boot = 0x0102030405060708;
inline void esp_fill_random(void *buffer, size_t size) {
  assert(size == 8);
  std::memcpy(buffer, &random_boot, size);
  ++random_boot;
}
