// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
#include <cstring>
constexpr int MBEDTLS_MD_SHA256 = 1;
inline int algorithm = 1;
inline const int *mbedtls_md_info_from_type(int type) {
  assert(type == 1);
  return &algorithm;
}
inline int mbedtls_md_hmac(const int *info, const unsigned char *key,
                           size_t key_size, const unsigned char *data,
                           size_t size, unsigned char *digest) {
  assert(*info == 1 && key_size == 32 &&
         std::memcmp(key, "fake-secret-byte-array-1234567890", 32) == 0);
  assert(size > 32 && data[0] == 1);
  std::memset(digest, 0, 32);
  return 0;
}
