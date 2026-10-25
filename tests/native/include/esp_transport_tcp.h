// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
using esp_transport_handle_t = int *;
inline int test_handle_id = 0;
inline int test_connect_result = -1;
inline int fail_tcp_attempts = 0, test_tcp_calls = 0;
inline int test_destroy_calls = 0, test_close_calls = 0;
inline int test_connect_calls = 0;
inline esp_transport_handle_t esp_transport_tcp_init() {
  ++test_tcp_calls;
  if (fail_tcp_attempts > 0) {
    --fail_tcp_attempts;
    return nullptr;
  }
  return new int(++test_handle_id);
}
inline int esp_transport_destroy(esp_transport_handle_t handle) {
  ++test_destroy_calls;
  delete handle;
  return 0;
}
inline int esp_transport_close(esp_transport_handle_t) {
  ++test_close_calls;
  return 0;
}
inline int esp_transport_connect(esp_transport_handle_t, const char *, int,
                                 int timeout) {
  assert(timeout <= 250);
  ++test_connect_calls;
  return test_connect_result;
}
