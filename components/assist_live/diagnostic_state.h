// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "pre_roll_buffer.h"
#include <array>
#include <cmath>

namespace esphome::assist_live {
enum TurnSensor : size_t {
  PRE_ROLL_MS, REPLAY_GATE_DELAY_MS, HISTORY_TRIMMED_MS, OVERFLOWS, DROPPED_MS,
  FIRST_LIVE_QUEUE_MS, HISTORY_END_QUEUE_MS, TURN_END_QUEUE_MS, TURN_SENSOR_COUNT
};
enum CounterSensor : size_t {
  EVENTS_SENT, EVENTS_CONFIRMED, EVENTS_DROPPED, EVENTS_REFUSED,
  SENDER_INITIALIZATION_FAILURES, EXPIRED_GATES, COUNTER_SENSOR_COUNT
};
struct TurnDiagnostics {
  std::array<float, TURN_SENSOR_COUNT> values{};
  uint32_t expired_gates{0};
  bool passthrough{false};
};

class DiagnosticState {
public:
  void finish_turn(const PreRollBuffer &buffer, uint64_t gate_delay, bool expired,
                   bool replay_started = true) {
    if (expired)
      ++expired_gates_;
    turn_.values = {
        replay_started ? static_cast<float>(buffer.pre_roll_ms()) : 0.0f,
        replay_started ? static_cast<float>(gate_delay) : NAN,
        static_cast<float>(buffer.trimmed_frames() / 16),
        static_cast<float>(buffer.overflows()),
        static_cast<float>(buffer.dropped_frames() / 16),
        buffer.first_live_queue_ms() < 0 ? NAN : static_cast<float>(buffer.first_live_queue_ms()),
        buffer.history_end_queue_ms() < 0 ? NAN : static_cast<float>(buffer.history_end_queue_ms()),
        static_cast<float>(buffer.queue_delay_ms())};
    turn_.expired_gates = expired_gates_;
    turn_.passthrough = buffer.passthrough_reached();
    pending_ = true;
  }
  bool take_turn(TurnDiagnostics &turn) {
    if (!pending_)
      return false;
    turn = turn_;
    pending_ = false;
    return true;
  }
  bool counters_due(uint64_t now) {
    if (published_ && now - published_ms_ < 1000)
      return false;
    published_ = true;
    published_ms_ = now;
    return true;
  }

protected:
  TurnDiagnostics turn_;
  uint32_t expired_gates_{0};
  uint64_t published_ms_{0};
  bool pending_{false}, published_{false};
};
}
