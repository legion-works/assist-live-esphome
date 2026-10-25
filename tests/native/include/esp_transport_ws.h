// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "esp_transport_tcp.h"
#include <cstring>
#include <deque>
#include <string>
enum ws_transport_opcodes_t {
  WS_TRANSPORT_OPCODES_TEXT = 1,
  WS_TRANSPORT_OPCODES_CLOSE = 8,
  WS_TRANSPORT_OPCODES_PING = 9,
  WS_TRANSPORT_OPCODES_PONG = 10,
  WS_TRANSPORT_OPCODES_FIN = 128
};
struct TestFrame {
  int opcode;
  std::string data;
};
inline std::deque<TestFrame> test_frames;
inline int test_read_opcode = 0, test_read_payload_len = 0;
inline bool test_read_error = false, test_auto_pong = true;
inline int test_http_status = 0, test_close_after_write = 0;
inline int test_text_writes = 0, test_pongs = 0;
inline std::string test_last_pong;
inline bool test_propagate_control = false;
struct esp_transport_ws_config_t {
  const char *ws_path = nullptr;
  const char *sub_protocol = nullptr;
  const char *user_agent = nullptr;
  const char *headers = nullptr;
  const char *auth = nullptr;
  bool propagate_control_frames = false;
};
inline int
esp_transport_ws_set_config(esp_transport_handle_t,
                            const esp_transport_ws_config_t *config) {
  assert(std::strcmp(config->ws_path, "/v1/device") == 0);
  test_propagate_control = config->propagate_control_frames;
  return 0;
}
inline int esp_transport_ws_get_upgrade_request_status(esp_transport_handle_t) {
  return test_http_status;
}
inline int esp_transport_poll_read(esp_transport_handle_t, int timeout) {
  assert(timeout == 0);
  return test_read_error ? -1 : !test_frames.empty();
}
inline int esp_transport_read(esp_transport_handle_t, char *buffer, int size,
                              int timeout) {
  assert(timeout == 0 && size >= 125 && !test_frames.empty());
  auto frame = test_frames.front();
  test_frames.pop_front();
  test_read_opcode = frame.opcode;
  test_read_payload_len = frame.data.size();
  assert(frame.data.size() <= static_cast<size_t>(size));
  std::memcpy(buffer, frame.data.data(), frame.data.size());
  return frame.data.size();
}
inline ws_transport_opcodes_t
esp_transport_ws_get_read_opcode(esp_transport_handle_t) {
  return static_cast<ws_transport_opcodes_t>(test_read_opcode);
}
inline int esp_transport_ws_get_read_payload_len(esp_transport_handle_t) {
  return test_read_payload_len;
}
inline bool esp_transport_ws_get_fin_flag(esp_transport_handle_t) {
  return true;
}
inline bool test_write_success = true;
inline std::string test_ws_packet;
inline int fail_ws_attempts = 0;
inline esp_transport_handle_t esp_transport_ws_init(esp_transport_handle_t) {
  if (fail_ws_attempts > 0) {
    --fail_ws_attempts;
    return nullptr;
  }
  return new int(++test_handle_id);
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
  auto kind = static_cast<int>(opcode) & 15;
  if (kind == WS_TRANSPORT_OPCODES_TEXT) {
    ++test_text_writes;
    test_ws_packet.assign(packet, size);
    if (test_close_after_write) {
      test_frames.push_back(
          {8, std::string{static_cast<char>(test_close_after_write >> 8),
                          static_cast<char>(test_close_after_write)}});
      test_close_after_write = 0;
    }
  } else if (kind == WS_TRANSPORT_OPCODES_PING && test_auto_pong) {
    test_frames.push_back({10, std::string(packet, size)});
  } else if (kind == WS_TRANSPORT_OPCODES_PONG) {
    ++test_pongs;
    test_last_pong.assign(packet, size);
  } else {
    assert(kind == WS_TRANSPORT_OPCODES_PING ||
           kind == WS_TRANSPORT_OPCODES_CLOSE);
  }
  return test_write_success ? size : -1;
}
