// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
using esp_transport_handle_t = int *;
inline int tcp_handle = 1;
inline int test_connect_result = -1;
inline int fail_tcp_attempts = 0, test_tcp_calls = 0;
inline esp_transport_handle_t esp_transport_tcp_init() {
  ++test_tcp_calls;
  if (fail_tcp_attempts > 0) {
    --fail_tcp_attempts;
    return nullptr;
  }
  return &tcp_handle;
}
inline int esp_transport_destroy(esp_transport_handle_t) { return 0; }
inline int esp_transport_close(esp_transport_handle_t) { return 0; }
inline int esp_transport_connect(esp_transport_handle_t, const char *, int,
                                 int timeout) {
  assert(timeout <= 250);
  return test_connect_result;
}
