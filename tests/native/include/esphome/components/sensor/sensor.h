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
  }
  std::vector<float> states;
};
}
