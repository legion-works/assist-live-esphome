// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
#include <vector>
inline bool test_publish_allowed = false;
namespace esphome::sensor {
class Sensor {
public:
  void publish_state(float value) {
    assert(test_publish_allowed && "entities publish only from the main loop");
    states.push_back(value);
    has_state_ = true;
  }
  bool has_state() const { return has_state_; }
  void set_has_state(bool value) { has_state_ = value; }
  std::vector<float> states;
  bool has_state_{false};
};
}
