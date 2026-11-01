// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#ifdef USE_ASSIST_LIVE_DIAGNOSTICS
#include "diagnostic_state.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome::assist_live {
class DiagnosticPublisher {
public:
  void set_turn_sensor(size_t index, sensor::Sensor *value) { turn_sensors_[index] = value; }
  void set_counter_sensor(size_t index, sensor::Sensor *value) { counter_sensors_[index] = value; }
  void set_passthrough(binary_sensor::BinarySensor *value) { passthrough_ = value; }
  void set_connected(binary_sensor::BinarySensor *value) { connected_ = value; }
  void publish_turn(const TurnDiagnostics &turn) {
    expired_gates_ = turn.expired_gates;
    for (size_t i = 0; i < TURN_SENSOR_COUNT; ++i)
      if (turn_sensors_[i] != nullptr)
        turn_sensors_[i]->publish_state(turn.values[i]);
    if (passthrough_ != nullptr)
      passthrough_->publish_state(turn.passthrough);
  }
  void loop(uint64_t now, std::array<uint32_t, COUNTER_SENSOR_COUNT> counters, bool connected) {
    if (!schedule_.counters_due(now))
      return;
    counters[EXPIRED_GATES] = expired_gates_;
    for (size_t i = 0; i < COUNTER_SENSOR_COUNT; ++i)
      if (counter_sensors_[i] != nullptr)
        counter_sensors_[i]->publish_state(counters[i]);
    if (connected_ != nullptr)
      connected_->publish_state(connected);
  }

protected:
  std::array<sensor::Sensor *, TURN_SENSOR_COUNT> turn_sensors_{};
  std::array<sensor::Sensor *, COUNTER_SENSOR_COUNT> counter_sensors_{};
  binary_sensor::BinarySensor *passthrough_{nullptr}, *connected_{nullptr};
  DiagnosticState schedule_;
  uint32_t expired_gates_{0};
};
}
#endif
