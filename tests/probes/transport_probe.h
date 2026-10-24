// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdio>
#include <cstring>
#include <string>

#include "esp_random.h"
#include "esp_timer.h"
#include "esp_transport_tcp.h"
#include "esp_transport_ws.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "mbedtls/md.h"

namespace transport_probe {

struct Probe {
  std::string token, server, revision, run_id, boot;
  sockaddr_in address{};

  static uint64_t now() { return esp_timer_get_time() / 1000; }

  std::string sign(const std::string &body) const {
    unsigned char digest[32];
    auto *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (mbedtls_md_hmac(
            info, reinterpret_cast<const unsigned char *>(token.data()),
            token.size(), reinterpret_cast<const unsigned char *>(body.data()),
            body.size(), digest) != 0)
      return "";
    char tag[65];
    for (size_t i = 0; i < 32; ++i)
      snprintf(tag + 2 * i, 3, "%02x", digest[i]);
    return body + "|" + tag;
  }

  std::string event(unsigned seq, const char *stage, const char *transport,
                    unsigned trial = 0, uint64_t elapsed = 0) const {
    std::string body = "1|voice-pe-probe|" + boot + "|" + std::to_string(seq) +
                       "|" + std::to_string(now()) + "|" + stage +
                       "|device,voice-pe-probe," + revision + "," + run_id +
                       "," + transport + "," + std::to_string(trial) + "," +
                       std::to_string(elapsed);
    return sign(body);
  }

  int udp_socket() const {
    int fd = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (fd >= 0) {
      timeval timeout{1, 0};
      setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    }
    return fd;
  }

  void send_udp(int fd, const std::string &packet) const {
    if (fd >= 0 && !packet.empty())
      sendto(fd, packet.data(), packet.size(), 0,
             reinterpret_cast<const sockaddr *>(&address), sizeof(address));
  }

  bool await_arm(int fd) const {
    if (fd < 0)
      return false;
    const std::string expected = sign("arm|" + boot + "|" + run_id);
    // The boot identifier binds the command to this start, not a previous run.
    while (true) {
      send_udp(fd, event(0, "ready", "udp"));
      char buffer[256];
      sockaddr_in peer{};
      socklen_t length = sizeof(peer);
      int count = recvfrom(fd, buffer, sizeof(buffer), 0,
                           reinterpret_cast<sockaddr *>(&peer), &length);
      if (count == static_cast<int>(expected.size()) &&
          peer.sin_addr.s_addr == address.sin_addr.s_addr &&
          peer.sin_port == address.sin_port) {
        unsigned char difference = 0;
        for (int i = 0; i < count; ++i)
          difference |= static_cast<unsigned char>(buffer[i] ^ expected[i]);
        if (difference == 0)
          return true;
      }
      vTaskDelay(pdMS_TO_TICKS(100));
    }
  }

  void run() {
    address.sin_family = AF_INET;
    address.sin_port = htons(8765);
    if (inet_pton(AF_INET, server.c_str(), &address.sin_addr) != 1)
      return;
    char identifier[17];
    snprintf(identifier, sizeof(identifier), "%08lx%08lx",
             static_cast<unsigned long>(esp_random()),
             static_cast<unsigned long>(esp_random()));
    boot = identifier;
    int udp = udp_socket();
    if (!await_arm(udp)) {
      if (udp >= 0)
        close(udp);
      return;
    }
    for (unsigned seq = 0; seq < 1000; ++seq) {
      send_udp(udp, event(seq, "probe_event", "udp"));
      vTaskDelay(pdMS_TO_TICKS(10));
    }
    for (unsigned trial = 1; trial <= 10; ++trial) {
      close(udp);
      vTaskDelay(pdMS_TO_TICKS(100));
      uint64_t started = now();
      udp = udp_socket();
      send_udp(udp,
               event(999 + trial, "reconnect", "udp", trial, now() - started));
    }
    if (udp >= 0)
      close(udp);

    auto tcp = esp_transport_tcp_init();
    auto ws = tcp == nullptr ? nullptr : esp_transport_ws_init(tcp);
    if (ws == nullptr) {
      if (tcp != nullptr)
        esp_transport_destroy(tcp);
      return;
    }
    esp_transport_ws_set_path(ws, "/q1");
    if (esp_transport_connect(ws, server.c_str(), 8765, 2000) >= 0) {
      for (unsigned seq = 1010; seq < 2010; ++seq) {
        auto packet = event(seq, "probe_event", "websocket");
        int sent = esp_transport_ws_send_raw(
            ws,
            static_cast<ws_transport_opcodes_t>(WS_TRANSPORT_OPCODES_TEXT |
                                                WS_TRANSPORT_OPCODES_FIN),
            packet.data(), packet.size(), 100);
        if (sent != static_cast<int>(packet.size()))
          break;
        vTaskDelay(pdMS_TO_TICKS(10));
      }
    }
    for (unsigned trial = 1; trial <= 10; ++trial) {
      esp_transport_close(ws);
      vTaskDelay(pdMS_TO_TICKS(100));
      uint64_t started = now();
      if (esp_transport_connect(ws, server.c_str(), 8765, 2000) >= 0) {
        auto packet = event(2009 + trial, "reconnect", "websocket", trial,
                            now() - started);
        esp_transport_ws_send_raw(
            ws,
            static_cast<ws_transport_opcodes_t>(WS_TRANSPORT_OPCODES_TEXT |
                                                WS_TRANSPORT_OPCODES_FIN),
            packet.data(), packet.size(), 100);
      }
    }
    esp_transport_close(ws);
    esp_transport_destroy(ws);
    esp_transport_destroy(tcp);
  }
};

inline void start(const char *token, const char *server, const char *revision,
                  const char *run) {
  static bool started = false;
  if (started)
    return;
  started = true;
  auto *probe = new Probe{token, server, revision, run, "", {}};
  // Core 0 and priority 0 keep this worker below the core 1 ESPHome loop.
  BaseType_t result = xTaskCreatePinnedToCore(
      [](void *argument) {
        auto *instance = static_cast<Probe *>(argument);
        instance->run();
        delete instance;
        vTaskDelete(nullptr);
      },
      "transport_probe", 8192, probe, 0, nullptr, 0);
  if (result != pdPASS)
    delete probe;
}

} // namespace transport_probe
