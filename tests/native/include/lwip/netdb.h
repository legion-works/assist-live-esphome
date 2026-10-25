// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <netdb.h>
inline int test_dns_calls = 0;
inline int test_getaddrinfo(const char *, const char *, const addrinfo *,
                            addrinfo **) {
  ++test_dns_calls;
  return EAI_AGAIN;
}
inline void test_freeaddrinfo(addrinfo *) {}
#define getaddrinfo test_getaddrinfo
#define freeaddrinfo test_freeaddrinfo
