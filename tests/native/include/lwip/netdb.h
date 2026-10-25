// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <netdb.h>
inline int test_dns_calls = 0;
inline bool test_dns_success = false;
inline int test_getaddrinfo(const char *, const char *, const addrinfo *hints,
                            addrinfo **result) {
  ++test_dns_calls;
  if (test_dns_success)
    return getaddrinfo("192.0.2.1", nullptr, hints, result);
  return EAI_AGAIN;
}
inline void test_freeaddrinfo(addrinfo *result) { freeaddrinfo(result); }
#define getaddrinfo test_getaddrinfo
#define freeaddrinfo test_freeaddrinfo
