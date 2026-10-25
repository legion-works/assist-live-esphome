// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
namespace esphome {
namespace setup_priority {
constexpr float AFTER_WIFI = 200;
}
class Component {
public:
  virtual ~Component() = default;
  virtual void setup() {}
  virtual void dump_config() {}
  virtual float get_setup_priority() const { return 0; }
  void mark_failed() { failed = true; }
  bool failed{false};
};
} // namespace esphome
