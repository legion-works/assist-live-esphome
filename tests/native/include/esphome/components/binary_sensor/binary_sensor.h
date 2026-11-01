// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "esphome/components/sensor/sensor.h"
namespace esphome::binary_sensor {
class BinarySensor {
public:
  void publish_state(bool value) {
    assert(test_publish_allowed && "entities publish only from the main loop");
    states.push_back(value);
  }
  std::vector<bool> states;
};
}
