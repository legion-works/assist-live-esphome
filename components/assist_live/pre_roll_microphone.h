// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "esphome/core/defines.h"
#ifdef USE_ASSIST_LIVE_PRE_ROLL
#include "esphome/components/microphone/microphone.h"
#include "esphome/components/switch/switch.h"
#include "esphome/core/component.h"
#include "pre_roll_buffer.h"
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
#include "diagnostic_state.h"
#endif
#include <memory>

namespace esphome::assist_live {
class AssistLiveComponent;

class PreRollMicrophone : public Component, public microphone::Microphone {
public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  void on_shutdown() override { clear(); }
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }
  void start() override;
  void stop() override;
  void set_source(microphone::Microphone *source) { source_ = source; }
  void set_wake_sound(switch_::Switch *value) { wake_sound_ = value; }
  void set_length_ms(uint32_t value) { length_ms_ = value; }
  void set_parent(AssistLiveComponent *value) { parent_ = value; }
  void wake_detected();
  void wake_started();
  void begin_turn();
  void finish_turn();
  void finish_turn_if_idle();
  bool turn_active();
  void listening();
  void set_privacy_mute(bool muted);
  void clear();
  bool history_complete();
  uint32_t pre_roll_ms();
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
  bool take_diagnostics(TurnDiagnostics &turn) {
    LockGuard lock(mutex_);
    return diagnostics_.take_turn(turn);
  }
#endif

protected:
  void receive_(const std::vector<uint8_t> &data);
  void push_frames_(const std::vector<uint8_t> &data);
  void update_mute_();
  void log_turn_();
  microphone::Microphone *source_{nullptr};
  switch_::Switch *wake_sound_{nullptr};
  AssistLiveComponent *parent_{nullptr};
  Mutex mutex_;
  HighFrequencyLoopRequester fast_loop_;
  StereoFrame *memory_{nullptr};
  std::unique_ptr<PreRollBuffer> buffer_;
  std::vector<uint8_t> output_, silence_;
  uint32_t length_ms_{250};
  size_t capacity_{0}, reported_overflows_{0};
  unsigned listeners_{0};
  uint64_t arm_ms_{0}, arm_to_start_ms_{0};
  uint32_t last_pre_roll_ms_{0};
  bool arm_pending_{false}, arm_expired_{false};
  bool turn_active_{false}, wake_bound_{false}, replay_started_{false};
  bool privacy_mute_{false}, effective_mute_{false}, passthrough_{false};
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
  DiagnosticState diagnostics_;
#endif
};
}
#endif
