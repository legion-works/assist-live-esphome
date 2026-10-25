// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "esp_transport_tcp.h"
#include <cstring>
#include <string>
enum ws_transport_opcodes_t {
  WS_TRANSPORT_OPCODES_TEXT = 1,
  WS_TRANSPORT_OPCODES_FIN = 128
};
inline int ws_handle = 2;
inline bool test_write_success = true;
inline std::string test_ws_packet;
inline int fail_ws_attempts = 0;
inline esp_transport_handle_t esp_transport_ws_init(esp_transport_handle_t) {
  if (fail_ws_attempts > 0) {
    --fail_ws_attempts;
    return nullptr;
  }
  return &ws_handle;
}
inline void esp_transport_ws_set_path(esp_transport_handle_t,
                                      const char *path) {
  assert(std::strcmp(path, "/v1/device") == 0);
}
inline int esp_transport_ws_send_raw(esp_transport_handle_t,
                                     ws_transport_opcodes_t opcode,
                                     const char *packet, int size,
                                     int timeout) {
  assert(timeout <= 50);
  assert(opcode == static_cast<ws_transport_opcodes_t>(
                       WS_TRANSPORT_OPCODES_TEXT | WS_TRANSPORT_OPCODES_FIN));
  test_ws_packet.assign(packet, size);
  return test_write_success ? size : -1;
}
