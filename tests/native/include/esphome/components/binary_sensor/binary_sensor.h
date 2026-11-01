// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "esphome/components/sensor/sensor.h"
namespace esphome::binary_sensor {
class BinarySensor {
public:
  void publish_state(bool value) {
    assert(test_publish_allowed && "entities publish only from the main loop");
    states.push_back(value);
    has_state_ = true;
  }
  bool has_state() const { return has_state_; }
  void set_has_state(bool value) { has_state_ = value; }
  std::vector<bool> states;
  bool has_state_{false};
};
}
