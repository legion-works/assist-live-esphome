// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
#include <cstddef>
#include <cstring>
#include <vector>
inline std::vector<size_t> test_zeroized_sizes;
inline void mbedtls_platform_zeroize(void *buffer, size_t size) {
  std::memset(buffer, 0, size);
  auto *bytes = static_cast<unsigned char *>(buffer);
  for (size_t i = 0; i < size; ++i)
    assert(bytes[i] == 0);
  test_zeroized_sizes.push_back(size);
}
