// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "esphome/components/media_player/media_player.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "event_codec.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "mbedtls/platform_util.h"
#include <array>
#include <atomic>

namespace esphome {
namespace assist_live {

class AssistLiveComponent : public Component {
public:
  void setup() override;
  void dump_config() override;
  void on_shutdown() override;
  bool teardown() override { return worker_stopped_.load(); }
  float get_setup_priority() const override {
    return setup_priority::AFTER_WIFI;
  }
  void set_device(const std::string &device) { device_ = device; }
  void set_hmac_key(std::array<uint8_t, 32> key) {
    key_ = key;
    mbedtls_platform_zeroize(key.data(), key.size());
  }
  void set_server(const std::string &server) { server_ = server; }
  void set_port(uint16_t port) { port_ = port; }
  void set_websocket(bool websocket) { websocket_ = websocket; }
  void set_media_player(media_player::MediaPlayer *player) { player_ = player; }
  static uint64_t monotonic_ms();
  // The worker checks canonical data to keep JSON parsing off the audio path.
  void emit_event(Stage stage, uint64_t device_ms,
                  const char *canonical_data = "{}");
  void command_stream_start();
  void command_stream_end() { command_open_.exchange(false); }
  void playback_state(bool active);
  // Only an externally validated sample callback can call this hook.
  void measured_sample_boundary(bool started, uint64_t device_ms);
  uint32_t dropped_events() const { return dropped_.load(); }
  uint32_t refused_events() const { return refused_.load(); }
  uint32_t sender_initialization_failures() const {
    return initialization_failures_.load();
  }

protected:
  void run_();
  std::string device_, server_;
  std::array<uint8_t, 32> key_{};
  QueueHandle_t queue_{nullptr};
  uint64_t boot_{0}, next_seq_{0};
  std::atomic<bool> command_open_{false};
  std::atomic<bool> stop_requested_{false}, worker_stopped_{true};
  bool exhausted_{false}, playback_active_{false}, websocket_{false};
  uint16_t port_{8765};
  std::atomic<uint32_t> dropped_{0};
  std::atomic<uint32_t> initialization_failures_{0};
  std::atomic<uint32_t> refused_{0};
  media_player::MediaPlayer *player_{nullptr};
};

template <typename... Ts> class EmitEventAction : public Action<Ts...> {
public:
  explicit EmitEventAction(AssistLiveComponent *parent) : parent_(parent) {}
  void set_stage(Stage stage) { stage_ = stage; }
  void set_data(const std::string &data) { data_ = data; }
  TEMPLATABLE_VALUE(uint64_t, device_ms)
  void play(const Ts &...x) override {
    parent_->emit_event(stage_, this->device_ms_.value(x...), data_.c_str());
  }

protected:
  AssistLiveComponent *parent_;
  Stage stage_{Stage::WAKE_DETECTED};
  std::string data_{"{}"};
};

} // namespace assist_live
} // namespace esphome
